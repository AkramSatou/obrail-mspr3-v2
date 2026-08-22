"""
schema.py — règles de validation du jeu de données ObRail Europe.

Ces règles constituent le contrat que tout jeu de données doit respecter avant
d'entrer dans le pipeline d'entraînement. Elles sont exécutées automatiquement
par la chaîne d'intégration continue (job `model`), avant toute étape
d'entraînement ou d'évaluation.

Le principe : un jeu de données invalide doit faire échouer la chaîne
immédiatement, plutôt que de produire silencieusement un modèle dégradé.
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# Colonnes indispensables au pipeline de modélisation.
REQUIRED_COLUMNS = [
    "trip_id",
    "country",
    "type_train",
    "distance_km",
    "duration_minutes",
    "n_stops",
    "consommation_energy",
    "gco2_per_kwh",
    "consommation_totale",
    "co2_estime",
]

# Ordre exact des variables attendu par le modèle de classification et par le
# StandardScaler associé. Toute divergence fausse les prédictions en silence :
# c'est l'incident du StandardScaler rencontré lors de la MSPR 3.
# Vérifié sur les artefacts livrés : scaler.feature_names_in_ et les noms du
# booster XGBoost conservent les noms d'origine `type_train` et `country`, mais
# attendent des valeurs déjà encodées en entiers par les LabelEncoder.
CLASSIFICATION_FEATURE_ORDER = [
    "distance_km",
    "duration_minutes",
    "n_stops",
    "co2_estime",
    "consommation_totale",
    "type_train",
    "country",
]

EXPECTED_COUNTRIES = {"DE", "ES", "FR", "IT"}
EXPECTED_TRAIN_TYPES = {"diesel", "electric"}

# Règles métier de construction de la variable cible de classification,
# issues des études Transport & Environment et Back-on-Track.
SUBSTITUTION_MIN_DISTANCE_KM = 300.0
SUBSTITUTION_MAX_DISTANCE_KM = 1500.0
SUBSTITUTION_MAX_DURATION_MIN = 480.0


@dataclass
class ColumnRule:
    """Contrainte appliquée à une colonne numérique."""

    name: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    max_null_ratio: float = 0.0


NUMERIC_RULES = [
    ColumnRule("distance_km", minimum=0.0),
    ColumnRule("duration_minutes", minimum=0.0),
    ColumnRule("n_stops", minimum=0.0),
    ColumnRule("consommation_energy", minimum=0.0),
    ColumnRule("gco2_per_kwh", minimum=0.0),
    ColumnRule("consommation_totale", minimum=0.0),
    ColumnRule("co2_estime", minimum=0.0),
]


@dataclass
class ValidationReport:
    """Résultat d'une validation : la liste des écarts constatés."""

    errors: list = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        if self.is_valid:
            return "Jeu de données conforme."
        return "Jeu de données non conforme :\n  - " + "\n  - ".join(self.errors)


def validate_dataset(df: pd.DataFrame) -> ValidationReport:
    """Applique l'ensemble des règles et retourne un rapport d'écarts."""
    report = ValidationReport()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        report.errors.append(f"colonnes manquantes : {missing}")
        return report  # inutile de poursuivre sans les colonnes

    for rule in NUMERIC_RULES:
        serie = df[rule.name]
        if not pd.api.types.is_numeric_dtype(serie):
            report.errors.append(f"{rule.name} : type non numérique ({serie.dtype})")
            continue

        null_ratio = float(serie.isna().mean())
        if null_ratio > rule.max_null_ratio:
            report.errors.append(
                f"{rule.name} : {null_ratio:.1%} de valeurs manquantes "
                f"(maximum toléré {rule.max_null_ratio:.1%})"
            )

        if rule.minimum is not None and (serie.dropna() < rule.minimum).any():
            report.errors.append(f"{rule.name} : valeurs inférieures à {rule.minimum}")

        if rule.maximum is not None and (serie.dropna() > rule.maximum).any():
            report.errors.append(f"{rule.name} : valeurs supérieures à {rule.maximum}")

    unknown_countries = set(df["country"].dropna().unique()) - EXPECTED_COUNTRIES
    if unknown_countries:
        report.errors.append(f"pays inattendus : {sorted(unknown_countries)}")

    unknown_types = set(df["type_train"].dropna().unique()) - EXPECTED_TRAIN_TYPES
    if unknown_types:
        report.errors.append(f"types de traction inattendus : {sorted(unknown_types)}")

    duplicated = int(df["trip_id"].duplicated().sum())
    if duplicated:
        report.errors.append(f"{duplicated} trip_id en doublon")

    return report


def build_substitution_target(df: pd.DataFrame) -> pd.Series:
    """
    Reconstruit la variable cible de classification à partir des règles métier.

    Cette fonction est la source unique de vérité : les tests l'utilisent pour
    vérifier que le modèle livré prédit bien ce que la règle définit.
    """
    return (
        df["distance_km"].between(SUBSTITUTION_MIN_DISTANCE_KM, SUBSTITUTION_MAX_DISTANCE_KM)
        & (df["duration_minutes"] < SUBSTITUTION_MAX_DURATION_MIN)
    ).astype(int)
