"""
C12 — contrat d'inférence du classifieur : les cas de référence du rapport.

Partie visée   : le chemin d'inférence complet, tel que l'API l'exécute.
Périmètre      : les quatre liaisons documentées dans le rapport TPRE622 section 6.4,
                 plus la vérification que le StandardScaler n'est pas réintroduit.
Stratégie      : test de non-régression par valeur attendue, et non par code HTTP.
                 C'est précisément l'absence de ce type de test qui a laissé passer
                 l'incident 002 : les 12 tests existants vérifiaient que la route
                 répondait 200, jamais ce qu'elle répondait.
"""

import pandas as pd
import pytest
from sklearn.metrics import f1_score

from validation.schema import CLASSIFICATION_FEATURE_ORDER

# nom, distance_km, duration_minutes, n_stops, co2_estime, consommation_totale,
# type_train, country, attendu
CAS_DE_REFERENCE = [
    ("Paris-Marseille 800 km", 800.0, 195.0, 3, 450000.0, 16000.0, "electric", "FR", 1),
    ("Paris-New York 5800 km", 5800.0, 800.0, 1, 3000000.0, 90000.0, "electric", "FR", 0),
    ("Lyon-Dijon 180 km", 180.0, 80.0, 0, 81000.0, 1620.0, "electric", "FR", 0),
    ("Berlin-Munich 600 km", 600.0, 240.0, 3, 2640000.0, 6600.0, "electric", "DE", 1),
]


def _construire(encoders, distance, duree, arrets, co2, conso, traction, pays):
    return pd.DataFrame(
        [
            {
                "distance_km": distance,
                "duration_minutes": duree,
                "n_stops": arrets,
                "co2_estime": co2,
                "consommation_totale": conso,
                "type_train": int(encoders["le_type_train"].transform([traction])[0]),
                "country": int(encoders["le_country"].transform([pays])[0]),
            }
        ]
    )[CLASSIFICATION_FEATURE_ORDER]


@pytest.mark.parametrize(
    "nom,distance,duree,arrets,co2,conso,traction,pays,attendu", CAS_DE_REFERENCE
)
def test_les_cas_documentes_du_rapport_sont_reproduits(
    encoders, classifier, nom, distance, duree, arrets, co2, conso, traction, pays, attendu
):
    X = _construire(encoders, distance, duree, arrets, co2, conso, traction, pays)
    obtenu = int(classifier.predict(X)[0])
    assert obtenu == attendu, f"{nom} : attendu {attendu}, obtenu {obtenu}"


def test_appliquer_le_scaler_a_l_inference_casse_le_modele(
    encoders, scaler, classifier, features_and_target
):
    """
    Incident 002, figé en test. Le modèle est un XGBClassifier entraîné sur des
    variables brutes ; standardiser à l'inférence effondre le rappel de la classe
    positive à zéro, sans erreur ni avertissement.

    Ce test échouera si quelqu'un réintroduit le scaler dans le chemin d'inférence,
    ou si un futur modèle est au contraire entraîné sur des variables standardisées
    — dans ce cas, il faudra le mettre à jour en connaissance de cause.
    """
    X, y = features_and_target

    f1_brut = f1_score(y, classifier.predict(X), average="macro")
    f1_standardise = f1_score(
        y, classifier.predict(pd.DataFrame(scaler.transform(X), columns=X.columns)), average="macro"
    )

    assert f1_brut > f1_standardise, (
        f"F1 brut {f1_brut:.4f} <= F1 standardisé {f1_standardise:.4f} : "
        "le contrat d'inférence a changé, revoir la préparation"
    )
    assert f1_brut >= 0.95, f"le chemin d'inférence brut s'est dégradé : F1 {f1_brut:.4f}"
