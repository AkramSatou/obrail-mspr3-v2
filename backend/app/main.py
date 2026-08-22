"""
api.py — API commune ObRail Europe
Démarrage : uvicorn api:app --reload
Documentation : http://localhost:8000/docs

Routes exposées :
    GET  /               → message d'accueil
    GET  /health         → statut de l'API et des modèles chargés
    GET  /trajets        → liste paginée et filtrable des trajets
    GET  /trajets/{id}   → détail d'un trajet par identifiant stable
    GET  /stats/volumes  → volumes agrégés du dataset
    POST /predict                  → classification substitution (compat. v1)
    POST /predict/substitution     → classification substitution avion/train
    POST /predict/co2              → régression émissions CO2 futures

Monitoring en production (à brancher sur Prometheus / Evidently) :
    - Taux de requêtes par minute par route
    - Distribution des prédictions dans le temps
      (proportion de 1 sur /predict/substitution, moyenne kgCO2 sur /predict/co2)
    - Data drift : comparer les distributions des features en entrée
      vs. les distributions du jeu d'entraînement à l'aide d'Evidently ou WhyLogs
    - Latence P50 / P95 / P99 par route
    - Taux d'erreurs HTTP 422 (payload invalide) et 500 (erreur modèle)
"""

from collections import defaultdict
from functools import lru_cache
from math import ceil
import logging
import os
import threading
from pathlib import Path
from time import perf_counter
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Trip, User
from app.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ROLE_ADMIN,
    ROLE_VIEWER,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    require_role,
)

import logging_loki

handler = logging_loki.LokiHandler(
    url="http://loki:3100/loki/api/v1/push",
    tags={"application": "obrail-api"},
    version="1",
)

# Appliquer sur tous les loggers concernés
for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
    logging.getLogger(logger_name).addHandler(handler)

# Journal applicatif dédié : trace les événements d'authentification (succès et
# échecs) sans jamais enregistrer de mot de passe — conformité RGPD, minimisation.
logger = logging.getLogger("obrail.api")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Journal de l'agent IA — obrail.agent.* propage vers ce logger (ÉTAPE D)
logger_agent = logging.getLogger("obrail.agent")
logger_agent.setLevel(logging.INFO)
logger_agent.addHandler(handler)

# ---------------------------------------------------------------------------
# Limitation des tentatives de connexion (OWASP A07)
# ---------------------------------------------------------------------------

_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
_LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", str(15 * 60)))


class _LoginRateLimiter:
    """
    Compteur en mémoire des tentatives de connexion échouées.

    Deux clés sont suivies indépendamment pour chaque tentative :
      - « user:<username> » — protège un compte donné (brute force ciblé)
      - « ip:<adresse> »   — protège l'API d'un hôte donné (bourrage de mots de passe)

    Si l'une des deux clés dépasse le seuil, la tentative est rejetée avec 429.
    """

    def __init__(self) -> None:
        # clé → (nb_echecs, timestamp_fin_de_blocage ou 0.0 si pas encore bloqué)
        self._store: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, *keys: str) -> None:
        """Lève HTTPException 429 si l'une des clés est actuellement bloquée."""
        with self._lock:
            now = perf_counter()
            for key in keys:
                entry = self._store.get(key)
                if entry is None:
                    continue
                count, until = entry
                if until > 0 and now < until:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Trop de tentatives de connexion. Reessayez dans quelques minutes.",
                    )
                if until > 0 and now >= until:
                    del self._store[key]

    def record_failure(self, *keys: str) -> None:
        """Incrémente le compteur ; déclenche le blocage au seuil."""
        with self._lock:
            now = perf_counter()
            for key in keys:
                entry = self._store.get(key, (0, 0.0))
                count = entry[0] + 1
                until = now + _LOGIN_LOCKOUT_SECONDS if count >= _LOGIN_MAX_ATTEMPTS else 0.0
                self._store[key] = (count, until)

    def record_success(self, *keys: str) -> None:
        """Réinitialise le compteur après une authentification réussie."""
        with self._lock:
            for key in keys:
                self._store.pop(key, None)

    def clear(self) -> None:
        """Vide tout l'état — utilisé par les tests pour repartir d'une ardoise vide."""
        with self._lock:
            self._store.clear()


login_rate_limiter = _LoginRateLimiter()

