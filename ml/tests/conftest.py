"""
Fixtures partagées des tests du pipeline de modélisation.

Le jeu de données complet compte 142 420 lignes : les tests travaillent sur un
échantillon aléatoire à graine fixe, ce qui garde la chaîne d'intégration
continue rapide tout en restant représentatif.
"""

import os
import sys
from pathlib import Path
import warnings

import joblib
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ml"))

from validation import thresholds  # noqa: E402
from validation.schema import build_substitution_target  # noqa: E402

DATASET_PATH = Path(os.getenv("OBRAIL_DATASET_PATH", REPO_ROOT / "data" / "eu_trips_v2.csv"))
MODELS_DIR = Path(os.getenv("OBRAIL_MODELS_PATH", REPO_ROOT / "models"))

# Les artefacts ont été entraînés avec une version de scikit-learn différente de
# celle épinglée ici : le chargement émet un InconsistentVersionWarning connu et
# documenté comme limite dans le rapport technique. On le neutralise pour ne pas
# noyer la sortie des tests, sans masquer les vraies erreurs.
warnings.filterwarnings("ignore", message=".*InconsistentVersion.*")


@pytest.fixture(scope="session")
def dataset() -> pd.DataFrame:
    if not DATASET_PATH.exists():
        pytest.skip(f"Jeu de données absent : {DATASET_PATH}")
    return pd.read_csv(DATASET_PATH, low_memory=False)


@pytest.fixture(scope="session")
def sample(dataset) -> pd.DataFrame:
    size = min(thresholds.SAMPLE_SIZE, len(dataset))
    return dataset.sample(n=size, random_state=thresholds.RANDOM_SEED).reset_index(drop=True)


@pytest.fixture(scope="session")
def encoders():
    path = MODELS_DIR / "encoders.joblib"
    if not path.exists():
        pytest.skip(f"Artefact absent : {path}")
    return joblib.load(path)


@pytest.fixture(scope="session")
def scaler():
    path = MODELS_DIR / "scaler.joblib"
    if not path.exists():
        pytest.skip(f"Artefact absent : {path}")
    return joblib.load(path)


@pytest.fixture(scope="session")
def classifier():
    path = MODELS_DIR / "classification_substitution_avion.joblib"
    if not path.exists():
        pytest.skip(f"Artefact absent : {path}")
    return joblib.load(path)


@pytest.fixture(scope="session")
def regressor():
    path = MODELS_DIR / "regression_co2.joblib"
    if not path.exists():
        pytest.skip(f"Artefact absent : {path}")
    return joblib.load(path)


@pytest.fixture(scope="session")
def features_and_target(sample, encoders):
    """
    Reproduit exactement la préparation appliquée à l'entraînement :
    encodage ordinal des deux variables catégorielles, puis sélection des
    7 variables dans l'ordre attendu par le scaler et le modèle.
    """
    df = sample.copy()
    # Les noms de colonnes sont conservés : le scaler et le booster les attendent
    # tels quels, seules les valeurs passent de texte à entier.
    df["type_train"] = encoders["le_type_train"].transform(df["type_train"])
    df["country"] = encoders["le_country"].transform(df["country"])

    from validation.schema import CLASSIFICATION_FEATURE_ORDER

    X = df[CLASSIFICATION_FEATURE_ORDER]
    y = build_substitution_target(df)
    return X, y
