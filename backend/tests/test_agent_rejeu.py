"""
ÉTAPE E — tests du mode rejeu et de l'enregistreur.

Vérifie :
- Une question pré-enregistrée retourne mode="rejeu"
- Une question inconnue retourne une erreur 503 explicite (§0.6-1 — jamais de réponse inventée)
- L'enregistreur sauvegarde bien un fichier JSON dans le répertoire rejeu/
- La normalisation et la comparaison par similarité fonctionnent correctement
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agent.rejeu import (
    _normaliser,
    _score_similarite,
    enregistrer,
    rejouer,
    _REPERTOIRE_REJEU,
)


# ---------------------------------------------------------------------------
# Normalisation et similarité
# ---------------------------------------------------------------------------


def test_normaliser_minuscules_et_sans_accents():
    assert _normaliser("Le trajet Paris–Marseille est substituable ?") == \
        "le trajet paris marseille est substituable"


def test_normaliser_supprime_ponctuation():
    assert _normaliser("Combien de trajets, en France ?") == "combien de trajets en france"


def test_score_similarite_identique():
    assert _score_similarite("paris marseille", "paris marseille") == pytest.approx(1.0)


def test_score_similarite_aucun_mot_commun():
    assert _score_similarite("paris marseille", "berlin munich") == pytest.approx(0.0)


def test_score_similarite_partiel():
    score = _score_similarite("trajet paris france", "trajet paris allemagne")
    assert 0.3 < score < 1.0


# ---------------------------------------------------------------------------
# Lecture des fichiers pré-enregistrés
# ---------------------------------------------------------------------------


def test_rejouer_question_exacte():
    """Les 5 fichiers de démonstration doivent être lisibles."""
    resultat = rejouer("Le trajet Paris–Marseille en train est-il substituable à l'avion ?")
    assert resultat["mode"] == "rejeu"
    assert "reponse" in resultat
    assert resultat["reponse"]
    assert "trace" in resultat


def test_rejouer_retourne_mode_rejeu():
    resultat = rejouer("Quelles émissions de CO2 pour un trajet de 400 km en diesel ?")
    assert resultat["mode"] == "rejeu"


def test_rejouer_conserve_session_id_fourni():
    resultat = rejouer(
        "Combien de trajets électriques recense-t-on en France ?",
        session_id="ma-session-test",
    )
    assert resultat["session_id"] == "ma-session-test"


def test_rejouer_question_inconnue_leve_erreur():
    """§0.6-1 : une question non enregistrée lève une erreur — jamais de réponse inventée."""
    with pytest.raises((ValueError, FileNotFoundError)):
        rejouer("Question qui ne ressemble à rien de ce qui est enregistré xyz42")


# ---------------------------------------------------------------------------
# Enregistreur
# ---------------------------------------------------------------------------


def test_enregistrer_cree_fichier_json(tmp_path):
    """L'enregistreur crée un fichier lisible avec la question normalisée."""
    fake_resultat = {
        "reponse": "Test de réponse",
        "session_id": "test-123",
        "mode": "direct",
        "fournisseur": "ollama",
        "modele": "qwen3:8b",
        "duree_ms": 1234,
        "iterations": 1,
        "trace": [{"etape": 1, "type": "reponse", "contenu": "Test de réponse"}],
    }
    with patch("app.agent.rejeu._REPERTOIRE_REJEU", tmp_path):
        chemin = enregistrer("Ma question de test ?", fake_resultat)

    assert chemin.exists()
    with open(chemin, encoding="utf-8") as f:
        donnees = json.load(f)

    assert donnees["question"] == "Ma question de test ?"
    assert donnees["question_normalisee"] == "ma question de test"
    assert donnees["reponse"] == "Test de réponse"
    assert donnees["mode"] == "rejeu"


def test_enregistrer_puis_rejouer(tmp_path):
    """Le cycle complet : enregistrer une trace, puis la retrouver par rejouer."""
    fake_resultat = {
        "reponse": "Réponse de démonstration",
        "session_id": "session-abc",
        "mode": "direct",
        "fournisseur": "ollama",
        "modele": "qwen3:8b",
        "duree_ms": 2000,
        "iterations": 1,
        "trace": [{"etape": 1, "type": "reponse", "contenu": "Réponse de démonstration"}],
    }
    question = "Combien de lignes dans le dataset ObRail ?"

    with patch("app.agent.rejeu._REPERTOIRE_REJEU", tmp_path):
        enregistrer(question, fake_resultat)
        resultat = rejouer(question)

    assert resultat["mode"] == "rejeu"
    assert resultat["reponse"] == "Réponse de démonstration"


# ---------------------------------------------------------------------------
# Intégration avec la route (via admin_client)
# ---------------------------------------------------------------------------


def test_route_agent_chat_mode_rejeu(admin_client):
    """La route retourne mode='rejeu' quand OBRAIL_LLM_PROVIDER=rejeu."""
    from app.agent.fournisseurs import FournisseurRejeu
    with patch("app.agent.selection.obtenir_fournisseur", return_value=FournisseurRejeu()):
        r = admin_client.post(
            "/agent/chat",
            json={"message": "Combien de trajets électriques recense-t-on en France ?"},
        )
    assert r.status_code == 200
    assert r.json()["mode"] == "rejeu"


def test_route_agent_chat_rejeu_question_inconnue_renvoie_503(admin_client):
    """§0.6-1 : question inconnue en mode rejeu → 503 explicite, aucune réponse inventée."""
    from app.agent.fournisseurs import FournisseurRejeu
    with patch("app.agent.selection.obtenir_fournisseur", return_value=FournisseurRejeu()):
        r = admin_client.post(
            "/agent/chat",
            json={"message": "QzkXYZ3798 question totalement inconnue absurde"},
        )
    assert r.status_code == 503
    msg = r.json()["error"]["message"]
    # Doit contenir un message explicite — jamais silencieux
    assert len(msg) > 10
