"""
Pytest fixtures for ObRail Europe backend tests.

Provides an in-memory SQLite database (via SQLAlchemy) seeded with 10
representative rows (FR/DE, electric/diesel), and a FastAPI TestClient
wired to use that database instead of the real PostgreSQL instance.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# backend/app/* uses absolute imports like "from app.database import Base" (matches
# the Docker image layout where WORKDIR=/app and backend/app is copied to /app/app).
# Put backend/ on sys.path so that "app.*" resolves the same way pytest-side as it
# does inside the container, and import everything through that single "app.*"
# namespace so there is only one FastAPI app / one Base.metadata in the process
# (importing both "backend.app.main" and "app.main" would load the module twice
# under two different names and register the SQLAlchemy "trips" table twice).
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_TESTS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault("DATABASE_URL", "postgresql://obrail:obrail@localhost:5432/obrail")
# Secret de signature dédié aux tests — indépendant de celui de production.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

from app.database import Base, get_db
from app.models import Trip, User
from app.security import ROLE_ADMIN, ROLE_VIEWER, hash_password
from app.main import app, login_rate_limiter

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


SAMPLE_TRIPS = [
    dict(
        trip_id="T1", route_id="R1", route_long_name="Paris - Lyon", route_type=2,
        service_id="S1", country="FR",
        origin_stop_id="P1", origin_stop_name="Paris Gare de Lyon", origin_stop_lat=48.844, origin_stop_lon=2.374,
        destination_stop_id="P2", destination_stop_name="Lyon Part-Dieu", destination_stop_lat=45.760, destination_stop_lon=4.859,
        departure_minutes=480.0, arrival_minutes=600.0, duration_minutes=120.0, n_stops=1.0, distance_km=460.0,
        type_train="electric", consommation_energy=10.0, gco2_per_kwh=50.0, consommation_totale=4600.0, co2_estime=230000.0,
    ),
    dict(
        trip_id="T2", route_id="R2", route_long_name="Lyon - Dijon", route_type=2,
        service_id="S1", country="FR",
        origin_stop_id="P2", origin_stop_name="Lyon Part-Dieu", origin_stop_lat=45.760, origin_stop_lon=4.859,
        destination_stop_id="P3", destination_stop_name="Dijon Ville", destination_stop_lat=47.321, destination_stop_lon=5.024,
        departure_minutes=620.0, arrival_minutes=700.0, duration_minutes=80.0, n_stops=0.0, distance_km=180.0,
        type_train="electric", consommation_energy=9.0, gco2_per_kwh=50.0, consommation_totale=1620.0, co2_estime=81000.0,
    ),
    dict(
        trip_id="T3", route_id="R3", route_long_name="Dijon - Strasbourg", route_type=2,
        service_id="S2", country="FR",
        origin_stop_id="P3", origin_stop_name="Dijon Ville", origin_stop_lat=47.321, origin_stop_lon=5.024,
        destination_stop_id="P4", destination_stop_name="Strasbourg", destination_stop_lat=48.585, destination_stop_lon=7.734,
        departure_minutes=720.0, arrival_minutes=840.0, duration_minutes=120.0, n_stops=2.0, distance_km=335.0,
        type_train="diesel", consommation_energy=20.0, gco2_per_kwh=300.0, consommation_totale=6700.0, co2_estime=2010000.0,
    ),
    dict(
        trip_id="T4", route_id="R4", route_long_name="Paris - Bordeaux", route_type=2,
        service_id="S2", country="FR",
        origin_stop_id="P5", origin_stop_name="Paris Montparnasse", origin_stop_lat=48.840, origin_stop_lon=2.319,
        destination_stop_id="P6", destination_stop_name="Bordeaux Saint-Jean", destination_stop_lat=44.826, destination_stop_lon=-0.556,
        departure_minutes=540.0, arrival_minutes=720.0, duration_minutes=180.0, n_stops=1.0, distance_km=500.0,
        type_train="electric", consommation_energy=10.5, gco2_per_kwh=50.0, consommation_totale=5250.0, co2_estime=262500.0,
    ),
    dict(
        trip_id="T5", route_id="R5", route_long_name="Toulouse - Bordeaux", route_type=2,
        service_id="S3", country="FR",
        origin_stop_id="P7", origin_stop_name="Toulouse Matabiau", origin_stop_lat=43.611, origin_stop_lon=1.454,
        destination_stop_id="P6", destination_stop_name="Bordeaux Saint-Jean", destination_stop_lat=44.826, destination_stop_lon=-0.556,
        departure_minutes=300.0, arrival_minutes=420.0, duration_minutes=120.0, n_stops=1.0, distance_km=250.0,
        type_train="diesel", consommation_energy=18.0, gco2_per_kwh=300.0, consommation_totale=4500.0, co2_estime=1350000.0,
    ),
    dict(
        trip_id="T6", route_id="R6", route_long_name="Berlin - Munich", route_type=2,
        service_id="S4", country="DE",
        origin_stop_id="D1", origin_stop_name="Berlin Hbf", origin_stop_lat=52.525, origin_stop_lon=13.369,
        destination_stop_id="D2", destination_stop_name="Munich Hbf", destination_stop_lat=48.140, destination_stop_lon=11.558,
        departure_minutes=400.0, arrival_minutes=640.0, duration_minutes=240.0, n_stops=3.0, distance_km=600.0,
        type_train="electric", consommation_energy=11.0, gco2_per_kwh=400.0, consommation_totale=6600.0, co2_estime=2640000.0,
    ),
    dict(
        trip_id="T7", route_id="R7", route_long_name="Munich - Frankfurt", route_type=2,
        service_id="S4", country="DE",
        origin_stop_id="D2", origin_stop_name="Munich Hbf", origin_stop_lat=48.140, origin_stop_lon=11.558,
        destination_stop_id="D3", destination_stop_name="Frankfurt Hbf", destination_stop_lat=50.107, destination_stop_lon=8.663,
        departure_minutes=660.0, arrival_minutes=900.0, duration_minutes=240.0, n_stops=2.0, distance_km=400.0,
        type_train="electric", consommation_energy=10.0, gco2_per_kwh=400.0, consommation_totale=4000.0, co2_estime=1600000.0,
    ),
    dict(
        trip_id="T8", route_id="R8", route_long_name="Frankfurt - Hamburg", route_type=2,
        service_id="S5", country="DE",
        origin_stop_id="D3", origin_stop_name="Frankfurt Hbf", origin_stop_lat=50.107, origin_stop_lon=8.663,
        destination_stop_id="D4", destination_stop_name="Hamburg Hbf", destination_stop_lat=53.553, destination_stop_lon=10.007,
        departure_minutes=420.0, arrival_minutes=660.0, duration_minutes=240.0, n_stops=2.0, distance_km=490.0,
        type_train="diesel", consommation_energy=19.0, gco2_per_kwh=350.0, consommation_totale=9310.0, co2_estime=3258500.0,
    ),
    dict(
        trip_id="T9", route_id="R9", route_long_name="Hamburg - Cologne", route_type=2,
        service_id="S5", country="DE",
        origin_stop_id="D4", origin_stop_name="Hamburg Hbf", origin_stop_lat=53.553, origin_stop_lon=10.007,
        destination_stop_id="D5", destination_stop_name="Cologne Hbf", destination_stop_lat=50.943, destination_stop_lon=6.959,
        departure_minutes=540.0, arrival_minutes=780.0, duration_minutes=240.0, n_stops=1.0, distance_km=420.0,
        type_train="diesel", consommation_energy=18.5, gco2_per_kwh=350.0, consommation_totale=7770.0, co2_estime=2719500.0,
    ),
    dict(
        trip_id="T10", route_id="R10", route_long_name="Cologne - Berlin", route_type=2,
        service_id="S6", country="DE",
        origin_stop_id="D5", origin_stop_name="Cologne Hbf", origin_stop_lat=50.943, origin_stop_lon=6.959,
        destination_stop_id="D1", destination_stop_name="Berlin Hbf", destination_stop_lat=52.525, destination_stop_lon=13.369,
        departure_minutes=300.0, arrival_minutes=540.0, duration_minutes=240.0, n_stops=2.0, distance_km=575.0,
        type_train="electric", consommation_energy=11.5, gco2_per_kwh=400.0, consommation_totale=6612.5, co2_estime=2645000.0,
    ),
]


# Comptes applicatifs de test : un par rôle, plus un compte désactivé pour
# vérifier que la révocation par is_active=False est bien prise en compte.
TEST_USERS = [
    dict(username="test_viewer", password="viewer-pwd", role=ROLE_VIEWER, is_active=True),
    dict(username="test_admin", password="admin-pwd", role=ROLE_ADMIN, is_active=True),
    dict(username="test_disabled", password="disabled-pwd", role=ROLE_VIEWER, is_active=False),
]


@pytest.fixture(autouse=True)
def reset_login_rate_limiter():
    """Remet le compteur de tentatives à zéro avant chaque test."""
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


@pytest.fixture()
def db_session():
    """Creates the schema, yields a session seeded with 10 sample trips and 3 users, then drops it."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        for row in SAMPLE_TRIPS:
            session.add(Trip(**row))
        for entry in TEST_USERS:
            session.add(
                User(
                    username=entry["username"],
                    hashed_password=hash_password(entry["password"]),
                    role=entry["role"],
                    is_active=entry["is_active"],
                )
            )
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def anonymous_client(db_session):
    """TestClient sans jeton — sert à vérifier que les routes protégées renvoient 401."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def _login(test_client, username, password):
    """Authentifie un compte de test et retourne la charge utile des jetons."""
    response = test_client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def viewer_token(anonymous_client):
    return _login(anonymous_client, "test_viewer", "viewer-pwd")


@pytest.fixture()
def admin_token(anonymous_client):
    return _login(anonymous_client, "test_admin", "admin-pwd")


@pytest.fixture()
def client(anonymous_client, viewer_token):
    """
    Client authentifié avec le rôle viewer — utilisé par défaut par les tests
    de données existants, qui restent ainsi inchangés dans leur logique.
    """
    anonymous_client.headers.update(
        {"Authorization": f"Bearer {viewer_token['access_token']}"}
    )
    yield anonymous_client
    anonymous_client.headers.pop("Authorization", None)


@pytest.fixture()
def admin_client(anonymous_client, admin_token):
    """Client authentifié avec le rôle admin — accès aux routes d'inférence."""
    anonymous_client.headers.update(
        {"Authorization": f"Bearer {admin_token['access_token']}"}
    )
    yield anonymous_client
    anonymous_client.headers.pop("Authorization", None)
