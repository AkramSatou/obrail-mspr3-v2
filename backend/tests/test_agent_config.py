"""
Tests de la configuration et de la sélection de fournisseur LLM (étape A).
Aucun appel réseau réel — verifier_disponibilite est toujours mocké.
"""

import pytest
from unittest.mock import patch

from app.agent.config import charger_config, FOURNISSEURS_VALIDES
from app.agent import selection
from app.agent.selection import obtenir_fournisseur, _vider_cache
from app.agent.fournisseurs import FournisseurOpenRouter, FournisseurOllama, FournisseurRejeu


@pytest.fixture(autouse=True)
def reset_cache():
    _vider_cache()
    yield
    _vider_cache()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_config_defauts(monkeypatch):
    for var in [
        "OBRAIL_LLM_PROVIDER", "OPENROUTER_API_KEY",
        "OBRAIL_LLM_MODEL_OLLAMA", "OBRAIL_LLM_MODEL_OPENROUTER",
        "OLLAMA_BASE_URL", "OBRAIL_AGENT_AUTO_TIMEOUT_S", "OBRAIL_AGENT_AUTO_CACHE_S",
        "OBRAIL_AGENT_MAX_ITERATIONS", "OBRAIL_AGENT_TIMEOUT_S",
        "OBRAIL_AGENT_MAX_TOKENS", "OBRAIL_AGENT_TEMPERATURE",
    ]:
        monkeypatch.delenv(var, raising=False)

    cfg = charger_config()

    assert cfg.provider == "auto"
    assert cfg.openrouter_api_key == ""
    assert cfg.model_ollama == "qwen3:8b"
    assert cfg.model_openrouter == "meta-llama/llama-3.3-70b-instruct:free"
    assert cfg.ollama_base_url == "http://host.docker.internal:11434/v1"
    assert cfg.auto_timeout_s == 1.5
    assert cfg.auto_cache_s == 45
    assert cfg.max_iterations == 5
    assert cfg.timeout_s == 60
    assert cfg.max_tokens == 800
    assert cfg.temperature == 0.0


def test_config_surchargeable_par_env(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OBRAIL_LLM_MODEL_OLLAMA", "llama3.2:3b")
    monkeypatch.setenv("OBRAIL_AGENT_MAX_ITERATIONS", "3")
    monkeypatch.setenv("OBRAIL_AGENT_TEMPERATURE", "0.2")

    cfg = charger_config()

    assert cfg.provider == "ollama"
    assert cfg.model_ollama == "llama3.2:3b"
    assert cfg.max_iterations == 3
    assert cfg.temperature == 0.2


def test_config_provider_invalide_leve_erreur(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "gemini")

    with pytest.raises(ValueError, match="OBRAIL_LLM_PROVIDER invalide"):
        charger_config()


def test_tous_fournisseurs_valides_acceptes(monkeypatch):
    for provider in FOURNISSEURS_VALIDES:
        monkeypatch.setenv("OBRAIL_LLM_PROVIDER", provider)
        cfg = charger_config()
        assert cfg.provider == provider


# ---------------------------------------------------------------------------
# Fournisseur explicite (pas de détection réseau)
# ---------------------------------------------------------------------------


def test_fournisseur_explicite_openrouter(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    fournisseur = obtenir_fournisseur()

    assert isinstance(fournisseur, FournisseurOpenRouter)
    assert fournisseur.nom == "openrouter"


def test_fournisseur_explicite_ollama(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "ollama")

    fournisseur = obtenir_fournisseur()

    assert isinstance(fournisseur, FournisseurOllama)
    assert fournisseur.nom == "ollama"


def test_fournisseur_explicite_rejeu(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "rejeu")

    fournisseur = obtenir_fournisseur()

    assert isinstance(fournisseur, FournisseurRejeu)
    assert fournisseur.nom == "rejeu"


def test_fournisseur_explicite_ne_teste_pas_reseau(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "ollama")

    with patch.object(selection, "verifier_disponibilite") as mock_vd:
        obtenir_fournisseur()
        mock_vd.assert_not_called()


# ---------------------------------------------------------------------------
# Mode auto — sélection dynamique
# ---------------------------------------------------------------------------


def test_auto_openrouter_disponible_choisit_openrouter(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "auto")

    with patch.object(selection, "verifier_disponibilite") as mock_vd:
        mock_vd.side_effect = lambda nom, timeout: nom == "openrouter"
        fournisseur = obtenir_fournisseur()

    assert isinstance(fournisseur, FournisseurOpenRouter)


def test_auto_openrouter_indisponible_choisit_ollama(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "auto")

    with patch.object(selection, "verifier_disponibilite") as mock_vd:
        mock_vd.side_effect = lambda nom, timeout: nom == "ollama"
        fournisseur = obtenir_fournisseur()

    assert isinstance(fournisseur, FournisseurOllama)


def test_auto_les_deux_indisponibles_choisit_rejeu(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "auto")

    with patch.object(selection, "verifier_disponibilite", return_value=False):
        fournisseur = obtenir_fournisseur()

    assert isinstance(fournisseur, FournisseurRejeu)


def test_auto_cache_evite_second_appel_dans_la_fenetre(monkeypatch):
    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "auto")
    monkeypatch.setenv("OBRAIL_AGENT_AUTO_CACHE_S", "60")

    with patch.object(selection, "verifier_disponibilite") as mock_vd:
        mock_vd.side_effect = lambda nom, timeout: nom == "ollama"
        obtenir_fournisseur()  # premier appel → remplit le cache

        mock_vd.reset_mock()
        obtenir_fournisseur()  # second appel dans la fenêtre → doit utiliser le cache

        mock_vd.assert_not_called()


def test_auto_cache_expire_redeclenche_detection(monkeypatch):
    import time as time_mod

    monkeypatch.setenv("OBRAIL_LLM_PROVIDER", "auto")
    monkeypatch.setenv("OBRAIL_AGENT_AUTO_CACHE_S", "0")

    with patch.object(selection, "verifier_disponibilite") as mock_vd:
        mock_vd.side_effect = lambda nom, timeout: nom == "openrouter"

        obtenir_fournisseur()  # premier appel, cache durée 0
        # Avec cache_s=0, expire_at = now + 0 → immédiatement expiré au prochain appel
        # On attend 1 ms pour garantir l'expiration
        time_mod.sleep(0.001)

        mock_vd.reset_mock()
        obtenir_fournisseur()  # doit re-tester

        mock_vd.assert_called()
