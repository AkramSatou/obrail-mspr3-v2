# `ml/` — pipeline MLOps et tests du modèle ObRail

Ce dossier contient la chaîne MLOps complète (C13) : script d'entraînement de
production, règles de validation et tests du modèle.

Les tests ML sont distincts des tests de l'API (`backend/tests/`) :
les tests backend vérifient que les routes se comportent correctement,
ceux-ci vérifient que le modèle prédit correctement.
L'incident 002 est né précisément de cette confusion.

## Organisation

```
ml/
├── train.py            Script d'entraînement de production (C13)
├── validation/
│   ├── schema.py       Contrat du jeu de données et règle métier de la cible
│   └── thresholds.py   Seuils de non-régression, centralisés
└── tests/
    ├── test_dataset_validation.py   Validation des données en entrée
    ├── test_preparation.py          Encodeurs, scaler, ordre des variables
    ├── test_training.py             Reproductibilité et capacité d'apprentissage
    ├── test_inference_contract.py   Cas de référence du rapport
    └── test_model_evaluation.py     Garde-fous de non-régression
```

## Cas de test — périmètre et stratégie

| Cas | Partie du modèle visée | Périmètre | Stratégie |
|---|---|---|---|
| Conformité du jeu de données | Entrée du pipeline | Schéma, types, plages, complétude, unicité, cardinalités | Contrat exécutable : toute violation arrête la chaîne avant l'entraînement |
| Détection d'un jeu corrompu | Les règles elles-mêmes | Jeu volontairement invalide | Test du test : vérifie que le contrat détecte réellement une anomalie |
| Reproductibilité de la cible | Règle métier de labellisation | Proportion de liaisons substituables | Fige la règle 300-1500 km et moins de 8 h ; la modifier casse la chaîne |
| Classes des encodeurs | Préparation | `type_train`, `country` | Valeurs et ordre figés, encodage déterministe |
| Effet du StandardScaler | Préparation | 7 variables | Vérifie le centrage-réduction, et que son application à l'inférence casse le modèle (incident 002) |
| Ordre des variables | Préparation | Vecteur d'entrée positionnel | Permuter deux colonnes ne lève aucune erreur mais fausse tout : le risque est testé |
| Capacité d'apprentissage | Entraînement | Échantillon de 20 000 lignes, graine fixe | Réentraîne un modèle réduit et exige un F1-macro plancher |
| Reproductibilité | Entraînement | Deux exécutions, même graine | Prédictions identiques attendues |
| Absence de fuite de données | Entraînement | Partitions train et test | Vérifie qu'elles sont disjointes |
| Cas de référence | Inférence complète | 4 liaisons documentées au rapport | Non-régression **par valeur prédite**, pas par code HTTP |
| Non-régression classification | Modèle livré | F1-macro, rappel classe 1, exactitude | Seuils sous les performances de référence : détectent une dégradation |
| Invariants régression | Modèle livré | Positivité, cohérence des scénarios | `xfail` documenté — voir l'incident 003 |

## Chaîne MLOps (C13)

```
Données → Validation schéma → Entraînement classifieur → Validation métriques
       → Validation régresseur (invariants) → Versioning registre → Promotion
       → CI existante (non-régression)
```

**Déclenchement :** `.github/workflows/model-retrain.yml` (manuel ou cron hebdo).
**Documentation complète :** `docs/MLOPS_PIPELINE.md`

## Exécution

```bash
pip install -r backend/requirements.txt

# Pipeline MLOps complet (entraînement + validation + versioning + promotion)
python ml/train.py

# Tests de non-régression seuls (CI existante)
python -m pytest ml/tests -v
```

Le job `model` dans `ci.yml` exécute `pytest ml/tests` avant toute publication :
un modèle qui ne passe pas ses garde-fous n'est jamais livré.

## Seuils de non-régression

Définis dans `validation/thresholds.py`, volontairement **inférieurs** aux
performances mesurées lors de l'entraînement initial. Ils ne récompensent pas la
performance : ils détectent une dégradation.

| Métrique | Seuil | Référence mesurée |
|---|---|---|
| Classification — F1-macro | 0.95 | 0.997 |
| Classification — rappel classe 1 | 0.90 | 1.00 |
| Classification — exactitude | 0.95 | 0.998 |
| Régression — R² | 0.90 | non vérifiable, incident 003 |
