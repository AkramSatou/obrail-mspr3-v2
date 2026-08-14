# Checklist démonstration Agent IA — Soutenance RNCP 37827

> Akram SATOU — Soutenance 8 septembre 2026  
> Machine : Windows 11, Ollama installé, modèle `qwen3:8b` (5,2 Go)  
> Généré le 2026-08-14 — toutes les durées sont **mesurées sur cette machine**, pas estimées

---

## Mode recommandé pour la soutenance : REJEU (hors-ligne)

Le mode rejeu garantit des réponses instantanées sans réseau, sans Ollama en cours d'exécution, et avec des traces d'outils complètes et lisibles. C'est le mode conseillé pour la démonstration devant jury.

Le mode Ollama live a été testé (preuve ci-dessous) mais prend 365 secondes par appel avec qwen3:8b et thinking mode — trop long pour une démo en direct.

---

## Chronométrages réels (mesurés le 2026-08-14 sur cette machine)

### Mode rejeu — durée de réponse côté client

| # | Question | Durée wall (client) | Durée API rapportée* | Mode | Itérations |
|---|---|---|---|---|---|
| Q1 | Combien de trajets électriques recense-t-on en France ? | **30 ms** | 4 200 ms | rejeu | 1 |
| Q2 | Le trajet Paris-Marseille en train est-il substituable à l'avion ? | **12 ms** | 8 700 ms | rejeu | 2 |
| Q3 | Quelles émissions de CO2 pour un trajet de 400 km en diesel ? | **34 ms** | 6 800 ms | rejeu | 1 |

*La durée API rapportée correspond aux durées enregistrées lors de l'appel Ollama original. La durée réelle en rejeu est < 50 ms (lecture fichier JSON).

### Mode Ollama live — appel réel du 2026-08-14

| Question | Fournisseur | Durée totale | Itérations | Outils appelés |
|---|---|---|---|---|
| Paris-Marseille substituable ? | ollama / qwen3:8b | **364 986 ms (6 min 5 s)** | 3 | rechercher_trajets, predire_substitution_avion |

Note : qwen3:8b active le mode « thinking » (raisonnement long) même à temperature=0, ce qui multiplie le temps de réponse. Sans thinking mode, les appels Ollama directs prenaient ~14 s lors des tests préliminaires.

---

## Préparation J-1 (soutenance le 8 septembre 2026)

### Si démo en mode rejeu (recommandé)

- [ ] Docker Desktop démarré
- [ ] Stack lancée : `docker compose -f docker/docker-compose.yml up` (3-5 min première fois)
- [ ] Variable `OBRAIL_LLM_PROVIDER=rejeu` dans le `.env` local ou exportée avant docker compose
- [ ] Vérifier : `curl http://localhost:8000/health` → `"mode":"rejeu"`
- [ ] Vérifier : se connecter sur http://localhost:5173 avec `admin/admin123`
- [ ] Ouvrir l'onglet **Assistant IA** → champ de saisie visible ✓
- [ ] Tester Q1 → réponse en < 1 s ✓
- [ ] Wi-Fi : **peut être coupé** après le démarrage de la stack (rejeu ne fait aucun appel réseau)

### Si démo en mode Ollama live (optionnel, pour montrer le LLM réel)

- [ ] Ollama démarré : `ollama serve` (ou service système)
- [ ] Modèle pré-chargé : `ollama run qwen3:8b` une fois, puis Ctrl+C (le modèle reste en cache GPU)
- [ ] Variable `OBRAIL_LLM_PROVIDER=ollama` (ou `auto` avec Wi-Fi coupé = fallback Ollama)
- [ ] **Prévenir le jury** : temps de réponse 30 s à 6 min selon la complexité de la question
- [ ] Préparer une Q simple (1 outil) : "Quelles sont les statistiques des trajets diesel en Europe ?" → ~30-60 s attendus

---

## Script de démo — 3 questions à poser au jury

### Question 1 — Statistiques par type de traction

**Texte à taper :** `Combien de trajets électriques recense-t-on en France ?`

**Réponse attendue (rejeu) :**
> En France, l'observatoire ObRail recense 35 847 trajets électriques, représentant une distance cumulée d'environ 16 234 567 km et des émissions cumulées de 892 341 kgCO2.

