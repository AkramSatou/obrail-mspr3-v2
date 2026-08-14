"""
C12 — étapes de préparation des données.

Partie visée   : encodeurs ordinaux et StandardScaler, entre les données brutes
                 et le modèle de classification.
Périmètre      : classes encodées, ordre des variables, effet réel du centrage-réduction.
Stratégie      : figer le contrat réel, établi par mesure sur les artefacts livrés.
                 Le classifieur est un XGBClassifier entraîné sur des variables
                 BRUTES ; le StandardScaler n'a servi qu'à la régression logistique
                 de comparaison (rapport TPRE622, section 5.3.3). Voir l'incident 002.
"""

import numpy as np

from validation.schema import CLASSIFICATION_FEATURE_ORDER


def test_les_encodeurs_exposent_les_classes_attendues(encoders):
    assert list(encoders["le_type_train"].classes_) == ["diesel", "electric"]
    assert list(encoders["le_country"].classes_) == ["DE", "ES", "FR", "IT"]


def test_l_encodage_est_deterministe(encoders):
    valeurs = ["electric", "diesel", "electric"]
    premier = encoders["le_type_train"].transform(valeurs)
    second = encoders["le_type_train"].transform(valeurs)
    assert np.array_equal(premier, second)


def test_le_scaler_attend_exactement_les_sept_variables_du_contrat(scaler):
    assert scaler.n_features_in_ == len(CLASSIFICATION_FEATURE_ORDER) == 7


def test_le_scaler_centre_et_reduit_reellement(scaler, features_and_target):
    """
    Le scaler fonctionne correctement — ce n'est pas lui le problème, c'est son
    usage à l'inférence sur un modèle qui ne l'attend pas.
    """
    X, _ = features_and_target
    transforme = scaler.transform(X)

    assert np.abs(transforme.mean(axis=0)).max() < 0.5
    assert np.abs(transforme.std(axis=0) - 1.0).max() < 1.0


def test_standardiser_a_l_inference_annule_la_detection(scaler, classifier, features_and_target):
    """
    Incident 002. Standardiser avant de prédire fait tomber le nombre de liaisons
    détectées comme substituables à zéro, alors que la référence en attend ~8 %.
    Aucune exception n'est levée : la dégradation est totalement silencieuse.
    """
    X, y = features_and_target

    brut = classifier.predict(X)
    standardise = classifier.predict(scaler.transform(X))

    assert brut.mean() > 0.05, "le chemin brut ne détecte plus de liaisons substituables"
    assert standardise.mean() == 0.0, (
        "le comportement du chemin standardisé a changé : revoir l'incident 002"
    )
    assert float(y.mean()) > 0.05


def test_l_ordre_des_variables_est_fige(features_and_target):
    """
    Le modèle consomme un tableau positionnel : permuter deux colonnes ne lève
    aucune erreur mais fausse toutes les prédictions. L'ordre est donc figé ici.
    """
    X, _ = features_and_target
    assert list(X.columns) == CLASSIFICATION_FEATURE_ORDER


def test_permuter_deux_variables_degrade_les_predictions(classifier, features_and_target):
    """Démontre le risque ci-dessus : l'inversion passe silencieusement mais casse tout."""
    X, _ = features_and_target
    permute = X.copy()
    permute[["distance_km", "duration_minutes"]] = X[
        ["duration_minutes", "distance_km"]
    ].to_numpy()

    reference = classifier.predict(X)
    inverse = classifier.predict(permute)

    assert not np.array_equal(reference, inverse), (
        "permuter distance et durée ne change rien : le modèle n'utilise pas ces variables"
    )
