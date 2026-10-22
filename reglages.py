# =====================================================================
#  TES RÉGLAGES — c'est le seul fichier que tu as besoin de modifier.
#  (Sur GitHub : ouvre ce fichier, clique sur le crayon ✏️, modifie,
#   puis "Commit changes".)
# =====================================================================

# --- Ton école (le point de départ pour calculer les trajets) --------
# ESILV - Campus du Parc, 29 allée Le Corbusier, 92000 Nanterre
# (à côté du parc André-Malraux, RER A Nanterre-Préfecture / RER E Nanterre-La Folie).
# Pour info, le Campus Cyber (5-7 rue Bellini, Puteaux) est à 48.8865, 2.2493.
ECOLE_NOM = "ESILV - Campus du Parc (Nanterre)"
ECOLE_LAT = 48.892594
ECOLE_LON = 2.222363

# --- Budget (en euros par mois, charges comprises) ------------------
# L'objectif : le moins cher possible, idéalement moins de 500 €.
LOYER_IDEAL = 500         # ≤ 500 € : alerte "💰 OBJECTIF" (et accepté jusqu'à 45 min de trajet)
LOYER_MAX = 700           # jusqu'à 700 € : alerte normale
LOYER_MAX_SI_TOP = 800    # 700 à 800 € : SEULEMENT si coup de cœur
                          # (= à 20 min à pied max du campus, ou à La Défense)
MARCHE_TOP_MIN = 20       # "vraiment top" = à 20 min à pied max de l'école

# --- Trajet ---------------------------------------------------------
# Le trajet est une ESTIMATION (distance + lignes RER A, métro 1, T2,
# Transilien L, RER E). Il peut se tromper de quelques minutes.
TRAJET_MAX_MIN = 35       # trajet normal accepté
TRAJET_MAX_SI_TOP = 45    # accepté quand même si c'est à La Défense ou à un super prix (≤ LOYER_IDEAL)

# Zone "La Défense" (Courbevoie, Puteaux, quartier d'affaires)
DEFENSE_LAT = 48.8919
DEFENSE_LON = 2.2380
DEFENSE_RAYON_KM = 1.5
MARCHE_MAX_MIN = 25       # jusqu'à ce temps de marche, on considère "à pied"

# --- Type de logement -------------------------------------------------
INCLURE_COLOCATION = True     # False = ignorer les colocations CROUS

# --- Sites surveillés (True = oui, False = non) -----------------------
SURVEILLER_CROUS = True
SURVEILLER_FAC_HABITAT = True    # Fac-Habitat + Logifac
SURVEILLER_ARPEJ = True
SURVEILLER_ALJT = True
ALERTER_FAC_HABITAT_A_VENIR = True   # prévenir aussi quand c'est "A venir"

# Numéros des "outils" de recherche CROUS (ils changent chaque année).
# 47 = phase complémentaire 2026, 44 = attribution au fil de l'eau.
CROUS_OUTILS = [47, 44]

# --- Pages en plus à surveiller (optionnel) --------------------------
# Exemple, quand le site ALJT sera revenu :
# PAGES_EN_PLUS = [
#     {"nom": "ALJT Nanterre",
#      "url": "https://www.aljt.com/....",
#      "alerte_si_ne_contient_plus": "complet"},
# ]
PAGES_EN_PLUS = []
