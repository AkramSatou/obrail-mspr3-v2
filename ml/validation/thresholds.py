"""
thresholds.py — seuils de non-régression des modèles.

Ces valeurs sont volontairement inférieures aux performances mesurées lors de
l'entraînement initial : elles ne récompensent pas la performance, elles
détectent une dégradation. Si un réentraînement fait passer une métrique sous
son seuil, la chaîne d'intégration continue échoue et le modèle n'est pas livré.

Références mesurées lors de la MSPR TPRE622 (jeu de test, 21 363 lignes) :
    classification — F1-macro 0.997, recall classe 1 = 100 %, AUC 1.000
    régression     — R² 1.000, MAE 0.939 kgCO2

Rappel de limite, documenté dans le rapport : les deux variables cibles sont
construites par règles, ce qui explique ces niveaux. Les seuils ci-dessous
gardent donc une marge, mais restent exigeants.
"""

# Classification substitution avion/train
MIN_F1_MACRO = 0.95
MIN_RECALL_CLASS_1 = 0.90
MIN_ACCURACY = 0.95

# Régression CO2
MIN_R2 = 0.90

# Validation du jeu de données
MAX_ROUTE_LONG_NAME_NULL_RATIO = 0.50  # ~44 % constatés, marge assumée

# Taille des échantillons utilisés par les tests, pour garder la CI rapide
SAMPLE_SIZE = 20_000
RANDOM_SEED = 42
