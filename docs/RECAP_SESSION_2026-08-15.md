# Récap complet des corrections — ObRail Europe
**Période couverte :** messages du 2026-08-14 au 2026-08-15
**Spec de départ :** `docs/CORRECTIONS_UI_ET_DISTANCE_AUTO.md` puis `docs/CORRECTIONS_CHAT_ET_FOURNISSEUR.md`

---

## 1. Corrections d'interface (CORRECTIONS_UI_ET_DISTANCE_AUTO.md)

### 1.1 Badge de statut API (navbar)

**Problème :** le badge affichait toujours "API" sans distinguer les états, et ses bords entraient en conflit avec le bouton de déconnexion.

**Correctifs (`main.jsx` + `styles.css`) :**
- Contenu du badge : `"API OK"`, `"API Dégradée"`, `"API Indispo."`, `"API …"` (préfixe `API` en gris + état en gras)
- Hauteur alignée sur le bouton de déconnexion : `height: 32px`, `border: 1px solid`, `background: var(--bg-00)`
- Taille du texte unifiée à `0.8rem`

### 1.2 Suppression des emojis

**Problème :** l'emoji 🔒 restait dans l'interface.

**Correctif :**
- Ajout de `IconeCadenas` (SVG) dans `icones.jsx`
- Remplacement du 🔒 par `<IconeCadenas taille={13} />` dans `main.jsx`

### 1.3 Labels de champs — noms techniques → libellés lisibles

**Problème :** les formulaires Substitution et Projection affichaient les noms de paramètres Python bruts.

**Correctifs (`main.jsx`) :**

| Avant | Après |
|---|---|
| `distance_km` | Distance (km) |
| `duration_minutes` | Durée (min) |
| `n_stops` | Nombre d'arrêts |
| `co2_estime (gCO₂ total)` | CO₂ estimé (g) |
| `consommation_totale (kWh)` | Consommation totale (kWh) |
| `consommation_energy (kWh/km)` | Consommation énergétique (kWh/km) |
| `gco2_per_kwh — facteur réseau` | Facteur carbone (gCO₂/kWh) |
| `type_train` (electric/diesel) | Type de traction (Électrique/Diesel) |
| `country` | Pays |

Ajout de `<span className="field-hint">` sous les champs complexes (n_stops, CO₂, consommation, facteur carbone).

---

## 2. Fonctionnalité — Distance et durée automatiques

### Backend

**Fichier créé : `backend/app/geocodage.py`**
- Client Nominatim (OpenStreetMap) : rate-limit 1 req/s, User-Agent obligatoire, jamais appelé depuis le navigateur
- Cache LRU `maxsize=512` pour éviter les requêtes répétées
- Formule Haversine : distance à vol d'oiseau entre deux coordonnées GPS
- Vitesses conventionnelles : électrique 160 km/h, diesel 90 km/h
- `calculer_trajet(origine, destination, type_train)` → `{ distance_km, duree_estimee_minutes, origine, destination }`

**Route ajoutée dans `backend/app/main.py` :**
- `GET /geocode?origine=Paris&destination=Lyon&type_train=electric`
- Accessible à tous les utilisateurs authentifiés (pas seulement admin)
- Retourne 404 si un lieu est introuvable, 503 si Nominatim est indisponible

**Tests créés : `backend/tests/test_geocodage.py`**
- 13 tests unitaires (Nominatim entièrement mocké)
- Haversine, cas de référence Paris-Marseille / Paris-Berlin, gestion d'erreur lieu introuvable
- Résultat au moment de l'écriture : **13/13 passés**

### Frontend

**`frontend/src/services/api.js` :**
- Fonction `geocoderTrajet(origine, destination, type_train)` → appelle `GET /geocode`

**`frontend/src/components/icones.jsx` :**
- Ajout `IconeLocalisation` (marqueur GPS, SVG)

**Composant `GeocodageAuto` (`main.jsx`) :**
- Bloc optionnel en haut des formulaires ML : deux champs texte (Origine / Destination) + bouton Calculer
- Remplit automatiquement Distance (km) et, quand applicable, Durée (min)
- Badge `estimation` affiché à côté du résultat
- Gestion d'erreur : message rouge si lieu introuvable
- Intégré dans : Substitution avion→train, Projection CO₂, **et Calculateur CO₂ local**

---

## 3. Assistant IA — chrono de chargement

**Problème perçu :** le chat semblait ne pas fonctionner. Cause réelle : Ollama (qwen3:8b) met 72–111 s pour répondre sur CPU ; sans indicateur, l'utilisateur abandonnait.

