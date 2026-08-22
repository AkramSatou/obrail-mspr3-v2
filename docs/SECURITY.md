# Sécurité de l'API ObRail Europe

Document de référence sur l'authentification, l'autorisation et la couverture des risques OWASP.

---

## 1. Modèle d'authentification

L'API utilise des **JWT (RFC 7519)** signés en HS256, transportés par l'en-tête HTTP `Authorization: Bearer <token>`.

Deux jetons distincts sont émis à la connexion :

| Jeton | Durée de vie | Rôle |
|---|---|---|
| **access** | 30 min (`ACCESS_TOKEN_EXPIRE_MINUTES`) | Présenté à chaque appel protégé |
| **refresh** | 7 jours (`REFRESH_TOKEN_EXPIRE_DAYS`) | Sert uniquement à obtenir un nouvel `access` via `POST /auth/refresh` |

Le champ `type` est inscrit dans la charge utile et vérifié à l'usage : un jeton de rafraîchissement ne peut pas ouvrir une route protégée, et un jeton d'accès ne peut pas servir à renouveler la session. Les deux cas sont couverts par des tests.

### Renouvellement

Le frontend intercepte les réponses `401`, tente **une** fois un renouvellement silencieux via `/auth/refresh`, puis rejoue la requête d'origine. Si le renouvellement échoue, la session est purgée et l'écran de connexion réapparaît.

Le compte est revalidé en base à chaque renouvellement : désactiver un utilisateur (`is_active = false`) le révoque au plus tard à l'expiration de son jeton d'accès courant.

---

## 2. Rôles et matrice d'accès

| Rôle | Périmètre |
|---|---|
| `viewer` | Consultation des données ferroviaires |
| `admin` | Consultation + appel des modèles d'inférence |

| Route | Anonyme | viewer | admin |
|---|:--:|:--:|:--:|
| `GET /` | oui | oui | oui |
| `GET /health` | oui | oui | oui |
| `GET /metrics` | oui | oui | oui |
| `POST /auth/login` | oui | oui | oui |
| `POST /auth/refresh` | oui | oui | oui |
| `GET /auth/me` | 401 | oui | oui |
| `GET /trajets` | 401 | oui | oui |
| `GET /trajets/{id}` | 401 | oui | oui |
| `GET /stats/volumes` | 401 | oui | oui |
| `POST /predict` | 401 | **403** | oui |
| `POST /predict/substitution` | 401 | **403** | oui |
| `POST /predict/co2` | 401 | **403** | oui |
| `POST /agent/chat` | 401 | **403** | oui |
| `GET /agent/info` | 401 | **403** | oui |

La distinction **401 / 403** est volontaire : `401` signifie « non authentifié », `403` « authentifié mais non habilité ».

### Règle D5 — isolation de l'agent IA

Les routes `/agent/*` sont réservées au rôle `admin` via `require_role(ROLE_ADMIN)`. Cette règle est appliquée côté serveur avant toute exécution de la boucle agent :

- Un utilisateur `viewer` reçoit un `403 Forbidden` avant que le moindre outil ou modèle de prédiction ne soit invoqué.
- L'agent ne peut donc pas servir de vecteur d'accès indirect aux routes de prédiction (`/predict/*`) pour un compte viewer.
- L'interface frontend affiche un message d'accès refusé côté client (confort UX) — ce n'est pas la garde de sécurité réelle, qui reste côté serveur.

### Pourquoi trois routes restent publiques

Ce n'est pas un oubli, c'est un choix contraint et assumé :

- **`GET /health`** — appelé par le `healthcheck` Docker et par le badge d'état du frontend, tous deux **avant** toute connexion. Le protéger empêcherait l'orchestrateur de démarrer la stack. La réponse ne contient aucune donnée métier : uniquement un statut et un compteur de lignes.
- **`GET /metrics`** — scrapé par Prometheus toutes les 15 s. Prometheus ne porte pas de jeton dans cette configuration. En production, cet endpoint serait exposé sur un réseau interne et non publié.
- **`GET /`** — page d'accueil qui liste les routes, équivalente à la documentation.

---

## 3. Stockage des mots de passe

Les mots de passe ne sont **jamais** stockés en clair. Seule leur empreinte **bcrypt** (sel unique généré automatiquement) est conservée dans la colonne `users.hashed_password`.

La vérification se fait via `bcrypt.checkpw`, qui compare en temps constant — pas de fuite d'information par mesure du temps de réponse.

---

## 4. Non-énumération des comptes

`POST /auth/login` renvoie **exactement le même message et le même code** que l'utilisateur soit inconnu, que le mot de passe soit faux, ou que le compte soit désactivé. Un attaquant ne peut donc pas déduire quels identifiants existent. Un test le vérifie explicitement.

---

## 5. Gestion des secrets

| Secret | Où | Jamais |
|---|---|---|
| `JWT_SECRET_KEY` | Variable d'environnement, injectée par Docker Compose ou la CI | En dur dans le code, ni committé |
| Mots de passe de démo | Variables d'environnement lues par `seed_users.py` | En dur dans le script |
| Identifiants PostgreSQL | Variables d'environnement | — |

