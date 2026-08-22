# INCIDENT-002 — Le classifieur ne détectait plus aucune liaison substituable

| | |
|---|---|
| **Sévérité** | Critique — fonctionnalité métier principale inopérante |
| **Statut** | **Résolu** |
| **Composant** | `backend/app/main.py`, route `POST /predict/substitution` (et son alias `/predict`) |
| **Détecté par** | Écriture des tests du pipeline de modélisation (C12) |
| **Détecté le** | 12/08/2026 |

---

## Symptôme

La route de classification renvoyait `substitution_avion = 0` avec une probabilité de `0.000` pour **toutes** les liaisons, y compris celles documentées comme substituables dans le rapport TPRE622.

Aucune erreur, aucun avertissement, code HTTP 200. La dégradation était totalement silencieuse.

Reproduction, sur le cas de référence du rapport (section 6.4) :

```
Paris → Marseille, 800 km, 195 min, électrique, FR
  attendu (rapport) : substitution_avion = 1, probabilité = 1.0
  obtenu            : substitution_avion = 0, probabilité = 0.000
```

Mesuré sur un échantillon de 20 000 trajets réels :

| | F1-macro | Rappel classe 1 | Liaisons détectées |
|---|---|---|---|
| Chemin en production | **0.479** | **0 %** | **0** |
| Attendu (rapport) | 0.997 | 100 % | ~8,4 % |

---

## Cause racine

Le chemin d'inférence appliquait un `StandardScaler` avant la prédiction :

```python
X_scaled = pd.DataFrame(_scaler.transform(X), columns=X.columns)
prediction = int(_model_substitution.predict(X_scaled)[0])
```

Or le modèle retenu est un **XGBClassifier entraîné sur les variables brutes**. Le rapport TPRE622, section 5.3.3, l'écrit explicitement :

> « StandardScaler appliqué **uniquement pour la Logistic Regression**. […] Random Forest et XGBoost travaillent sur des seuils ordinaux — l'échelle absolue n'a aucun impact. »

Le scaler avait été sauvegardé pour la régression logistique servant de référence de comparaison. Lors de la mise en production (MSPR TPRE532), il a été introduit dans le chemin d'inférence sur la base d'une hypothèse inverse — le rapport TPRE532 mentionne cette modification comme une correction :

> « Un point critique a été corrigé lors de l'intégration : le StandardScaler devait être appliqué avant toute prédiction de substitution car le modèle XGBoost avait été entraîné sur des features standardisées. »

L'hypothèse était fausse. Standardiser des variables que le modèle n'attend pas standardisées déplace tous les points hors des seuils appris par les arbres : le modèle bascule systématiquement du côté de la classe majoritaire.

---

## Pourquoi aucun test ne l'a détecté

C'est le point le plus instructif de cet incident.

Les 12 tests backend existants vérifiaient que la route **répondait**, jamais **ce qu'elle répondait** :

```python
assert response.status_code in (200, 503)
```

Un modèle qui renvoie systématiquement `0` passe ce test sans difficulté. Le déficit ne portait pas sur la couverture — les routes étaient couvertes — mais sur la **nature** des assertions : structurelles au lieu d'être comportementales.

---

## Correction

Suppression du scaler du chemin d'inférence, avec un commentaire renvoyant à cet incident :

```python
# NE PAS appliquer _scaler ici. Le modèle retenu est un XGBClassifier,
# entraîné sur les variables BRUTES (rapport TPRE622, section 5.3.3).
prediction = int(_model_substitution.predict(X)[0])
```

Vérification après correction, sur les quatre cas de référence :

| Liaison | Attendu | Obtenu |
|---|---|---|
| Paris → Marseille, 800 km | 1 | **1** (p = 1.000) |
| Paris → New York, 5 800 km | 0 | **0** (p = 0.008) |
| Lyon → Dijon, 180 km | 0 | **0** (p = 0.000) |
| Berlin → Munich, 600 km | 1 | **1** (p = 1.000) |

F1-macro sur 20 000 trajets : **0.997**.

---

## Mesures préventives

1. **`ml/tests/test_inference_contract.py`** — les quatre cas de référence sont désormais des tests paramétrés. Toute régression sur une valeur prédite, et non seulement sur un code HTTP, fait échouer la chaîne.
2. **`test_standardiser_a_l_inference_annule_la_detection`** — fige le contrat : si quelqu'un réintroduit le scaler, ce test échoue avec un message explicite.
3. **`test_permuter_deux_variables_degrade_les_predictions`** — le modèle consomme un tableau positionnel ; permuter deux colonnes ne lève aucune erreur mais fausse tout. Le risque est maintenant couvert.
4. **Le scaler reste chargé** au démarrage : il fait partie des artefacts et alimente `/health`. Il n'est simplement plus appliqué au XGBoost.

---

## Enseignement

Un test qui vérifie un code HTTP ne teste pas un modèle. Un modèle se teste sur ses **valeurs de sortie**, contre des cas de référence documentés. C'est exactement ce que demande la compétence C12 en parlant de « règles de validation […] des étapes d'évaluation et de validation du modèle » — et cet incident montre pourquoi.
