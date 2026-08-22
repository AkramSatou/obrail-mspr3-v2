# Benchmark des services d'IA — ObRail (C7)

**Date** : 2026-08-19
**Responsable** : Akram — RNCP 37827, Bloc 2, Intégrer des modèles et services d'IA
**Périmètre** : choix du service de génération de texte utilisé par l'agent conversationnel ObRail (`backend/app/agent/`), et rappel de la décision prise en MSPR 2 pour le futur service d'OCR de PharmaGo.

---

## 1. Pourquoi ce document

Le code de l'agent (`backend/app/agent/fournisseurs.py`, `config.py`) intègre déjà deux fournisseurs de modèle de langage avec un mode de bascule automatique. Ce choix n'était documenté nulle part sous forme de comparaison : ce document formalise les critères qui ont mené à cette architecture, et écarte explicitement les services qui ne conviennent pas au besoin.

Le besoin à couvrir : un assistant qui répond en langage naturel sur les données ferroviaires ObRail, réservé aux comptes admin, sans jamais inventer de chiffre. Le modèle de langage sert uniquement à formuler la réponse à partir de données réelles déjà récupérées en base ; il n'a pas besoin d'être le plus puissant du marché, il doit surtout être disponible, prévisible en coût, et remplaçable sans réécrire l'agent.

## 2. Services étudiés

| Service | Nature | Hébergement / résidence des données | Modèle de coût | Dépendance réseau |
|---|---|---|---|---|
| **OpenRouter** | Passerelle vers plusieurs modèles (routage vers le fournisseur du modèle demandé) | Hors UE selon le modèle choisi | Facturation à l'usage, offre des modèles gratuits en accès limité | Oui, obligatoire |
| **Ollama (local)** | Serveur d'inférence auto-hébergé | Poste local, aucune donnée ne sort de la machine | Gratuit, coût = matériel local | Aucune (hors réseau) |
| **Azure OpenAI Service** | API managée sur infrastructure Azure | Choix de région, dont France Central | Facturation à l'usage, engagement de type entreprise | Oui, obligatoire |
| **Mistral AI (API)** | API d'un fournisseur français | France / UE | Facturation à l'usage | Oui, obligatoire |
| **Google Gemini API** | API managée Google | Hors UE par défaut | Facturation à l'usage | Oui, obligatoire |

## 3. Critères de comparaison

- **Continuité de service en démonstration** : le projet doit pouvoir tourner en soutenance sans connexion internet garantie dans la salle.
- **Coût pour un usage de certification** : pas de budget récurrent, pas d'engagement contractuel possible.
- **Latence perçue** : l'agent est interrogé en direct par un évaluateur, une réponse qui met plusieurs dizaines de secondes casse la démonstration.
- **Résidence des données** : critère hérité du benchmark réalisé en MSPR 2, qui avait déjà écarté les hébergements hors UE pour tout traitement impliquant des données sensibles.
- **Facilité de remplacement** : le fournisseur ne doit pas être codé en dur dans la logique métier de l'agent.

## 4. Solution retenue : bascule automatique OpenRouter → Ollama → mode rejeu

Le code (`config.py`, variable `OBRAIL_LLM_PROVIDER=auto`) tente OpenRouter en premier avec un délai de bascule court (`OBRAIL_AGENT_AUTO_TIMEOUT_S=1.5`) et une mise en cache de la disponibilité pendant 45 secondes (`OBRAIL_AGENT_AUTO_CACHE_S=45`) pour ne pas retester le réseau à chaque message. Si OpenRouter ne répond pas dans ce délai, l'agent bascule sur une instance Ollama locale (modèle `qwen3:8b`). Un troisième mode, rejeu, sert de filet de sécurité total en cas de coupure réseau complète pendant la soutenance : il rejoue des échanges pré-enregistrés sans appeler de service externe.

Cette architecture répond aux cinq critères simultanément : aucun engagement financier, fonctionnement garanti sans réseau (Ollama ou rejeu), latence bornée par le timeout de bascule, et le fournisseur est un paramètre d'environnement, pas une dépendance codée en dur.

## 5. Services écartés et pourquoi

**Azure OpenAI Service** — écarté pour l'agent conversationnel ObRail : la mise en place d'un abonnement Azure pour un usage de quelques requêtes de démonstration est disproportionnée, et l'auto-hébergement (Ollama) répond déjà au besoin de résidence des données sans dépendance externe. En revanche, ce service reste la solution retenue pour le futur service d'OCR de PharmaGo (intervention ⑤ du plan de certification) : l'OCR de documents de santé est un traitement de données sensibles au sens de l'article 9 du RGPD, ce qui justifie un hébergeur identifié et localisé, alors que l'agent ObRail ne manipule aucune donnée personnelle.

**Mistral AI** — écarté malgré son hébergement en France, pour la même raison qu'Azure : il ajoute une dépendance réseau et un compte à créer pour un besoin déjà couvert gratuitement par Ollama en local. Il resterait un candidat pertinent si le projet devait un jour servir plusieurs utilisateurs simultanés, ce qu'Ollama en local ne permet pas de façon réaliste.

**Google Gemini** — écarté en premier examen : résidence des données hors UE par défaut, sans avantage technique qui justifierait de l'accepter sur ce projet précis.

## 6. Limite assumée

Ce benchmark compare des services au niveau architecture (coût, résidence, dépendance réseau), pas au niveau qualité des réponses générées modèle par modèle : aucune évaluation comparative de la pertinence des réponses n'a été menée entre les modèles disponibles sur OpenRouter et `qwen3:8b` sur Ollama. Ce n'était pas nécessaire ici, l'agent étant contraint à ne restituer que des données réelles récupérées en base — la qualité de formulation du modèle a un impact secondaire par rapport à l'exactitude des données qu'il restitue.
