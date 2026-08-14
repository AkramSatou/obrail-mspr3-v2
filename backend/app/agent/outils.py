"""
outils.py — Les 4 outils exposés à l'agent IA (ÉTAPE B du plan).

Chaque outil est une fonction Python pure, indépendante de tout appel LLM,
accompagnée d'un schéma JSON compatible OpenAI (format "tools") et d'une
validation Pydantic de ses arguments. Aucune exception ne remonte au LLM :
en cas d'erreur, l'outil renvoie {"erreur": "..."} pour que l'agent puisse
corriger son tir (§0.6-1 du plan — pas de réponse inventée, pas de plantage
silencieux non plus).

Conformément à D4 : les deux outils de prédiction réutilisent directement
les fonctions et modèles déjà chargés par app.main (_build_substitution_df,
_model_substitution, _build_co2_df, _model_co2) — aucune logique d'inférence
n'est dupliquée ici.
"""

from typing import Callable, Optional

from pydantic import BaseModel, Field, ValidationError

from app import main as _main
from app.database import SessionLocal
from app.models import Trip
from app.main import (
    LiaisonCO2Input,
    LiaisonSubstitutionInput,
    _build_co2_df,
    _build_substitution_df,
    _model_co2,
    _model_substitution,
)

# _substitution_error / _co2_error ne sont assignées par app.main que dans la
# branche `except` du chargement des modèles (elles n'existent pas comme
# attribut de module si le chargement a réussi) : on les lit donc via getattr
# avec un message par défaut plutôt que de les importer directement, pour ne
# jamais faire échouer l'import de ce fichier selon l'état des modèles.
def _erreur_substitution() -> str:
    return getattr(_main, "_substitution_error", "modèle non chargé (raison inconnue)")


def _erreur_co2() -> str:
    return getattr(_main, "_co2_error", "modèle non chargé (raison inconnue)")


# ---------------------------------------------------------------------------
# Outil 1 — rechercher_trajets
# ---------------------------------------------------------------------------


class ArgsRechercherTrajets(BaseModel):
    """Arguments acceptés par l'outil rechercher_trajets."""

    origine: Optional[str] = Field(default=None, description="Gare ou ville de départ (recherche partielle)")
    destination: Optional[str] = Field(default=None, description="Gare ou ville d'arrivée (recherche partielle)")
    pays: Optional[str] = Field(default=None, description="Code pays ISO à 2 lettres, ex. FR, DE")
    type_train: Optional[str] = Field(default=None, description="Type de traction : 'electric' ou 'diesel'")
    distance_min: Optional[float] = Field(default=None, ge=0, description="Distance minimale en kilomètres")
    distance_max: Optional[float] = Field(default=None, ge=0, description="Distance maximale en kilomètres")
    limite: int = Field(default=5, ge=1, le=50, description="Nombre maximum de trajets à retourner")


SCHEMA_RECHERCHER_TRAJETS = {
    "type": "function",
    "function": {
        "name": "rechercher_trajets",
        "description": (
            "Recherche des trajets ferroviaires dans l'observatoire ObRail selon "
            "des critères optionnels (origine, destination, pays, type de train, "
            "plage de distance). Utilise cet outil pour trouver un ou plusieurs "
            "trajets réels avant de répondre à une question sur une liaison "
            "précise."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origine": {"type": "string", "description": "Gare ou ville de départ (recherche partielle)"},
                "destination": {"type": "string", "description": "Gare ou ville d'arrivée (recherche partielle)"},
                "pays": {"type": "string", "description": "Code pays ISO à 2 lettres, ex. FR, DE"},
                "type_train": {"type": "string", "enum": ["electric", "diesel"], "description": "Type de traction"},
                "distance_min": {"type": "number", "description": "Distance minimale en kilomètres"},
                "distance_max": {"type": "number", "description": "Distance maximale en kilomètres"},
                "limite": {"type": "integer", "description": "Nombre maximum de trajets à retourner (défaut 5)"},
            },
            "required": [],
        },
    },
}


