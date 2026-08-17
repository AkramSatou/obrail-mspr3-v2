#!/usr/bin/env python3
"""
ml/train.py — Script d'entraînement de production ObRail.

Usage :
    python ml/train.py [--dataset PATH] [--models-out PATH]

Ce que produit chaque exécution réussie :
    models/registry/<YYYYMMDD_HHMMSS>/   artefacts versionnés + metadata.json
    models/*.joblib                       version promue (volume docker-compose)

Code de sortie non nul si :
    - le jeu de données ne respecte pas le schéma attendu ;
    - le classifieur n'atteint pas les seuils de ml/validation/thresholds.py ;
    - les invariants physiques du régresseur existant ne sont pas respectés.

Périmètre intentionnellement limité au classifieur :
    Le régresseur CO2 (regression_co2.joblib) n'est PAS réentraîné ici.
    Sa cible d'entraînement kgCO2_futur a été construite par un notebook de
    simulation absent de ce dépôt (cf. note dans ml/tests/test_model_evaluation.py,
    lignes 103-118). Une tentative de reconstruction donne un R² négatif.
    Le pipeline valide le régresseur existant avec des invariants physiques.
    Recommandation C13 : versionner ce notebook dans ml/ pour clore ce gap.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

# ── Chemins ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ml"))

from validation import thresholds                          # noqa: E402
from validation.schema import (                            # noqa: E402
    CLASSIFICATION_FEATURE_ORDER,
    build_substitution_target,
    validate_dataset,
)

DEFAULT_DATASET = Path(
    os.getenv("OBRAIL_DATASET_PATH", str(REPO_ROOT / "data" / "eu_trips_v2.csv"))
)
DEFAULT_MODELS_OUT = Path(
    os.getenv("OBRAIL_MODELS_PATH", str(REPO_ROOT / "models"))
)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


# ── Étape 1 : validation du jeu de données ──────────────────────────────────
def charger_et_valider(dataset_path: Path) -> pd.DataFrame:
    print(f"\n[1/4] Chargement du jeu de données : {dataset_path}")
    if not dataset_path.exists():
        print(f"  ✗ Fichier introuvable : {dataset_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(dataset_path, low_memory=False)
    print(f"  → {len(df):,} lignes × {df.shape[1]} colonnes")

    rapport = validate_dataset(df)
    if not rapport.is_valid:
        print(f"\n  ✗ Jeu de données invalide :\n{rapport}", file=sys.stderr)
        sys.exit(1)

    print("  ✓ Validation du schéma : OK")
    return df


# ── Étape 2 : entraînement du classifieur ───────────────────────────────────
def entrainer_classifieur(df: pd.DataFrame):
    print("\n[2/4] Entraînement du classifieur (substitution avion→train)")
    seed = thresholds.RANDOM_SEED

    # Encodage ordinal — même logique que conftest.py / features_and_target
    le_type_train = LabelEncoder().fit(["diesel", "electric"])
    le_country    = LabelEncoder().fit(["DE", "ES", "FR", "IT"])
    encoders = {"le_type_train": le_type_train, "le_country": le_country}

    prep = df.copy()
    prep["type_train"] = le_type_train.transform(prep["type_train"])
    prep["country"]    = le_country.transform(prep["country"])

    X = prep[CLASSIFICATION_FEATURE_ORDER]
    y = build_substitution_target(prep)

    # StandardScaler conservé pour compatibilité /health — NON appliqué
    # au classifieur XGBoost (INCIDENT-002 : dégrade le F1 à 0.479)
    scaler = StandardScaler().fit(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y
    )
    print(f"  Train : {len(X_train):,} lignes  |  Test : {len(X_test):,} lignes")

    # Hyperparamètres production (n_estimators plus élevé qu'en test)
    clf = XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.1,
        random_state=seed,
        n_jobs=-1,
        eval_metric="logloss",
    )
    clf.fit(X_train, y_train)

    # Évaluation
    y_pred = clf.predict(X_test)
    f1     = f1_score(y_test, y_pred, average="macro")
    pos    = int((y_test == 1).sum())
    vp     = int(((y_pred == 1) & (y_test == 1)).sum())
    recall = vp / pos if pos else 0.0
    acc    = accuracy_score(y_test, y_pred)

    print(f"  F1-macro   : {f1:.4f}  (seuil ≥ {thresholds.MIN_F1_MACRO})")
    print(f"  Rappel cl.1: {recall:.4f}  (seuil ≥ {thresholds.MIN_RECALL_CLASS_1})")
    print(f"  Exactitude : {acc:.4f}  (seuil ≥ {thresholds.MIN_ACCURACY})")

    echecs = []
    if f1     < thresholds.MIN_F1_MACRO:        echecs.append(f"F1-macro {f1:.4f} < {thresholds.MIN_F1_MACRO}")
    if recall < thresholds.MIN_RECALL_CLASS_1:  echecs.append(f"Rappel cl.1 {recall:.4f} < {thresholds.MIN_RECALL_CLASS_1}")
    if acc    < thresholds.MIN_ACCURACY:        echecs.append(f"Exactitude {acc:.4f} < {thresholds.MIN_ACCURACY}")

    if echecs:
        print("\n  ✗ Seuils non atteints :", file=sys.stderr)
        for e in echecs:
            print(f"    - {e}", file=sys.stderr)
        sys.exit(1)

    print("  ✓ Tous les seuils atteints")
    metrics = {
        "f1_macro":    round(f1, 4),
        "recall_class1": round(recall, 4),
        "accuracy":    round(acc, 4),
        "n_estimators": 400,
    }
    return clf, encoders, scaler, metrics


# ── Étape 3 : validation du régresseur existant ─────────────────────────────
def valider_regresseur_existant(models_dir: Path, sample: pd.DataFrame) -> dict:
    """
    Valide le régresseur CO2 livré avec deux invariants physiques.
    Voir module docstring pour l'explication de pourquoi il n'est pas réentraîné.
    """
    print("\n[3/4] Validation du régresseur CO2 existant (invariants physiques)")

    regressor_path = models_dir / "regression_co2.joblib"
    if not regressor_path.exists():
        print(f"  ✗ Régresseur introuvable : {regressor_path}", file=sys.stderr)
        sys.exit(1)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        regressor = joblib.load(regressor_path)

    def _preparer(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
        x = df.copy()
        if scenario == "conso_moins_15":
            x["consommation_scenario"] = x["consommation_totale"] * 0.85
            x["distance_scenario_km"]  = x["distance_km"]
        elif scenario == "diesel_50_electrique":
            facteur = np.where(x["type_train"] == "diesel", 0.50, 1.0)
            x["consommation_scenario"] = x["consommation_totale"] * facteur
            x["distance_scenario_km"]  = x["distance_km"]
        elif scenario == "distance_moins_10":
            x["consommation_scenario"] = x["consommation_totale"] * 0.90
            x["distance_scenario_km"]  = x["distance_km"] * 0.90
        else:  # reference
            x["consommation_scenario"] = x["consommation_totale"]
            x["distance_scenario_km"]  = x["distance_km"]

        x["vitesse_moyenne_kmh"] = np.where(
            x["duration_minutes"] > 0,
            x["distance_km"] / (x["duration_minutes"] / 60.0),
            0.0,
        )
        # Formule exacte de INCIDENT-003 — ne pas modifier
        x["co2_par_km"] = np.where(
            x["distance_km"] > 0,
            (x["consommation_energy"] * x["gco2_per_kwh"]) / x["distance_km"],
            0.0,
        )
        x["is_diesel"]   = (x["type_train"] == "diesel").astype(int)
        x["is_electric"]  = (x["type_train"] == "electric").astype(int)
        x["scenario"] = scenario
        return x[[
            "distance_scenario_km", "duration_minutes", "n_stops",
            "consommation_energy", "gco2_per_kwh", "consommation_scenario",
            "vitesse_moyenne_kmh", "co2_par_km", "is_diesel", "is_electric",
            "type_train", "scenario",
        ]]

    petit = sample.head(2_000)
    pred_ref  = regressor.predict(_preparer(petit, "reference"))
    pred_opt  = regressor.predict(_preparer(petit, "conso_moins_15"))

    positif   = bool((pred_ref > 0).all())
    coherent  = bool(pred_opt.mean() < pred_ref.mean())

    print(f"  Positivité (toutes émissions > 0) : {'✓' if positif else '✗'}")
    print(f"  conso_moins_15 < reference        : {'✓' if coherent else '✗'}")

    if not positif or not coherent:
        print("  ✗ Invariants physiques violés — le régresseur livré est dégradé",
              file=sys.stderr)
        sys.exit(1)

    print("  ✓ Invariants physiques respectés")
    print("  ℹ  Régresseur conservé (cible d'entraînement non reconstituable)")
    return {"status": "validated_only", "invariants_passed": True}


# ── Étape 4 : versioning et promotion ───────────────────────────────────────
def versionner_et_promouvoir(
    version: str,
    models_dir: Path,
    classifier,
    encoders: dict,
    scaler,
    cls_metrics: dict,
    reg_metrics: dict,
    dataset_path: Path,
    n_rows: int,
):
    print(f"\n[4/4] Versioning → {version}")
    registry_path = models_dir / "registry" / version
    registry_path.mkdir(parents=True, exist_ok=True)

    # Nouveaux artefacts classifieur
    joblib.dump(classifier, registry_path / "classification_substitution_avion.joblib")
    joblib.dump(encoders,   registry_path / "encoders.joblib")
    joblib.dump(scaler,     registry_path / "scaler.joblib")

    # Régresseur : copié tel quel depuis la version courante
    src_reg = models_dir / "regression_co2.joblib"
    shutil.copy2(src_reg, registry_path / "regression_co2.joblib")

    metadata = {
        "version":   version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "dataset":   dataset_path.name,
        "dataset_rows": n_rows,
        "classifier": cls_metrics,
        "regressor":  reg_metrics,
        "thresholds_applied": {
            "f1_macro":      thresholds.MIN_F1_MACRO,
            "recall_class1": thresholds.MIN_RECALL_CLASS_1,
            "accuracy":      thresholds.MIN_ACCURACY,
        },
    }
    (registry_path / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  ✓ Registre    : {registry_path}")

    # Promotion vers models/ (répertoire monté par docker-compose)
    joblib.dump(classifier, models_dir / "classification_substitution_avion.joblib")
    joblib.dump(encoders,   models_dir / "encoders.joblib")
    joblib.dump(scaler,     models_dir / "scaler.joblib")
    print(f"  ✓ Promotion   : {models_dir}")
    print(f"\n  Résumé — version {version}")
    print(f"    F1-macro={cls_metrics['f1_macro']}  "
          f"Rappel={cls_metrics['recall_class1']}  "
          f"Exactitude={cls_metrics['accuracy']}")


# ── Point d'entrée ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pipeline d'entraînement ObRail (C13)")
    parser.add_argument("--dataset",    type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--models-out", type=Path, default=DEFAULT_MODELS_OUT)
    args = parser.parse_args()

    version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print(f"ObRail — Pipeline d'entraînement   version {version}")
    print("=" * 60)

    df      = charger_et_valider(args.dataset)
    sample  = df.sample(
        n=min(thresholds.SAMPLE_SIZE, len(df)),
        random_state=thresholds.RANDOM_SEED,
    )

    clf, encoders, scaler, cls_metrics = entrainer_classifieur(df)
    reg_metrics = valider_regresseur_existant(args.models_out, sample)

    versionner_et_promouvoir(
        version      = version,
        models_dir   = args.models_out,
        classifier   = clf,
        encoders     = encoders,
        scaler       = scaler,
        cls_metrics  = cls_metrics,
        reg_metrics  = reg_metrics,
        dataset_path = args.dataset,
        n_rows       = len(df),
    )

    print("\n✓ Pipeline terminé avec succès.\n")


if __name__ == "__main__":
    main()
