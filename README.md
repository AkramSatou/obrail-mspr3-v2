> **Fork de travail — Akram SATOU**
> Projet réalisé en équipe dans le cadre de la MSPR TPRE532 : Akram SATOU, Aymen GHARBI,
> Sumunh'Mvil M. POATY TENGO, Adam SAWI. Dépôt d'origine : <https://github.com/AdamSawi/obrail-mspr3>.
> Ce fork porte les évolutions réalisées par Akram SATOU en vue de la certification
> **Développeur en Intelligence Artificielle (RNCP 37827)** : authentification JWT et
> gestion des rôles, tests associés, documentation de sécurité.

# ObRail Europe — MSPR TPRE532

> Observatoire ferroviaire européen — Mise en production d'une solution IA  
> EPSI Lyon — Bachelor Développeur IA — Bloc E6.3 RNCP36581 — 2025/2026

Dépôt GitHub : https://github.com/AdamSawi/obrail-mspr3

---

## Présentation

ObRail Europe est un observatoire indépendant spécialisé dans l'analyse des flux ferroviaires européens et la promotion du transport bas-carbone. Ce projet industrialise une solution applicative complète autour d'un dataset de **142 411 trajets ferroviaires** couvrant l'Allemagne, l'Espagne, la France et l'Italie.

La solution expose une API REST FastAPI connectée à une base PostgreSQL, une interface React, des modèles IA de prédiction (substitution train/avion, régression CO2), et une supervision complète via Prometheus, Grafana et Loki.

---

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et en cours d'exécution
- Git
- Ports disponibles : 5432, 8000, 5173, 3001, 9090, 8081, 3100

---

## Lancement en une seule commande

Depuis la racine du dépôt :

```bash
docker compose -f docker/docker-compose.yml up --build
```

Cette commande :
1. Construit les images backend et frontend
2. Démarre PostgreSQL et attend qu'il soit prêt
3. Importe automatiquement les 142 411 trajets dans la base
4. Démarre l'API FastAPI
5. Démarre le frontend React
6. Démarre Prometheus, Grafana et Loki

**Première fois : prévoir 3 à 5 minutes.** Les relances suivantes démarrent en moins d'une minute.

Pour relancer sans reconstruire :

```bash
docker compose -f docker/docker-compose.yml up
```

Pour arrêter :

```bash
docker compose -f docker/docker-compose.yml down
```

---

## Services disponibles

| Service | URL | Identifiants |
|---|---|---|
| Frontend | http://localhost:5173 | — |
| API REST | http://localhost:8000 | — |
| Documentation Swagger | http://localhost:8000/docs | — |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Adminer (PostgreSQL) | http://localhost:8081 | voir ci-dessous |

**Connexion Adminer :**
- Système : PostgreSQL
- Serveur : db
- Utilisateur : obrail
- Mot de passe : obrail
- Base de données : obrail

---

## Authentification

Depuis l'ajout de la gestion des accès, les routes de données et d'inférence exigent un jeton **JWT**.

### Comptes de démonstration

Créés automatiquement au démarrage par `backend/seed_users.py` :

| Identifiant | Mot de passe | Rôle | Accès |
|---|---|---|---|
| `viewer` | `viewer123` | viewer | Consultation des trajets et des statistiques |
| `admin` | `admin123` | admin | Consultation + routes de prédiction `/predict/*` |

Ces identifiants sont surchargeables par variables d'environnement (`OBRAIL_VIEWER_USER`, `OBRAIL_ADMIN_PASSWORD`, etc.) et ne servent qu'à la démonstration locale.

### Se connecter

Depuis **Swagger** : ouvrir <http://localhost:8000/docs>, cliquer sur **Authorize**, saisir un compte ci-dessus. Toutes les routes deviennent testables depuis l'interface.

Depuis le **frontend** : un écran de connexion s'affiche au premier accès. Le rôle est rappelé en haut de page, avec un bouton de déconnexion.

En **ligne de commande** :

```bash
curl -s -X POST http://localhost:8000/auth/login -d "username=viewer&password=viewer123"
```

### Routes restées publiques

`GET /`, `GET /health` et `GET /metrics` ne demandent pas de jeton : le healthcheck Docker, le badge d'état du frontend et le scraping Prometheus les appellent avant toute connexion. Justification détaillée dans [docs/SECURITY.md](docs/SECURITY.md).

> Le détail du modèle d'authentification, la matrice des droits et la couverture du Top 10 OWASP sont documentés dans **[docs/SECURITY.md](docs/SECURITY.md)**.

---

## Agent IA (C8 — RNCP 37827)

L'interface intègre un assistant conversationnel ferroviaire accessible depuis l'onglet **Assistant IA** (compte `admin` requis).

### Fonctionnement

L'agent implémente une boucle `réfléchir → agir → observer` sans LangChain. À chaque message, il choisit parmi quatre outils métier (statistiques, recherche de trajets, substitution avion, CO2) et retourne une réponse factuelle basée **uniquement** sur les données ObRail — jamais une estimation inventée.

### Modes LLM

| Mode | Description | Variable |
|---|---|---|
| `auto` (défaut) | Ping OpenRouter → Ollama → rejeu | `OBRAIL_LLM_PROVIDER=auto` |
| `ollama` | Instance Ollama locale (modèle `qwen3:8b`) | `OBRAIL_LLM_PROVIDER=ollama` |
| `openrouter` | API distante (modèle `meta-llama/llama-3.1-8b-instruct:free`) | `OBRAIL_LLM_PROVIDER=openrouter` |
| `rejeu` | Démonstration hors-ligne, traces pré-enregistrées | `OBRAIL_LLM_PROVIDER=rejeu` |

