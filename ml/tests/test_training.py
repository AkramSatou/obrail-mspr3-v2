"""
C12 — étape d'entraînement.

Partie visée   : la procédure d'entraînement du classifieur, indépendamment de
                 l'artefact livré.
Périmètre      : reproductibilité à graine fixe, capacité d'apprentissage, absence
                 de fuite de données entre entraînement et évaluation.
Stratégie      : réentraîner un modèle réduit sur un échantillon et vérifier qu'il
                 atteint un niveau plancher. Un pipeline cassé produit un modèle
                 incapable d'apprendre, ce que ce test détecte.
"""

import numpy as np
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from validation import thresholds


def _entrainer(X, y, seed):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y
    )
    modele = XGBClassifier(
        n_estimators=60,
        max_depth=4,
        learning_rate=0.2,
        random_state=seed,
        n_jobs=2,
        eval_metric="logloss",
    )
    modele.fit(X_train, y_train)
    return modele, X_test, y_test


def test_le_pipeline_d_entrainement_produit_un_modele_qui_apprend(features_and_target):
    X, y = features_and_target
    modele, X_test, y_test = _entrainer(X, y, thresholds.RANDOM_SEED)

    score = f1_score(y_test, modele.predict(X_test), average="macro")
    assert score >= thresholds.MIN_F1_MACRO, (
        f"F1-macro {score:.4f} sous le seuil {thresholds.MIN_F1_MACRO}"
    )


def test_l_entrainement_est_reproductible_a_graine_fixe(features_and_target):
    X, y = features_and_target
    premier, X_test, _ = _entrainer(X, y, thresholds.RANDOM_SEED)
    second, _, _ = _entrainer(X, y, thresholds.RANDOM_SEED)

    assert np.array_equal(premier.predict(X_test), second.predict(X_test)), (
        "deux entraînements à graine identique divergent : le pipeline n'est pas reproductible"
    )


def test_le_jeu_d_evaluation_n_est_pas_vu_pendant_l_entrainement(features_and_target):
    """Garde-fou contre la fuite de données : les deux partitions sont disjointes."""
    X, y = features_and_target
    X_train, X_test, _, _ = train_test_split(
        X, y, test_size=0.2, random_state=thresholds.RANDOM_SEED, stratify=y
    )
    assert set(X_train.index).isdisjoint(set(X_test.index))
    assert len(X_train) + len(X_test) == len(X)
