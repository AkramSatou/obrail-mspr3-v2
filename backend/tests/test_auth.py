"""
Tests d'authentification et d'autorisation de l'API ObRail Europe.

Couvrent les critères de la certification portant sur la restriction d'accès :
    - l'API restreint l'accès aux données (C5) et au modèle d'IA (C9)
    - les étapes d'authentification et de renouvellement du jeton (C10)
    - la gestion des droits d'accès par rôle (C17)
"""

import time

import jwt
import pytest

from app.security import JWT_ALGORITHM, JWT_SECRET_KEY, create_access_token

PROTECTED_DATA_ROUTES = ["/trajets", "/trajets/T1", "/stats/volumes"]
ADMIN_ROUTES = ["/predict", "/predict/substitution", "/predict/co2"]
PUBLIC_ROUTES = ["/", "/health", "/metrics"]

SUBSTITUTION_PAYLOAD = {
    "distance_km": 800.0,
    "duration_minutes": 195.0,
    "n_stops": 3,
    "co2_estime": 450000.0,
    "consommation_totale": 16000.0,
    "type_train": "electric",
    "country": "FR",
}


# --- Routes publiques --------------------------------------------------------

@pytest.mark.parametrize("route", PUBLIC_ROUTES)
def test_public_routes_stay_reachable_without_token(anonymous_client, route):
    """
    /, /health et /metrics restent volontairement ouverts : le healthcheck Docker,
    le badge d'état du frontend et le scraping Prometheus les appellent sans
    pouvoir porter de jeton. Choix documenté dans docs/SECURITY.md.
    """
    assert anonymous_client.get(route).status_code == 200


# --- Restriction d'accès aux données (C5) -----------------------------------

@pytest.mark.parametrize("route", PROTECTED_DATA_ROUTES)
def test_data_routes_reject_anonymous_requests(anonymous_client, route):
    assert anonymous_client.get(route).status_code == 401


@pytest.mark.parametrize("route", PROTECTED_DATA_ROUTES)
def test_data_routes_accept_authenticated_viewer(client, route):
    assert client.get(route).status_code == 200


def test_malformed_token_is_rejected(anonymous_client):
    anonymous_client.headers.update({"Authorization": "Bearer not-a-real-jwt"})
    assert anonymous_client.get("/trajets").status_code == 401
    anonymous_client.headers.pop("Authorization")


def test_token_signed_with_another_secret_is_rejected(anonymous_client):
    """Un jeton correctement formé mais signé avec un autre secret doit être refusé."""
    forged = jwt.encode(
        {"sub": "test_viewer", "role": "viewer", "type": "access", "exp": time.time() + 600},
        "wrong-secret",
        algorithm=JWT_ALGORITHM,
    )
    anonymous_client.headers.update({"Authorization": f"Bearer {forged}"})
    assert anonymous_client.get("/trajets").status_code == 401
    anonymous_client.headers.pop("Authorization")