### Démonstration hors-ligne (recommandé en soutenance)

```bash
# Lancer avec le mode rejeu pour ne pas dépendre du réseau
OBRAIL_LLM_PROVIDER=rejeu docker compose -f docker/docker-compose.yml up --build

# Tester directement via curl
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=admin123" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8000/agent/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Combien de trajets electriques recense-t-on en France ?"}' | python -m json.tool
```

Documentation complète : **[docs/AGENT_IA.md](docs/AGENT_IA.md)**

---

## Vérification rapide

```bash
# Santé de l'API (doit afficher status ok et rows 142411)
curl http://localhost:8000/health

# Liste des trajets (première page)
curl "http://localhost:8000/trajets?page_size=5"

# Statistiques CO2 par pays
curl http://localhost:8000/stats/volumes
```

---

## Tests automatisés

### Tests backend (Pytest)

```bash
pip install psycopg2-binary python-logging-loki
python -m pytest backend/tests/ -v
# Résultat attendu : ~102 passed (tests données + auth + agent chat + agent rejeu)
```

### Tests du pipeline de modélisation

```bash
python -m pytest ml/tests -v
# Résultat attendu : 27 passed, 3 xfailed (incident 003 en cours)
```

Ces tests valident le jeu de données, les étapes de préparation, d'entraînement et
d'évaluation du modèle. Ils tournent en CI dans le job `model`, **avant** la
publication des images : un modèle qui ne passe pas ses garde-fous n'est pas livré.
Détail des cas dans [ml/README.md](ml/README.md).

### Tests E2E (Playwright)

Le frontend doit être démarré avant de lancer les tests E2E.

```bash
pip install playwright
playwright install chromium
python -m pytest frontend/tests/test_e2e.py -v
# Résultat attendu : 10 passed (7 tests initiaux + 3 tests onglets/agent)
```

---

## Structure du projet

```
obrail-mspr3/
├── backend/              API FastAPI, modèles ORM, tests Pytest
│   ├── app/
│   │   ├── main.py       Routes API, modèles IA, monitoring, agent
│   │   ├── database.py   Connexion SQLAlchemy
│   │   ├── models.py     Modèle Trip (24 colonnes)
│   │   ├── security.py   JWT, hachage bcrypt, dépendances d'autorisation
│   │   └── agent/        Boucle agent, fournisseurs LLM, outils, rejeu
│   ├── tests/            ~102 tests (données, auth, agent chat, agent rejeu)
│   ├── seed.py           Import CSV → PostgreSQL
│   └── seed_users.py     Création idempotente des comptes applicatifs
├── frontend/             Interface React/Vite (3 onglets : tableau, trajets, assistant)
│   └── tests/            10 tests E2E Playwright
├── data/                 Dataset eu_trips_v2.csv (142 420 lignes)
├── models/               Modèles IA (.joblib)
├── docker/               docker-compose.yml (8 services)
├── monitoring/           Prometheus, Grafana, Loki, Promtail
├── scripts/              entrypoint.sh, preuve_postgresql.sh
├── ml/                   Validation des données et tests du modèle
├── docs/                 SECURITY.md, AGENT_IA.md et journal des incidents
├── .github/workflows/    Pipeline CI/CD GitHub Actions
└── RAPPORT_TECHNIQUE.md  Documentation technique complète
```

---

## Pipeline CI/CD

Le pipeline GitHub Actions se déclenche sur chaque push et pull request avec 4 jobs :

- **Backend** : installe les dépendances, seed PostgreSQL, lance Pytest
- **Frontend** : installe Node.js, lance les tests JS, build Vite
- **Docker** : valide le docker-compose et construit les images
- **E2E** : lance la stack complète et exécute les tests Playwright

---

## Livraison continue — images publiées

Après le succès de **tous** les tests (backend, frontend, E2E) et de la construction des images, le job `publish` de la CI pousse automatiquement les images sur **GitHub Container Registry**.

| Image | Tags |
|---|---|
| `ghcr.io/akramsatou/obrail-backend` | `latest`, `<sha du commit>` |
| `ghcr.io/akramsatou/obrail-frontend` | `latest`, `<sha du commit>` |

La publication n'a lieu que sur la branche `main` : une pull request est testée et construite, mais ne publie rien.

Récupérer une image sans cloner ni reconstruire :

```bash
docker pull ghcr.io/akramsatou/obrail-backend:latest
docker pull ghcr.io/akramsatou/obrail-frontend:latest
```

Le double tag `latest` + SHA permet de remonter de n'importe quelle image déployée au commit exact qui l'a produite.

> Les images d'un dépôt public sont privées par défaut sur GHCR. Après la première publication, les rendre publiques depuis l'onglet **Packages** du profil GitHub pour qu'un évaluateur puisse les récupérer.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic |
| Base de données | PostgreSQL 15 |
| Frontend | React, Vite |
| IA | XGBoost, scikit-learn, joblib, agent LLM (OpenRouter / Ollama) |
| Conteneurisation | Docker, Docker Compose |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus, Grafana, Loki, Promtail |
| Tests | Pytest, Playwright |

---

## Documentation

| Document | Contenu |
|---|---|
| [RAPPORT_TECHNIQUE.md](./RAPPORT_TECHNIQUE.md) | Documentation technique complète |
| [docs/SECURITY.md](docs/SECURITY.md) | Authentification, matrice des droits, OWASP Top 10 |
| [docs/AGENT_IA.md](docs/AGENT_IA.md) | Agent IA — architecture, outils, modes LLM, rejeu (C8) |
| [docs/INCIDENT-002-scaler-inference.md](docs/INCIDENT-002-scaler-inference.md) | Post-mortem correctif StandardScaler XGBoost |