**Correctifs (`main.jsx`) :**
- Hook `useElapsedSeconds(active)` : incrémente un compteur toutes les secondes pendant l'attente
- Bulle de chargement enrichie : `⬤⬤⬤ · {N}s · [message contextuel]` (ex. "Ollama réfléchit…")

---

## 4. Corrections UX du bloc GeocodageAuto et des formulaires ML

### 4.1 Bouton Calculer — bords arrondis

**Problème :** `border-radius: var(--rayon)` utilisait une variable CSS inexistante → pas de bords arrondis.

**Correctif (`styles.css`) :**
- `.geocode-run-btn` : `var(--rayon)` → `var(--rayon-pill)` (cohérent avec `.calc-run-btn`)
- `.geocode-block` : `var(--rayon)` → `var(--rayon-lg)`

### 4.2 Résultat d'estimation — affichage compact

**Problème :** le résultat montrait trois lignes séparées, avec le texte "Les champs ci-dessous restent modifiables" jugé superflu.

**Correctif (`main.jsx`) :**
- Résultat compact sur une ligne : `→ 481,7 km · 3h01 estimation`
- Helper `minutesEnHHMM(m)` : convertit 181 min en `3h01`, 45 min en `45 min`
- Suppression du texte "modifiables"

### 4.3 Résultat de substitution — redesign

**Problème :** le bloc ✓/✕ avec cercle était jugé peu intuitif.

**Correctif (`main.jsx` + `styles.css`) :**
- Ancien : grand cercle avec ✓ ou ✕ + texte imbriqué
- Nouveau : bannière horizontale avec bordure gauche colorée (vert si substituable, rouge sinon), label à gauche, pourcentage à droite
- Barre de probabilité conservée sous la bannière
- Classes : `.sub-banner`, `.sub-banner-yes`, `.sub-banner-no`, `.sub-banner-label`, `.sub-banner-proba`, `.sub-banner-detail`

### 4.4 Réinitialisation du résultat de substitution lors du changement d'onglet

**Problème :** en quittant l'onglet Substitution puis en y revenant, le résultat de la prédiction précédente restait affiché avec les nouvelles valeurs saisies.

**Correctif (`main.jsx`) :**
```js
useEffect(() => { if (op !== "substitution") setSubR(null); }, [op]);
```
Les valeurs du formulaire (distance, durée, etc.) sont conservées ; seul le résultat est effacé.

---

## 5. Calculateur CO₂ — redesign complet

**Problème :** le menu "Traction" forçait à choisir un seul type de train, alors que montrer les deux côte à côte est plus informatif. L'affichage des résultats était basique.

### Changements (`main.jsx`)

- Suppression du champ "Traction" (select électrique/diesel)
- `runCo2()` calcule désormais les 4 modes en une fois : train électrique, train diesel, voiture (essence), avion court-courrier
- Helper `formatCO2(kg)` : affiche en grammes si < 100g, en kg sinon
- Nouveau composant résultat : graphique horizontal avec icône + label + barre animée + valeur

### Icônes SVG ajoutées (`icones.jsx`)

| Icône | Usage |
|---|---|
| `IconeTrainElec` | Train électrique (rectangle + éclair) |
| `IconeTrainDiesel` | Train diesel (rectangle + fumée) |
| `IconeVoiture` | Voiture |
| `IconeAvion` | Avion |

### Nouveau CSS (`.co2-chart-*`, `styles.css`)

- Grille 4 colonnes : icône · label · barre · valeur
- Barres animées (transition `0.7s cubic-bezier`) qui partent de 0 à l'affichage
- Callout comparatif : "Train électrique : X× moins d'émissions que l'avion"
- Facteurs ADEME 2023 : élec. 14 g/km/pass. · diesel 49 g · voiture 218 g · avion 255 g

### Distance automatique dans le CO₂ calculateur

`GeocodageAuto` intégré dans le Calculateur CO₂ :
- Entrer "Paris" et "Lyon" → la distance se remplit automatiquement dans le champ
- Le champ Distance (km) reste entièrement modifiable à la main

---

## 6. Bug critique chat IA — cause racine et correctifs

### Cause réelle

Avec l'ajout de la clé OpenRouter dans `.env`, le backend en mode `auto` sélectionnait OpenRouter comme fournisseur. OpenRouter répondait `404 Not Found` pour le modèle `meta-llama/llama-3.3-70b-instruct:free` (modèle déprécié). Cette exception (`httpx.HTTPStatusError`) n'était **pas capturée** dans le handler `/agent/chat` → uvicorn coupait la connexion → le navigateur interprétait ça comme une erreur réseau → message "Impossible de contacter l'API ObRail".

### Correctifs backend