`.gitignore` exclut `.env` et `.env.*` tout en conservant `.env.example`, qui documente les variables sans en révéler les valeurs.

Pour générer un secret de production :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 6. Couverture du Top 10 OWASP (2021)

| Risque | État | Mesure en place / écart assumé |
|---|---|---|
| **A01 — Broken Access Control** | Couvert | Authentification JWT obligatoire sur toutes les routes de données et d'inférence. Autorisation par rôle sur `/predict/*` via la dépendance `require_role`. Distinction 401/403. Tests dédiés pour l'accès anonyme, le mauvais rôle et le mauvais type de jeton |
| **A02 — Cryptographic Failures** | Partiel | Mots de passe hachés bcrypt, JWT signé HS256, secret hors du code. **Écart : pas de HTTPS** — la stack tourne en local pour la démonstration. En production, terminaison TLS par un reverse proxy |
| **A03 — Injection** | Couvert | Accès aux données exclusivement via l'ORM SQLAlchemy, requêtes paramétrées, aucune concaténation de SQL. Validation stricte des entrées par Pydantic (types, bornes, énumérations) |
| **A04 — Insecure Design** | Couvert | Séparation des rôles dès la conception, deux types de jetons aux durées de vie distinctes, révocation par `is_active`, principe du moindre privilège (`viewer` par défaut) |
| **A05 — Security Misconfiguration** | Partiel | CORS restreint aux origines déclarées, dataset et modèles montés en lecture seule, droits GitHub Actions limités à la lecture, erreurs 500 loggées côté serveur mais renvoyées sans trace interne. **Écart : Grafana en `admin/admin`** — acceptable en démonstration locale |
| **A06 — Vulnerable Components** | Partiel | Toutes les dépendances Python épinglées à une version exacte. **Écart : pas d'analyse automatisée** — Dependabot ou `pip-audit` serait l'étape suivante |
| **A07 — Identification & Authentication Failures** | Couvert | Jetons à durée de vie courte, renouvellement explicite, comptes désactivables, messages d'erreur non discriminants. Limitation en mémoire : 5 tentatives échouées par identifiant ou par adresse IP entraînent un blocage de 15 minutes (HTTP 429). Seuils configurables via `LOGIN_MAX_ATTEMPTS` et `LOGIN_LOCKOUT_SECONDS`. |
| **A08 — Software & Data Integrity Failures** | Partiel | Images construites **et publiées** par la CI à partir de Dockerfiles versionnés, uniquement après succès des tests backend, frontend, E2E et de la construction. Chaque image porte le SHA du commit qui l'a produite, ce qui rend la traçabilité artefact → source exacte. Droit d'écriture sur le registre limité au seul job `publish` (moindre privilège). Dépendances épinglées. **Écart : pas de signature d'image (cosign)** |
| **A09 — Security Logging & Monitoring Failures** | Couvert | Succès et échecs d'authentification journalisés avec l'identifiant tenté, jamais le mot de passe. Logs centralisés dans Loki, métriques Prometheus, tableau de bord Grafana |
| **A10 — Server-Side Request Forgery** | Couvert | L'agent IA n'accepte que des appels aux fonctions Python internes (contrainte D4 — pas d'URL dynamique issue du message utilisateur). L'URL du fournisseur LLM est configurée par variable d'environnement, pas par l'entrée utilisateur |

**Lecture honnête de ce tableau :** cinq risques sont couverts, quatre partiellement avec un écart identifié et justifié, un est sans objet. Les écarts restants relèvent tous d'un déploiement en production réelle, hors du périmètre d'une démonstration locale — mais ils sont connus, pas subis.

---

## 7. Conformité RGPD

Les journaux d'authentification enregistrent l'identifiant utilisé et le résultat de la tentative. Ils **n'enregistrent jamais** le mot de passe, ni le contenu des jetons.

L'identifiant est une donnée à caractère personnel au sens du RGPD : sa conservation relève de l'intérêt légitime en matière de sécurité, avec une durée de rétention à définir dans le registre des traitements.

---

## 8. Vérifier soi-même

```bash
# 1. Route protégée sans jeton -> 401
curl -i http://localhost:8000/trajets

# 2. Connexion -> récupération du jeton
curl -s -X POST http://localhost:8000/auth/login \
  -d "username=viewer&password=viewer123" | tee /tmp/token.json

# 3. Même route avec jeton -> 200
TOKEN=$(python -c "import json;print(json.load(open('/tmp/token.json'))['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/trajets?page_size=1"

# 4. Route admin avec un jeton viewer -> 403
curl -i -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"distance_km":800,"duration_minutes":195,"n_stops":3,"co2_estime":450000,"consommation_totale":16000,"type_train":"electric","country":"FR"}' \
  http://localhost:8000/predict/substitution
```

Depuis Swagger (`http://localhost:8000/docs`), le bouton **Authorize** fait la même chose sans ligne de commande — pratique pour une démonstration devant un jury.