BASE_DIR = Path(__file__).resolve().parents[2]
TRIPS_CSV_PATH = Path(os.getenv("OBRAIL_DATASET_PATH", BASE_DIR / "data" / "eu_trips_v2.csv"))
# En local : BASE_DIR = racine du dépôt → BASE_DIR/models/
# Dans Docker : main.py est dans /app/app/, BASE_DIR = /app → /app/models/
MODELS_PATH = Path(os.getenv("OBRAIL_MODELS_PATH", BASE_DIR / "models"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("OBRAIL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ObRail Europe — API de prédiction ferroviaire",
    description=(
        "API REST du projet ObRail Europe. "
        "Deux enjeux exposés :\n\n"
        "- **Substitution avion/train** : classification binaire — la liaison "
        "est-elle candidate à remplacer un vol aérien ?\n"
        "- **Émissions CO2 futures** : régression — estimation des émissions "
        "kgCO2 selon un scénario de développement du réseau."
    ),
    version="2.0.0",
    contact={"name": "ObRail Europe", "email": "data@obrail.eu"},
)

# GZip sur toutes les réponses > 1 kB — éco-conception RGESN R3.5 / GreenIT BP-049
# Réduction mesurée : ~75 % des réponses JSON (/trajets, /stats/volumes, /health)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Observabilité HTTP
# ---------------------------------------------------------------------------

_LATENCY_BUCKETS_SECONDS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_REQUESTS_TOTAL: dict[tuple[str, str, int], int] = defaultdict(int)
_REQUEST_DURATION_SUM: dict[tuple[str, str], float] = defaultdict(float)
_REQUEST_DURATION_COUNT: dict[tuple[str, str], int] = defaultdict(int)
_REQUEST_DURATION_BUCKETS: dict[tuple[str, str, float], int] = defaultdict(int)


def _route_template(request: Request) -> str:
    """Retourne le template de route pour limiter la cardinalité Prometheus."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


def _record_http_metric(request: Request, status_code: int, duration_seconds: float) -> None:
    """Mémorise les métriques HTTP exposées ensuite au format Prometheus."""
    method = request.method
    path = _route_template(request)
    _REQUESTS_TOTAL[(method, path, status_code)] += 1
    _REQUEST_DURATION_SUM[(method, path)] += duration_seconds
    _REQUEST_DURATION_COUNT[(method, path)] += 1
    for bucket in _LATENCY_BUCKETS_SECONDS:
        if duration_seconds <= bucket:
            _REQUEST_DURATION_BUCKETS[(method, path, bucket)] += 1


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Mesure le volume, la latence et le statut HTTP de chaque requête."""
    start = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_seconds = perf_counter() - start
        _record_http_metric(request, status_code, duration_seconds)


def _prometheus_escape(value: str) -> str:
    """Échappe une valeur de label Prometheus."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(labels: dict[str, str]) -> str:
    return ",".join(f'{key}="{_prometheus_escape(value)}"' for key, value in labels.items())


def _format_sample(metric_name: str, labels: dict[str, str], value: float | int) -> str:
    return f"{metric_name}{{{_format_labels(labels)}}} {value}"


def _dependency_metrics_lines(db: Session) -> list[str]:
    """Expose l'état des dépendances critiques sous forme de gauges."""
    dataset = _dataset_health(db)
    dependencies = {
        "dataset": dataset["status"] == "ok",
        "classification_substitution": _substitution_ok,
        "regression_co2": _co2_ok,
    }

    lines = [
        "# HELP obrail_dependency_up Dependency availability, 1 for available and 0 for unavailable.",
        "# TYPE obrail_dependency_up gauge",
    ]
    for dependency, available in dependencies.items():
        lines.append(
            _format_sample(
                "obrail_dependency_up",
                {"dependency": dependency},
                1 if available else 0,
            )
        )

    if dataset.get("rows") is not None:
        lines.extend(
            [
                "# HELP obrail_dataset_rows Number of rows loaded from the harmonized trips dataset.",
                "# TYPE obrail_dataset_rows gauge",
                f"obrail_dataset_rows {dataset['rows']}",
            ]
        )

    return lines


def _http_metrics_lines() -> list[str]:
    """Expose les compteurs et histogrammes HTTP au format Prometheus."""
    lines = [
        "# HELP obrail_http_requests_total Total HTTP requests handled by the API.",
        "# TYPE obrail_http_requests_total counter",
    ]
    for (method, path, status_code), count in sorted(_REQUESTS_TOTAL.items()):
        lines.append(
            _format_sample(
                "obrail_http_requests_total",
                {"method": method, "path": path, "status": str(status_code)},
                count,
            )
        )

    lines.extend(
        [
            "# HELP obrail_http_request_duration_seconds HTTP request latency in seconds.",
            "# TYPE obrail_http_request_duration_seconds histogram",
        ]
    )
    for method, path in sorted(_REQUEST_DURATION_COUNT):
        cumulative = 0
        for bucket in _LATENCY_BUCKETS_SECONDS:
            cumulative = _REQUEST_DURATION_BUCKETS.get((method, path, bucket), cumulative)
            lines.append(
                _format_sample(
                    "obrail_http_request_duration_seconds_bucket",
                    {"method": method, "path": path, "le": str(bucket)},
                    cumulative,
                )
            )
        lines.append(
            _format_sample(
                "obrail_http_request_duration_seconds_bucket",
                {"method": method, "path": path, "le": "+Inf"},
                _REQUEST_DURATION_COUNT[(method, path)],
            )
        )
        lines.append(
            _format_sample(
                "obrail_http_request_duration_seconds_count",
                {"method": method, "path": path},
                _REQUEST_DURATION_COUNT[(method, path)],
            )
        )
        lines.append(
            _format_sample(
                "obrail_http_request_duration_seconds_sum",
                {"method": method, "path": path},
                round(_REQUEST_DURATION_SUM[(method, path)], 6),
            )
        )

    return lines


# ---------------------------------------------------------------------------
# Métriques agent IA (ÉTAPE D) — nommage obrail_agent_* comme existant
# ---------------------------------------------------------------------------

_AGENT_LATENCY_BUCKETS = (0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
_AGENT_ITERATION_BUCKETS = (1, 2, 3, 4, 5)
_AGENT_REQUESTS_TOTAL: dict[str, int] = defaultdict(int)     # statut → count
_AGENT_TOOL_CALLS_TOTAL: dict[str, int] = defaultdict(int)   # outil → count
_AGENT_DURATION_SUM: dict[str, float] = defaultdict(float)   # "v" → somme
_AGENT_DURATION_COUNT: dict[str, int] = defaultdict(int)     # "v" → count
_AGENT_DURATION_BUCKETS: dict[float, int] = defaultdict(int) # seuil → count cumulatif
_AGENT_ITERATIONS_SUM: dict[str, int] = defaultdict(int)
_AGENT_ITERATIONS_COUNT: dict[str, int] = defaultdict(int)
_AGENT_ITERATIONS_BUCKETS: dict[int, int] = defaultdict(int)


def _record_agent_metric(
    duree_s: float,
    iterations: int,
    statut: str,
    outils: list[str],
) -> None:
    """Enregistre les métriques d'une requête agent."""
    _AGENT_REQUESTS_TOTAL[statut] += 1
    _AGENT_DURATION_SUM["v"] += duree_s
    _AGENT_DURATION_COUNT["v"] += 1
    for bucket in _AGENT_LATENCY_BUCKETS:
        if duree_s <= bucket:
            _AGENT_DURATION_BUCKETS[bucket] += 1
    _AGENT_ITERATIONS_SUM["v"] += iterations
    _AGENT_ITERATIONS_COUNT["v"] += 1
    for bucket in _AGENT_ITERATION_BUCKETS:
        if iterations <= bucket:
            _AGENT_ITERATIONS_BUCKETS[bucket] += 1
    for outil in outils:
        _AGENT_TOOL_CALLS_TOTAL[outil] += 1


def _agent_up_value() -> int:
    try:
        from app.agent.config import charger_config
        charger_config()
        return 1
    except Exception:
        return 0


def _agent_metrics_lines() -> list[str]:
    """Expose les compteurs et histogrammes agent au format Prometheus."""
    lines = [
        "# HELP obrail_agent_requests_total Nombre total de requêtes traitées par l'agent IA.",
        "# TYPE obrail_agent_requests_total counter",
    ]
    for statut, count in sorted(_AGENT_REQUESTS_TOTAL.items()):
        lines.append(_format_sample("obrail_agent_requests_total", {"statut": statut}, count))

    lines.extend([
        "# HELP obrail_agent_tool_calls_total Nombre d'appels par outil de l'agent.",
        "# TYPE obrail_agent_tool_calls_total counter",
    ])
    for outil, count in sorted(_AGENT_TOOL_CALLS_TOTAL.items()):
        lines.append(_format_sample("obrail_agent_tool_calls_total", {"outil": outil}, count))

    lines.extend([
        "# HELP obrail_agent_duration_seconds Durée des requêtes agent en secondes.",
        "# TYPE obrail_agent_duration_seconds histogram",
    ])
    cumul = 0
    for bucket in _AGENT_LATENCY_BUCKETS:
        cumul = _AGENT_DURATION_BUCKETS.get(bucket, cumul)
        lines.append(
            _format_sample("obrail_agent_duration_seconds_bucket", {"le": str(bucket)}, cumul)
        )
    total_dur = _AGENT_DURATION_COUNT["v"]
    lines.append(_format_sample("obrail_agent_duration_seconds_bucket", {"le": "+Inf"}, total_dur))
    lines.append(_format_sample("obrail_agent_duration_seconds_count", {}, total_dur))
    lines.append(
        _format_sample("obrail_agent_duration_seconds_sum", {}, round(_AGENT_DURATION_SUM["v"], 6))
    )

    lines.extend([
        "# HELP obrail_agent_iterations Nombre d'itérations de la boucle agent par requête.",
        "# TYPE obrail_agent_iterations histogram",
    ])
    cumul_it = 0
    for bucket in _AGENT_ITERATION_BUCKETS:
        cumul_it = _AGENT_ITERATIONS_BUCKETS.get(bucket, cumul_it)
        lines.append(
            _format_sample("obrail_agent_iterations_bucket", {"le": str(bucket)}, cumul_it)
        )
    total_it = _AGENT_ITERATIONS_COUNT["v"]
    lines.append(_format_sample("obrail_agent_iterations_bucket", {"le": "+Inf"}, total_it))
    lines.append(_format_sample("obrail_agent_iterations_count", {}, total_it))
    lines.append(_format_sample("obrail_agent_iterations_sum", {}, _AGENT_ITERATIONS_SUM["v"]))

    lines.extend([
        "# HELP obrail_agent_up Disponibilité de l'agent IA (1=opérationnel, 0=erreur config).",
        "# TYPE obrail_agent_up gauge",
        _format_sample("obrail_agent_up", {}, _agent_up_value()),
    ])
    return lines


def _error_payload(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details=None,
) -> dict:
    """Construit le format d'erreur homogène de l'API."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "status_code": status_code,
            "timestamp": _utc_now_iso(),
            "path": request.url.path,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Normalise les erreurs HTTP contrôlées."""
    detail = exc.detail if getattr(exc, "detail", None) else "Erreur HTTP"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request=request,
            status_code=exc.status_code,
            code=f"HTTP_{exc.status_code}",
            message=str(detail),
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalise les erreurs de validation FastAPI/Pydantic."""
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request=request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Paramètres ou payload invalides",
            details=jsonable_encoder(exc.errors()),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Évite les réponses hétérogènes en cas d'erreur inattendue."""
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request=request,
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="Erreur interne du serveur",
        ),
    )

# ---------------------------------------------------------------------------
# Chargement des modèles au démarrage (une seule fois)
# ---------------------------------------------------------------------------

try:
    _model_substitution = joblib.load(MODELS_PATH / "classification_substitution_avion.joblib")
    _encoders = joblib.load(MODELS_PATH / "encoders.joblib")
    # Le scaler reste chargé (artefact légitime, exposé via /health), mais n'est PAS
    # appliqué à l'inférence XGBoost — voir docs/INCIDENT-002-scaler-inference.md.
    _scaler = joblib.load(MODELS_PATH / "scaler.joblib")
    _substitution_ok = True
except Exception as e:
    _substitution_ok = False
    _substitution_error = str(e)

try:
    # Pipeline complet sklearn (ColumnTransformer + XGBoost) — pas d'encodeur séparé
    _model_co2 = joblib.load(MODELS_PATH / "regression_co2.joblib")
    _co2_ok = True
except Exception as e:
    _co2_ok = False
    _co2_error = str(e)

# ---------------------------------------------------------------------------
# Schémas Pydantic — Classification substitution
# ---------------------------------------------------------------------------

class LiaisonSubstitutionInput(BaseModel):
    """Caractéristiques d'une liaison ferroviaire pour la classification substitution."""

    distance_km: float = Field(
        ..., example=1200.0,
        description="Distance géographique de la liaison en km"
    )
    duration_minutes: float = Field(
        ..., example=360.0,
        description="Durée du trajet en minutes"
    )
    n_stops: int = Field(
        ..., example=2,
        description="Nombre d'arrêts intermédiaires"
    )
    co2_estime: float = Field(
        ..., example=450000.0,
        description="Émissions CO2 estimées en gCO2"
    )
    consommation_totale: float = Field(
        ..., example=20000.0,
        description="Consommation énergétique totale en kWh"
    )
    type_train: str = Field(
        ..., example="electric",
        description="Type de traction : 'electric' ou 'diesel'"
    )
    country: str = Field(
        ..., example="FR",
        description="Code pays : 'FR', 'ES', 'IT' ou 'DE'"
    )


class SubstitutionOutput(BaseModel):
    """Résultat de la classification substitution avion/train."""

    substitution_avion: int = Field(description="1 = substituable, 0 = non substituable")
    probabilite: float = Field(description="Probabilité d'être substituable (entre 0 et 1)")
    label: str = Field(description="Libellé lisible de la prédiction")


# ---------------------------------------------------------------------------
# Schémas Pydantic — Régression CO2
# ---------------------------------------------------------------------------

class LiaisonCO2Input(BaseModel):
    """Caractéristiques d'une liaison ferroviaire et scénario pour l'estimation CO2."""

    distance_km: float = Field(
        ..., example=400.0,
        description="Distance géographique de la liaison en km"
    )
    duration_minutes: float = Field(
        ..., example=120.0,
        description="Durée du trajet en minutes"
    )
    n_stops: int = Field(
        ..., example=2,
        description="Nombre d'arrêts intermédiaires"
    )
    consommation_energy: float = Field(
        ..., example=10.0,
        description="Consommation énergétique en kWh/km"
    )
    gco2_per_kwh: float = Field(
        ..., example=21.7,
        description="Facteur carbone du pays en gCO2/kWh"
    )
    consommation_totale: float = Field(
        ..., example=4000.0,
        description="Consommation totale actuelle en kWh"
    )
    type_train: str = Field(
        ..., example="diesel",
        description="Type de traction : 'electric' ou 'diesel'"
    )
    scenario: str = Field(
        ..., example="diesel_50_electrique",
        description=(
            "Scénario de développement du réseau. "
            "Valeurs : 'reference', 'diesel_50_electrique', "
            "'conso_moins_15', 'distance_moins_10'"
        )
    )


class CO2Output(BaseModel):
    """Résultat de l'estimation des émissions CO2 futures."""

    scenario: str = Field(description="Scénario appliqué")
    co2_estime_kg: float = Field(description="Émissions CO2 estimées en kgCO2")
    label: str = Field(description="Libellé lisible du résultat")


# ---------------------------------------------------------------------------
# Schémas Pydantic — Consultation des trajets
# ---------------------------------------------------------------------------

class TrajetOutput(BaseModel):
    """Trajet ferroviaire harmonisé exposé par l'API."""

    id: str = Field(description="Identifiant unique du trajet, issu de trip_id")
    route_id: str = Field(description="Identifiant de la ligne ou route")
    route_long_name: Optional[str] = Field(default=None, description="Nom commercial de la ligne")
    origin_stop_name: str = Field(description="Gare de départ")
    destination_stop_name: str = Field(description="Gare d'arrivée")
    country: str = Field(description="Code pays ISO du trajet")
    type_train: str = Field(description="Type de traction du train")
    distance_km: float = Field(description="Distance du trajet en kilomètres")
    duration_minutes: float = Field(description="Durée du trajet en minutes")
    n_stops: int = Field(description="Nombre d'arrêts intermédiaires")
    departure_minutes: Optional[float] = Field(default=None, description="Départ en minutes depuis minuit")
    arrival_minutes: Optional[float] = Field(default=None, description="Arrivée en minutes depuis minuit")
    kg_co2_emis: Optional[float] = Field(default=None, description="Émissions estimées en kgCO2")


class TrajetsResponse(BaseModel):
    """Réponse paginée de la liste des trajets."""

    page: int = Field(description="Page courante, indexée à partir de 1")
    page_size: int = Field(description="Nombre maximum de trajets retournés")
    total: int = Field(description="Nombre total de trajets après filtrage")
    total_pages: int = Field(description="Nombre total de pages après filtrage")
    items: list[TrajetOutput] = Field(description="Trajets de la page demandée")


class VolumeBucket(BaseModel):
    """Agrégat de volume pour une dimension métier."""

    key: str = Field(description="Valeur de regroupement, par exemple FR ou electric")
    total_trajets: int = Field(description="Nombre de trajets du groupe")
    total_distance_km: float = Field(description="Distance cumulée en kilomètres")
    total_kg_co2_emis: float = Field(description="Émissions cumulées en kgCO2")


class StatsVolumesResponse(BaseModel):
    """Indicateurs de volumes exposés au tableau de bord."""

    generated_at: str = Field(description="Timestamp UTC de génération")
    total_trajets: int = Field(description="Nombre total de trajets dans le dataset")
    total_countries: int = Field(description="Nombre de pays représentés")
    total_routes: int = Field(description="Nombre de routes distinctes")
    total_distance_km: float = Field(description="Distance cumulée en kilomètres")
    total_kg_co2_emis: float = Field(description="Émissions cumulées en kgCO2")
    by_country: list[VolumeBucket] = Field(description="Volumes agrégés par pays")
    by_type_train: list[VolumeBucket] = Field(description="Volumes agrégés par type de train")


# ---------------------------------------------------------------------------
# Schémas Pydantic — Agent IA (ÉTAPE C)
# ---------------------------------------------------------------------------


class AgentChatRequest(BaseModel):
    """Corps attendu par POST /agent/chat."""

    message: str = Field(..., min_length=1, max_length=2000, description="Question adressée à l'agent")
    session_id: Optional[str] = Field(default=None, description="Identifiant de session (généré si absent)")
    fournisseur_force: Optional[str] = Field(
        default=None,
        description="Forcer un fournisseur pour cette requête : 'ollama', 'openrouter' ou 'auto'. "
                    "Ne modifie pas la configuration globale du serveur.",
    )


class EntreeTrace(BaseModel):
    """Une étape dans la trace de raisonnement de l'agent."""

    etape: int = Field(description="Numéro d'étape dans la trace")
    type: str = Field(description="Type d'entrée : 'outil' ou 'reponse'")
    outil: Optional[str] = Field(default=None, description="Nom de l'outil appelé (si type='outil')")
    arguments: Optional[dict] = Field(default=None, description="Arguments fournis à l'outil")
    resultat_resume: Optional[str] = Field(default=None, description="Résumé une ligne du résultat")
    duree_ms: Optional[int] = Field(default=None, description="Durée d'exécution de l'outil en ms")
    contenu: Optional[str] = Field(default=None, description="Contenu de la réponse finale (si type='reponse')")


class AgentChatResponse(BaseModel):
    """Réponse complète de la route POST /agent/chat (contrat §3 du plan)."""

    reponse: str = Field(description="Réponse finale de l'agent en langage naturel")
    session_id: str = Field(description="Identifiant de session")
    mode: str = Field(description="Mode d'exécution : 'direct' ou 'rejeu'")
    fournisseur: str = Field(description="Fournisseur LLM utilisé")
    modele: str = Field(description="Modèle LLM utilisé")
    duree_ms: int = Field(description="Durée totale de la requête en millisecondes")
    iterations: int = Field(description="Nombre d'itérations de la boucle")
    trace: list[EntreeTrace] = Field(description="Trace détaillée du raisonnement")


class AgentInfoResponse(BaseModel):
    """Réponse de GET /agent/info."""

    fournisseur: str = Field(description="Fournisseur configuré (auto/openrouter/ollama/rejeu)")
    modele: str = Field(description="Modèle actif selon le fournisseur")
    mode: str = Field(description="Mode d'exécution : 'direct' ou 'rejeu'")
    disponible: bool = Field(description="True si la configuration est valide")
    outils: list[str] = Field(description="Liste des outils disponibles pour l'agent")
    max_iterations: int = Field(description="Nombre maximum d'itérations de la boucle")
    timeout_s: int = Field(description="Timeout global d'une requête agent en secondes")


# ---------------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------------

def _build_substitution_df(liaison: LiaisonSubstitutionInput) -> pd.DataFrame:
    """Encode et construit le DataFrame d'entrée pour le modèle de classification."""
    type_train_enc = _encoders["le_type_train"].transform([liaison.type_train])[0]
    country_enc = _encoders["le_country"].transform([liaison.country])[0]
    return pd.DataFrame([{
        "distance_km":        liaison.distance_km,
        "duration_minutes":   liaison.duration_minutes,
        "n_stops":            liaison.n_stops,
        "co2_estime":         liaison.co2_estime,
        "consommation_totale": liaison.consommation_totale,
        "type_train":         type_train_enc,
        "country":            country_enc,
    }])


def _build_co2_df(liaison: LiaisonCO2Input) -> pd.DataFrame:
    """Calcule les features dérivées et construit le DataFrame pour le Pipeline CO2."""
    # Features dérivées (identiques à predict_co2.py)
    vitesse = (liaison.distance_km / (liaison.duration_minutes / 60)
               if liaison.duration_minutes > 0 else 0.0)
    # NOTE dimensionnelle : consommation_energy est en kWh/km, gco2_per_kwh en gCO2/kWh.
    # Leur produit donne gCO2/km, puis la division par distance_km produit gCO2/km².
    # Cette formule est celle qui reproduit exactement le cas de référence du rapport
    # (104,34 kgCO2 pour 400 km, diesel, consommation_energy=10, gco2_per_kwh=21,7),
    # et qui a donc été utilisée à l'entraînement. Ne pas corriger sans rapatrier
    # le notebook 01_regression_co2.ipynb — voir docs/INCIDENT-003-regression-co2.md.
    co2_par_km = ((liaison.consommation_energy * liaison.gco2_per_kwh) / liaison.distance_km
                  if liaison.distance_km > 0 else 0.0)
    is_diesel   = 1 if liaison.type_train == "diesel" else 0
    is_electric = 1 if liaison.type_train == "electric" else 0

    # Adaptation selon le scénario
    distance_scenario_km  = liaison.distance_km
    consommation_scenario = liaison.consommation_totale

    if liaison.scenario == "diesel_50_electrique" and liaison.type_train == "diesel":
        consommation_scenario *= 0.50
    elif liaison.scenario == "conso_moins_15":
        consommation_scenario *= 0.85
    elif liaison.scenario == "distance_moins_10":
        distance_scenario_km  *= 0.90
        consommation_scenario *= 0.90
    # "reference" : aucune modification

    return pd.DataFrame([{
        "distance_scenario_km":  distance_scenario_km,
        "duration_minutes":      liaison.duration_minutes,
        "n_stops":               liaison.n_stops,
        "consommation_energy":   liaison.consommation_energy,
        "gco2_per_kwh":          liaison.gco2_per_kwh,
        "consommation_scenario": consommation_scenario,
        "vitesse_moyenne_kmh":   vitesse,
        "co2_par_km":            co2_par_km,
        "is_diesel":             is_diesel,
        "is_electric":           is_electric,
        "type_train":            liaison.type_train,
        "scenario":              liaison.scenario,
    }])


@lru_cache(maxsize=1)
def _load_trips_df() -> pd.DataFrame:
    """Charge le dataset harmonisé des trajets une seule fois par processus."""
    if not TRIPS_CSV_PATH.exists():
        raise FileNotFoundError(f"Dataset introuvable : {TRIPS_CSV_PATH}")

    required_columns = [
        "arrival_minutes",
        "departure_minutes",
        "destination_stop_name",
        "duration_minutes",
        "n_stops",
        "origin_stop_name",
        "route_id",
        "route_long_name",
        "trip_id",
        "country",
        "distance_km",
        "type_train",
    ]
    header = pd.read_csv(TRIPS_CSV_PATH, nrows=0).columns
    co2_column = "kgCO2_emis" if "kgCO2_emis" in header else "co2_estime"
    if co2_column not in header:
        raise ValueError("Dataset invalide : colonne CO2 attendue absente (kgCO2_emis ou co2_estime)")

    trips = pd.read_csv(TRIPS_CSV_PATH, usecols=[*required_columns, co2_column], low_memory=False)
    if co2_column != "kgCO2_emis":
        trips = trips.rename(columns={co2_column: "kgCO2_emis"})
    return trips


def _load_trips_from_db(db: Session) -> pd.DataFrame:
    """Load trips from PostgreSQL.
    Converts co2_estime (gCO2) to kgCO2_emis (kgCO2) by dividing by 1000.
    """
    rows = db.query(Trip).all()
    data = [{
        "trip_id": row.trip_id,
        "route_id": row.route_id,
        "route_long_name": row.route_long_name,
        "country": row.country,
        "origin_stop_name": row.origin_stop_name,
        "destination_stop_name": row.destination_stop_name,
        "departure_minutes": row.departure_minutes,
        "arrival_minutes": row.arrival_minutes,
        "duration_minutes": row.duration_minutes,
        "n_stops": row.n_stops,
        "distance_km": row.distance_km,
        "type_train": row.type_train,
        "kgCO2_emis": row.co2_estime / 1000,
    } for row in rows]
    return pd.DataFrame(data)


def _build_trips_query(
    db: Session,
    country: Optional[str],
    type_train: Optional[str],
    origin: Optional[str],
    destination: Optional[str],
    min_distance_km: Optional[float],
    max_distance_km: Optional[float],
):
    """Construit la requête SQLAlchemy filtrée sur Trip, sans charger les lignes."""
    query = db.query(Trip)

    if country:
        query = query.filter(Trip.country.ilike(country))
    if type_train:
        query = query.filter(Trip.type_train.ilike(type_train))
    if origin:
        query = query.filter(Trip.origin_stop_name.ilike(f"%{origin}%"))
    if destination:
        query = query.filter(Trip.destination_stop_name.ilike(f"%{destination}%"))
    if min_distance_km is not None:
        query = query.filter(Trip.distance_km >= min_distance_km)
    if max_distance_km is not None:
        query = query.filter(Trip.distance_km <= max_distance_km)

    return query


def _optional_float(value) -> Optional[float]:
    """Convertit une valeur potentiellement absente en float JSON-compatible."""
    if value is None:
        return None
    return float(value)


def _trip_to_trajet(row: Trip) -> TrajetOutput:
    """Convertit une ligne ORM Trip en contrat API stable."""
    return TrajetOutput(
        id=str(row.trip_id),
        route_id=str(row.route_id) if row.route_id is not None else "",
        route_long_name=row.route_long_name,
        origin_stop_name=row.origin_stop_name,
        destination_stop_name=row.destination_stop_name,
        country=row.country,
        type_train=row.type_train,
        distance_km=float(row.distance_km),
        duration_minutes=float(row.duration_minutes),
        n_stops=int(row.n_stops),
        departure_minutes=_optional_float(row.departure_minutes),
        arrival_minutes=_optional_float(row.arrival_minutes),
        kg_co2_emis=_optional_float(row.co2_estime / 1000 if row.co2_estime is not None else None),
    )


def _utc_now_iso() -> str:
    """Retourne un timestamp UTC ISO 8601 utilisable dans les réponses API."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _round_metric(value: float) -> float:
    """Arrondit les agrégats numériques pour des réponses stables et lisibles."""
    return round(float(value), 3)


def _volume_buckets(trips: pd.DataFrame, group_column: str) -> list[VolumeBucket]:
    """Construit des agrégats de volume pour une colonne du dataset."""
    grouped = (
        trips.groupby(group_column, dropna=False)
        .agg(
            total_trajets=("trip_id", "count"),
            total_distance_km=("distance_km", "sum"),
            total_kg_co2_emis=("kgCO2_emis", "sum"),
        )
        .reset_index()
        .sort_values(["total_trajets", group_column], ascending=[False, True])
    )

    return [
        VolumeBucket(
            key="unknown" if pd.isna(row[group_column]) else str(row[group_column]),
            total_trajets=int(row["total_trajets"]),
            total_distance_km=_round_metric(row["total_distance_km"]),
            total_kg_co2_emis=_round_metric(row["total_kg_co2_emis"]),
        )
        for _, row in grouped.iterrows()
    ]


def _model_health(name: str, available: bool, error: Optional[str] = None) -> dict:
    """Normalise l'état d'un modèle pour /health."""
    payload = {"status": "ok" if available else "unavailable"}
    if error:
        payload["error"] = error
    return {name: payload}


def _dataset_health(db: Session) -> dict:
    """Retourne l'état de la base de données sans masquer les erreurs de lecture."""
    try:
        count = db.query(Trip).count()
        return {"status": "ok", "rows": count, "columns": 13}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# ─── Authentification ─────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """Couple de jetons renvoyé à la connexion."""

    access_token: str = Field(..., description="Jeton d'accès, à placer dans l'en-tête Authorization: Bearer <token>")
    refresh_token: str = Field(..., description="Jeton de rafraîchissement, à envoyer à POST /auth/refresh")
    token_type: str = Field("bearer", description="Type de jeton, conforme à OAuth2")
    expires_in: int = Field(..., description="Durée de vie du jeton d'accès, en secondes")
    role: str = Field(..., description="Rôle applicatif de l'utilisateur : viewer ou admin")


class RefreshRequest(BaseModel):
    """Corps attendu par POST /auth/refresh."""

    refresh_token: str = Field(..., description="Jeton de rafraîchissement obtenu à la connexion")


class UserOutput(BaseModel):
    """Identité de l'utilisateur authentifié."""

    username: str
    role: str
    is_active: bool


@app.post("/auth/login", response_model=TokenResponse, tags=["Authentification"])
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authentifie un utilisateur et délivre un couple de jetons JWT.

    Le formulaire attend les champs OAuth2 standards `username` et `password`,
    ce qui rend la route directement utilisable depuis le bouton « Authorize »
    de Swagger.

    Le message d'erreur est volontairement identique que l'utilisateur soit
    inconnu ou que le mot de passe soit incorrect, afin de ne pas permettre
    l'énumération des comptes existants.

    Après 5 tentatives échouées (par identifiant ou par adresse IP), les
    nouvelles tentatives sont bloquées pendant 15 minutes (HTTP 429).
    """
    ip = request.client.host if request.client else "unknown"
    key_user = f"user:{form_data.username}"
    key_ip = f"ip:{ip}"

    login_rate_limiter.check(key_user, key_ip)

    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        login_rate_limiter.record_failure(key_user, key_ip)
        logger.warning("Echec d authentification pour l utilisateur '%s'", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_rate_limiter.record_success(key_user, key_ip)
    logger.info("Authentification reussie pour '%s' (role %s)", user.username, user.role)
    return TokenResponse(
        access_token=create_access_token(user.username, user.role),
        refresh_token=create_refresh_token(user.username, user.role),
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
    )


@app.post("/auth/refresh", response_model=TokenResponse, tags=["Authentification"])
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    """
    Renouvelle un jeton d'accès expiré à partir du jeton de rafraîchissement,
    sans redemander le mot de passe.

    Le type du jeton est vérifié : un jeton d'accès présenté ici est rejeté.
    Le compte est revalidé en base à chaque renouvellement, ce qui permet de
    révoquer un utilisateur en le désactivant.
    """
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    user = db.query(User).filter(User.username == claims["sub"]).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Compte introuvable ou désactivé",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user.username, user.role),
        refresh_token=create_refresh_token(user.username, user.role),
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
    )


@app.get("/auth/me", response_model=UserOutput, tags=["Authentification"])
def read_current_user(current_user: User = Depends(get_current_user)):
    """Retourne l'identité et le rôle de l'utilisateur porteur du jeton."""
    return UserOutput(
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@app.get("/", tags=["Général"])
def root():
    """Message d'accueil — liste les routes disponibles."""
    return {
        "message": "ObRail Europe — API de prédiction ferroviaire",
        "version": "2.0.0",
        "routes": {
            "POST /auth/login":           "Authentification — délivre un jeton JWT",
            "POST /auth/refresh":         "Renouvellement du jeton d'accès",
            "GET  /auth/me":              "Identité et rôle de l'utilisateur connecté",
            "GET  /health":               "Statut de l'API, du dataset et des modèles (public)",
            "GET  /trajets":              "Liste paginée et filtrable des trajets (authentification requise)",
            "GET  /trajets/{id}":         "Détail d'un trajet par trip_id",
            "GET  /stats/volumes":        "Volumes agrégés par pays et type de train",
            "GET  /metrics":              "Métriques Prometheus de l'API",
            "POST /predict/substitution": "Classification substitution avion/train (rôle admin)",
            "POST /predict/co2":          "Estimation CO2 futur selon scénario (rôle admin)",
            "GET  /docs":                 "Documentation interactive (Swagger)",
        },
    }


@app.get("/trajets", response_model=TrajetsResponse, tags=["Données"])
def list_trajets(
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page à retourner, indexée à partir de 1"),
    page_size: int = Query(25, ge=1, le=100, description="Nombre de trajets par page"),
    country: Optional[str] = Query(None, min_length=2, max_length=2, description="Filtre par code pays, ex. FR"),
    type_train: Optional[str] = Query(None, description="Filtre par type de train, ex. electric ou diesel"),
    origin: Optional[str] = Query(None, description="Recherche partielle sur la gare de départ"),
    destination: Optional[str] = Query(None, description="Recherche partielle sur la gare d'arrivée"),
    min_distance_km: Optional[float] = Query(None, ge=0, description="Distance minimale en kilomètres"),
    max_distance_km: Optional[float] = Query(None, ge=0, description="Distance maximale en kilomètres"),
    db: Session = Depends(get_db),
):
    """Retourne les trajets harmonisés avec pagination et filtres simples."""
    if (
        min_distance_km is not None
        and max_distance_km is not None
        and min_distance_km > max_distance_km
    ):
        raise HTTPException(
            status_code=422,
            detail="min_distance_km doit être inférieur ou égal à max_distance_km",
        )

    query = _build_trips_query(
        db=db,
        country=country,
        type_train=type_train,
        origin=origin,
        destination=destination,
        min_distance_km=min_distance_km,
        max_distance_km=max_distance_km,
    )

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0
    rows = (
        query.order_by(Trip.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [_trip_to_trajet(row) for row in rows]

    return TrajetsResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        items=items,
    )


@app.get("/trajets/{trajet_id}", response_model=TrajetOutput, tags=["Données"])
def get_trajet(
    trajet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne le détail d'un trajet à partir de son identifiant stable trip_id."""
    row = db.query(Trip).filter(Trip.trip_id == trajet_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trajet '{trajet_id}' introuvable")

    return _trip_to_trajet(row)


@app.get("/stats/volumes", response_model=StatsVolumesResponse, tags=["Données"])
def stats_volumes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Expose des volumes globaux et agrégés pour le tableau de bord ObRail."""
    try:
        trips = _load_trips_from_db(db)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    payload = StatsVolumesResponse(
        generated_at=_utc_now_iso(),
        total_trajets=int(len(trips)),
        total_countries=int(trips["country"].nunique(dropna=True)),
        total_routes=int(trips["route_id"].nunique(dropna=True)),
        total_distance_km=_round_metric(trips["distance_km"].sum()),
        total_kg_co2_emis=_round_metric(trips["kgCO2_emis"].sum()),
        by_country=_volume_buckets(trips, "country"),
        by_type_train=_volume_buckets(trips, "type_train"),
    )
    # Éco-conception RGESN R4.2 / GreenIT BP-075 : données agrégées stables 5 min
    # Le dataset ne change pas en cours de session — inutile de refetcher à chaque render.
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Cache-Control": "private, max-age=300"},
    )


def _agent_health() -> dict:
    """Informations de configuration de l'agent IA pour /health (D6 : hors calcul du statut global)."""
    try:
        from app.agent.selection import etat_agent
        return etat_agent()
    except Exception as exc:
        return {"status": "erreur_config", "detail": str(exc)}


@app.get("/health", tags=["Général"])
def health(db: Session = Depends(get_db)):
    """Vérifie que l'API, le dataset et les deux modèles sont opérationnels."""
    dataset = _dataset_health(db)
    models = {}
    models.update(
        _model_health(
            "classification_substitution",
            _substitution_ok,
            None if _substitution_ok else _substitution_error,
        )
    )
    models.update(
        _model_health(
            "regression_co2",
            _co2_ok,
            None if _co2_ok else _co2_error,
        )
    )

    dependency_statuses = [dataset["status"], *(model["status"] for model in models.values())]
    if all(status == "ok" for status in dependency_statuses):
        status = "ok"
    elif dataset["status"] != "ok":
        status = "unavailable"
    else:
        status = "degraded"

    return {
        "status": status,
        "timestamp": _utc_now_iso(),
        "dataset": dataset,
        "models": models,
        "agent": _agent_health(),
    }


@app.get("/metrics", tags=["Monitoring"], include_in_schema=False)
def metrics(db: Session = Depends(get_db)):
    """Expose les métriques Prometheus collectées par le backend."""
    lines = [
        "# HELP obrail_api_info Static API information.",
        "# TYPE obrail_api_info gauge",
        'obrail_api_info{app="obrail-backend",version="2.0.0"} 1',
        *_dependency_metrics_lines(db),
        *_http_metrics_lines(),
        *_agent_metrics_lines(),
    ]
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.post("/predict", response_model=SubstitutionOutput, tags=["Classification"])
def predict_compat(
    liaison: LiaisonSubstitutionInput,
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    """
    [Compatibilité v1] Prédit si une liaison est candidate à la substitution avion/train.
    Identique à POST /predict/substitution — conservée pour ne pas casser les intégrations existantes.
    """
    return _predict_substitution_logic(liaison)


@app.post("/predict/substitution", response_model=SubstitutionOutput, tags=["Classification"])
def predict_substitution(
    liaison: LiaisonSubstitutionInput,
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    """
    Prédit si une liaison ferroviaire est candidate à remplacer un vol aérien.

    - **1** : liaison substituable (distance 300-1500 km, durée < 8h)
    - **0** : liaison non substituable
    """
    return _predict_substitution_logic(liaison)


def _predict_substitution_logic(liaison: LiaisonSubstitutionInput) -> SubstitutionOutput:
    """Logique commune aux routes /predict et /predict/substitution."""
    if not _substitution_ok:
        raise HTTPException(status_code=503, detail=f"Modèle de classification indisponible : {_substitution_error}")
    try:
        X = _build_substitution_df(liaison)
        # NE PAS appliquer _scaler ici. Le modele retenu est un XGBClassifier,
        # entraine sur les variables BRUTES : le rapport TPRE622 section 5.3.3
        # precise que le StandardScaler n a servi qu a la regression logistique,
        # les modeles a base d arbres travaillant sur des seuils ordinaux.
        # Appliquer le scaler renvoyait 0 pour absolument toutes les liaisons
        # (F1-macro 0.479, rappel de la classe 1 nul) sans lever la moindre erreur.
        # Voir docs/INCIDENT-002-scaler-inference.md et ml/tests/test_inference_contract.py
        prediction = int(_model_substitution.predict(X)[0])
        proba = float(_model_substitution.predict_proba(X)[0][1])
        label = "Substituable à l'avion" if prediction == 1 else "Non substituable"
        return SubstitutionOutput(
            substitution_avion=prediction,
            probabilite=round(proba, 4),
            label=label,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Valeur invalide : {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de prédiction : {e}")


_SCENARIOS_CO2_VALIDES = frozenset(
    {"reference", "diesel_50_electrique", "conso_moins_15", "distance_moins_10"}
)


def _predict_co2_logic(liaison: LiaisonCO2Input) -> CO2Output:
    """Logique commune à la route /predict/co2 et à l'outil estimer_co2_futur."""
    if not _co2_ok:
        raise HTTPException(status_code=503, detail=f"Modèle de régression CO2 indisponible : {_co2_error}")

    if liaison.scenario not in _SCENARIOS_CO2_VALIDES:
        raise HTTPException(
            status_code=422,
            detail=f"Scénario '{liaison.scenario}' inconnu. Valeurs acceptées : {sorted(_SCENARIOS_CO2_VALIDES)}"
        )

    try:
        X = _build_co2_df(liaison)
        co2_predit = float(_model_co2.predict(X)[0])
        return CO2Output(
            scenario=liaison.scenario,
            co2_estime_kg=round(co2_predit, 4),
            label=f"CO2 estimé : {co2_predit:.2f} kgCO2 (scénario : {liaison.scenario})",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de prédiction CO2 : {e}")


@app.post("/predict/co2", response_model=CO2Output, tags=["Régression CO2"])
def predict_co2(
    liaison: LiaisonCO2Input,
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    """
    Estime les émissions CO2 futures d'une liaison ferroviaire selon un scénario.

    Scénarios disponibles :
    - **reference** : pas de changement — baseline actuel
    - **diesel_50_electrique** : trains diesel à -50% d'émissions
    - **conso_moins_15** : consommation réduite de 15% sur tous les trains
    - **distance_moins_10** : trajets raccourcis de 10%

    Retourne le CO2 estimé en **kgCO2**.
    """
    return _predict_co2_logic(liaison)


# ---------------------------------------------------------------------------
# Routes agent IA — D5 : require_role(ROLE_ADMIN) sur toutes les routes /agent/*
# ---------------------------------------------------------------------------


@app.post("/agent/chat", response_model=AgentChatResponse, tags=["Agent IA"])
def agent_chat(
    requete: AgentChatRequest,
    request: Request,
    current_user: User = Depends(require_role(ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Traite un message via la boucle d'agent IA et retourne la réponse avec sa trace.

    Requiert le rôle **admin** (D5) — un viewer ne peut pas appeler les outils
    de prédiction, même indirectement via l'agent.
    """
    import httpx as _httpx
    from app.agent.boucle import executer_boucle
    from app.agent.selection import obtenir_fournisseur as _obtenir_fournisseur
    try:
        fournisseur = (
            _obtenir_fournisseur(requete.fournisseur_force)
            if requete.fournisseur_force
            else None
        )
        resultat = executer_boucle(
            message=requete.message,
            session_id=requete.session_id,
            fournisseur=fournisseur,
            db=db,
        )
        outils_appeles = [e["outil"] for e in resultat["trace"] if e["type"] == "outil"]
        logger_agent.info(
            "Agent statut=succes session=%s durée=%dms itérations=%d outils=%s",
            resultat["session_id"], resultat["duree_ms"], resultat["iterations"], outils_appeles,
        )
        _record_agent_metric(
            duree_s=resultat["duree_ms"] / 1000,
            iterations=resultat["iterations"],
            statut="succes",
            outils=outils_appeles,
        )
        return AgentChatResponse(**resultat)
    except TimeoutError:
        logger_agent.warning("Agent statut=erreur type=timeout")
        _record_agent_metric(0.0, 0, "erreur", [])
        raise HTTPException(
            status_code=504,
            detail="Délai d'attente dépassé — l'agent n'a pas répondu à temps",
        )
    except (_httpx.RequestError, _httpx.HTTPStatusError) as exc:
        logger_agent.warning("Agent statut=erreur type=fournisseur_injoignable erreur=%s", exc)
        _record_agent_metric(0.0, 0, "erreur", [])
        # Invalide le cache auto pour que la prochaine requête re-sélectionne un fournisseur
        try:
            from app.agent.selection import invalider_cache_si_auto
            if fournisseur:
                invalider_cache_si_auto(fournisseur.nom)
        except Exception:
            pass
        raise HTTPException(
            status_code=503,
            detail=f"Fournisseur LLM injoignable : {exc}",
        )
    except NotImplementedError as exc:
        logger_agent.warning("Agent statut=erreur type=non_implemente erreur=%s", exc)
        _record_agent_metric(0.0, 0, "erreur", [])
        raise HTTPException(status_code=503, detail=str(exc))
    except (ValueError, FileNotFoundError) as exc:
        # Question non trouvée en mode rejeu — §0.6-1 : erreur explicite, pas de réponse inventée
        logger_agent.warning("Agent statut=erreur type=rejeu_introuvable erreur=%s", exc)
        _record_agent_metric(0.0, 0, "erreur", [])
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/geocode", tags=["Géocodage"])
def geocode(
    origine: str = Query(..., description="Nom du lieu de départ (ville ou gare)"),
    destination: str = Query(..., description="Nom du lieu d'arrivée (ville ou gare)"),
    type_train: str = Query("electric", description="Type de traction pour l'estimation de durée"),
    current_user: User = Depends(get_current_user),
):
    """
    Géocode deux lieux via Nominatim (OpenStreetMap) et retourne :
    - distance à vol d'oiseau (formule de Haversine)
    - durée estimée selon la traction (vitesse conventionnelle, pas un horaire réel)
    - coordonnées des deux points géocodés

    Passe toujours par le backend pour respecter la politique Nominatim
    (1 req/s, User-Agent identifiable, cache serveur).
    """
    from app.geocodage import calculer_trajet
    try:
        return calculer_trajet(origine, destination, type_train)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Service de géocodage indisponible : {exc}")


@app.get("/agent/info", response_model=AgentInfoResponse, tags=["Agent IA"])
def agent_info(
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    """
    Retourne la configuration active de l'agent IA.
    N'expose jamais la clé API (D7).
    Requiert le rôle **admin** (D5).
    """
    from app.agent.config import charger_config
    from app.agent.outils import REGISTRE_OUTILS
    config = charger_config()
    modele = (
        config.model_openrouter
        if config.provider in ("openrouter", "auto")
        else config.model_ollama
    )
    return AgentInfoResponse(
        fournisseur=config.provider,
        modele=modele,
        mode="rejeu" if config.provider == "rejeu" else "direct",
        disponible=config.provider != "rejeu",
        outils=list(REGISTRE_OUTILS.keys()),
        max_iterations=config.max_iterations,
        timeout_s=config.timeout_s,
    )
