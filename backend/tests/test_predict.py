"""
Tests for POST /predict, POST /predict/substitution, and POST /predict/co2.

Each route is covered by:
- valid admin request → 200, response shape checked (fields present, correct types)
- no token → 401
- viewer token → 403
- invalid payload (missing or wrong-typed field) → 422

Models and encoders are mocked so the suite runs without model artefacts on disk.
Authentication follows require_role(ROLE_ADMIN) as defined in security.py.
"""

from unittest.mock import MagicMock, patch
import numpy as np


# ---------------------------------------------------------------------------
# Reference payloads
# ---------------------------------------------------------------------------

SUBSTITUTION_VALID_PAYLOAD = {
    "distance_km": 800.0,
    "duration_minutes": 240.0,
    "n_stops": 2,
    "co2_estime": 350000.0,
    "consommation_totale": 12000.0,
    "type_train": "electric",
    "country": "FR",
}

CO2_VALID_PAYLOAD = {
    "distance_km": 400.0,
    "duration_minutes": 120.0,
    "n_stops": 2,
    "consommation_energy": 10.0,
    "gco2_per_kwh": 21.7,
    "consommation_totale": 4000.0,
    "type_train": "diesel",
    "scenario": "reference",
}


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _mock_substitution_model():
    """XGBClassifier mock: predicts class 1 with probability 0.85."""
    model = MagicMock()
    model.predict.return_value = np.array([1])
    model.predict_proba.return_value = np.array([[0.15, 0.85]])
    return model


def _mock_co2_model():
    """Sklearn pipeline mock: predicts 104.34 kgCO2."""
    model = MagicMock()
    model.predict.return_value = np.array([104.34])
    return model


def _mock_encoders():
    """LabelEncoder mock for type_train and country."""
    enc = MagicMock()
    enc.transform.return_value = np.array([0])
    return {"le_type_train": enc, "le_country": enc}


# ---------------------------------------------------------------------------
# POST /predict  (compat v1 — same logic as /predict/substitution)
# ---------------------------------------------------------------------------

def test_predict_compat_valid_admin_returns_substitution_shape(admin_client):
    with (
        patch("app.main._substitution_ok", True),
        patch("app.main._model_substitution", _mock_substitution_model()),
        patch("app.main._encoders", _mock_encoders()),
    ):
        response = admin_client.post("/predict", json=SUBSTITUTION_VALID_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"substitution_avion", "probabilite", "label"}
    assert isinstance(body["substitution_avion"], int)
    assert body["substitution_avion"] in {0, 1}
    assert isinstance(body["probabilite"], float)
    assert 0.0 <= body["probabilite"] <= 1.0
    assert isinstance(body["label"], str)
    assert body["label"]


def test_predict_compat_no_token_returns_401(anonymous_client):
    response = anonymous_client.post("/predict", json=SUBSTITUTION_VALID_PAYLOAD)

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["status_code"] == 401
    assert error["path"] == "/predict"


def test_predict_compat_viewer_returns_403(client):
    response = client.post("/predict", json=SUBSTITUTION_VALID_PAYLOAD)

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["status_code"] == 403
    assert error["path"] == "/predict"


def test_predict_compat_missing_field_returns_422(admin_client):
    payload = {k: v for k, v in SUBSTITUTION_VALID_PAYLOAD.items() if k != "distance_km"}
    response = admin_client.post("/predict", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["status_code"] == 422
    assert error["details"]


# ---------------------------------------------------------------------------
# POST /predict/substitution
# ---------------------------------------------------------------------------

def test_predict_substitution_valid_admin_returns_substitution_shape(admin_client):
    with (
        patch("app.main._substitution_ok", True),
        patch("app.main._model_substitution", _mock_substitution_model()),
        patch("app.main._encoders", _mock_encoders()),
    ):
        response = admin_client.post("/predict/substitution", json=SUBSTITUTION_VALID_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"substitution_avion", "probabilite", "label"}
    assert isinstance(body["substitution_avion"], int)
    assert body["substitution_avion"] in {0, 1}
    assert isinstance(body["probabilite"], float)
    assert 0.0 <= body["probabilite"] <= 1.0
    assert isinstance(body["label"], str)
    assert body["label"]


def test_predict_substitution_no_token_returns_401(anonymous_client):
    response = anonymous_client.post("/predict/substitution", json=SUBSTITUTION_VALID_PAYLOAD)

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["status_code"] == 401
    assert error["path"] == "/predict/substitution"


def test_predict_substitution_viewer_returns_403(client):
    response = client.post("/predict/substitution", json=SUBSTITUTION_VALID_PAYLOAD)

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["status_code"] == 403
    assert error["path"] == "/predict/substitution"


def test_predict_substitution_missing_field_returns_422(admin_client):
    payload = {k: v for k, v in SUBSTITUTION_VALID_PAYLOAD.items() if k != "country"}
    response = admin_client.post("/predict/substitution", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["status_code"] == 422
    assert error["details"]


def test_predict_substitution_wrong_type_returns_422(admin_client):
    payload = {**SUBSTITUTION_VALID_PAYLOAD, "n_stops": "pas_un_entier"}
    response = admin_client.post("/predict/substitution", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["status_code"] == 422


# ---------------------------------------------------------------------------
# POST /predict/co2
# ---------------------------------------------------------------------------

def test_predict_co2_valid_admin_returns_co2_shape(admin_client):
    with (
        patch("app.main._co2_ok", True),
        patch("app.main._model_co2", _mock_co2_model()),
    ):
        response = admin_client.post("/predict/co2", json=CO2_VALID_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"scenario", "co2_estime_kg", "label"}
    assert isinstance(body["scenario"], str)
    assert body["scenario"] == CO2_VALID_PAYLOAD["scenario"]
    assert isinstance(body["co2_estime_kg"], float)
    assert body["co2_estime_kg"] >= 0.0
    assert isinstance(body["label"], str)
    assert body["label"]


def test_predict_co2_no_token_returns_401(anonymous_client):
    response = anonymous_client.post("/predict/co2", json=CO2_VALID_PAYLOAD)

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["status_code"] == 401
    assert error["path"] == "/predict/co2"


def test_predict_co2_viewer_returns_403(client):
    response = client.post("/predict/co2", json=CO2_VALID_PAYLOAD)

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["status_code"] == 403
    assert error["path"] == "/predict/co2"


def test_predict_co2_missing_field_returns_422(admin_client):
    payload = {k: v for k, v in CO2_VALID_PAYLOAD.items() if k != "scenario"}
    response = admin_client.post("/predict/co2", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["status_code"] == 422
    assert error["details"]


def test_predict_co2_wrong_type_returns_422(admin_client):
    payload = {**CO2_VALID_PAYLOAD, "distance_km": "pas_un_nombre"}
    response = admin_client.post("/predict/co2", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["status_code"] == 422


def test_predict_co2_unknown_scenario_returns_422(admin_client):
    payload = {**CO2_VALID_PAYLOAD, "scenario": "scenario_inconnu"}
    with (
        patch("app.main._co2_ok", True),
        patch("app.main._model_co2", _mock_co2_model()),
    ):
        response = admin_client.post("/predict/co2", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "HTTP_422"
    assert "scenario_inconnu" in error["message"]
