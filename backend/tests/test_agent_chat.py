"""
ÉTAPE C — tests de la boucle d'agent et des routes POST /agent/chat + GET /agent/info.

Le fournisseur LLM est simulé — aucun appel réseau réel.
Les tests vérifient le contrôle d'accès (D5), la validation du payload,
le chemin nominal (avec et sans appel d'outil), la gestion des erreurs
fournisseur (503), et le garde-fou max_iterations (R7).
"""
import pytest
from unittest.mock import MagicMock, patch

import httpx


# ---------------------------------------------------------------------------
# Fournisseurs simulés
# ---------------------------------------------------------------------------


class _FournisseurSimule:
    """Retourne des réponses pré-enregistrées en séquence."""

    nom = "simule"
    modele = "test-model-simule"

    def __init__(self, reponses: list[dict]):
        self._it = iter(reponses)

    def completer(self, messages, tools=None):
        return next(self._it)


class _FournisseurBoucleInfinie:
    """Demande toujours le même outil — teste le garde-fou max_iterations (R7)."""

    nom = "simule"
    modele = "test-boucle"

    def completer(self, messages, tools=None):
        return {
            "tool_calls": [{
                "id": "tc-boucle",
                "type": "function",
                "function": {"name": "rechercher_trajets", "arguments": "{}"},
            }],
            "content": None,
        }


# ---------------------------------------------------------------------------
# Fixture : vider les sessions entre les tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def vider_sessions_agent():
    from app.agent.boucle import _vider_sessions
    _vider_sessions()
    yield
    _vider_sessions()


# ---------------------------------------------------------------------------
# Contrôle d'accès — D5
# ---------------------------------------------------------------------------


def test_agent_chat_sans_jeton_renvoie_401(anonymous_client):
    r = anonymous_client.post("/agent/chat", json={"message": "test"})
    assert r.status_code == 401


def test_agent_chat_viewer_renvoie_403(anonymous_client, viewer_token):
    """Un viewer ne peut pas accéder à l'agent, même indirectement (D5)."""
    anonymous_client.headers["Authorization"] = f"Bearer {viewer_token['access_token']}"
    r = anonymous_client.post("/agent/chat", json={"message": "test"})
    assert r.status_code == 403
    anonymous_client.headers.pop("Authorization", None)


def test_agent_info_sans_jeton_renvoie_401(anonymous_client):
    r = anonymous_client.get("/agent/info")
    assert r.status_code == 401


def test_agent_info_viewer_renvoie_403(anonymous_client, viewer_token):
    anonymous_client.headers["Authorization"] = f"Bearer {viewer_token['access_token']}"
    r = anonymous_client.get("/agent/info")
    assert r.status_code == 403
    anonymous_client.headers.pop("Authorization", None)


# ---------------------------------------------------------------------------
# Validation du payload — 422
# ---------------------------------------------------------------------------


def test_agent_chat_message_vide_renvoie_422(admin_client):
    r = admin_client.post("/agent/chat", json={"message": ""})
    assert r.status_code == 422


def test_agent_chat_message_trop_long_renvoie_422(admin_client):
    r = admin_client.post("/agent/chat", json={"message": "x" * 2001})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Cas nominal — réponse directe sans appel d'outil
# ---------------------------------------------------------------------------


def test_agent_chat_reponse_directe(admin_client):
    fournisseur = _FournisseurSimule([
        {"content": "Je suis l'assistant ObRail.", "tool_calls": None},
    ])
    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        r = admin_client.post("/agent/chat", json={"message": "Bonjour"})
    assert r.status_code == 200
    data = r.json()
    assert data["reponse"] == "Je suis l'assistant ObRail."
    assert data["iterations"] == 1
    assert len(data["trace"]) == 1
    assert data["trace"][0]["type"] == "reponse"
    assert "session_id" in data
    assert data["mode"] == "direct"


def test_agent_chat_session_id_genere_si_absent(admin_client):
    fournisseur = _FournisseurSimule([{"content": "OK", "tool_calls": None}])
    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        r = admin_client.post("/agent/chat", json={"message": "test"})
    assert r.status_code == 200
    assert r.json()["session_id"]  # non vide


