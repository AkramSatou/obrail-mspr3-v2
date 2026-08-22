# Diagramme de flux de données et conclusion de preuve de concept — ObRail (C15)

**Date** : 2026-08-19
**Responsable** : Akram — RNCP 37827, Bloc 3, Concevoir le cadre technique
**Distinction avec le diagramme d'architecture** : le diagramme d'architecture (section 4 ci-dessous) montre les composants applicatifs et leurs connexions. Celui-ci suit la donnée elle-même : d'où elle vient, sous quelle forme, ce qu'elle devient à chaque étape, et où elle finit.

---

## 1. Constat de départ : deux flux distincts, pas encore reliés

Le projet ObRail comporte en réalité deux pipelines de données séparés, qui répondent à deux blocs de compétences différents et n'ont pas vocation actuelle à fusionner automatiquement :

- le flux **Bloc 1 — entrepôt** (`obrail-etl-bloc1`), qui construit un entrepôt PostgreSQL à partir de cinq sources hétérogènes ;
- le flux **Bloc 3 — application** (`obrail-mspr3`), qui alimente la base opérationnelle consommée par l'API et le frontend à partir d'un extrait CSV déjà harmonisé.

Ce point est assumé comme une limite actuelle et détaillé en section 5.

## 2. Flux Bloc 1 — construction de l'entrepôt

```text
Sources hétérogènes
  ├─ eu_trips.csv (fichier)              173 662 trajets jour + 22 292 trajets nuit
  ├─ API REST Eurostat (RAIL_PA_QUARTAL) statistiques passagers, format JSON
  ├─ Scraping Wikipédia                  trains nommés, robots.txt vérifié avant collecte
  ├─ PySpark local[*]                    agrégations sur eu_trips.csv
  └─ Overpass API (OpenStreetMap)        gares ferroviaires Paris intra-muros, 50 gares
        │
        ▼
  Nettoyage / homogénéisation (etl.py, orchestrator.py)
        │
        ▼
  Entrepôt PostgreSQL, schéma `entrepot`
  12 tables, 18 clés étrangères, TRUNCATE...RESTART IDENTITY CASCADE à chaque exécution
  (idempotence : deux exécutions successives produisent le même état)
        │
        ▼
  Contrôle : tests/test_etl.py, tests/test_new_tables.py (comptage, idempotence, FK)
        │
        ▼
  outputs/*.csv + rapport_insertions.md (traçabilité du volume inséré par source)
```

## 3. Flux Bloc 3 — alimentation de l'application et retour de supervision

```text
data/eu_trips_v2.csv (142 420 lignes, extrait harmonisé pour l'application)
        │
        ▼
  backend/seed.py  →  PostgreSQL, base `obrail`, table `trips` (24 colonnes)
        │
        ▼
  API FastAPI (backend/app/main.py)
  authentification JWT, pagination, filtres, endpoints /predict/*
        │
        ├──────────────────────────────┐
        ▼                              ▼
  Frontend React                Agent conversationnel
  (tableau de bord, recherche)  (lecture seule des données réelles,
                                  jamais de valeur inventée — voir docs/AGENT_IA.md)
        │
        ▼
  Utilisateur (viewer ou admin)

En parallèle, à chaque requête :
  backend → /metrics → Prometheus → Grafana (tableaux de bord)
  conteneurs Docker → Promtail → Loki → Grafana (logs centralisés)
```

## 4. Architecture applicative — composants et connexions

Diagramme des composants réels, dérivé directement de `docker/docker-compose.yml`
(8 services). Distinct du flux de données ci-dessus : ceci montre les briques
applicatives et comment elles se connectent entre elles, pas ce que devient une donnée.

```text
  PostgreSQL 15 (db, :5432)
        │
        ├──────────────────────────────────┐
        ▼                                   ▼
  Backend FastAPI (backend, :8000)     Adminer (:8081)
  JWT, /trajets, /predict/*,           administration directe de la base
  /agent/chat, /metrics
        │
        ├────────────────────┐
        ▼                    ▼
  Frontend React        Prometheus (:9090)
  (frontend,             scrape /metrics du backend
  :5199 → :5173)               │
        │                      ▼
        ▼                Grafana (:3001) ◄── Loki (:3100) ◄── Promtail
  Utilisateur                                                 (logs de tous
  (viewer ou admin)                                            les conteneurs)
```

Chaque flèche correspond à une dépendance réelle déclarée dans le `docker-compose.yml`
(`depends_on` ou variable d'environnement pointant vers un autre service), pas à une
supposition : le backend attend que `db` soit prêt (`condition: service_healthy`),
Grafana attend Prometheus et Loki, Promtail lit `/var/run/docker.sock` pour capter les
logs de tous les conteneurs.

## 5. Point de vigilance assumé

Les deux flux ne sont aujourd'hui pas connectés : l'application ne lit pas en direct l'entrepôt du Bloc 1, elle repose sur son propre extrait CSV déjà nettoyé. C'est cohérent avec le découpage des blocs de certification (le Bloc 1 démontre la capacité à construire un entrepôt multi-sources, le Bloc 3 démontre la mise en production d'une application), mais ce n'est pas l'architecture cible d'un vrai produit : dans une suite réelle, l'API applicative interrogerait l'entrepôt directement, ce qui éviterait de maintenir deux jeux de données en parallèle. Ce point est assumé plutôt que masqué.

## 6. Conclusion — preuve de concept : décision

Trois hypothèses fondaient le projet depuis la MSPR 1 :

1. **Des données ferroviaires ouvertes, hétérogènes par nature, peuvent être agrégées en un entrepôt cohérent et fiable.** Validée : cinq sources distinctes intégrées, contraintes d'intégrité référentielle respectées, réexécution idempotente vérifiée par tests automatisés.
2. **Un modèle entraîné sur ces données atteint une précision suffisante pour servir d'aide à la décision (substitution avion, projection CO2).** Validée avec seuils explicites et vérifiés en continu : F1-macro ≥ 0,95 et rappel de la classe positive ≥ 0,90 pour le modèle de substitution (`ml/validation/thresholds.py`), contrôlés à chaque exécution de la CI et avant toute promotion d'un nouveau modèle (`model-retrain.yml`).
3. **Un assistant conversationnel peut répondre en langage naturel sans jamais inventer de donnée.** Validée après correction : un incident réel (`docs/INCIDENT-004-agent-parametres-invente.md`) a montré que l'agent pouvait halluciner des paramètres techniques ; le correctif contraint désormais l'agent à n'utiliser que des outils qui interrogent la base réelle, jamais une estimation du modèle de langage lui-même.

**Décision : Go.** Les trois hypothèses de la preuve de concept sont vérifiées avec des critères mesurables et automatisés, pas seulement observées une fois manuellement. Le passage à une application industrialisée (Bloc 3 : authentification, CI/CD, supervision, gestion d'incidents) est la suite cohérente de ce constat, et c'est ce que couvre le dépôt `obrail-mspr3`.

Cette décision reste conditionnée par les points encore ouverts listés dans le reste du dossier (rapprochement des deux flux de données, service d'OCR PharmaGo non encore implémenté) : le "go" porte sur la viabilité technique démontrée, pas sur une couverture à 100 % du périmètre visé.
