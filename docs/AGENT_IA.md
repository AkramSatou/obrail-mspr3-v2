# Agent IA ObRail — Documentation technique

> **Compétence C8 — RNCP 37827 :** Paramétrer un service d'intelligence artificielle  
> **Auteur :** Akram SATOU — Soutenance septembre 2026

---

## 1. Présentation

L'agent IA ObRail est un service conversationnel intégré au backend FastAPI. Il permet aux administrateurs de poser des questions en langage naturel sur les données ferroviaires européennes et obtient des réponses factuelles en invoquant les outils métier disponibles — sans jamais inventer un chiffre, une distance ou une probabilité.

**Route principale :** `POST /agent/chat` (rôle `admin` requis)  
**Route d'info :** `GET /agent/info` (rôle `admin` requis)

---

## 2. Architecture — boucle réfléchir → agir → observer

L'agent implémente manuellement le cycle `ReAct` sans LangChain (contrainte D3) :

```
Utilisateur → POST /agent/chat
                │
                ▼
         executer_boucle()          ← boucle.py
                │
    ┌── Itération (max 5) ──────────────────────────────────┐
    │                                                        │
    │  1. Préparer messages (système + historique + user)   │
    │  2. LLM.completer(messages, tools=_SCHEMAS_OUTILS)    │
    │  3. Si tool_calls → exécuter chaque outil → loop      │
    │  4. Si pas de tool_calls → réponse finale             │
    │                                                        │
    └────────────────────────────────────────────────────────┘
                │
                ▼
         Retour JSON : reponse, session_id, mode, trace, …
```

### Garde-fous

| Paramètre | Valeur par défaut | Variable d'environnement |
|---|---|---|
| Itérations max | 5 | `OBRAIL_AGENT_MAX_ITERATIONS` |
| Timeout total | 120 s | `OBRAIL_AGENT_TIMEOUT_S` |
| Mémoire de session | 20 messages | — |

---

## 3. Outils disponibles (D4 — appels internes, jamais HTTP)

Les outils appellent directement les fonctions Python internes ; ils ne passent pas par les routes HTTP de l'API.

| Nom de l'outil | Fonction Python | Description |
|---|---|---|
| `obtenir_statistiques` | `app.agent.outils` | Statistiques agrégées (trajets, km, CO2) filtrable par pays/type |
| `rechercher_trajets` | `app.agent.outils` | Recherche de trajets avec filtres (origine, destination, pays) — retourne les paramètres réels du trajet dont `consommation_energy` et `gco2_per_kwh`, requis par `estimer_co2_futur` |
| `predire_substitution_avion` | `app.agent.outils` | Prédit si un trajet est substituable à l'avion (modèle XGBoost) |
| `estimer_co2_futur` | `app.agent.outils` | Régression CO2 sur une distance donnée |

Les schémas sont déclarés au format OpenAI Function Calling et transmis à tous les fournisseurs.

---

## 4. Fournisseurs LLM configurables

La sélection du fournisseur est déterminée par la variable `OBRAIL_LLM_PROVIDER` (valeur par défaut : `auto`).

| Valeur | Comportement |
|---|---|
| `openrouter` | API distante OpenRouter (modèle `meta-llama/llama-3.1-8b-instruct:free`) |
| `ollama` | Instance Ollama locale sur `http://localhost:11434` (modèle `qwen3:8b`) |
| `rejeu` | Mode hors-ligne : lit les traces pré-enregistrées dans `backend/app/agent/rejeu/` |
| `auto` | Ping OpenRouter (1,5 s timeout) → Ollama → rejeu ; résultat mis en cache 45 s |

### Mode auto-détection (D2)

```
auto:
  1. Tenter OpenRouter (timeout 1,5 s)
     → succès : utiliser OpenRouter
  2. Tenter Ollama GET /tags (timeout 1,5 s)
     → succès : utiliser Ollama
  3. Utiliser rejeu (garanti hors-ligne)

Cache : 45 secondes (évite 3 pings par requête)
```

### Clé API OpenRouter (D7 — confidentialité)

La clé est lue depuis la variable d'environnement `OPENROUTER_API_KEY`.  
**Elle n'est jamais commitée** : elle est dans `.gitignore` et les logs ne l'exposent pas.  
Seules les données ferroviaires publiques sont transmises au LLM — aucune donnée personnelle, aucun jeton.

---

## 5. Mode rejeu — démonstration hors-ligne (D — étape E)

Le mode rejeu permet de démontrer l'agent sans connexion réseau ni Ollama, en rejoignant des échanges pré-enregistrés.

### Algorithme de correspondance

```
1. Normaliser la question (minuscules, sans accents, sans ponctuation)
2. Correspondance exacte (MD5) → retourner si trouvée
3. Score Jaccard (mots communs / mots totaux) sur tous les fichiers
4. Si max(score) ≥ 0,30 → retourner le meilleur match
5. Sinon → lever ValueError  ← §0.6-1 : jamais de réponse inventée
```

