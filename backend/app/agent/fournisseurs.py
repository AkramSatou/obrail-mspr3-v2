from abc import ABC, abstractmethod

import httpx

from app.agent.config import ConfigAgent, charger_config


class FournisseurLLM(ABC):
    @property
    @abstractmethod
    def nom(self) -> str: ...

    @property
    @abstractmethod
    def modele(self) -> str: ...

    @abstractmethod
    def completer(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Appelle l'API de complétion et retourne le message de l'assistant."""


class FournisseurOpenRouter(FournisseurLLM):
    _NOM = "openrouter"
    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config: ConfigAgent | None = None) -> None:
        self._config = config or charger_config()

    @property
    def nom(self) -> str:
        return self._NOM

    @property
    def modele(self) -> str:
        return self._config.model_openrouter

    def completer(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {
            "model": self._config.model_openrouter,
            "messages": messages,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self._config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/obrail/obrail-mspr3",
            "X-Title": "ObRail Agent IA",
        }

        with httpx.Client(timeout=self._config.timeout_s) as client:
            response = client.post(
                f"{self._BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]


class FournisseurOllama(FournisseurLLM):
    _NOM = "ollama"

    def __init__(self, config: ConfigAgent | None = None) -> None:
        self._config = config or charger_config()

    @property
    def nom(self) -> str:
        return self._NOM

    @property
    def modele(self) -> str:
        return self._config.model_ollama

    def completer(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {
            "model": self._config.model_ollama,
            "messages": messages,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            # Désactive le mode thinking de qwen3 (raisonnement interne) pour
            # réduire la latence : sans think:false, qwen3:8b génère un bloc
            # <think>...</think> avant chaque appel d'outil (~365 s mesuré).
            "think": False,
        }
        if tools:
            payload["tools"] = tools

        with httpx.Client(timeout=self._config.timeout_s) as client:
            response = client.post(
                f"{self._config.ollama_base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]


class FournisseurRejeu(FournisseurLLM):
    """
    Fournisseur mode démonstration hors-ligne (ÉTAPE E).

    Ce fournisseur ne fait pas d'appel réseau : il signale à executer_boucle
    (boucle.py) de lire la trace depuis les fichiers pré-enregistrés dans
    backend/app/agent/rejeu/. La méthode completer() n'est donc jamais appelée
    directement — le bypass est géré en amont dans executer_boucle.
    """

    _NOM = "rejeu"

    @property
    def nom(self) -> str:
        return self._NOM

    @property
    def modele(self) -> str:
        return "rejeu"

    def completer(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        # Jamais appelé directement — executer_boucle court-circuite avant
        raise NotImplementedError(
            "FournisseurRejeu.completer() n'est pas appelé directement. "
            "Le bypass est géré par executer_boucle() dans boucle.py."
        )