def rechercher_trajets(
    origine: Optional[str] = None,
    destination: Optional[str] = None,
    pays: Optional[str] = None,
    type_train: Optional[str] = None,
    distance_min: Optional[float] = None,
    distance_max: Optional[float] = None,
    limite: int = 5,
    db=None,
) -> dict:
    """Recherche des trajets — même logique de filtrage que GET /trajets."""
    fermer_apres = False
    if db is None:
        db = SessionLocal()
        fermer_apres = True
    try:
        query = db.query(Trip)
        if pays:
            query = query.filter(Trip.country.ilike(pays))
        if type_train:
            query = query.filter(Trip.type_train.ilike(type_train))
        if origine:
            query = query.filter(Trip.origin_stop_name.ilike(f"%{origine}%"))
        if destination:
            query = query.filter(Trip.destination_stop_name.ilike(f"%{destination}%"))
        if distance_min is not None:
            query = query.filter(Trip.distance_km >= distance_min)
        if distance_max is not None:
            query = query.filter(Trip.distance_km <= distance_max)

        total_trouve = query.count()
        rows = query.order_by(Trip.id).limit(limite).all()

        trajets = [
            {
                "id": row.trip_id,
                "route_long_name": row.route_long_name,
                "origine": row.origin_stop_name,
                "destination": row.destination_stop_name,
                "pays": row.country,
                "type_train": row.type_train,
                "distance_km": float(row.distance_km),
                "duration_minutes": float(row.duration_minutes),
                "n_stops": int(row.n_stops),
                "co2_estime_g": float(row.co2_estime) if row.co2_estime is not None else None,
                "consommation_totale": float(row.consommation_totale) if row.consommation_totale is not None else None,
            }
            for row in rows
        ]

        if not trajets:
            resume = "Aucun trajet trouvé pour ces critères."
        else:
            resume = f"{len(trajets)} trajet(s) trouvé(s) sur {total_trouve} correspondant(s)."

        return {
            "trajets": trajets,
            "total_trouve": total_trouve,
            "resultat_resume": resume,
        }
    finally:
        if fermer_apres:
            db.close()


# ---------------------------------------------------------------------------
# Outil 2 — obtenir_statistiques
# ---------------------------------------------------------------------------


class ArgsObtenirStatistiques(BaseModel):
    """Arguments acceptés par l'outil obtenir_statistiques."""

    pays: Optional[str] = Field(default=None, description="Code pays ISO à 2 lettres, ex. FR, DE")
    type_train: Optional[str] = Field(default=None, description="Type de traction : 'electric' ou 'diesel'")


SCHEMA_OBTENIR_STATISTIQUES = {
    "type": "function",
    "function": {
        "name": "obtenir_statistiques",
        "description": (
            "Retourne des volumes agrégés (nombre de trajets, distance cumulée, "
            "émissions CO2 cumulées) sur le réseau ferroviaire ObRail, "
            "optionnellement filtrés par pays et/ou type de train. Utilise cet "
            "outil pour répondre à des questions globales ('combien de trajets "
            "diesel en Allemagne ?') plutôt que sur un trajet précis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pays": {"type": "string", "description": "Code pays ISO à 2 lettres, ex. FR, DE"},
                "type_train": {"type": "string", "enum": ["electric", "diesel"], "description": "Type de traction"},
            },
            "required": [],
        },
    },
}


def obtenir_statistiques(
    pays: Optional[str] = None,
    type_train: Optional[str] = None,
    db=None,
) -> dict:
    """Volumes agrégés — même logique de filtrage que GET /stats/volumes, sans pagination."""
    fermer_apres = False
    if db is None:
        db = SessionLocal()
        fermer_apres = True
    try:
        query = db.query(Trip)
        if pays:
            query = query.filter(Trip.country.ilike(pays))
        if type_train:
            query = query.filter(Trip.type_train.ilike(type_train))
        rows = query.all()

        total_trajets = len(rows)
        total_distance_km = sum(float(row.distance_km) for row in rows)
        total_kg_co2_emis = sum(
            float(row.co2_estime) / 1000 for row in rows if row.co2_estime is not None
        )

        if total_trajets == 0:
            resume = "Aucun trajet ne correspond à ces critères."
        else:
            resume = (
                f"{total_trajets} trajet(s), {round(total_distance_km, 1)} km cumulés, "
                f"{round(total_kg_co2_emis, 1)} kgCO2 cumulés."
            )

        return {
            "total_trajets": total_trajets,
            "total_distance_km": round(total_distance_km, 3),
            "total_kg_co2_emis": round(total_kg_co2_emis, 3),
            "resultat_resume": resume,
        }
    finally:
        if fermer_apres:
            db.close()


