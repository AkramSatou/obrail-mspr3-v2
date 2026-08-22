"""
SQLAlchemy ORM models for ObRail Europe.

Defines the Trip model representing a single rail journey with its
geographic, operational, and CO2 emission attributes.
"""

from sqlalchemy import Boolean, Column, Float, Integer, String

from app.database import Base


class Trip(Base):
    """One rail journey between an origin stop and a destination stop."""

    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String, unique=True, index=True, nullable=False)
    route_id = Column(String, nullable=True)
    route_long_name = Column(String, nullable=True)
    route_type = Column(Integer, nullable=False)
    service_id = Column(String, nullable=False)
    country = Column(String(2), index=True, nullable=False)

    origin_stop_id = Column(String, nullable=False)
    origin_stop_name = Column(String, nullable=False)
    origin_stop_lat = Column(Float, nullable=False)
    origin_stop_lon = Column(Float, nullable=False)

    destination_stop_id = Column(String, nullable=False)
    destination_stop_name = Column(String, nullable=False)
    destination_stop_lat = Column(Float, nullable=False)
    destination_stop_lon = Column(Float, nullable=False)

    departure_minutes = Column(Float, nullable=False)
    arrival_minutes = Column(Float, nullable=False)
    duration_minutes = Column(Float, nullable=False)
    n_stops = Column(Float, nullable=False)
    distance_km = Column(Float, nullable=False)

    type_train = Column(String, index=True, nullable=False)
    consommation_energy = Column(Float, nullable=False)
    gco2_per_kwh = Column(Float, nullable=False)
    consommation_totale = Column(Float, nullable=False)
    co2_estime = Column(Float, nullable=False)


class User(Base):
    """
    Compte applicatif autorisé à interroger l'API.

    Le mot de passe n'est jamais stocké en clair : seule son empreinte bcrypt
    est conservée dans `hashed_password`.

    Rôles :
        viewer — consultation des données ferroviaires
        admin  — consultation + appel des modèles d'inférence (/predict/*)
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")
    is_active = Column(Boolean, nullable=False, default=True)
