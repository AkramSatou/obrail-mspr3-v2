import logging
import time
from urllib.parse import urlparse

import httpx

from app.agent.config import charger_config
from app.agent.fournisseurs import (
    FournisseurLLM,
    FournisseurOllama,
    FournisseurOpenRouter,
    FournisseurRejeu,
)

logger = logging.getLogger("obrail.agent.selection")

_OPENROUTER_PING_URL = "https://openrouter.ai/api/v1/models"

_cache: dict = {"fournisseur_nom": None, "expire_at": 0.0}


def _vider_cache() -> None:
    _cache["fournisseur_nom"] = None
    _cache["expire_at"] = 0.0


def invalider_cache_si_auto(fournisseur_nom: str) -> None:
    """À appeler quand un fournisseur échoue en mode auto pour forcer la re-sélection."""
    if _cache.get("fournisseur_nom") == fournisseur_nom:
        _vider_cache()
        logger.info("Cache auto invalidé suite à l'échec de %s", fournisseur_nom)


def verifier_disponibilite(fournisseur_nom: str, timeout: float) -> bool:
    """Vérifie si un fournisseur est joignable. Ne lève jamais d'exception."""
    config = charger_config()
    try:
        if fournisseur_nom == "openrouter":
            if not config.openrouter_api_key:
                return False
            with httpx.Client(timeout=timeout) as client:
                r = client.get(
                    _OPENROUTER_PING_URL,
                    headers={"Authorization": f"Bearer {config.openrouter_api_key}"},
                )
                return r.status_code < 500
        if fournisseur_nom == "ollama":
            parsed = urlparse(config.ollama_base_url)
            ping_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
            with httpx.Client(timeout=timeout) as client:
                r = client.get(ping_url)
                return r.status_code == 200
    except Exception:
        return False
    return False


def obtenir_fournisseur(fournisseur_force: str | None = None) -> FournisseurLLM:
    """Retourne le fournisseur LLM selon la configuration ou la détection auto.

    fournisseur_force: si fourni, court-circuite la config pour cette requête uniquement.
    Valeurs acceptées : 'ollama', 'openrouter', 'rejeu', 'auto' (= comportement par défaut).
    """
    config = charger_config()

    effective = fournisseur_force if (fournisseur_force and fournisseur_force != "auto") else config.provider

    if effective == "openrouter":
        return FournisseurOpenRouter(config)
    if effective == "ollama":
        return FournisseurOllama(config)
    if effective == "rejeu":
        return FournisseurRejeu()

    # Mode auto : vérification ou lecture du cache
    now = time.monotonic()
    cached_nom = _cache["fournisseur_nom"]
    if cached_nom and now < _cache["expire_at"]:
        logger.debug("Fournisseur issu du cache : %s", cached_nom)
        nom = cached_nom
    else:
        if verifier_disponibilite("openrouter", config.auto_timeout_s):
            nom = "openrouter"
        elif verifier_disponibilite("ollama", config.auto_timeout_s):
            nom = "ollama"
        else:
            nom = "rejeu"
        _cache["fournisseur_nom"] = nom
        _cache["expire_at"] = now + config.auto_cache_s
        logger.info(
            "Fournisseur auto sélectionné : %s (cache %ds)", nom, config.auto_cache_s
        )

    if nom == "openrouter":
        return FournisseurOpenRouter(config)
    if nom == "ollama":
        return FournisseurOllama(config)
    return FournisseurRejeu()


def etat_agent() -> dict:
    """Retourne les informations de configuration pour le health check."""
    try:
        config = charger_config()
        return {
            "fournisseur": config.provider,
            "modele_ollama": config.model_ollama,
            "modele_openrouter": config.model_openrouter,
            "mode": config.provider,
        }
    except Exception as exc:
        return {"status": "erreur_config", "detail": str(exc)}
