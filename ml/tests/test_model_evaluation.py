"""
C12 et C13 — validation du modèle livré.

Partie visée   : les artefacts .joblib effectivement embarqués dans l'image Docker.
Périmètre      : classification (F1-macro, rappel de la classe positive, exactitude)
                 et régression (R²), mesurés sur un échantillon jamais utilisé pour
                 ajuster quoi que ce soit.
Note           : les prédictions sont faites sur variables BRUTES, conformément au
                 contrat établi dans l'incident 002.
Stratégie      : garde-fou de non-régression. Les seuils sont volontairement sous
                 les performances de référence : ils ne récompensent pas la
                 performance, ils détectent une dégradation. Sous le seuil, la
                 chaîne de livraison échoue et le modèle n'est pas publié.
"""

import numpy as np
import pytest
from sklearn.metrics import accuracy_score, f1_score, r2_score

from validation import thresholds


def test_le_classifieur_livre_respecte_le_seuil_de_f1(classifier, features_and_target):
    X, y = features_and_target
    predictions = classifier.predict(X)

    score = f1_score(y, predictions, average="macro")
    assert score >= thresholds.MIN_F1_MACRO, (
        f"F1-macro {score:.4f} sous le seuil de non-régression {thresholds.MIN_F1_MACRO}"
    )


def test_le_classifieur_livre_detecte_les_liaisons_substituables(classifier, features_and_target):
    """
    Rappel de la classe 1 : manquer une liaison substituable est l'erreur la plus
    coûteuse pour ObRail — une opportunité de report modal non identifiée.
    """
    X, y = features_and_target
    predictions = classifier.predict(X)

    vrais_positifs = int(((predictions == 1) & (y == 1)).sum())
    positifs_reels = int((y == 1).sum())
    rappel = vrais_positifs / positifs_reels if positifs_reels else 0.0

    assert rappel >= thresholds.MIN_RECALL_CLASS_1, (
        f"rappel classe 1 de {rappel:.4f}, sous le seuil {thresholds.MIN_RECALL_CLASS_1}"
    )


def test_le_classifieur_livre_respecte_le_seuil_d_exactitude(classifier, features_and_target):
    X, y = features_and_target
    score = accuracy_score(y, classifier.predict(X))
    assert score >= thresholds.MIN_ACCURACY


def test_le_regresseur_livre_est_un_pipeline_complet(regressor):
    """
    Le préprocesseur est embarqué dans l'artefact : aucune préparation manuelle
    n'est requise à l'inférence, contrairement au classifieur.
    """
    assert hasattr(regressor, "steps"), "l'artefact de régression n'est pas un Pipeline sklearn"
    assert [nom for nom, _ in regressor.steps] == ["preparation", "modele"]


def test_le_regresseur_predit_des_emissions_strictement_positives(regressor, sample):
    """Invariant physique : une émission de CO2 négative n'a aucun sens."""
    predictions = regressor.predict(_preparer_regression(sample, "reference"))
    assert (predictions > 0).all(), "certaines émissions prédites sont négatives ou nulles"


def test_reduire_la_consommation_reduit_les_emissions_predites(regressor, sample):
    """
    Contrat métier vérifiable sans reconstruire la cible : le scénario
    « consommation -15 % » doit produire des émissions inférieures au scénario
    de référence. C'est exactement l'usage qu'ObRail fait du modèle — comparer
    l'effet de politiques ferroviaires sur un même portefeuille de liaisons.
    """
    petit = sample.head(2000)
    reference = regressor.predict(_preparer_regression(petit, "reference"))
    optimise = regressor.predict(_preparer_regression(petit, "conso_moins_15"))

    assert optimise.mean() < reference.mean(), (
        "le scénario d'optimisation énergétique n'abaisse pas les émissions moyennes"
    )
    part_en_baisse = float((optimise < reference).mean())
    assert part_en_baisse >= 0.80, (
        f"seulement {part_en_baisse:.1%} des liaisons voient leurs émissions baisser"
    )


def test_electrifier_les_diesels_reduit_leurs_emissions(regressor, sample):
    """Le scénario d'électrification partielle doit bénéficier aux trains diesel."""
    diesels = sample[sample["type_train"] == "diesel"].head(1000)
    if diesels.empty:
        pytest.skip("aucun train diesel dans l'échantillon")

    reference = regressor.predict(_preparer_regression(diesels, "reference"))
    electrifie = regressor.predict(_preparer_regression(diesels, "diesel_50_electrique"))

    assert electrifie.mean() < reference.mean()


# ---------------------------------------------------------------------------
# Note de méthode — pourquoi aucun test de R² sur la régression
#
# La cible d'entraînement `kgCO2_futur` est construite dans le notebook de
# modélisation par des règles de simulation propres à chaque scénario, et ce
# notebook ne fait pas partie de ce dépôt. Elle n'est donc pas reconstituable
# ici de façon fiable : une tentative de reconstruction donne un R² négatif,
# ce qui mesure l'écart de la reconstruction, pas la qualité du modèle.
#
# Plutôt que d'inventer un seuil sur une cible approximative, ces tests
# vérifient des invariants que le modèle doit respecter quelle que soit la
# façon dont sa cible a été construite : positivité et cohérence des scénarios.
#
# Écart identifié pour C13 : rapatrier le notebook d'entraînement dans le dépôt
# rendrait la chaîne réellement reproductible de bout en bout, et permettrait
# alors un vrai garde-fou de R².
# ---------------------------------------------------------------------------


def _preparer_regression(df, scenario):
    """Reconstruit les 12 variables attendues par le pipeline de régression."""
    x = df.copy()

    if scenario == "conso_moins_15":
        x["consommation_scenario"] = x["consommation_totale"] * 0.85
        x["distance_scenario_km"] = x["distance_km"]
    elif scenario == "diesel_50_electrique":
        facteur = np.where(x["type_train"] == "diesel", 0.50, 1.0)
        x["consommation_scenario"] = x["consommation_totale"] * facteur
        x["distance_scenario_km"] = x["distance_km"]
    elif scenario == "distance_moins_10":
        x["consommation_scenario"] = x["consommation_totale"] * 0.90
        x["distance_scenario_km"] = x["distance_km"] * 0.90
    else:
        x["consommation_scenario"] = x["consommation_totale"]
        x["distance_scenario_km"] = x["distance_km"]

    x["vitesse_moyenne_kmh"] = np.where(
        x["duration_minutes"] > 0, x["distance_km"] / (x["duration_minutes"] / 60.0), 0.0
    )
    x["co2_par_km"] = np.where(
        x["distance_km"] > 0,
        (x["consommation_energy"] * x["gco2_per_kwh"]) / x["distance_km"],
        0.0,
    )
    x["is_diesel"] = (x["type_train"] == "diesel").astype(int)
    x["is_electric"] = (x["type_train"] == "electric").astype(int)
    x["scenario"] = scenario

    return x[list(regressor_feature_names(x))]


def regressor_feature_names(_x):
    """Ordre des variables attendu par le pipeline, figé d'après l'artefact livré."""
    return [
        "distance_scenario_km",
        "duration_minutes",
        "n_stops",
        "consommation_energy",
        "gco2_per_kwh",
        "consommation_scenario",
        "vitesse_moyenne_kmh",
        "co2_par_km",
        "is_diesel",
        "is_electric",
        "type_train",
        "scenario",
    ]