# ---------------------------------------------------------------------------
# Outil 3 — predire_substitution_avion
# ---------------------------------------------------------------------------


SCHEMA_PREDIRE_SUBSTITUTION_AVION = {
    "type": "function",
    "function": {
        "name": "predire_substitution_avion",
        "description": (
            "Prédit, à partir des caractéristiques d'une liaison ferroviaire, si "
            "cette liaison est candidate à remplacer un vol aérien équivalent. "
            "Utilise TOUJOURS cet outil pour toute question de substitution "
            "avion/train — ne devine jamais la réponse toi-même."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "distance_km": {"type": "number", "description": "Distance géographique de la liaison en km"},
                "duration_minutes": {"type": "number", "description": "Durée du trajet en minutes"},
                "n_stops": {"type": "integer", "description": "Nombre d'arrêts intermédiaires"},
                "co2_estime": {"type": "number", "description": "Émissions CO2 estimées en gCO2"},
                "consommation_totale": {"type": "number", "description": "Consommation énergétique totale en kWh"},
                "type_train": {"type": "string", "enum": ["electric", "diesel"], "description": "Type de traction"},
                "country": {"type": "string", "description": "Code pays : FR, ES, IT ou DE"},
            },
            "required": [
                "distance_km", "duration_minutes", "n_stops", "co2_estime",
                "consommation_totale", "type_train", "country",
            ],
        },
    },
}


def predire_substitution_avion(
    distance_km: float,
    duration_minutes: float,
    n_stops: int,
    co2_estime: float,
    consommation_totale: float,
    type_train: str,
    country: str,
) -> dict:
    """Réutilise directement le modèle de classification chargé par app.main (D4)."""
    if not _main._substitution_ok:
        return {"erreur": f"Modèle de classification indisponible : {_erreur_substitution()}"}

    liaison = LiaisonSubstitutionInput(
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        n_stops=n_stops,
        co2_estime=co2_estime,
        consommation_totale=consommation_totale,
        type_train=type_train,
        country=country,
    )
    X = _build_substitution_df(liaison)
    prediction = int(_model_substitution.predict(X)[0])
    proba = float(_model_substitution.predict_proba(X)[0][1])
    label = "Substituable à l'avion" if prediction == 1 else "Non substituable"

    return {
        "substitution_avion": prediction,
        "probabilite": round(proba, 4),
        "label": label,
        "resultat_resume": f"substitution_avion={prediction}, probabilite={round(proba, 4)}",
    }


# ---------------------------------------------------------------------------
# Outil 4 — estimer_co2_futur
# ---------------------------------------------------------------------------


SCHEMA_ESTIMER_CO2_FUTUR = {
    "type": "function",
    "function": {
        "name": "estimer_co2_futur",
        "description": (
            "Estime les émissions CO2 futures (en kgCO2) d'une liaison ferroviaire "
            "selon un scénario de développement du réseau. Utilise TOUJOURS cet "
            "outil pour toute question d'émission de CO2 future — n'estime jamais "
            "toi-même un chiffre."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "distance_km": {"type": "number", "description": "Distance géographique de la liaison en km"},
                "duration_minutes": {"type": "number", "description": "Durée du trajet en minutes"},
                "n_stops": {"type": "integer", "description": "Nombre d'arrêts intermédiaires"},
                "consommation_energy": {"type": "number", "description": "Consommation énergétique en kWh/km"},
                "gco2_per_kwh": {"type": "number", "description": "Facteur carbone du pays en gCO2/kWh"},
                "consommation_totale": {"type": "number", "description": "Consommation totale actuelle en kWh"},
                "type_train": {"type": "string", "enum": ["electric", "diesel"], "description": "Type de traction"},
                "scenario": {
                    "type": "string",
                    "enum": ["reference", "diesel_50_electrique", "conso_moins_15", "distance_moins_10"],
                    "description": "Scénario de développement du réseau",
                },
            },
            "required": [
                "distance_km", "duration_minutes", "n_stops", "consommation_energy",
                "gco2_per_kwh", "consommation_totale", "type_train", "scenario",
            ],
        },
    },
}


