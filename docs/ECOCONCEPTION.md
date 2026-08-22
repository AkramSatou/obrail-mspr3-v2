# Éco-conception — ObRail (obrail-mspr3)

**Date** : 2026-08-13
**Responsable** : Akram — RNCP 37827, Bloc 1 Gérer les données
**Référentiels utilisés** :
- RGESN 2024 (Référentiel Général d'Écoconception de Services Numériques, DINUM)
- GreenIT 115 bonnes pratiques (Collectif GreenIT, 2022)
- Éco-index (EcoIndex.fr — modèle DOM/requêtes/poids de page)

---

## 1. Méthodologie

1. Mesure AVANT tout changement (baseline `npm run build` + mesure réseau API)
2. Identification des optimisations justifiées par la mesure
3. Implémentation, tests de non-régression, mesure APRÈS
4. Documentation par critère du référentiel

---

## 2. Mesures AVANT optimisation

### 2.1 Bundle frontend (`npm run build`, Vite 7.3.5)

| Fichier | Taille brute | Taille gzip |
|---------|-------------|-------------|
| `index.html` | 0.40 kB | 0.27 kB |
| `assets/index.css` | 6.90 kB | 2.22 kB |
| `assets/index.js` | 206.13 kB | 64.57 kB |
| **Total** | **213.43 kB** | **67.06 kB** |

### 2.2 Réponses API (sans compression)

| Endpoint | Taille brute | Compression | Cache-Control |
|----------|-------------|-------------|---------------|
| `GET /stats/volumes` | 810 octets | aucune | absent |
| `GET /trajets?page_size=12` | 5 485 octets | aucune | absent |
| `GET /health` | 401 octets | aucune | absent |

### 2.3 Comportement frontend

| Comportement | Valeur mesurée |
|--------------|----------------|
| Polling auth (setInterval) | 1 requête / **2 s** = 30 req/min/utilisateur |
| Requêtes au 1er chargement | 3 (health + stats + trajets) |
| Champs retournés par `/trajets` | 13 champs/item |
| Champs affichés dans l'UI | 9 champs/item |
| Champs inutilisés | 4 (`route_id`, `route_long_name`, `n_stops`, `arrival_minutes`) |

---

## 3. Optimisations appliquées

### 3.1 Compression GZip sur toutes les réponses JSON

**Fichiers modifiés** : `backend/app/main.py`

**Changement** :
```python
# Avant
app.add_middleware(CORSMiddleware, ...)

# Après
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)  # compresse > 500 octets
app.add_middleware(CORSMiddleware, ...)
```

**Référentiel** :
- RGESN R3.5 — *Compresser les ressources transférées*
- GreenIT BP-049 — *Compresser les flux HTTP*

**Impact mesuré** :

| Endpoint | Avant | Après (gzip) | Réduction |
|----------|-------|--------------|-----------|
| `/stats/volumes` | 810 o | 339 o | **−58 %** |
| `/trajets (12 items)` | 5 485 o | 539 o | **−90 %** |

**Vérification** : Headers retournés `Content-Encoding: gzip` confirmés.
Tests backend : 44 passed (aucune régression, le TestClient Starlette n'envoie pas
`Accept-Encoding: gzip` par défaut → les assertions JSON restent valides).

---

### 3.2 Cache HTTP pour `/stats/volumes`

**Fichiers modifiés** : `backend/app/main.py`

**Changement** :
```python
# Avant
return StatsVolumesResponse(...)

# Après
payload = StatsVolumesResponse(...)
return JSONResponse(
    content=jsonable_encoder(payload),
    headers={"Cache-Control": "private, max-age=300"},
)
```

**Justification** : Les statistiques globales (`total_trajets`, `by_country`, etc.)
sont calculées à partir d'un dataset statique (public.trips, 142 411 lignes non modifiées
en cours de session). Recalculer et refetcher ces données à chaque rendu de composant
est inutile. Un cache de 5 minutes (`max-age=300`) évite ~60 requêtes HTTP par heure
pour un utilisateur actif.

**Référentiel** :
- RGESN R4.2 — *Mettre en cache les données statiques ou peu changeantes*
- GreenIT BP-075 — *Utiliser les en-têtes Cache-Control*

**Impact** :
- 1re visite : 339 octets (gzip) transférés
- Visites suivantes (< 5 min) : **0 octet** (réponse depuis cache navigateur)
- Sur une session de 30 min avec navigation : économie de ~5 × 339 o = ~1.7 ko

---

### 3.3 Réduction du polling d'authentification

**Fichiers modifiés** : `frontend/src/main.jsx`

**Changement** :
```javascript
// Avant
const interval = setInterval(() => {
  setAuthenticated(isAuthenticated());
}, 2000);  // 30 fois par minute

// Après (éco-conception RGESN R1.8)
const interval = setInterval(() => {
  setAuthenticated(isAuthenticated());
}, 30000); // 2 fois par minute
```

**Justification** : Ce `setInterval` sert uniquement à détecter qu'un token a été
supprimé de `sessionStorage` (cas de déconnexion silencieuse). La vérification toutes
les 2 secondes génère 30 exécutions JavaScript/minute par onglet, pour une valeur
fonctionnelle nulle (la session dure 60 minutes par défaut). Passer à 30 secondes
détecte toujours une déconnexion dans les 30s, sans coût notable.

**Référentiel** :
- RGESN R1.8 — *Limiter les traitements JavaScript au strict nécessaire*
- GreenIT BP-007 — *Réduire les opérations DOM et les timers inutiles*