### Cinq questions pré-enregistrées pour la soutenance

| Fichier | Question |
|---|---|
| `q1_stats_electrique_france.json` | Combien de trajets électriques recense-t-on en France ? |
| `q2_substitution_paris_marseille.json` | Le trajet Paris-Marseille en train est-il substituable à l'avion ? |
| `q3_co2_400km_diesel.json` | Quelles émissions de CO2 pour un trajet de 400 km en diesel ? |
| `q4_stats_allemagne.json` | Quelles sont les statistiques ferroviaires pour l'Allemagne ? |
| `q5_stats_diesel_europe.json` | Quelles sont les statistiques des trajets diesel en Europe ? |

### Enregistrement de nouvelles traces

Définir `OBRAIL_AGENT_ENREGISTRER=1` avant un appel réel (Ollama ou OpenRouter) :
les échanges sont automatiquement sauvegardés dans `backend/app/agent/rejeu/`.

---

## 6. Sécurité des routes (D5)

Les routes `/agent/chat` et `/agent/info` exigent le rôle `admin` via `require_role(ROLE_ADMIN)`.

- Un utilisateur `viewer` reçoit un **403 Forbidden** avant que le moindre outil ne soit invoqué.
- Le viewer ne peut pas accéder indirectement aux modèles de prédiction via l'agent.
- L'interface frontend vérifie le rôle côté client pour afficher un message d'accès refusé sans appel réseau inutile (confort UX, pas une garde de sécurité — la vraie garde est côté serveur).

---

## 7. Métriques Prometheus (D — étape C)

Cinq séries exposées sur `GET /metrics` :

| Métrique | Type | Description |
|---|---|---|
| `obrail_agent_requests_total` | counter | Nombre total de requêtes par statut (succès/erreur) |
| `obrail_agent_tool_calls_total` | counter | Appels d'outils par nom d'outil |
| `obrail_agent_duration_seconds` | histogram | Latence de la boucle (buckets 0,5 s → 300 s) |
| `obrail_agent_iterations` | histogram | Nombre d'itérations par échange |
| `obrail_agent_up` | gauge | 1 si l'agent a répondu au moins une requête, 0 sinon |

Trois panneaux Grafana ajoutés dans `monitoring/grafana/dashboards/obrail-api.json` :
requêtes totales, appels d'outils par outil (rate 5 m), latence P95.

---

## 8. Logs structurés — Loki

Toutes les traces passent par le logger `obrail.agent` (hiérarchie : `obrail.agent.boucle`, `obrail.agent.selection`, `obrail.agent.rejeu`). Le handler Loki est attaché dans `main.py` au démarrage.

Chaque échange logué contient : `session_id`, `fournisseur`, `durée_ms`, `itérations`, `outils`.

---

## 9. Mémoire de session

Les échanges sont conservés en mémoire du processus dans le dictionnaire `_SESSIONS` (clé = `session_id` UUID). La fenêtre est de 20 messages maximum par session. Aucune persistence en base de données.

Le `session_id` est retourné dans chaque réponse et doit être renvoyé par le client pour maintenir le contexte conversationnel.

---

## 10. Tests automatisés

| Fichier | Tests | Couverture |
|---|---|---|
| `backend/tests/test_agent_chat.py` | 14 | Contrôle d'accès 401/403, validation 422, nominaux, timeouts, max_iterations, rejeu, /agent/info |
| `backend/tests/test_agent_rejeu.py` | 13 | Normalisation, similarité Jaccard, lecture fichiers, cycle enregistrer→rejouer, intégration route |
| `frontend/src/services/api.test.js` | +3 | `envoyerMessageAgent` (POST avec/sans session_id), `fetchAgentInfo` |
| `frontend/tests/test_e2e.py` | +3 | Tablist affiché, viewer→accès refusé, admin→interface chat |

---

## 11. Variables d'environnement de référence

```bash
# Fournisseur LLM : auto | openrouter | ollama | rejeu
OBRAIL_LLM_PROVIDER=auto

# Clé OpenRouter (ne pas committer)
OPENROUTER_API_KEY=sk-or-...

# URL Ollama (défaut : http://localhost:11434)
OBRAIL_OLLAMA_BASE_URL=http://localhost:11434

# Modèles
OBRAIL_MODEL_OLLAMA=qwen3:8b
OBRAIL_MODEL_OPENROUTER=meta-llama/llama-3.1-8b-instruct:free

# Garde-fous
OBRAIL_AGENT_MAX_ITERATIONS=5
OBRAIL_AGENT_TIMEOUT_S=120

# Enregistrement automatique des échanges pour le mode rejeu
OBRAIL_AGENT_ENREGISTRER=1  # activer uniquement pendant la session d'enregistrement
```
