"""
C12 — règles de validation des jeux de données.

Partie visée   : les données en entrée du pipeline, avant toute préparation.
Périmètre      : schéma, types, plages de valeurs, complétude, unicité, cardinalités.
Stratégie      : contrat exécutable. Toute violation fait échouer la chaîne avant
                 l'entraînement, plutôt que de produire un modèle dégradé en silence.
"""

import pandas as pd
import pytest

from validation import thresholds
from validation.schema import (
    EXPECTED_COUNTRIES,
    EXPECTED_TRAIN_TYPES,
    REQUIRED_COLUMNS,
    build_substitution_target,
    validate_dataset,
)


def test_le_jeu_de_donnees_respecte_le_contrat(dataset):
    report = validate_dataset(dataset)
    assert report.is_valid, str(report)


def test_toutes_les_colonnes_requises_sont_presentes(dataset):
    manquantes = [c for c in REQUIRED_COLUMNS if c not in dataset.columns]
    assert manquantes == [], f"colonnes manquantes : {manquantes}"


def test_les_identifiants_de_trajet_sont_uniques(dataset):
    doublons = int(dataset["trip_id"].duplicated().sum())
    assert doublons == 0, f"{doublons} trip_id en doublon"


def test_les_cardinalites_categorielles_sont_celles_attendues(dataset):
    assert set(dataset["country"].unique()) <= EXPECTED_COUNTRIES
    assert set(dataset["type_train"].unique()) <= EXPECTED_TRAIN_TYPES


def test_aucune_valeur_manquante_sur_les_variables_de_modelisation(dataset):
    colonnes = [c for c in REQUIRED_COLUMNS if c != "trip_id"]
    taux = dataset[colonnes].isna().mean()
    fautives = taux[taux > 0]
    assert fautives.empty, f"valeurs manquantes : {fautives.to_dict()}"


def test_route_long_name_reste_sous_le_seuil_de_completude_tolere(dataset):
    """
    Colonne connue comme incomplète (~44 %), exclue de la modélisation.
    Le test borne la dégradation : au-delà du seuil, la source a changé.
    """
    if "route_long_name" not in dataset.columns:
        pytest.skip("colonne absente")
    taux = float(dataset["route_long_name"].isna().mean())
    assert taux <= thresholds.MAX_ROUTE_LONG_NAME_NULL_RATIO, (
        f"{taux:.1%} de valeurs manquantes, au-delà du seuil toléré"
    )


def test_un_jeu_de_donnees_corrompu_est_bien_rejete():
    """Vérifie que le contrat détecte réellement une anomalie — test du test."""
    corrompu = pd.DataFrame(
        {
            "trip_id": ["A", "A"],           # doublon
            "country": ["FR", "XX"],          # pays inconnu
            "type_train": ["electric", "vapeur"],  # traction inconnue
            "distance_km": [-10.0, 100.0],    # distance négative
            "duration_minutes": [60.0, 90.0],
            "n_stops": [1.0, 2.0],
            "consommation_energy": [10.0, 10.0],
            "gco2_per_kwh": [50.0, 50.0],
            "consommation_totale": [1000.0, 1000.0],
            "co2_estime": [50000.0, 50000.0],
        }
    )
    report = validate_dataset(corrompu)
    assert not report.is_valid
    assert len(report.errors) >= 4


def test_la_regle_metier_de_la_cible_est_reproductible(dataset):
    """
    La cible est construite par règles (300-1500 km et moins de 8 h).
    Ce test fige la règle : la modifier sans le vouloir casse la chaîne.
    """
    y = build_substitution_target(dataset)
    taux = float(y.mean())
    assert 0.05 <= taux <= 0.15, (
        f"proportion de liaisons substituables inattendue : {taux:.1%} "
        "(référence documentée : 8,4 %)"
    )