**Impact mesuré** :
| Métrique | Avant | Après | Réduction |
|----------|-------|-------|-----------|
| Exécutions JS/min (setInterval) | 30 | 2 | **−93 %** |
| Requêtes réseau/min | 0 (sessionStorage local) | 0 | N/A |
| CPU wakups/min | 30 | 2 | **−93 %** |

---

## 4. Tableau de synthèse AVANT / APRÈS

| Métrique | AVANT | APRÈS | Gain |
|----------|-------|-------|------|
| Bundle JS (gzip) | 64.57 kB | 64.57 kB | = (pas de code splitting justifié) |
| `/stats/volumes` (gzip) | 810 o (non compressé) | 339 o | **−58 %** |
| `/trajets 12 items` (gzip) | 5 485 o (non compressé) | 539 o | **−90 %** |
| Requêtes API sur cache /stats | 0 économie | ~5 req évitées/session 30min | |
| Exécutions setInterval/min | 30 | 2 | **−93 %** |

---

## 4b. Routes Agent IA (ajout post-étape C)

Les routes `/agent/chat` (POST) et `/agent/info` (GET) sont couvertes par le
`GZipMiddleware` existant (minimum_size=500 octets) — aucun changement de code nécessaire.

### Payload `/agent/chat`

| Cas | Taille brute estimée | Après gzip | Note |
|---|---|---|---|
| Mode rejeu (1 outil, trace simple) | ~800 o | ~340 o | Similaire à /stats/volumes |
| Mode direct (3 itérations, 2 outils) | ~3 500 o | ~900 o | Trace JSON complète avec arguments et résumés |
| Mode direct (5 itérations, réponse longue) | ~6 000 o | ~1 500 o | Cas observé en session qwen3:8b |

**GZip s'applique automatiquement** — la trace d'agent (champs `trace`, `reponse`, `session_id`, etc.)
dépasse systématiquement 500 octets, le seuil du middleware.

### Cache

`/agent/chat` ne reçoit **pas** d'en-tête `Cache-Control` — chaque question produit une réponse
différente. C'est intentionnel.

`/agent/info` retourne la configuration statique (fournisseur, modèle, outils). Une mise en cache
courte (30 s) serait justifiable mais n'est pas implémentée : la route est peu appelée
(1 fois au montage du composant AssistantIA).

### Fréquence d'appels — impact frontend

Avant la correction de l'étape correction-2 (2026-08-14) :
- `/agent/chat` : appelé uniquement à l'envoi de message (0 requête à vide)
- `/agent/info` : **non appelé** — badge mode absent avant premier message

Après correction :
- `/agent/info` : **1 appel au montage** de AssistantIA (ouverture onglet) — nécessaire pour
  afficher le badge de mode avant le premier message. Surcoût : 1 requête de ~200 o par ouverture
  d'onglet.

### Conformité référentielle

| Critère | Règle | Statut |
|---|---|---|
| RGESN R3.5 | Compresser les ressources transférées | Couvert via GZipMiddleware |
| RGESN R4.2 | Mettre en cache les données peu changeantes | `/agent/info` : non mis en cache (faible fréquence) |
| RGESN R1.8 | Limiter les requêtes JavaScript | 1 requête /agent/info à l'ouverture d'onglet, pas de polling |
| OWASP A10 | SSRF / injection côté serveur | Les outils (D4) n'effectuent aucun appel HTTP externe — que des requêtes SQL et appels ML locaux |

---

## 5. Recommandations non implémentées

### 5.1 Champs API inutilisés dans `/trajets` (recommandation C15)

L'API retourne 13 champs par trajet, mais l'UI n'en affiche que 9.
Les 4 champs non utilisés (`route_id`, `route_long_name`, `n_stops`, `arrival_minutes`)
représentent ~25 % de la payload JSON brute.

**Recommandation** : Ajouter un paramètre `?fields=` optionnel au endpoint `/trajets`
pour permettre la sélection des colonnes. Le frontend enverrait :
```
GET /trajets?fields=id,origin_stop_name,destination_stop_name,country,type_train,distance_km,duration_minutes,departure_minutes,kg_co2_emis
```
Gain estimé : réduction supplémentaire de ~25 % de la payload,
soit ~135 octets/requête (après gzip).

Non implémentée dans cette itération : nécessite une modification du modèle
`TrajetOutput` et des tests associés.

### 5.2 Code splitting du bundle JavaScript

Le bundle JS unique fait 206 kB (64 kB gzip). L'application est simple
(une seule page, pas de router) — le code splitting n'est pas justifié à cette échelle.
Si l'application évolue avec du lazy-loading (`React.lazy`), Vite le gérerait automatiquement.

---

## 6. Justification du choix de services (critère C15)

| Service | Justification éco-conception |
|---------|------------------------------|
| **PostgreSQL 15 (Docker)** | Base relationnelle open-source, efficace en mémoire. Données lues en mémoire via ORM avec mise en cache LRU (`@lru_cache` dans main.py), évitant des requêtes répétées. |
| **FastAPI (Python)** | Framework asynchrone, faible overhead. GZipMiddleware intégré, pas de dépendance externe pour la compression. |
| **Vite (build)** | Tree-shaking automatique : seul le code importé est inclus dans le bundle. |
| **PySpark (local[*])** | Utilisé uniquement en batch ETL — pas de service long-running. La session est démarrée et stoppée à chaque exécution. |
| **Docker Compose** | Infrastructure locale, pas de cloud — empreinte réseau nulle pour les appels internes. |
| **Pas de CDN externe** | Aucune dépendance à des CDN tiers pour React/Vite (bundlé localement) → une seule origine réseau, réduction du nombre de connexions TCP. |

---

*Document conforme au critère C15 RNCP 37827 — Éco-conception de services numériques.*
