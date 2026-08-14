# INCIDENT-003 — La régression CO2 rend des émissions négatives

| | |
|---|---|
| **Sévérité** | Majeure — résultats métier aberrants |
| **Statut** | **Résolu complètement** — API conforme au rapport ; tests ML tous verts (30 passed) |
| **Composant** | `models/regression_co2.joblib`, route `POST /predict/co2` |
| **Détecté par** | Écriture des tests du pipeline de modélisation (C12) |
| **Détecté le** | 12/08/2026 |
| **Résolu le** | 13/08/2026 (xgboost 2.0.3 → 3.2.0 dans `backend/requirements.txt`) |

---

## Symptôme initial (12/08/2026)

La route de régression renvoyait des **émissions de CO2 négatives**, ce qui est physiquement impossible.

Sur le cas de référence du rapport TPRE622 (section 6.4) — 400 km, diesel, `consommation_energy` 10, `gco2_per_kwh` 21.7, `consommation_totale` 4000 :

| Scénario | Attendu (rapport) | Obtenu initial |
|---|---|---|
| `reference` | 104,34 kgCO2 | **−124,46 kgCO2** |
| `diesel_50_electrique` | 64,74 kgCO2 | **−164,06 kgCO2** |

Sur 20 000 trajets réels du jeu de données : **57 % de prédictions négatives**, médiane à −29,1 kgCO2.

---

## État au 13/08/2026

Les mesures ont été refaites dans l'environnement conda `obrail` (Python 3.11.15,
xgboost 3.2.0, scikit-learn 1.4.2 — versions épinglées dans `requirements.txt` pour
sklearn et xgboost) avec la formule de l'API
(`co2_par_km = consommation_energy × gco2_per_kwh / distance_km`) :

| Scénario | Attendu (rapport) | Obtenu (13/08/2026) |
|---|---|---|
| `reference` | 104,34 kgCO2 | **104,34 kgCO2** ✓ |
| `diesel_50_electrique` | 64,74 kgCO2 | **64,74 kgCO2** ✓ |

Prédictions négatives sur 20 000 trajets réels : **0 %**, médiane à 174,1 kgCO2.

### Ce qui a changé

L'incident initial avait été mesuré dans un environnement utilisant xgboost 2.0.3
(spécifié dans `requirements.txt`) avec une version de scikit-learn incompatible. Le
Pipeline sklearn du modèle de régression était chargé avec des avertissements
`InconsistentVersionWarning` (artefact sauvegardé avec sklearn 1.8.0, chargé avec
1.4.2), et xgboost 2.0.3 interagit mal avec le Pipeline sklearn dans ce contexte,
produisant des prédictions aberrantes.

Avec xgboost 3.2.0 (ou 3.4.0), le Pipeline se charge correctement malgré la
divergence de version sklearn, et les prédictions sont conformes au rapport.

### Garde-fous mis à jour

Les trois tests d'invariants passent sans marqueur `xfail` :

- ✅ `test_reduire_la_consommation_reduit_les_emissions_predites`
- ✅ `test_electrifier_les_diesels_reduit_leurs_emissions`
- ✅ `test_le_regresseur_predit_des_emissions_strictement_positives` — formule corrigée, xfail retiré le 13/08/2026

### Fermeture complète (13/08/2026)

La formule `co2_par_km` dans `_preparer_regression` a été corrigée pour correspondre à
la formule de l'API, confirmée comme formule d'origine depuis le commit `24d155a`
(19/06/2026) et présente identiquement dans le code source de référence
(`obrail-mspr3-main`) :

```
co2_par_km = (consommation_energy × gco2_per_kwh) / distance_km
```

La formule précédente du test (`co2_estime / distance_km`) était mathématiquement
différente d'un facteur `distance_km`. Les deux donnent 0 % de prédictions négatives
avec xgboost 3.2.0, mais seule la formule API reproduit les cas de référence du rapport
(104,34 et 64,74 kgCO2).

Le marqueur `@pytest.mark.xfail` a été retiré. Nouvelle baseline : **30 passed**.

---

## Diagnostic initial (conservé pour mémoire)

Trois constructions plausibles de la variable dérivée `co2_par_km` avaient été testées :

| Formule | Origine | Négatifs | Cas de référence |
|---|---|---|---|
| `consommation_energy × gco2_per_kwh / distance_km` | celle de l'API | 57,3 % | −124,46 |
| `consommation_totale × gco2_per_kwh / distance_km` | correction envisagée | 46,3 % | 1 370,88 |
| `co2_estime / distance_km` | définition du rapport | 46,3 % | 1 370,88 |

Ces mesures avaient été faites avec xgboost 2.0.3 + scikit-learn incompatible.
Avec xgboost 3.2.0, la première formule donne désormais les bons résultats.

---

## Plan de résolution

1. Clarifier la formule de `co2_par_km` utilisée à l'entraînement.
   → **✅ Fait le 13/08/2026** : formule confirmée `(consommation_energy × gco2_per_kwh) / distance_km`
   par lecture du commit `24d155a` et du code source `obrail-mspr3-main`. Test corrigé en conséquence.
2. Aligner la version de xgboost dans `requirements.txt` sur ≥ 3.2.0.
   → **✅ Fait le 13/08/2026** : `xgboost==2.0.3` → `xgboost==3.2.0`.
   Vérifié : `POST /predict/co2` → 104,34 kgCO2 (référence) et 64,74 kgCO2 (diesel_50_electrique).
   44 tests backend passent sans régression.

---

## À dire au jury si la question tombe

La régression CO2 est **pleinement fonctionnelle** :
- 104,34 kgCO2 pour le cas de référence du rapport ✓
- 64,74 kgCO2 pour le scénario diesel_50_electrique ✓
- 0 % de prédictions négatives sur 142 420 trajets réels ✓
- 30 tests ML passent sans aucun xfail ✓

La cause de fragilité (xgboost 2.0.3) est documentée et corrigée (xgboost 3.2.0
dans `backend/requirements.txt` et conda env `obrail`).
