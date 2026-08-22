# INCIDENT-004 — L'agent inventait les paramètres énergétiques pour les questions CO2

| | |
|---|---|
| **Sévérité** | Majeure — résultats CO2 inventés, incohérents d'une session à l'autre |
| **Statut** | **Résolu** |
| **Composant** | `backend/app/agent/outils.py` (`rechercher_trajets`), `backend/app/agent/boucle.py` (`CONSIGNE_SYSTEME`) |
| **Détecté par** | Usage manuel via le chat (question "émissions CO2 Paris → Lyon") |
| **Détecté le** | 17/08/2026 |
| **Résolu le** | 17/08/2026 |

---

## Symptôme observé

Lors d'une question en langage naturel du type **"Quelles sont les émissions CO2 du trajet Paris → Lyon ?"**, l'agent répondait avec des chiffres inventés :

- Les valeurs de CO2 variaient sans raison d'une session à l'autre pour la même liaison.
- Des paramètres techniques (`consommation_energy`, `gco2_per_kwh`) apparaissaient dans les arguments de l'outil sans jamais provenir de la base de données.
- La réponse contredisait frontalement la consigne système : *"Tu n'inventes jamais un chiffre"*.

Exemple d'appel d'outil anormal observé :

```json
{
  "name": "estimer_co2_futur",
  "arguments": {
    "distance_km": 460.0,
    "consommation_energy": 0.033,
    "gco2_per_kwh": 58.0,
    ...
  }
}
```

Ces deux valeurs (`0.033` et `58.0`) ne correspondent à aucune liaison de la base — le modèle les avait inventées.

---

## Diagnostic

### Cause racine

L'outil `estimer_co2_futur` (`outils.py`, ~ligne 309) exige en paramètres obligatoires `consommation_energy` et `gco2_per_kwh`. Ces valeurs sont propres à chaque trajet réel (type de traction, pays) et stockées dans la table `trips` (colonnes `nullable=False`).

L'outil `rechercher_trajets` (même fichier, ~ligne 124) interrogeait bien la base de données mais son dict de retour **n'incluait pas** ces deux colonnes, alors qu'elles existent dans le modèle `Trip` et sont toujours non nulles.

Résultat : même quand le LLM appelait correctement `rechercher_trajets` d'abord, il ne recevait jamais `consommation_energy` ni `gco2_per_kwh`. Pour pouvoir appeler `estimer_co2_futur` — que la consigne lui imposait d'utiliser —, il n'avait d'autre choix que de les inventer.

### Facteurs aggravants

1. **Consigne système insuffisante** : `CONSIGNE_SYSTEME` (`boucle.py`) interdisait d'inventer des chiffres mais ne mentionnait pas explicitement l'obligation d'appeler `rechercher_trajets` en premier pour les liaisons nommées.

2. **Description de l'outil ambiguë** : `SCHEMA_ESTIMER_CO2_FUTUR` décrivait `consommation_energy` et `gco2_per_kwh` comme de simples paramètres numériques, sans préciser qu'ils devaient provenir d'un appel préalable à `rechercher_trajets`.

3. **Absence de test de contrat** : aucun test ne vérifiait que `rechercher_trajets` retournait ces deux champs — la régression aurait pu passer inaperçue en CI.

---

## Correction

### 1. `backend/app/agent/outils.py` — `rechercher_trajets`

Ajout de `consommation_energy` et `gco2_per_kwh` au dict retourné pour chaque trajet :

```python
"consommation_energy": float(row.consommation_energy),
"gco2_per_kwh": float(row.gco2_per_kwh),
```

Mise à jour de la description de `SCHEMA_RECHERCHER_TRAJETS` pour lister ces champs et indiquer que l'outil doit être appelé en premier pour toute liaison nommée.

### 2. `backend/app/agent/outils.py` — `SCHEMA_ESTIMER_CO2_FUTUR`

- Description de l'outil mise à jour : signale explicitement qu'il s'agit d'une **projection de scénario réseau** (distincte d'une estimation instantanée par facteur kilométrique), et que `consommation_energy` / `gco2_per_kwh` doivent venir de `rechercher_trajets`.
- Descriptions des deux paramètres enrichies avec la même précision.
- Valeur `label` retournée par la fonction mise à jour pour afficher "Projection de scénario réseau" dans la réponse du chat, évitant la confusion avec le calculateur frontend (badge LOCAL, facteur ADEME).

### 3. `backend/app/agent/boucle.py` — `CONSIGNE_SYSTEME`

Ajout de la règle explicite :

> Pour toute question portant sur une liaison nommée (ville, gare, ligne), appelle `rechercher_trajets` EN PREMIER pour obtenir les paramètres réels du trajet. Si aucun trajet ne correspond, dis-le clairement — n'appelle jamais `estimer_co2_futur` avec des valeurs supposées ou inventées.

---

## Reproduction / vérification

**Avant correction** — pour reproduire l'état défaillant :
1. Retirer `consommation_energy` et `gco2_per_kwh` du dict de `rechercher_trajets`
2. Poser la question `"Quelles sont les émissions CO2 du trajet Paris → Lyon ?"` en mode Ollama ou OpenRouter
3. Observer dans la trace JSON des arguments inventés pour `estimer_co2_futur`

**Après correction** — pour vérifier :
```bash
pytest backend/tests/test_agent_outils.py::test_rechercher_trajets_retourne_parametres_energetiques -v
pytest backend/tests/test_agent_outils.py::test_rechercher_trajets_parametres_energetiques_valeurs_exactes -v
pytest backend/tests/test_agent_outils.py::test_consigne_systeme_contient_regle_rechercher_trajets_en_premier -v
```

Ces trois tests échouent dans l'état pré-correction et passent après.

---

## Impact sur le mode rejeu

Aucun. Le mode rejeu lit des traces JSON pré-enregistrées sans exécuter les fonctions d'outil — l'ajout de champs dans `rechercher_trajets` est transparent pour les cinq questions pré-enregistrées.

---

## À dire au jury si la question tombe

Le bug illustre une **fracture de contrat entre outils** : l'outil B exigeait des données que l'outil A (censé les fournir) ne retournait pas. Le LLM comblait silencieusement le vide en inventant des valeurs — comportement précisément interdit par la consigne, mais rendu inévitable par la lacune du contrat.

La correction est **additive** (deux champs supplémentaires dans le dict de retour) et couverte par trois tests de régression.
