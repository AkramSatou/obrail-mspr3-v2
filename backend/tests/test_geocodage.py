"""
Tests unitaires — geocodage.py

Règles :
  - Aucun appel réseau réel : Nominatim est mocké dans tous les tests
  - La formule Haversine est testée avec des valeurs connues (distances à vol
    d'oiseau, différentes des distances ferroviaires réelles du dataset)
  - Paris-Marseille ≈ 660 km à vol d'oiseau (vs ~800 km ferrovia ires du dataset)
  - Paris-Berlin  ≈ 878 km à vol d'oiseau (vs ~1 100 km ferroviaires)
"""

import pytest
from unittest.mock import patch

from app.geocodage import distance_haversine, calculer_trajet


# ---------------------------------------------------------------------------
# Formule Haversine — valeurs de référence
# ---------------------------------------------------------------------------

class TestHaversine:
    def test_paris_marseille(self):
        # Coordonnées centres-villes WGS-84
        dist = distance_haversine(48.8566, 2.3522, 43.2965, 5.3698)
        assert 650 < dist < 670, f"Paris-Marseille attendu ~660 km à vol d'oiseau, obtenu {dist:.1f} km"

    def test_paris_berlin(self):
        dist = distance_haversine(48.8566, 2.3522, 52.5200, 13.4050)
        assert 870 < dist < 900, f"Paris-Berlin attendu ~878 km, obtenu {dist:.1f} km"

    def test_meme_point(self):
        assert distance_haversine(48.0, 2.0, 48.0, 2.0) == pytest.approx(0.0, abs=1e-6)

    def test_symetrie(self):
        d1 = distance_haversine(48.8566, 2.3522, 43.2965, 5.3698)
        d2 = distance_haversine(43.2965, 5.3698, 48.8566, 2.3522)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_non_negatif(self):
        dist = distance_haversine(0.0, 0.0, 1.0, 1.0)
        assert dist > 0

    def test_demi_tour_terre(self):
        # Deux points antipodaux ≈ π × R ≈ 20 015 km
        dist = distance_haversine(0.0, 0.0, 0.0, 180.0)
        assert 20000 < dist < 20100


# ---------------------------------------------------------------------------
# calculer_trajet — Nominatim mocké
# ---------------------------------------------------------------------------

PARIS  = (48.8566, 2.3522)
BERLIN = (52.5200, 13.4050)


class TestCalculerTrajet:
    def test_calcul_paris_berlin_electric(self):
        with patch("app.geocodage._geocode_cached", side_effect=[PARIS, BERLIN]):
            result = calculer_trajet("Paris", "Berlin", "electric")
        assert 870 < result["distance_km"] < 900
        # Vitesse 160 km/h → durée ≈ 329 min pour 878 km
        assert 300 < result["duree_estimee_minutes"] < 360
        assert result["origine"]["nom"] == "Paris"
        assert result["destination"]["nom"] == "Berlin"

    def test_calcul_paris_berlin_diesel(self):
        with patch("app.geocodage._geocode_cached", side_effect=[PARIS, BERLIN]):
            result = calculer_trajet("Paris", "Berlin", "diesel")
        # Vitesse 90 km/h → durée ≈ 585 min pour 878 km
        assert 550 < result["duree_estimee_minutes"] < 640

    def test_lieu_origine_introuvable(self):
        with patch("app.geocodage._geocode_cached", return_value=None):
            with pytest.raises(ValueError, match="introuvable"):
                calculer_trajet("LIEU_INEXISTANT_XYZ999", "Berlin")

    def test_lieu_destination_introuvable(self):
        def side_effect(q):
            return PARIS if q == "Paris" else None

        with patch("app.geocodage._geocode_cached", side_effect=side_effect):
            with pytest.raises(ValueError, match="introuvable"):
                calculer_trajet("Paris", "LIEU_INEXISTANT_XYZ999")

    def test_type_train_inconnu_utilise_vitesse_defaut(self):
        with patch("app.geocodage._geocode_cached", side_effect=[PARIS, BERLIN]):
            result = calculer_trajet("Paris", "Berlin", "hydrogene")
        # Vitesse par défaut = 160 km/h (même que electric)
        assert result["duree_estimee_minutes"] > 0

    def test_structure_retour(self):
        with patch("app.geocodage._geocode_cached", side_effect=[PARIS, BERLIN]):
            result = calculer_trajet("Paris", "Berlin")
        assert "distance_km" in result
        assert "duree_estimee_minutes" in result
        assert "origine" in result and "lat" in result["origine"] and "lon" in result["origine"]
        assert "destination" in result and "lat" in result["destination"]

    def test_duree_minimum_un(self):
        # Deux villes très proches → durée arrondie à 1 min minimum
        proche = (48.8566, 2.3522)
        quasi_meme = (48.8570, 2.3525)
        with patch("app.geocodage._geocode_cached", side_effect=[proche, quasi_meme]):
            result = calculer_trajet("A", "B")
        assert result["duree_estimee_minutes"] >= 1