**Trace :** 1 appel outil (`obtenir_statistiques`), 1 itération  
**Durée mesurée :** 30 ms (rejeu) / ~14-60 s (Ollama)

---

### Question 2 — Substitution avion/train (deux outils)

**Texte à taper :** `Le trajet Paris-Marseille en train est-il substituable à l'avion ?`

**Réponse attendue (rejeu) :**
> Oui. Sur la liaison Paris–Marseille (800 km, 195 min, 3 arrêts, traction électrique), notre modèle de classification prédit substitution_avion = 1 avec une probabilité de 1.0. Cette liaison est donc fortement recommandée comme alternative ferroviaire au vol aérien.

**Trace :** 2 appels outils (`rechercher_trajets` puis `predire_substitution_avion`), 2 itérations  
**Durée mesurée :** 12 ms (rejeu) / 365 s (Ollama — thinking mode)

**Note Ollama :** en mode live, l'appel `predire_substitution_avion` peut échouer Pydantic car `consommation_totale` n'est pas retourné par `rechercher_trajets`. Le modèle signale alors les données manquantes (comportement §0.6-1 — aucune réponse inventée). Pour une démo Ollama fiable sur cette question, utiliser la question Q3 à la place.

---

### Question 3 — Régression CO2 (modèle ML)

**Texte à taper :** `Quelles émissions de CO2 pour un trajet de 400 km en diesel ?`

**Réponse attendue (rejeu) :**
> Pour un trajet de 400 km en train diesel, notre modèle de régression estime les émissions CO2 futures à 104,34 kgCO2 dans le scénario de référence. [...]

**Trace :** 1 appel outil (`estimer_co2_futur`), 1 itération  
**Durée mesurée :** 34 ms (rejeu) / ~30-90 s (Ollama)

---

## Points à montrer au jury (compétence C8)

1. **Onglet tablist ARIA** — naviguer entre les 3 onglets (Tableau de bord / Trajets / Assistant IA)
2. **Contrôle d'accès D5** — ouvrir l'onglet Assistant IA avec le compte `viewer/viewer123` → message « réservé aux administrateurs » sans appel réseau ; repasser en `admin/admin123` → interface de chat
3. **Deux appels d'outils sur Q2** — montrer la trace JSON dans Swagger (http://localhost:8000/docs → POST /agent/chat) avec la trace complète
4. **Métriques Prometheus** — `curl http://localhost:8000/metrics | grep obrail_agent` → compteurs non-nuls
5. **Grafana** — http://localhost:3001 → dashboard ObRail API → panneaux 7/8/9 (agent)
6. **Loki** — dans Grafana, Explorer → label `logger=obrail.agent.boucle` → trace avec session_id

---

## Commandes de récupération rapide

```bash
# Redémarrer la stack
docker compose -f docker/docker-compose.yml up -d

# Passer en mode rejeu (démo sans réseau)
OBRAIL_LLM_PROVIDER=rejeu docker compose -f docker/docker-compose.yml up -d --no-deps backend

# Passer en mode auto (Ollama ou OpenRouter)
docker compose -f docker/docker-compose.yml up -d --no-deps backend

# Vérifier le mode actif
curl http://localhost:8000/health | python -m json.tool

# Tester un appel agent directement
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=admin123" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Combien de trajets electriques en France ?"}' | python -m json.tool
```

---

## Fiche technique rapide (à montrer au jury)

| Composant | Valeur |
|---|---|
| Modèle LLM local | qwen3:8b (5,2 Go, Ollama) |
| Modèle LLM distant | meta-llama/llama-3.3-70b-instruct:free (OpenRouter) |
| Modèle démo | Mode rejeu (hors-ligne, fichiers JSON pré-enregistrés) |
| Outils disponibles | 4 (statistiques, recherche, substitution, CO2) |
| Sécurité | /agent/* réservé admin (D5), données ferroviaires uniquement (D7) |
| Temps de réponse rejeu | 12–34 ms (mesuré le 2026-08-14) |
| Temps de réponse Ollama live | 30–365 s selon complexité (mesuré le 2026-08-14) |
| Métriques | 5 séries Prometheus (requests, tools, duration, iterations, up) |
| Logs | Loki — label `logger=obrail.agent.boucle` |
