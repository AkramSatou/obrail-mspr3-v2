# Pipeline MLOps — ObRail Europe
**Compétence RNCP 37827 visée : C13** — Élaborer et mettre en œuvre une chaîne de livraison
continue adaptée à un modèle d'intelligence artificielle (MLOps).

---

## 1. Vue d'ensemble de la chaîne

```
eu_trips_v2.csv
      │
      ▼
┌─────────────────────┐
│  Validation schéma  │  ml/validation/schema.py
│  (types, plages,    │  → Échoue si données invalides
│   cardinalités)     │  → exit(1) immédiat
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Entraînement       │  ml/train.py
│  XGBClassifier      │  Dataset complet (142 420 lignes)
│  (substitution)     │  n_estimators=400, seed=42
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Validation         │  ml/validation/thresholds.py
│  métriques          │  F1-macro ≥ 0.95
│                     │  Rappel classe 1 ≥ 0.90
│                     │  Exactitude ≥ 0.95
└──────────┬──────────┘  → exit(1) si non atteints
           │             → modèles existants conservés (rollback implicite)
           ▼
┌─────────────────────┐
│  Validation         │  ml/tests/test_model_evaluation.py
│  régresseur CO2     │  Invariants physiques :
│  (invariants)       │  · émissions > 0
│                     │  · conso_moins_15 < référence
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Versioning         │  models/registry/<YYYYMMDD_HHMMSS>/
│                     │  ├── *.joblib
│                     │  └── metadata.json
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Promotion          │  models/*.joblib  ← volume docker-compose
│  conditionnelle     │  Uniquement si TOUTES les validations passent
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  CI existante       │  .github/workflows/ci.yml, job "model"
│  (non-régression)   │  pytest ml/tests — sur le modèle promu
└─────────────────────┘
```

---

## 2. Déclenchement du workflow

Fichier : `.github/workflows/model-retrain.yml`

| Déclencheur | Cas d'usage |
|---|---|
| `workflow_dispatch` (manuel) | Nouveau dataset, ajustement hyperparamètres, correction post-incident |
| `schedule` (cron dim. 02:00 UTC) | Filet de sécurité si le dataset est alimenté automatiquement |

**Pourquoi pas sur chaque push ?**
Le dataset `eu_trips_v2.csv` n'évolue pas à chaque commit de code. Un réentraînement
complet prend ~30 min et consomme des ressources de CI pour aucun gain. La CI
existante (`ci.yml`, job `model`) suffit à vérifier que le code n'a pas cassé le modèle
statique embarqué. Ce workflow est réservé aux moments où une mise à jour des modèles
est justifiée.

---

## 3. Versioning et rollback

### Structure du registre

```
models/
├── classification_substitution_avion.joblib  ← version active (montée par Docker)
├── encoders.joblib
├── scaler.joblib
├── regression_co2.joblib
└── registry/
    ├── 20260815_143022/
    │   ├── classification_substitution_avion.joblib
    │   ├── encoders.joblib
    │   ├── scaler.joblib
    │   ├── regression_co2.joblib
    │   └── metadata.json
    └── 20260901_020045/
        └── ...
```

### Contenu de `metadata.json`

```json
{
  "version": "20260815_143022",
  "timestamp": "2026-08-15T14:30:22+00:00",
  "git_commit": "a3f9b12",
  "dataset": "eu_trips_v2.csv",
  "dataset_rows": 142420,
  "classifier": {
    "f1_macro": 0.9971,
    "recall_class1": 0.9954,
    "accuracy": 0.9978,
    "n_estimators": 400
  },
  "regressor": {
    "status": "validated_only",
    "invariants_passed": true
  },
  "thresholds_applied": {
    "f1_macro": 0.95,
    "recall_class1": 0.90,
    "accuracy": 0.95
  }
}
```

### Procédure de rollback

```bash
# Lister les versions disponibles
ls models/registry/

# Restaurer la version du 15 août 2026
cp models/registry/20260815_143022/*.joblib models/

# Redémarrer le backend pour charger les nouveaux artefacts
docker compose restart backend
```

Les archives GitHub Actions (artifacts `model-registry-<run_id>`) sont conservées
90 jours, ce qui permet de récupérer une version même si elle n'est plus dans le registre git.

---

## 4. Choix techniques

| Décision | Choix retenu | Alternative écartée | Justification |
|---|---|---|---|
| Registre d'artefacts | Dossier horodaté `models/registry/` | MLflow, DVC | Zéro dépendance externe, lisible directement par `ls`, suffisant pour 1–2 modèles en cours de projet. MLflow apporterait de la valeur si plusieurs expériences sont comparées en parallèle (recommandé pour un projet de production). |
| Versioning git | Commit des `.joblib` dans le repo | Git-LFS, S3 | Compatible avec le montage Docker existant (`../models:/app/models:ro`) sans modification de l'infrastructure. |
| Déclenchement | Manuel + cron | Sur chaque push | Coût vs valeur : le dataset ne change pas à chaque commit. |
| Seuils | `ml/validation/thresholds.py` | Seuils inline | Source unique de vérité, réutilisée par la CI et le script d'entraînement. |

---

## 5. Limitation documentée — Régresseur CO₂

### État actuel

Le régresseur `regression_co2.joblib` **n'est pas réentraîné** par `ml/train.py`.

**Cause :** la variable cible `kgCO2_futur` a été construite par un notebook de simulation
qui n'a pas été versionné dans ce dépôt. Toute tentative de reconstruction à partir du
dataset produit un R² négatif, indiquant que la formule exacte de simulation n'est pas
directement dérivable des colonnes disponibles.

Ce point est explicitement documenté dans `ml/tests/test_model_evaluation.py` (lignes 103–118) :

