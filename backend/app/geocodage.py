"""
geocodage.py — Géocodage via Nominatim (OpenStreetMap) + distance Haversine.

Contraintes Nominatim (politique officielle) :
  - 1 requête/seconde maximum
  - User-Agent obligatoire et identifiable
  - Jamais appelé côté navigateur : toujours proxy backend
"""

import json
import math
import threading
import time
import urllib.parse
import urllib.request
from functools import lru_cache

_LOCK = threading.Lock()
_LAST_CALL: float = 0.0
_MIN_INTERVAL = 1.15  # légèrement > 1 s pour absorber la latence réseau

# Vitesses moyennes conventionnelles par type de traction (km/h).
# Source : moyennes commerciales TGV/ICE (~160) et trains diesel régionaux (~90).
VITESSE_MOYENNE_KMH: dict[str, float] = {
    "electric": 160.0,
    "diesel": 90.0,
}


def distance_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Retourne la distance à vol d'oiseau en kilomètres entre deux points WGS-84."""
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


@lru_cache(maxsize=512)
def _geocode_cached(q: str) -> tuple[float, float] | None:
    """
    Interroge Nominatim avec respect du rate-limit (1 req/s).
    Résultats mis en cache par chaîne de requête normalisée.
    Retourne (lat, lon) ou None si lieu introuvable ou erreur réseau.
    """
    global _LAST_CALL
    with _LOCK:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.monotonic()

    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={urllib.parse.quote(q)}&format=json&limit=1"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ObRail-Europe/1.0 (contact: data@obrail.eu)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


def calculer_trajet(origine: str, destination: str, type_train: str = "electric") -> dict:
    """
    Géocode deux lieux et retourne distance Haversine + durée estimée.

    La durée est une estimation basée sur une vitesse moyenne conventionnelle —
    pas un horaire ferroviaire réel. L'affichage dans l'UI doit le signaler.

    Raises:
        ValueError: si l'un des lieux est introuvable par Nominatim.
    """
    coords_orig = _geocode_cached(origine)
    if coords_orig is None:
        raise ValueError(f"Lieu introuvable : « {origine} »")

    coords_dest = _geocode_cached(destination)
    if coords_dest is None:
        raise ValueError(f"Lieu introuvable : « {destination} »")

    dist_km = distance_haversine(*coords_orig, *coords_dest)
    vitesse = VITESSE_MOYENNE_KMH.get(type_train, 160.0)
    duree_min = max(1, round((dist_km / vitesse) * 60))

    return {
        "distance_km": round(dist_km, 1),
        "duree_estimee_minutes": duree_min,
        "origine": {"nom": origine, "lat": coords_orig[0], "lon": coords_orig[1]},
        "destination": {"nom": destination, "lat": coords_dest[0], "lon": coords_dest[1]},
    }