**`backend/app/agent/fournisseurs.py` :**
- `FournisseurOpenRouter.completer()` : capture `httpx.HTTPStatusError` et le convertit en `httpx.RequestError` (déjà géré dans `main.py`)

**`backend/app/main.py` :**
- Clause `except` élargie : `(_httpx.RequestError, _httpx.HTTPStatusError)`
- Appel à `invalider_cache_si_auto(fournisseur.nom)` → si OpenRouter échoue en mode auto, le cache est vidé et la prochaine requête re-sélectionne Ollama

**`backend/app/agent/selection.py` :**
- Nouvelle fonction `invalider_cache_si_auto(fournisseur_nom)` : vide le cache si le fournisseur qui a échoué est celui actuellement mis en cache

**`backend/app/agent/config.py` + `docker/docker-compose.yml` :**
- Modèle OpenRouter mis à jour : `llama-3.3-70b-instruct:free` → `meta-llama/llama-3.1-8b-instruct:free`

---

## 7. Spec CORRECTIONS_CHAT_ET_FOURNISSEUR.md

### 7.1 Persistance de la conversation (bug onglet)

**Problème :** changer d'onglet démontait `AssistantIA` → React détruisait tout l'état du chat (messages, session, attente en cours).

**Correctif (`main.jsx`) :**
- State du chat (`messages`, `sessionId`, `enAttente`, `badgeFournisseur`) remonté dans le composant parent `App`
- `AssistantIA` reçoit ces valeurs en props
- Rendu changé : conditionnel `{sectionActive === "assistant" && <AssistantIA />}` remplacé par toujours monté avec attribut `hidden` :
  ```jsx
  <div hidden={sectionActive !== "assistant"}>
    <AssistantIA messages={...} setMessages={...} ... />
  </div>
  ```
- La conversation survit au changement d'onglet ; une requête en cours arrive bien à destination même si l'utilisateur navigue ailleurs

### 7.2 Sélecteur de fournisseur IA

**Backend (`main.py` + `selection.py`) :**
- Nouveau champ `fournisseur_force` dans `AgentChatRequest` : `"ollama" | "openrouter" | "auto" | null`
- `obtenir_fournisseur(fournisseur_force=None)` : si fourni et ≠ "auto", court-circuite la config globale pour cette requête uniquement
- `GET /agent/info` et la config serveur restent inchangés

**Frontend (`api.js`) :**
- `envoyerMessageAgent(message, sessionId, fournisseurForce)` : ajoute `fournisseur_force` au corps si ≠ "auto"

**Frontend (`main.jsx`) :**
- Sélecteur 3 boutons dans le header du chat : **Auto** / **Ollama** / **Cloud**
- Choix conservé en état local du composant (pas de `localStorage`)
- "Auto" = comportement par défaut (pas de `fournisseur_force` envoyé)
- "Ollama" ou "Cloud" = `fournisseur_force` transmis à chaque message

### 7.3 Bouton "Nouveau chat"

**Correctif (`main.jsx`) :**
- Ancien : bouton icône seule, `aria-label="Effacer la conversation"`
- Nouveau : icône + texte **"Nouveau chat"** (libellé explicite visible)

---

## Fichiers modifiés

| Fichier | Nature des changements |
|---|---|
| `backend/app/agent/config.py` | Modèle OpenRouter mis à jour |
| `backend/app/agent/fournisseurs.py` | Gestion HTTPStatusError dans FournisseurOpenRouter |
| `backend/app/agent/selection.py` | `fournisseur_force` + `invalider_cache_si_auto()` |
| `backend/app/agent/boucle.py` | Inchangé |
| `backend/app/main.py` | `AgentChatRequest.fournisseur_force`, exception handler élargi, `/geocode` route |
| `backend/app/geocodage.py` | **Nouveau** — client Nominatim + Haversine |
| `backend/tests/test_geocodage.py` | **Nouveau** — 13 tests (Nominatim mocké) |
| `docker/docker-compose.yml` | Modèle OpenRouter mis à jour |
| `frontend/src/services/api.js` | `geocoderTrajet()`, `envoyerMessageAgent(fournisseurForce)` |
| `frontend/src/components/icones.jsx` | `IconeCadenas`, `IconeLocalisation`, `IconeTrainElec`, `IconeTrainDiesel`, `IconeVoiture`, `IconeAvion` |
| `frontend/src/main.jsx` | Chat state lifting, provider selector, CO₂ redesign, GeocodageAuto ×3, sub-banner, minutesEnHHMM, formatCO2, subR reset |
| `frontend/src/styles.css` | `.health-badge-compact`, `.field-hint`, `.geocode-*`, `.sub-banner-*`, `.co2-chart-*`, `.chat-provider-*`, `.chat-clear-btn` |