> *"Écart identifié pour C13 : rapatrier le notebook d'entraînement dans le dépôt rendrait
> la chaîne réellement reproductible de bout en bout."*

### Mitigation en place

Le pipeline valide le régresseur existant avec deux invariants physiques qui doivent être
respectés quelle que soit la façon dont la cible a été construite :
1. Toutes les émissions prédites sont strictement positives (CO₂ < 0 est physiquement impossible).
2. Le scénario « consommation −15 % » produit des émissions inférieures au scénario de référence.

### Chemin de résolution

Versionner le notebook de simulation dans `ml/notebooks/` rendrait la chaîne entièrement
reproductible et permettrait de :
- Recalculer `kgCO2_futur` à partir des données brutes
- Entraîner le régresseur dans `ml/train.py`
- Ajouter un vrai garde-fou R² ≥ 0.90

---

## 6. Incidents documentés — contraintes du pipeline

| Incident | Impact sur le pipeline | Contre-mesure |
|---|---|---|
| **INCIDENT-002** (StandardScaler + XGBoost) | F1-macro chute de 0.997 → 0.479 si le scaler est appliqué à l'inférence XGBoost | `ml/train.py` n'applique **jamais** le scaler au classifieur. Le scaler est conservé uniquement pour `/health`. |
| **INCIDENT-003** (xgboost 2.0.3 vs scikit-learn 1.4.2) | Émissions négatives (−124 kgCO2) | `backend/requirements.txt` épingle `xgboost==3.2.0`. Le pipeline de validation vérifie la positivité des émissions. |

---

## 7. Correspondance avec la grille RNCP C13

| Critère attendu par le jury | Implémentation dans ce projet |
|---|---|
| **Automatisation de l'entraînement** | `ml/train.py` — exécutable en une commande sans intervention manuelle ; intégré dans GitHub Actions |
| **Versioning des modèles** | `models/registry/<version>/metadata.json` — horodatage, commit git, métriques, seuils appliqués, nom du dataset |
| **Validation par critères de qualité avant mise en production** | Seuils dans `ml/validation/thresholds.py` — le pipeline échoue explicitement (exit 1) si non atteints ; les artefacts existants ne sont jamais écrasés par une version dégradée |
| **Traçabilité** | `metadata.json` dans chaque version du registre ; archive GitHub Actions 90 jours |
| **Possibilité de revenir à une version antérieure** | `cp models/registry/<version>/*.joblib models/` suffit ; aucune perte de données car chaque version est conservée dans le registre |
| **Déclenchement manuel et planifié** | `workflow_dispatch` (manuel) + cron hebdomadaire dans `model-retrain.yml` |

---

## 8. Exécution locale

```bash
# Pré-requis : dépendances installées, dataset en place
pip install -r backend/requirements.txt

# Lancer le pipeline complet
python ml/train.py

# Avec chemins explicites
python ml/train.py \
  --dataset data/eu_trips_v2.csv \
  --models-out models/

# Vérifier les tests de non-régression après entraînement
python -m pytest ml/tests -v
```

---

## 9. Couverture de tests (ml/tests)

### Installation

`pytest-cov` n'est pas listé dans `backend/requirements.txt`. Installation séparée :

```bash
pip install pytest-cov
```

### Commande

```bash
python -m pytest ml/tests --cov=ml --cov-report=term-missing --cov-config=.coveragerc
```

Un fichier de configuration dédié exclut `ml/tests/*` du calcul :

```ini
# .coveragerc
[run]
omit =
    */tests/*
    */__init__.py
```

Sans cette exclusion, `--cov=ml` compte aussi les fichiers de tests eux-mêmes, ce qui
gonfle artificiellement le résultat puisqu'un fichier de test se couvre toujours
lui-même à près de 100 %.

### Résultat mesuré le 22 août 2026

| Fichier | Instructions | Non couvertes | Couverture |
|---|---|---|---|
| `ml/validation/thresholds.py` | 7 | 0 | 100 % |
| `ml/validation/schema.py` | 57 | 9 | 84 % |
| `ml/train.py` | 153 | 153 | 0 % (voir note ci-dessous) |

30 tests exécutés, 30 passés.

### Cible retenue

**80 % minimum sur `ml/validation/`**, le seul module unitairement testable par import
direct depuis la suite `ml/tests`. Cible atteinte et dépassée sur les deux fichiers du
module (84 % et 100 %).

### Note sur ml/train.py

`ml/train.py` n'est jamais importé par la suite `pytest` : il est exécuté directement
comme un processus séparé (`python ml/train.py`) dans `model-retrain.yml` (section 2),
étape suivie d'une exécution complète de `python -m pytest ml/tests -v` en
non-régression contre le modèle fraîchement entraîné. `pytest-cov` ne peut instrumenter
que le code réellement importé pendant la mesure : l'exécution en sous-processus dans un
autre workflow n'apparaît donc jamais dans ce calcul, même si le script tourne bien et
que sa sortie est vérifiée à chaque réentraînement. Sa correction est donc garantie
fonctionnellement (exit code non nul si un seuil échoue, section 1) plutôt que mesurée en
couverture de lignes, et aucune cible de couverture ligne à ligne n'est fixée pour ce
fichier pour cette raison.

### Lignes non couvertes de schema.py

Les 9 lignes non couvertes (90-92, 101-102, 107-108, 112, 121) correspondent à des
branches de `validate_dataset` non déclenchées par les jeux de données utilisés dans la
suite actuelle, ni le jeu réel via les fixtures (toujours conforme), ni le jeu corrompu
construit à la main dans `test_un_jeu_de_donnees_corrompu_est_bien_rejete` (qui déclenche
une partie des règles mais pas toutes). Ce ne sont pas des lignes mortes : ce sont des
règles de validation réelles, simplement non exercées par les scénarios de test actuels.