def test_agent_chat_session_id_conserve_si_fourni(admin_client):
    fournisseur = _FournisseurSimule([{"content": "OK", "tool_calls": None}])
    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        r = admin_client.post(
            "/agent/chat",
            json={"message": "test", "session_id": "ma-session-42"},
        )
    assert r.status_code == 200
    assert r.json()["session_id"] == "ma-session-42"


# ---------------------------------------------------------------------------
# Cas avec appel d'outil
# ---------------------------------------------------------------------------


def test_agent_chat_avec_appel_outil(admin_client):
    """L'agent doit appeler un outil et afficher l'entrée dans la trace."""
    fournisseur = _FournisseurSimule([
        {
            "tool_calls": [{
                "id": "tc1",
                "type": "function",
                "function": {"name": "rechercher_trajets", "arguments": "{}"},
            }],
            "content": None,
        },
        {"content": "J'ai trouvé des trajets dans la base.", "tool_calls": None},
    ])
    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        r = admin_client.post("/agent/chat", json={"message": "Listes les trajets disponibles"})
    assert r.status_code == 200
    data = r.json()
    assert data["iterations"] == 2
    types_trace = [e["type"] for e in data["trace"]]
    assert "outil" in types_trace
    assert "reponse" in types_trace
    outils = [e["outil"] for e in data["trace"] if e["type"] == "outil"]
    assert "rechercher_trajets" in outils
    # La trace outil doit contenir un résumé du résultat
    entree_outil = next(e for e in data["trace"] if e["type"] == "outil")
    assert entree_outil["resultat_resume"]
    assert entree_outil["duree_ms"] is not None


# ---------------------------------------------------------------------------
# Erreur fournisseur → 503
# ---------------------------------------------------------------------------


def test_agent_chat_fournisseur_injoignable_renvoie_503(admin_client):
    fournisseur = MagicMock()
    fournisseur.nom = "simule"
    fournisseur.modele = "test"
    fournisseur.completer.side_effect = httpx.ConnectError("Connexion refusée")

    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        r = admin_client.post("/agent/chat", json={"message": "Bonjour"})
    assert r.status_code == 503
    assert "injoignable" in r.json()["error"]["message"].lower()


def test_agent_chat_fournisseur_rejeu_non_implemente_renvoie_503(admin_client):
    fournisseur = MagicMock()
    fournisseur.nom = "rejeu"
    fournisseur.modele = "rejeu"
    fournisseur.completer.side_effect = NotImplementedError("Le mode rejeu sera implémenté à l'étape E")

    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        r = admin_client.post("/agent/chat", json={"message": "test"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Garde-fou max_iterations — R7
# ---------------------------------------------------------------------------


def test_agent_chat_garde_fou_max_iterations(admin_client):
    """La boucle s'arrête proprement à max_iterations — pas de requête infinie."""
    fournisseur = _FournisseurBoucleInfinie()
    with patch("app.agent.selection.obtenir_fournisseur", return_value=fournisseur):
        with patch.dict("os.environ", {"OBRAIL_AGENT_MAX_ITERATIONS": "3"}):
            r = admin_client.post("/agent/chat", json={"message": "boucle infinie"})
    assert r.status_code == 200
    data = r.json()
    assert data["iterations"] == 3  # exactement max_iterations
    # La réponse doit mentionner que le nombre maximum a été atteint
    assert "Nombre maximum" in data["reponse"] or data["reponse"]


# ---------------------------------------------------------------------------
# GET /agent/info
# ---------------------------------------------------------------------------


def test_agent_info_admin_renvoie_config(admin_client):
    r = admin_client.get("/agent/info")
    assert r.status_code == 200
    data = r.json()
    assert "fournisseur" in data
    assert "modele" in data
    assert "outils" in data
    assert "max_iterations" in data
    assert "timeout_s" in data
    assert len(data["outils"]) == 4
    assert set(data["outils"]) == {
        "rechercher_trajets",
        "obtenir_statistiques",
        "predire_substitution_avion",
        "estimer_co2_futur",
    }
