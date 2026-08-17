"""
boucle.py — Boucle d'agent IA ObRail (ÉTAPES C et E du plan).

Cycle réfléchir → agir → observer sans LangChain (D3) :
1. Messages = consigne système + historique de session + message utilisateur
2. Appel LLM avec les 4 outils (format OpenAI tools)
3. Si tool_calls → exécuter chaque outil, ajouter les résultats, incrémenter
4. Si pas de tool_calls → réponse finale
Garde-fous : OBRAIL_AGENT_MAX_ITERATIONS + OBRAIL_AGENT_TIMEOUT_S.
Mémoire de session : dict en mémoire du processus, pas de persistence en base.

Mode rejeu (ÉTAPE E) :
- Si fournisseur.nom == "rejeu" → bypass de la boucle, lecture des traces enregistrées
- Si OBRAIL_AGENT_ENREGISTRER=1 → sauvegarde automatique de chaque échange réel
"""
import json
import logging
import os
import time
import uuid
from typing import Optional

from app.agent.config import charger_config
from app.agent.outils import REGISTRE_OUTILS, executer_outil

logger = logging.getLogger("obrail.agent.boucle")

_MAX_MESSAGES_SESSION = 20
_SESSIONS: dict[str, list[dict]] = {}

CONSIGNE_SYSTEME = (
    "Tu es l'assistant de l'observatoire ferroviaire européen ObRail. "
    "Tu réponds UNIQUEMENT à partir des résultats des outils. "
    "Tu n'inventes jamais un chiffre, une distance, une émission ou une probabilité. "
    "Pour toute question portant sur une liaison nommée (ville, gare, ligne), tu DOIS "
    "appeler rechercher_trajets EN PREMIER pour obtenir les paramètres réels du trajet "
    "(notamment consommation_energy et gco2_per_kwh). "
    "Si aucun trajet correspondant n'est trouvé, tu le dis clairement — "
    "tu n'appelles jamais estimer_co2_futur avec des valeurs supposées ou inventées. "
    "Si aucun outil ne permet de répondre, dis-le clairement. "
    "Pour toute question de substitution avion/train ou d'émission de CO2, tu DOIS "
    "appeler l'outil de prédiction correspondant — tu n'estimes jamais toi-même. "
    "Réponds en français, de façon concise, en citant les chiffres obtenus."
)

_SCHEMAS_OUTILS = [schema for _fn, schema, _model in REGISTRE_OUTILS.values()]


def _vider_sessions() -> None:
    """Vide toutes les sessions — utilisé dans les tests pour repartir d'un état propre."""
    _SESSIONS.clear()


def executer_boucle(
    message: str,
    session_id: Optional[str] = None,
    fournisseur=None,
    db=None,
) -> dict:
    """
    Lance la boucle agent pour un message utilisateur.
    Retourne le dict conforme au contrat §3 du plan.
    Lève TimeoutError ou httpx.RequestError — à intercepter dans la route.
    """
    config = charger_config()
    debut = time.monotonic()

    if session_id is None:
        session_id = str(uuid.uuid4())

    if fournisseur is None:
        from app.agent.selection import obtenir_fournisseur
        fournisseur = obtenir_fournisseur()

    # Mode rejeu (ÉTAPE E) : bypass de la boucle, lecture des traces enregistrées
    if fournisseur.nom == "rejeu":
        from app.agent.rejeu import rejouer
        # ValueError / FileNotFoundError → propagées telles quelles → route → 503
        # §0.6-1 : jamais de réponse inventée — si la trace est absente, erreur explicite
        resultat = rejouer(message, session_id=session_id)
        return resultat

    historique = _SESSIONS.get(session_id, [])
    messages: list[dict] = [{"role": "system", "content": CONSIGNE_SYSTEME}]
    messages.extend(historique[-max(0, _MAX_MESSAGES_SESSION - 2):])
    messages.append({"role": "user", "content": message})

    trace: list[dict] = []
    iterations = 0
    reponse_finale: Optional[str] = None
    outils_appeles: list[str] = []
    timeout_at = time.monotonic() + config.timeout_s

    while iterations < config.max_iterations:
        if time.monotonic() > timeout_at:
            raise TimeoutError(f"Timeout de {config.timeout_s}s dépassé")

        iterations += 1
        # Peut lever httpx.RequestError si le fournisseur est injoignable
        message_assistant = fournisseur.completer(messages=messages, tools=_SCHEMAS_OUTILS)

        tool_calls = message_assistant.get("tool_calls") or []

        if not tool_calls:
            reponse_finale = message_assistant.get("content") or ""
            trace.append({
                "etape": len(trace) + 1,
                "type": "reponse",
                "contenu": reponse_finale,
            })
            break

        # Message assistant avec ses tool_calls pour le tour suivant
        msg_a: dict = {
            "role": "assistant",
            "content": message_assistant.get("content"),
            "tool_calls": tool_calls,
        }
        messages.append(msg_a)

        for tc in tool_calls:
            nom_outil = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError, TypeError):
                arguments = {}

            t_outil = time.monotonic()
            resultat = executer_outil(nom_outil, arguments, db=db)
            duree_outil_ms = int((time.monotonic() - t_outil) * 1000)

            outils_appeles.append(nom_outil)
            resume = (
                resultat.get("resultat_resume")
                or resultat.get("erreur")
                or str(resultat)[:100]
            )

            trace.append({
                "etape": len(trace) + 1,
                "type": "outil",
                "outil": nom_outil,
                "arguments": arguments,
                "resultat_resume": resume,
                "duree_ms": duree_outil_ms,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(resultat, ensure_ascii=False),
            })

    else:
        # max_iterations atteint sans réponse finale
        reponse_finale = (
            f"Nombre maximum d'itérations atteint ({config.max_iterations}). "
            "Réponse incomplète — reformulez ou affinez votre question."
        )
        trace.append({
            "etape": len(trace) + 1,
            "type": "reponse",
            "contenu": reponse_finale,
        })

    # Mise à jour de l'historique de session
    historique_maj = historique + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reponse_finale or ""},
    ]
    _SESSIONS[session_id] = historique_maj[-_MAX_MESSAGES_SESSION:]

    duree_ms = int((time.monotonic() - debut) * 1000)

    logger.info(
        "Agent — session=%s fournisseur=%s durée=%dms itérations=%d outils=%s",
        session_id, fournisseur.nom, duree_ms, iterations, outils_appeles,
    )

    resultat = {
        "reponse": reponse_finale or "",
        "session_id": session_id,
        "mode": "direct",
        "fournisseur": fournisseur.nom,
        "modele": fournisseur.modele,
        "duree_ms": duree_ms,
        "iterations": iterations,
        "trace": trace,
    }

    # Enregistrement automatique (ÉTAPE E) — si OBRAIL_AGENT_ENREGISTRER=1
    if os.getenv("OBRAIL_AGENT_ENREGISTRER") == "1":
        try:
            from app.agent.rejeu import enregistrer
            enregistrer(message, resultat)
        except Exception as exc:
            logger.warning("Enregistrement rejeu échoué : %s", exc)

    return resultat