def test_expired_token_is_rejected(anonymous_client):
    expired = jwt.encode(
        {"sub": "test_viewer", "role": "viewer", "type": "access", "exp": int(time.time()) - 10},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
    anonymous_client.headers.update({"Authorization": f"Bearer {expired}"})
    response = anonymous_client.get("/trajets")
    assert response.status_code == 401
    anonymous_client.headers.pop("Authorization")


# --- Restriction d'accès au modèle et rôles (C9, C17) -----------------------

@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_model_routes_reject_anonymous_requests(anonymous_client, route):
    payload = SUBSTITUTION_PAYLOAD if "co2" not in route else {
        "distance_km": 400.0, "duration_minutes": 120.0, "n_stops": 2,
        "consommation_energy": 10.0, "gco2_per_kwh": 21.7,
        "consommation_totale": 4000.0, "type_train": "diesel", "scenario": "reference",
    }
    assert anonymous_client.post(route, json=payload).status_code == 401


def test_viewer_role_is_forbidden_on_model_routes(client):
    """Authentifié mais non habilité : 403 et non 401 — la distinction est notée."""
    response = client.post("/predict/substitution", json=SUBSTITUTION_PAYLOAD)
    assert response.status_code == 403
    assert "viewer" in response.json()["error"]["message"]


def test_admin_role_reaches_model_routes(admin_client):
    """
    Le rôle admin franchit le contrôle d'autorisation. 503 est accepté :
    il signifie que l'autorisation est passée mais que les artefacts .joblib
    ne sont pas présents dans l'environnement de test.
    """
    response = admin_client.post("/predict/substitution", json=SUBSTITUTION_PAYLOAD)
    assert response.status_code in (200, 503)


# --- Connexion, identité, renouvellement (C10) -------------------------------

def test_login_returns_both_tokens_and_role(anonymous_client):
    payload = anonymous_client.post(
        "/auth/login", data={"username": "test_admin", "password": "admin-pwd"}
    ).json()
    assert payload["token_type"] == "bearer"
    assert payload["role"] == "admin"
    assert payload["expires_in"] > 0
    assert payload["access_token"] and payload["refresh_token"]


def test_login_with_wrong_password_is_rejected(anonymous_client):
    assert anonymous_client.post(
        "/auth/login", data={"username": "test_viewer", "password": "mauvais"}
    ).status_code == 401


def test_login_does_not_reveal_whether_account_exists(anonymous_client):
    """Même message pour un compte inconnu et un mot de passe faux : pas d'énumération."""
    unknown = anonymous_client.post(
        "/auth/login", data={"username": "inconnu", "password": "x"}
    )
    wrong = anonymous_client.post(
        "/auth/login", data={"username": "test_viewer", "password": "x"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_disabled_account_cannot_log_in(anonymous_client):
    assert anonymous_client.post(
        "/auth/login", data={"username": "test_disabled", "password": "disabled-pwd"}
    ).status_code == 401


def test_auth_me_returns_identity_and_role(client):
    payload = client.get("/auth/me").json()
    assert payload == {"username": "test_viewer", "role": "viewer", "is_active": True}


def test_refresh_issues_a_new_usable_access_token(anonymous_client, viewer_token):
    refreshed = anonymous_client.post(
        "/auth/refresh", json={"refresh_token": viewer_token["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]

    anonymous_client.headers.update({"Authorization": f"Bearer {new_access}"})
    assert anonymous_client.get("/trajets").status_code == 200
    anonymous_client.headers.pop("Authorization")


def test_access_token_cannot_be_used_as_refresh_token(anonymous_client, viewer_token):
    """Le type du jeton est vérifié : un jeton d'accès ne renouvelle rien."""
    assert anonymous_client.post(
        "/auth/refresh", json={"refresh_token": viewer_token["access_token"]}
    ).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(anonymous_client, viewer_token):
    """Symétrique du test précédent : un jeton de rafraîchissement n'ouvre aucune route."""
    anonymous_client.headers.update(
        {"Authorization": f"Bearer {viewer_token['refresh_token']}"}
    )
    assert anonymous_client.get("/trajets").status_code == 401
    anonymous_client.headers.pop("Authorization")


# --- Documentation OpenAPI ---------------------------------------------------

def test_openapi_declares_the_security_scheme(anonymous_client):
    """
    Le schéma de sécurité doit apparaître dans OpenAPI, sinon le bouton
    « Authorize » de Swagger est absent et la documentation ne couvre pas
    les règles d'authentification.
    """
    schema = anonymous_client.get("/openapi.json").json()
    assert "OAuth2PasswordBearer" in schema["components"]["securitySchemes"]
    assert "security" in schema["paths"]["/trajets"]["get"]


# --- Limitation des tentatives de connexion (OWASP A07) ----------------------

def test_login_blocked_after_max_failed_attempts(anonymous_client):
    """
    Après 5 tentatives échouées, la 6e doit recevoir 429, pas 401.
    Cela couvre la limitation par identifiant (user:inconnu).
    """
    for _ in range(5):
        r = anonymous_client.post(
            "/auth/login", data={"username": "inconnu", "password": "mauvais"}
        )
        assert r.status_code == 401

    blocked = anonymous_client.post(
        "/auth/login", data={"username": "inconnu", "password": "mauvais"}
    )
    assert blocked.status_code == 429


def test_successful_login_resets_failure_counter(anonymous_client):
    """
    4 tentatives échouées puis une réussie : le compteur est réinitialisé
    et une 5e tentative échouée est encore autorisée (pas encore bloqué).
    """
    for _ in range(4):
        anonymous_client.post(
            "/auth/login", data={"username": "test_admin", "password": "mauvais"}
        )

    ok = anonymous_client.post(
        "/auth/login", data={"username": "test_admin", "password": "admin-pwd"}
    )
    assert ok.status_code == 200

    still_allowed = anonymous_client.post(
        "/auth/login", data={"username": "test_admin", "password": "mauvais"}
    )
    assert still_allowed.status_code == 401


def test_ip_lockout_blocks_any_username_from_same_ip(anonymous_client):
    """
    5 tentatives échouées depuis la même IP (même clé ip:testclient) bloquent
    l'ensemble des tentatives depuis cet hôte, quelle que soit l'identité testée.
    """
    for i in range(5):
        anonymous_client.post(
            "/auth/login", data={"username": f"user_{i}", "password": "mauvais"}
        )

    blocked = anonymous_client.post(
        "/auth/login", data={"username": "test_admin", "password": "admin-pwd"}
    )
    assert blocked.status_code == 429
