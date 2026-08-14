"""
ÉTAPE B — tests des 4 outils de l'agent, sans aucun appel LLM.

Réutilise la fixture db_session de conftest.py (10 trajets FR/DE de
démonstration) pour les deux outils de consultation, et les cas de
référence déjà validés (rapport TPRE622 / INCIDENT-003) pour les deux
outils de prédiction.
"""

import pytest

from app.agent.outils import (
    REGISTRE_OUTILS,
    SCHEMA_ESTIMER_CO2_FUTUR,
    SCHEMA_OBTENIR_STATISTIQUES,
    SCHEMA_PREDIRE_SUBSTITUTION_AVION,
    SCHEMA_RECHERCHER_TRAJETS,
    estimer_co2_futur,
    executer_outil,
    obtenir_statistiques,
    predire_substitution_avion,
    rechercher_trajets,
)


# ---------------------------------------------------------------------------
# rechercher_trajets
# ---------------------------------------------------------------------------


def test_rechercher_trajets_cas_nominal(db_session):
    resultat = rechercher_trajets(pays="FR", db=db_session)
    assert resultat["total_trouve"] == 5  # T1, T2, T3, T4, T5 sont FR dans SAMPLE_TRIPS
    assert len(resultat["trajets"]) == 5
    assert all(t["pays"] == "FR" for t in resultat["trajets"])
    assert "resultat_resume" in resultat


def test_rechercher_trajets_limite_le_nombre_de_resultats(db_session):
    resultat = rechercher_trajets(pays="FR", limite=2, db=db_session)
    assert resultat["total_trouve"] == 5
    assert len(resultat["trajets"]) == 2


def test_rechercher_trajets_resultat_vide(db_session):
    resultat = rechercher_trajets(pays="ZZ", db=db_session)
    assert resultat["total_trouve"] == 0
    assert resultat["trajets"] == []
    assert "Aucun" in resultat["resultat_resume"]


def test_rechercher_trajets_arguments_invalides_via_executer_outil(db_session):
    # limite hors bornes (max 50, Pydantic doit rejeter avant toute requête DB)
    resultat = executer_outil("rechercher_trajets", {"limite": 999}, db=db_session)
    assert "erreur" in resultat


# ---------------------------------------------------------------------------
# obtenir_statistiques
# ---------------------------------------------------------------------------


def test_obtenir_statistiques_cas_nominal(db_session):
    resultat = obtenir_statistiques(pays="DE", db=db_session)
    assert resultat["total_trajets"] == 5  # T6..T10 sont DE
    assert resultat["total_distance_km"] > 0
    assert resultat["total_kg_co2_emis"] > 0
    assert "resultat_resume" in resultat


def test_obtenir_statistiques_resultat_vide(db_session):
    resultat = obtenir_statistiques(pays="ZZ", db=db_session)
    assert resultat["total_trajets"] == 0
    assert resultat["total_distance_km"] == 0
    assert "Aucun" in resultat["resultat_resume"]


def test_obtenir_statistiques_arguments_invalides_via_executer_outil(db_session):
    # type_train n'est pas une chaîne valide sémantiquement mais Pydantic accepte
    # les chaînes libres ici (pas d'enum strict côté modèle) — on vérifie plutôt
    # qu'un type incorrect (liste au lieu de chaîne) est bien rejeté.
    resultat = executer_outil("obtenir_statistiques", {"type_train": ["diesel"]}, db=db_session)
    assert "erreur" in resultat


# ---------------------------------------------------------------------------
# predire_substitution_avion — cas de référence rapport TPRE622 (Paris-Marseille)
# ---------------------------------------------------------------------------


def test_predire_substitution_avion_cas_reference_paris_marseille():
    resultat = predire_substitution_avion(
        distance_km=800.0,
        duration_minutes=195.0,
        n_stops=3,
        co2_estime=450000.0,
        consommation_totale=16000.0,
        type_train="electric",
        country="FR",
    )
    assert resultat["substitution_avion"] == 1
    assert resultat["probabilite"] == pytest.approx(1.0, abs=0.01)
    assert "erreur" not in resultat


def test_predire_substitution_avion_arguments_invalides():
    # country manquant : champ requis du modèle Pydantic LiaisonSubstitutionInput
    resultat = executer_outil(
        "predire_substitution_avion",
        {
            "distance_km": 800.0,
            "duration_minutes": 195.0,
            "n_stops": 3,
            "co2_estime": 450000.0,
            "consommation_totale": 16000.0,
            "type_train": "electric",
        },
    )
    assert "erreur" in resultat


# ---------------------------------------------------------------------------
# estimer_co2_futur — cas de référence INCIDENT-003 (400 km diesel, reference)
# ---------------------------------------------------------------------------


def test_estimer_co2_futur_cas_reference_400km_diesel():
    resultat = estimer_co2_futur(
        distance_km=400.0,
        duration_minutes=120.0,
        n_stops=2,
        consommation_energy=10.0,
        gco2_per_kwh=21.7,
        consommation_totale=4000.0,
        type_train="diesel",
        scenario="reference",
    )
    assert resultat["co2_estime_kg"] == pytest.approx(104.3425, abs=0.01)
    assert resultat["co2_estime_kg"] > 0  # positif : c'est précisément le bug d'INCIDENT-003
    assert "erreur" not in resultat


def test_estimer_co2_futur_scenario_invalide():
    resultat = estimer_co2_futur(
        distance_km=400.0,
        duration_minutes=120.0,
        n_stops=2,
        consommation_energy=10.0,
        gco2_per_kwh=21.7,
        consommation_totale=4000.0,
        type_train="diesel",
        scenario="scenario_qui_n_existe_pas",
    )
    assert "erreur" in resultat


def test_estimer_co2_futur_arguments_invalides_via_executer_outil():
    # distance_km manquant : champ requis du modèle Pydantic LiaisonCO2Input
    resultat = executer_outil(
        "estimer_co2_futur",
        {
            "duration_minutes": 120.0,
            "n_stops": 2,
            "consommation_energy": 10.0,
            "gco2_per_kwh": 21.7,
            "consommation_totale": 4000.0,
            "type_train": "diesel",
            "scenario": "reference",
        },
    )
    assert "erreur" in resultat


# ---------------------------------------------------------------------------
# Registre et schémas
# ---------------------------------------------------------------------------


def test_registre_outils_contient_les_4_outils():
    assert set(REGISTRE_OUTILS) == {
        "rechercher_trajets",
        "obtenir_statistiques",
        "predire_substitution_avion",
        "estimer_co2_futur",
    }


def test_executer_outil_nom_inconnu(db_session):
    resultat = executer_outil("outil_qui_n_existe_pas", {}, db=db_session)
    assert "erreur" in resultat


@pytest.mark.parametrize(
    "schema",
    [
        SCHEMA_RECHERCHER_TRAJETS,
        SCHEMA_OBTENIR_STATISTIQUES,
        SCHEMA_PREDIRE_SUBSTITUTION_AVION,
        SCHEMA_ESTIMER_CO2_FUTUR,
    ],
)
def test_schema_est_conforme_au_format_openai_tools(schema):
    assert schema["type"] == "function"
    assert "name" in schema["function"]
    assert "description" in schema["function"]
    assert schema["function"]["parameters"]["type"] == "object"