def estimer_co2_futur(
    distance_km: float,
    duration_minutes: float,
    n_stops: int,
    consommation_energy: float,
    gco2_per_kwh: float,
    consommation_totale: float,
    type_train: str,
    scenario: str,
) -> dict:
    """Réutilise directement le pipeline de régression chargé par app.main (D4)."""
    if not _main._co2_ok:
        return {"erreur": f"Modèle de régression CO2 indisponible : {_erreur_co2()}"}

    scenarios_valides = {"reference", "diesel_50_electrique", "conso_moins_15", "distance_moins_10"}
    if scenario not in scenarios_valides:
        return {"erreur": f"Scénario '{scenario}' inconnu. Valeurs acceptées : {sorted(scenarios_valides)}"}

    liaison = LiaisonCO2Input(
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        n_stops=n_stops,
        consommation_energy=consommation_energy,
        gco2_per_kwh=gco2_per_kwh,
        consommation_totale=consommation_totale,
        type_train=type_train,
        scenario=scenario,
    )
    X = _build_co2_df(liaison)
    co2_predit = float(_model_co2.predict(X)[0])

    return {
        "scenario": scenario,
        "co2_estime_kg": round(co2_predit, 4),
        "label": f"CO2 estimé : {co2_predit:.2f} kgCO2 (scénario : {scenario})",
        "resultat_resume": f"co2_estime_kg={round(co2_predit, 4)} (scénario {scenario})",
    }


# ---------------------------------------------------------------------------
# Registre et point d'entrée unique
# ---------------------------------------------------------------------------

REGISTRE_OUTILS: dict[str, tuple[Callable[..., dict], dict, type[BaseModel]]] = {
    "rechercher_trajets": (rechercher_trajets, SCHEMA_RECHERCHER_TRAJETS, ArgsRechercherTrajets),
    "obtenir_statistiques": (obtenir_statistiques, SCHEMA_OBTENIR_STATISTIQUES, ArgsObtenirStatistiques),
    "predire_substitution_avion": (
        predire_substitution_avion, SCHEMA_PREDIRE_SUBSTITUTION_AVION, LiaisonSubstitutionInput,
    ),
    "estimer_co2_futur": (estimer_co2_futur, SCHEMA_ESTIMER_CO2_FUTUR, LiaisonCO2Input),
}


def executer_outil(nom: str, arguments: dict, db=None) -> dict:
    """
    Point d'entrée unique utilisé par la boucle d'agent (étape C).

    Valide les arguments avec le modèle Pydantic de l'outil, puis exécute la
    fonction correspondante. Ne lève jamais d'exception : toute erreur est
    renvoyée sous la forme {"erreur": "message lisible"} pour que le LLM
    puisse ajuster son appel suivant.
    """
    if nom not in REGISTRE_OUTILS:
        return {"erreur": f"Outil inconnu : '{nom}'. Outils disponibles : {sorted(REGISTRE_OUTILS)}"}

    fonction, _schema, modele_args = REGISTRE_OUTILS[nom]

    try:
        args_valides = modele_args(**(arguments or {}))
    except ValidationError as e:
        return {"erreur": f"Arguments invalides pour '{nom}' : {e}"}

    kwargs = args_valides.model_dump()
    if nom in ("rechercher_trajets", "obtenir_statistiques") and db is not None:
        kwargs["db"] = db

    try:
        return fonction(**kwargs)
    except Exception as e:
        return {"erreur": f"Erreur lors de l'exécution de l'outil '{nom}' : {e}"}
