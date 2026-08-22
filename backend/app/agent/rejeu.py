"""
rejeu.py — Enregistrement et lecture des traces d'agent (ÉTAPE E du plan).

Quand OBRAIL_AGENT_ENREGISTRER=1 : chaque échange réel est sauvegardé dans
  backend/app/agent/rejeu/<empreinte>.json
Quand OBRAIL_LLM_PROVIDER=rejeu : la réponse est lue depuis ces fichiers.
Correspondance par question normalisée (minuscules, sans accents ni ponctuation).

Règle §0.6-1 (aucun repli silencieux) :
- Si aucune trace ne correspond → ValueError explicite, jamais de réponse inventée.
- Le champ `mode` vaut toujours "rejeu" sur les réponses relues.
"""
import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger("obrail.agent.rejeu")

_REPERTOIRE_REJEU = Path(__file__).parent / "rejeu"
_SEUIL_SIMILARITE = 0.30


def _normaliser(question: str) -> str:
    """Minuscules, sans accents, sans ponctuation, espaces normalisés."""
    nfd = unicodedata.normalize("NFD", question.lower())
    sans_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    sans_ponctuation = re.sub(r"[^\w\s]", " ", sans_accents)
    return re.sub(r"\s+", " ", sans_ponctuation).strip()


def _empreinte(question_normalisee: str) -> str:
    return hashlib.md5(question_normalisee.encode()).hexdigest()[:12]


def _score_similarite(a: str, b: str) -> float:
    """Score Jaccard sur les mots."""
    mots_a = set(a.split())
    mots_b = set(b.split())
    if not mots_a and not mots_b:
        return 1.0
    union = len(mots_a | mots_b)
    return len(mots_a & mots_b) / union if union else 0.0


def _charger_tous() -> list[dict]:
    """Charge tous les fichiers .json du répertoire de rejeu."""
    if not _REPERTOIRE_REJEU.exists():
        return []
    traces = []
    for fichier in _REPERTOIRE_REJEU.glob("*.json"):
        try:
            with open(fichier, encoding="utf-8") as f:
                traces.append(json.load(f))
        except Exception as exc:
            logger.warning("Fichier rejeu illisible %s : %s", fichier.name, exc)
    return traces


def rejouer(question: str, session_id: Optional[str] = None) -> dict:
    """
    Charge la trace enregistrée la plus proche de la question.
    Lève ValueError si aucune correspondance n'est suffisamment proche.
    Ne retourne jamais une réponse inventée (§0.6-1).
    """
    question_norm = _normaliser(question)
    traces = _charger_tous()

    if not traces:
        raise ValueError(
            "Mode rejeu actif mais aucune trace enregistrée. "
            "Lancez d'abord une session réelle avec OBRAIL_AGENT_ENREGISTRER=1."
        )

    # Correspondance exacte en priorité
    for trace in traces:
        if trace.get("question_normalisee") == question_norm:
            resultat = {k: v for k, v in trace.items()}
            resultat["mode"] = "rejeu"
            if session_id:
                resultat["session_id"] = session_id
            logger.info("Rejeu exact — question='%s'", question_norm[:60])
            return resultat

    # Correspondance la plus proche (Jaccard)
    meilleur_score = -1.0
    meilleure_trace = None
    for trace in traces:
        score = _score_similarite(question_norm, trace.get("question_normalisee", ""))
        if score > meilleur_score:
            meilleur_score = score
            meilleure_trace = trace

    if meilleur_score < _SEUIL_SIMILARITE:
        raise ValueError(
            f"Aucune trace enregistrée ne correspond à cette question "
            f"(meilleur score de similarité : {meilleur_score:.2f}, seuil : {_SEUIL_SIMILARITE}). "
            "En mode rejeu, seules les questions pré-enregistrées sont disponibles."
        )

    resultat = {k: v for k, v in meilleure_trace.items()}
    resultat["mode"] = "rejeu"
    if session_id:
        resultat["session_id"] = session_id
    logger.info(
        "Rejeu approché — score=%.2f question='%s'",
        meilleur_score, question_norm[:60],
    )
    return resultat


def enregistrer(question: str, resultat: dict) -> Path:
    """
    Sauvegarde un échange dans le répertoire de rejeu.
    Retourne le chemin du fichier créé.
    """
    question_norm = _normaliser(question)
    empreinte = _empreinte(question_norm)

    _REPERTOIRE_REJEU.mkdir(exist_ok=True)

    # Champs à exclure de la sérialisation (internes à la boucle)
    champs_exclus = {"_outils_appeles"}

    donnees = {
        "question": question,
        "question_normalisee": question_norm,
        **{k: v for k, v in resultat.items() if k not in champs_exclus},
    }
    # On force mode="rejeu" dans le fichier pour la cohérence
    donnees["mode"] = "rejeu"

    fichier = _REPERTOIRE_REJEU / f"{empreinte}.json"
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)

    logger.info("Enregistrement rejeu sauvegardé — fichier=%s", fichier.name)
    return fichier
