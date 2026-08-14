import os
from dataclasses import dataclass

FOURNISSEURS_VALIDES = frozenset({"auto", "openrouter", "ollama", "rejeu"})


@dataclass
class ConfigAgent:
    provider: str
    openrouter_api_key: str
    model_ollama: str
    model_openrouter: str
    ollama_base_url: str
    auto_timeout_s: float
    auto_cache_s: int
    max_iterations: int
    timeout_s: int
    max_tokens: int
    temperature: float


def charger_config() -> ConfigAgent:
    provider = os.getenv("OBRAIL_LLM_PROVIDER", "auto")
    if provider not in FOURNISSEURS_VALIDES:
        raise ValueError(
            f"OBRAIL_LLM_PROVIDER invalide : {provider!r}. "
            f"Valeurs acceptées : {sorted(FOURNISSEURS_VALIDES)}"
        )
    return ConfigAgent(
        provider=provider,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        model_ollama=os.getenv("OBRAIL_LLM_MODEL_OLLAMA", "qwen3:8b"),
        model_openrouter=os.getenv(
            "OBRAIL_LLM_MODEL_OPENROUTER", "meta-llama/llama-3.3-70b-instruct:free"
        ),
        ollama_base_url=os.getenv(
            "OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"
        ),
        auto_timeout_s=float(os.getenv("OBRAIL_AGENT_AUTO_TIMEOUT_S", "1.5")),
        auto_cache_s=int(os.getenv("OBRAIL_AGENT_AUTO_CACHE_S", "45")),
        max_iterations=int(os.getenv("OBRAIL_AGENT_MAX_ITERATIONS", "5")),
        timeout_s=int(os.getenv("OBRAIL_AGENT_TIMEOUT_S", "60")),
        max_tokens=int(os.getenv("OBRAIL_AGENT_MAX_TOKENS", "800")),
        temperature=float(os.getenv("OBRAIL_AGENT_TEMPERATURE", "0")),
    )
