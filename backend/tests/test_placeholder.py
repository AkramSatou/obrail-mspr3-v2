def test_root_documents_operational_routes(client):
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "2.0.0"
    assert (
        payload["routes"]["GET  /trajets"]
        == "Liste paginée et filtrable des trajets (authentification requise)"
    )
    assert payload["routes"]["GET  /metrics"] == "Métriques Prometheus de l'API"


def test_root_documents_the_authentication_routes(client):
    """La page d'accueil doit annoncer les routes d'authentification ajoutées."""
    routes = client.get("/").json()["routes"]

    assert "POST /auth/login" in routes
    assert "POST /auth/refresh" in routes
    assert "GET  /auth/me" in routes


def test_models_path_defaults_to_repo_root(monkeypatch, tmp_path):
    """
    Sans OBRAIL_MODELS_PATH, MODELS_PATH doit pointer vers le dossier models/
    situé deux niveaux au-dessus de main.py — comportement identique en local
    et dans l'image Docker (/app/app/main.py → /app/models/).
    """
    import importlib
    import sys

    monkeypatch.delenv("OBRAIL_MODELS_PATH", raising=False)

    # Recharger le module pour que la variable de module soit recalculée avec
    # l'environnement actuel (monkeypatch a effacé OBRAIL_MODELS_PATH).
    if "app.main" in sys.modules:
        mod = importlib.reload(sys.modules["app.main"])
    else:
        import app.main as mod

    from pathlib import Path
    expected = (Path(mod.__file__).resolve().parents[2] / "models")
    assert mod.MODELS_PATH == expected, (
        f"MODELS_PATH attendu {expected}, obtenu {mod.MODELS_PATH}"
    )


def test_models_path_overridden_by_env(monkeypatch, tmp_path):
    """
    Quand OBRAIL_MODELS_PATH est défini, MODELS_PATH doit utiliser cette valeur.
    Cela permet de monter les modèles dans Docker à un chemin arbitraire.
    """
    import importlib
    import sys

    monkeypatch.setenv("OBRAIL_MODELS_PATH", str(tmp_path))

    if "app.main" in sys.modules:
        mod = importlib.reload(sys.modules["app.main"])
    else:
        import app.main as mod

    from pathlib import Path
    assert mod.MODELS_PATH == Path(str(tmp_path)), (
        f"MODELS_PATH devrait valoir {tmp_path}, obtenu {mod.MODELS_PATH}"
    )
