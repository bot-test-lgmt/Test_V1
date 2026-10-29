#!/usr/bin/env python3
"""Bot logement étudiant — surveille CROUS, Fac-Habitat/Logifac, ARPEJ et ALJT
autour de l'ESILV et prévient sur Telegram + email (+ ntfy en option).

Usage :
    python bot.py               passage normal (lancé automatiquement par GitHub)
    python bot.py --test        envoie un message de test sur chaque canal
    python bot.py --simulation  affiche ce qui serait envoyé, sans rien envoyer
                                ni enregistrer

Aucune dépendance : uniquement la bibliothèque standard Python (3.9+).
Les secrets (jetons, mots de passe) viennent des variables d'environnement,
jamais du code.
"""
import html
import json
import math
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover
    PARIS = timezone(timedelta(hours=1))

import reglages as R

ICI = Path(__file__).resolve().parent
# Les fichiers de données peuvent être dans un dossier "data/" ou à côté de bot.py
DATA = ICI / "data" if (ICI / "data" / "gares.json").exists() else ICI
ETAT = ICI / "etat.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
PAUSE = 0.4                 # pause polie entre deux requêtes (secondes)
SEUIL_PANNE = 12            # passages ratés d'affilée avant d'alerter (~1 h)
DELAI_REAPPARITION_MIN = 20 # un logement qui revient après ce délai => nouvelle alerte

CROUS_API = "https://trouverunlogement.lescrous.fr/api/fr/search/{outil}"
CROUS_LIEN = "https://trouverunlogement.lescrous.fr/tools/{outil}/accommodations/{id}"
ALJT_URL = "https://www.aljt.com/"


def log(msg):
    print(f"[{datetime.now(PARIS):%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Réseau
# ---------------------------------------------------------------------------
def http(url, data=None, headers=None, timeout=25, accepter_erreur=False):
    """Renvoie (code, texte). Lève une exception en cas d'erreur réseau."""
    h = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode() if not isinstance(data, bytes) else data
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if accepter_erreur:
            return e.code, e.read().decode("utf-8", "replace")
        raise


def get(url):
    code, txt = http(url)
    time.sleep(PAUSE)
    return txt


# ---------------------------------------------------------------------------
# Distances et trajets (estimation)
# ---------------------------------------------------------------------------
def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def minutes_marche(km):
    # 1 km à vol d'oiseau ≈ 1,3 km de rues, à 4,8 km/h
    return km * 1.3 / 4.8 * 60


_GARES = None


def gares():
    global _GARES
    if _GARES is None:
        _GARES = json.loads((DATA / "gares.json").read_text(encoding="utf-8"))["gares"]
    return _GARES


# Gares d'arrivée possibles près de l'école : (nom, lat, lon, ligne, position sur la ligne
# en minutes depuis La Défense). Une gare "à l'ouest" de La Défense est plus proche
# de Nanterre-Préfecture / Nanterre-La Folie ; une gare "à l'est" passe d'abord par La Défense.
ARRIVEES = [
    ("La Défense", 48.8919, 2.2380, None, 0),
    ("Nanterre-Préfecture", 48.8956, 2.2147, "RER A", 3),
    ("Nanterre-La Folie", 48.8964, 2.2219, "RER E", 3),
]
LON_LA_DEFENSE = 2.2380


def duree_vers(g, ligne, pos):
    """Minutes de transport entre la gare g et une gare d'arrivée (ou None)."""
    if ligne is None:
        return g["min"]
    if ligne not in g["ligne"]:
        return None
    if g["lon"] < LON_LA_DEFENSE:            # côté ouest (Nanterre, Rueil, Chatou…)
        return abs(g["min"] - pos)
    return g["min"] + pos                     # côté est : on passe par La Défense


def trajet(lat, lon):
    """Estime le trajet jusqu'à l'école. Renvoie (minutes, marche_min, texte)."""
    marche = minutes_marche(distance_km(lat, lon, R.ECOLE_LAT, R.ECOLE_LON))
    meilleur, texte = marche, f"≈ {round(marche)} min à pied"
    for g in gares():
        acces = minutes_marche(distance_km(lat, lon, g["lat"], g["lon"]))
        if acces > 18:
            continue
        for nom_a, la, lo, ligne, pos in ARRIVEES:
            ride = duree_vers(g, ligne, pos)
            if ride is None or (ride == 0 and nom_a == g["nom"]):
                continue
            sortie = minutes_marche(distance_km(la, lo, R.ECOLE_LAT, R.ECOLE_LON))
            total = acces + 4 + ride + sortie     # 4 min d'attente moyenne
            if total < meilleur - 3:              # le transport doit vraiment faire gagner du temps
                meilleur = total
                ligne_txt = ligne or g["ligne"]
                acces_txt = "gare juste à côté" if acces < 2 else f"{round(acces)} min à pied jusqu'à la gare"
                texte = (f"≈ {round(total)} min ({ligne_txt} de {g['nom']} à {nom_a}, "
                         f"{acces_txt})")
    return round(meilleur), round(marche), texte


def evaluer(offre):
    """Ajoute trajet + verdict à une offre. Renvoie True si elle correspond."""
    if offre.get("lat") is None:
        offre["trajet_txt"], offre["trajet"], offre["marche"] = "trajet inconnu", None, None
        ok_trajet = True
    else:
        t, m, txt = trajet(offre["lat"], offre["lon"])
        offre["trajet"], offre["marche"], offre["trajet_txt"] = t, m, txt
    prix = offre.get("prix")
    super_prix = prix is not None and prix <= R.LOYER_IDEAL
    defense = a_la_defense(offre.get("lat"), offre.get("lon"))
    a_pied = offre.get("marche") is not None and offre["marche"] <= R.MARCHE_TOP_MIN
    if offre.get("trajet") is not None:
        t = offre["trajet"]
        # Au-delà du trajet normal, on accepte quand même si c'est vraiment bien :
        # à La Défense, ou à un super prix.
        ok_trajet = t <= R.TRAJET_MAX_MIN or (t <= R.TRAJET_MAX_SI_TOP and (defense or super_prix))
    if prix is None or prix <= R.LOYER_MAX:
        ok_prix = True
    else:
        ok_prix = prix <= R.LOYER_MAX_SI_TOP and (a_pied or defense)
    offre["super_prix"] = super_prix
    offre["defense"] = defense
    offre["a_pied"] = offre.get("marche") is not None and offre["marche"] <= R.MARCHE_MAX_MIN
    return ok_trajet and ok_prix


def a_la_defense(lat, lon):
    if lat is None or lon is None:
        return False
    return distance_km(lat, lon, R.DEFENSE_LAT, R.DEFENSE_LON) <= R.DEFENSE_RAYON_KM


def proche(lat, lon, prix_min=None):
    """Pré-filtre rapide (évite de télécharger des pages inutiles)."""
    t, m, _ = trajet(lat, lon)
    if t > R.TRAJET_MAX_SI_TOP:
        return False
    if prix_min is not None and prix_min > R.LOYER_MAX_SI_TOP:
        return False
    return True


# ---------------------------------------------------------------------------
# Source 1 : CROUS (API JSON utilisée par le site lui-même)
# ---------------------------------------------------------------------------
def crous_page(outil, page):
    payload = {
        "idTool": outil, "need_aggregation": False, "page": page, "pageSize": 100,
        "sector": None, "occupationModes": [], "residence": None, "precision": None,
        "equipment": [], "price": {"min": 0, "max": 10000000}, "location": None,
    }
    code, txt = http(CROUS_API.format(outil=outil), data=payload,
                     headers={"Accept": "application/json"})
    time.sleep(PAUSE)
    if not txt.lstrip().startswith("{"):
        raise RuntimeError("le CROUS ne renvoie pas de données (salle d'attente ?)")
    return json.loads(txt)


def crous_items(outil):
    items, page = [], 1
    while page <= 30:
        res = (crous_page(outil, page).get("results") or {})
        lot = res.get("items") or []
        items.extend(lot)
        total = (res.get("total") or {}).get("value") or 0
        if not lot or len(items) >= total:
            break
        page += 1
    return items


OCCUP = {"alone": "seul(e)", "couple": "couple", "house_sharing": "colocation"}


def crous_offre(item, outil):
    """Transforme un logement de l'API CROUS en offre (ou None si exclu)."""
    resid = item.get("residence") or {}
    loc = resid.get("location") or {}
    modes = item.get("occupationModes") or []
    if not R.INCLURE_COLOCATION:
        modes = [m for m in modes if m.get("type") != "house_sharing"]
        if not modes:
            return None
    loyers = [(m.get("rent") or {}).get("min") for m in modes]
    loyers = [l for l in loyers if l]
    prix = int(min(loyers) / 100 + 0.5) if loyers else None
    surf = item.get("area") or {}
    if surf.get("min") and surf.get("max") and surf["min"] != surf["max"]:
        surface = f"{surf['min']:g} à {surf['max']:g} m²"
    elif surf.get("min"):
        surface = f"{surf['min']:g} m²"
    else:
        surface = ""
    occup = ", ".join(OCCUP.get(m.get("type"), m.get("type") or "") for m in modes)
    return {
        "cle": f"crous:{outil}:{item.get('id')}",
        "source": "CROUS",
        "titre": f"{(resid.get('label') or 'Résidence CROUS').title()} — {item.get('label') or 'logement'}",
        "adresse": resid.get("address") or "",
        "prix": prix,
        "details": " · ".join(x for x in (surface, occup) if x),
        "lien": CROUS_LIEN.format(outil=outil, id=item.get("id")),
        "lat": loc.get("lat"), "lon": loc.get("lon"),
        "statut": "Disponible",
    }


def crous_outils_actuels():
    """Numéros d'outils CROUS en cours (lus sur le site), + ceux des réglages."""
    outils = list(R.CROUS_OUTILS)
    try:
        code, txt = http("https://trouverunlogement.lescrous.fr/api/global/context",
                         headers={"Accept": "application/json"})
        ctx = json.loads(txt).get("tools") or {}
        for t in ctx.values():
            if isinstance(t, dict) and t.get("isEnabled") and not t.get("isLocked") \
                    and t.get("mechanism") in ("residual", "direct_allocation", "standard") \
                    and t.get("id") not in outils:
                outils.append(t["id"])
                log(f"CROUS : nouvel outil détecté automatiquement ({t['id']}, {t.get('mechanism')})")
    except Exception as e:
        log(f"CROUS : liste des outils non lue ({e}), j'utilise {outils}")
    return outils


def source_crous():
    offres = []
    erreurs = []
    outils = crous_outils_actuels()
    for outil in outils:
        try:
            for it in crous_items(outil):
                o = crous_offre(it, outil)
                if o:
                    offres.append(o)
        except Exception as e:
            erreurs.append(f"outil {outil} : {e}")
    noter("CROUS", verifiees=len(offres))
    if erreurs and len(erreurs) == len(outils):
        raise RuntimeError(" ; ".join(erreurs))
    for e in erreurs:
        log(f"CROUS (partiel) — {e}")
    return offres


# ---------------------------------------------------------------------------
# Source 2 : Fac-Habitat / Logifac (module de réservation de chaque résidence)
# ---------------------------------------------------------------------------
def _txt(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def statut_normalise(badge):
    b = badge.lower().replace("à", "a")
    if "disponible" in b:
        return "Disponible"
    if "venir" in b:
        return "A venir"
    return "Complet"


def parse_fac_habitat(page_html):
    """Renvoie la liste des types de logement : type, statut, prix, surface."""
    lignes = []
    morceaux = re.split(r'<section class="rounded py-2', page_html)[1:]
    for m in morceaux:
        typ = re.search(r'<span class="fw-bold me-1">(.*?)</span>', m, re.S)
        badge = re.search(r'<span class="badge[^"]*">(.*?)</span>', m, re.S)
        if not typ or not badge:
            continue
        prix = re.search(r'<span class="fw-bold">\s*(\d+)\s*€', m)
        surf = re.search(r'<span class="fw-bold">\s*([\d,]+m²(?: et [\d,]+m²)?)\s*</span>', m)
        lignes.append({
            "type": _txt(typ.group(1)),
            "statut": statut_normalise(_txt(badge.group(1))),
            "prix": int(prix.group(1)) if prix else None,
            "surface": surf.group(1).replace("m²", " m²") if surf else "",
        })
    return lignes


def source_fac_habitat():
    residences = json.loads((DATA / "fac_habitat.json").read_text(encoding="utf-8"))
    offres, ok = [], 0
    for r in residences:
        if not proche(r["lat"], r["lon"]):
            continue
        try:
            lignes = parse_fac_habitat(get(r["url_dispo"]))
            if not lignes:
                raise ValueError("aucun type de logement trouvé sur la page")
            ok += 1
            noter("Fac-Habitat", verifiees=1)
        except Exception as e:
            log(f"Fac-Habitat {r['nom']} illisible : {e}")
            continue
        for l in lignes:
            if l["statut"] != "Complet":
                noter("Fac-Habitat", dispo=f"{r['nom']} {l['type']} : {l['statut']} ({l['prix'] or '?'} €)")
            if l["statut"] == "Complet":
                continue
            if l["statut"] == "A venir" and not R.ALERTER_FAC_HABITAT_A_VENIR:
                continue
            offres.append({
                "cle": f"fh:{r['nom']}:{l['type']}:{l['statut']}",
                "source": "Fac-Habitat" if "logifac" not in r["url_dispo"] else "Logifac",
                "titre": f"{r['nom']} — {l['type']}",
                "adresse": r["adresse"],
                "prix": l["prix"],
                "details": l["surface"],
                "lien": r["page"] + "#reservation",
                "lat": r["lat"], "lon": r["lon"],
                "statut": l["statut"],
            })
    if ok == 0:
        raise RuntimeError("aucune page Fac-Habitat lisible")
    return offres


# ---------------------------------------------------------------------------
# Source 3 : ARPEJ (fiche de chaque résidence : "N logements disponibles")
# ---------------------------------------------------------------------------
def nom_arpej(titre):
    """'Résidence étudiante à Suresnes - Louis Blériot - ARPEJ' -> 'ARPEJ Louis Blériot'."""
    morceaux = [m.strip() for m in titre.replace("|", " - ").split(" - ") if m.strip()]
    morceaux = [m for m in morceaux if m.upper() != "ARPEJ"]
    if len(morceaux) >= 2:
        return f"ARPEJ {morceaux[1]}"
    return morceaux[0] if morceaux else "Résidence ARPEJ"


def parse_arpej(page_html):
    m = re.search(r'folder-points__text">\s*Disponibilit[ée]s?\s*</span>\s*'
                  r'<span class="folder-points__figure[^"]*">(.*?)</span>', page_html, re.S)
    if not m:
        raise ValueError("bloc Disponibilité introuvable")
    txt = _txt(m.group(1))
    n = re.search(r"(\d+)\s+logements?\s+disponibles?", txt, re.I)
    nb = int(n.group(1)) if n else 0
    lien = re.search(r'href="(https://ibail\.arpej\.fr/[^"]+)"[^>]*class="folder-cta"', page_html)
    prix = re.search(r'folder-price">.*?</span>\s*([\d.,]+)\s*€', page_html, re.S)
    nom = re.search(r"<title>(.*?)</title>", page_html, re.S)
    return {
        "nb": nb, "texte": txt,
        "lien_dossier": lien.group(1) if lien else None,
        "prix": round(float(prix.group(1).replace(",", "."))) if prix else None,
        "nom": nom_arpej(_txt(nom.group(1))) if nom else None,
    }


def source_arpej():
    residences = json.loads((DATA / "arpej.json").read_text(encoding="utf-8"))
    offres, ok = [], 0
    for r in residences:
        if r.get("jeunes_actifs"):
            continue
        if not proche(r["lat"], r["lon"], r.get("prix_min")):
            continue
        try:
            info = parse_arpej(get(r["page"]))
            ok += 1
            noter("ARPEJ", verifiees=1)
        except Exception as e:
            log(f"ARPEJ {r['nom']} illisible : {e}")
            continue
        if info["nb"] <= 0:
            continue
        noter("ARPEJ", dispo=f"{info['nom']} ({r['ville']}) : {info['texte']} ({info['prix']} €)")
        offres.append({
            "cle": f"arpej:{r['nom']}",
            "quantite": info["nb"],
            "source": "ARPEJ",
            "titre": f"{info['nom'] or 'Résidence ARPEJ'} ({r['ville']}) — {info['texte']}",
            "adresse": f"{r['cp']} {r['ville']}",
            "prix": info["prix"] or round(r["prix_min"]),
            "details": "loyer « à partir de »",
            "lien": info["lien_dossier"] or r["page"],
            "page": r["page"],
            "lat": r["lat"], "lon": r["lon"],
            "statut": "Disponible",
        })
    if ok == 0:
        raise RuntimeError("aucune page ARPEJ lisible")
    return offres


# ---------------------------------------------------------------------------
# Source 3 bis : Stud'City (AREF) — "Complet jusqu'au ..." ou pré-réservation ouverte
# ---------------------------------------------------------------------------
STUDCITY = [
    {"nom": "Stud'City La Colline de l'Arche", "adresse": "49 rue des Étudiants 92400 Courbevoie",
     "lat": 48.898253, "lon": 2.233361, "slug": "la-colline-de-l-arche"},
    {"nom": "Stud'City Paris Asnières", "adresse": "11 rue Pierre Curie 92600 Asnières-sur-Seine",
     "lat": 48.918861, "lon": 2.313906, "slug": "paris-asnieres"},
    {"nom": "Stud'City Paris Meudon", "adresse": "1 rue Mohammed Dib 92360 Meudon",
     "lat": 48.783204, "lon": 2.227026, "slug": "paris-meudon"},
]
STUDCITY_URL = "https://www.studcity.fr/aref/residences/{slug}/"


def parse_studcity(page_html):
    """Renvoie {"complet": bool, "jusqua": texte, "prix": loyer mini, "lien": pré-réservation}."""
    if "Pré-réservez votre logement" not in page_html and "is-complet" not in page_html:
        raise ValueError("page Stud'City inattendue")
    m = re.search(r'<p class="is-complet">\s*(.*?)\s*</p>', page_html, re.S)
    prix = re.search(r'id="tarifs".*?(\d{3})\s*à\s*\d{3}\s*€', page_html, re.S) or \
        re.search(r'(\d{3})\s*à\s*\d{3}\s*€', page_html)
    lien = re.search(r'href="([^"]*reservation-locataire[^"]*)"', page_html)
    return {
        "complet": bool(m),
        "jusqua": _txt(m.group(1)) if m else "",
        "prix": int(prix.group(1)) if prix else None,
        "lien": ("https://www.studcity.fr/" + lien.group(1).lstrip("/")) if lien and not
                lien.group(1).startswith("http") else (lien.group(1) if lien else None),
    }


def source_studcity():
    offres, ok = [], 0
    for r in STUDCITY:
        if not proche(r["lat"], r["lon"]):
            continue
        url = STUDCITY_URL.format(slug=r["slug"])
        try:
            info = parse_studcity(get(url))
            ok += 1
            noter("Stud'City", verifiees=1)
        except Exception as e:
            log(f"Stud'City {r['nom']} illisible : {e}")
            continue
        if info["complet"]:
            continue
        noter("Stud'City", dispo=f"{r['nom']} : pré-réservation ouverte (dès {info['prix']} €)")
        offres.append({
            "cle": f"studcity:{r['slug']}",
            "source": "Stud'City",
            "titre": f"{r['nom']} — plus affichée complète, pré-réservation ouverte",
            "adresse": r["adresse"], "prix": info["prix"],
            "details": "loyer « à partir de », T1",
            "lien": url, "lat": r["lat"], "lon": r["lon"], "statut": "Disponible",
        })
    if ok == 0 and any(proche(r["lat"], r["lon"]) for r in STUDCITY):
        raise RuntimeError("aucune page Stud'City lisible")
    return offres


# ---------------------------------------------------------------------------
# Source 4 : ALJT (site en maintenance au 22/10/2026 -> on guette son retour)
# ---------------------------------------------------------------------------
ALJT_RESIDENCES = [
 {
  "slug": "nanterre",
  "nom": "Nanterre | Jardin de l'Arche",
  "adresse": "215 Jardin de l'Arche 92000 Nanterre",
  "prix_min": 434,
  "lat": 48.89446,
  "lon": 2.230593
 },
 {
  "slug": "clichy-la-garenne-rose-guerin",
  "nom": "Clichy | Rose Guérin",
  "adresse": "1 rue Rose Guérin 92110 Clichy",
  "prix_min": 438,
  "lat": 48.907177,
  "lon": 2.30126
 },
 {
  "slug": "gennevilliers-gisele-halimi-homer",
  "nom": "Gennevilliers | Gisèle Halimi",
  "adresse": "5 rue Gisèle Halimi 92230 Gennevilliers",
  "prix_min": 478,
  "lat": 48.926054,
  "lon": 2.295122
 },
 {
  "slug": "gennevilliers-basly",
  "nom": "Gennevilliers | Basly",
  "adresse": "13-15 rue Basly 92230 Gennevilliers",
  "prix_min": 394,
  "lat": 48.918799,
  "lon": 2.293199
 },
 {
  "slug": "vaucresson",
  "nom": "Vaucresson | Château",
  "adresse": "58 rue de Garches 92420 Vaucresson",
  "prix_min": 465,
  "lat": 48.840349,
  "lon": 2.160122
 },
 {
  "slug": "chaville",
  "nom": "Chaville | Libération",
  "adresse": "34 bd de la Libération 92370 Chaville",
  "prix_min": 470,
  "lat": 48.802882,
  "lon": 2.186919
 },
 {
  "slug": "sevres",
  "nom": "Sèvres | Jules Hetzel",
  "adresse": "20 rue Jules Hetzel 92310 Sèvres",
  "prix_min": 612,
  "lat": 48.821182,
  "lon": 2.222106
 },
 {
  "slug": "boulogne-silly",
  "nom": "Boulogne | Silly",
  "adresse": "99 rue de Silly 92100 Boulogne-Billancourt",
  "prix_min": 530,
  "lat": 48.835148,
  "lon": 2.232734
 },
 {
  "slug": "boulogne-solferino",
  "nom": "Boulogne | Solférino",
  "adresse": "23 rue de Solférino 92100 Boulogne-Billancourt",
  "prix_min": 501,
  "lat": 48.82904,
  "lon": 2.243916
 },
 {
  "slug": "boulogne-vieux-pont-de-sevres",
  "nom": "Boulogne | Vieux Pont de Sèvres",
  "adresse": "155 rue du Vieux Pont de Sèvres 92100 Boulogne-Billancourt",
  "prix_min": 501,
  "lat": 48.831593,
  "lon": 2.242562
 },
 {
  "slug": "argenteuil",
  "nom": "Argenteuil | Alfred Labrière",
  "adresse": "74 rue Alfred Labrière 95100 Argenteuil",
  "prix_min": 494,
  "lat": 48.94812,
  "lon": 2.253753
 },
 {
  "slug": "saint-ouen-docks",
  "nom": "Saint-Ouen | Les Docks",
  "adresse": "20 rue Frida Kahlo 93400 Saint-Ouen-sur-Seine",
  "prix_min": 491,
  "lat": 48.912789,
  "lon": 2.327652
 }
]
ALJT_PAGE = "https://www.aljt.com/residence/{slug}/"
ALJT_DEMANDE = "https://gdc.aljt.com/gdcapi/candidate/step1?language=fr_FR"


def parse_aljt(page_html):
    """Cherche une mention de logements disponibles dans le TEXTE visible de la page."""
    if "<title>" in page_html and "maintenance" in re.search(r"<title>(.*?)</title>", page_html,
                                                              re.S | re.I).group(1).lower():
        raise RuntimeError("site ALJT en maintenance")
    sans_script = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page_html, flags=re.S | re.I)
    texte = _txt(sans_script)
    if "Jardin" not in texte and "logements" not in texte:
        raise ValueError("page ALJT inattendue")
    if re.search(r"aucune disponibilit", texte, re.I):
        return 0
    m = re.search(r"(\d+)\s+(?:logements?\s+)?disponibles?\b", texte, re.I)
    return int(m.group(1)) if m else 0


def source_aljt():
    offres, ok = [], 0
    for r in ALJT_RESIDENCES:
        if not proche(r["lat"], r["lon"], r.get("prix_min")):
            continue
        url = ALJT_PAGE.format(slug=r["slug"])
        try:
            nb = parse_aljt(get(url))
            ok += 1
            noter("ALJT", verifiees=1)
        except Exception as e:
            log(f"ALJT {r['nom']} illisible : {e}")
            continue
        if nb <= 0:
            continue
        noter("ALJT", dispo=f"{r['nom']} : {nb} logement(s) disponible(s)")
        offres.append({
            "cle": f"aljt:{r['slug']}", "quantite": nb, "source": "ALJT",
            "titre": f"ALJT {r['nom']} — {nb} logement(s) disponible(s)",
            "adresse": r["adresse"], "prix": r.get("prix_min"),
            "details": "loyer « à partir de », toutes charges comprises",
            "lien": url, "lat": r["lat"], "lon": r["lon"], "statut": "Disponible",
        })
    if ok == 0:
        raise RuntimeError("aucune page ALJT lisible")
    return offres


# ---------------------------------------------------------------------------
# Pages en plus (réglages.PAGES_EN_PLUS)
# ---------------------------------------------------------------------------
def source_pages():
    offres = []
    for p in R.PAGES_EN_PLUS:
        txt = _txt(get(p["url"])).lower()
        declenche = False
        if p.get("alerte_si_contient") and p["alerte_si_contient"].lower() in txt:
            declenche = True
        if p.get("alerte_si_ne_contient_plus") and p["alerte_si_ne_contient_plus"].lower() not in txt:
            declenche = True
        if declenche:
            offres.append({"cle": f"page:{p['url']}", "source": p["nom"],
                           "titre": f"{p['nom']} : la page a changé", "adresse": "",
                           "prix": None, "details": "va vérifier vite !",
                           "lien": p["url"], "lat": None, "lon": None,
                           "statut": "Disponible"})
    return offres


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def env(nom):
    return (os.environ.get(nom) or "").strip()


def telegram(texte, bouton=None):
    token, chat = env("TELEGRAM_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return None
    data = {"chat_id": chat, "text": texte, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if bouton:
        data["reply_markup"] = {"inline_keyboard": [[{"text": bouton[0], "url": bouton[1]}]]}
    code, rep = http(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                     accepter_erreur=True)
    if code != 200:
        raise RuntimeError(f"Telegram a refusé ({code}) : {rep[:200]}")
    return True


def email(sujet, texte, html_corps=None):
    user, mdp = env("GMAIL_ADRESSE"), env("GMAIL_MOT_DE_PASSE_APP").replace(" ", "")
    if not user or not mdp:
        return None
    dest = [d.strip() for d in (env("EMAIL_DESTINATAIRE") or user).split(",") if d.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = sujet, user, ", ".join(dest)
    msg.attach(MIMEText(texte, "plain", "utf-8"))
    if html_corps:
        msg.attach(MIMEText(html_corps, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(),
                          timeout=30) as s:
        s.login(user, mdp)
        s.sendmail(user, dest, msg.as_string())
    return True


def ntfy(titre, texte, lien=None, urgent=False):
    sujet = env("NTFY_TOPIC")
    if not sujet:
        return None
    data = {"topic": sujet, "title": titre, "message": texte,
            "priority": 5 if urgent else 4, "tags": ["house"]}
    if lien:
        data["click"] = lien
    code, rep = http("https://ntfy.sh/", data=data, accepter_erreur=True)
    if code != 200:
        raise RuntimeError(f"ntfy a refusé ({code}) : {rep[:200]}")
    return True


RAPPORT = {"sources": [], "envois": []}
FORCER_RESUME = False   # True en mode test : envoie le point du jour tout de suite
DETAILS = {}   # par source : {"verifiees": n, "dispo": [textes]}


def noter(source, verifiees=None, dispo=None):
    d = DETAILS.setdefault(source, {"verifiees": 0, "dispo": []})
    if verifiees:
        d["verifiees"] += verifiees
    if dispo:
        d["dispo"].append(dispo)


def envoyer(titre, texte_tg, texte_mail, html_mail=None, lien=None, urgent=False,
            simulation=False):
    """Envoie sur tous les canaux configurés. Lève une erreur si AUCUN n'a marché."""
    if simulation:
        log("SIMULATION — message :\n" + texte_mail)
        return
    reussis, essais = 0, 0
    for nom, f in (("Telegram", lambda: telegram(texte_tg, ("👉 Voir / réserver", lien) if lien else None)),
                   ("Email", lambda: email(titre, texte_mail, html_mail)),
                   ("ntfy", lambda: ntfy(titre, texte_mail, lien, urgent))):
        try:
            r = f()
            if r is None:
                continue
            essais += 1
            reussis += 1
            log(f"  ✔ {nom} envoyé")
            RAPPORT["envois"].append((titre, nom, "✅ envoyé"))
        except Exception as e:
            essais += 1
            log(f"  ✘ {nom} a échoué : {e}")
            RAPPORT["envois"].append((titre, nom, f"❌ échec : {e}"))
    if essais == 0:
        log("  (aucun canal configuré — rien n'est envoyé)")
        RAPPORT["envois"].append((titre, "—", "⚠️ aucun canal configuré"))
    elif reussis == 0:
        raise RuntimeError("aucun canal de notification n'a fonctionné")


def esc(s):
    return html.escape(str(s or ""))


def formater(o):
    """Construit les textes Telegram / email pour une offre."""
    tetes = []
    if o.get("statut") == "A venir":
        tetes.append("⏳ BIENTÔT DISPO")
    else:
        tetes.append("🚨 DISPO MAINTENANT")
    if o.get("a_pied"):
        tetes.append("🚶 à pied")
    if o.get("defense"):
        tetes.append("🏙 La Défense")
    if o.get("super_prix"):
        tetes.append("💰 OBJECTIF : moins de 500 €")
    elif o.get("prix") and o["prix"] > R.LOYER_MAX:
        tetes.append("❤️ coup de cœur ? (cher mais très bien placé)")
    prix = f"{o['prix']} €/mois" if o.get("prix") else "prix non indiqué"
    tg = (f"<b>{' · '.join(tetes)}</b>\n"
          f"🏠 <b>{esc(o['titre'])}</b>\n"
          f"🏷 {esc(o['source'])} — <b>{esc(prix)}</b>\n"
          + (f"📐 {esc(o['details'])}\n" if o.get("details") else "")
          + (f"📍 {esc(o['adresse'])}\n" if o.get("adresse") else "")
          + f"🚆 {esc(o.get('trajet_txt'))} jusqu'à l'ESILV\n"
          f"\n{esc(o['lien'])}")
    txt = (f"{' · '.join(tetes)}\n\n{o['titre']}\n{o['source']} — {prix}\n"
           + (f"{o['details']}\n" if o.get("details") else "")
           + (f"{o['adresse']}\n" if o.get("adresse") else "")
           + f"Trajet : {o.get('trajet_txt')} jusqu'à l'ESILV\n\n"
           f"Lien direct : {o['lien']}\n\nFonce, ça part vite !")
    sujet = f"🏠 {o['source']} : {o['titre'][:60]} — {prix} — {o.get('trajet_txt', '').split('(')[0].strip()}"
    h = (f"<div style='font-family:sans-serif;font-size:15px'>"
         f"<p style='font-size:18px'><b>{esc(' · '.join(tetes))}</b></p>"
         f"<p><b>{esc(o['titre'])}</b><br>{esc(o['source'])} — <b>{esc(prix)}</b><br>"
         f"{esc(o.get('details'))}<br>{esc(o.get('adresse'))}<br>"
         f"🚆 {esc(o.get('trajet_txt'))} jusqu'à l'ESILV</p>"
         f"<p><a href='{esc(o['lien'])}' style='background:#111;color:#fff;padding:12px 20px;"
         f"border-radius:24px;text-decoration:none;font-weight:bold'>👉 Voir et réserver</a></p>"
         f"<p style='color:#666'>Fonce, ça part vite !</p></div>")
    return sujet, tg, txt, h


# ---------------------------------------------------------------------------
# État (ce qui a déjà été vu)
# ---------------------------------------------------------------------------
def charger_etat():
    if ETAT.exists():
        try:
            return json.loads(ETAT.read_text(encoding="utf-8"))
        except Exception:
            log("etat.json illisible — on repart de zéro")
    return {}


def sauver_etat(etat):
    ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")


def maintenant():
    return datetime.now(timezone.utc)


def nouveautes(etat_src, offres):
    """Compare avec le passage précédent. Renvoie la liste des offres à signaler."""
    vus = etat_src.setdefault("vus", {})
    disparus = etat_src.setdefault("disparus", {})
    now = maintenant()
    a_signaler = []
    actuelles = {o["cle"]: o for o in offres}
    for cle, o in actuelles.items():
        q = o.get("quantite", 1)
        if cle in vus:
            if q > vus[cle].get("quantite", 1):
                a_signaler.append(o)
            vus[cle]["quantite"] = q
            continue
        parti = disparus.pop(cle, None)
        recent = parti and (now - datetime.fromisoformat(parti)) < timedelta(minutes=DELAI_REAPPARITION_MIN)
        if not recent:
            a_signaler.append(o)
        vus[cle] = {"depuis": now.isoformat(), "quantite": q}
    for cle in list(vus):
        if cle not in actuelles:
            vus.pop(cle)
            disparus[cle] = now.isoformat()
    for cle in list(disparus):
        if now - datetime.fromisoformat(disparus[cle]) > timedelta(days=2):
            disparus.pop(cle)
    return a_signaler


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------
SOURCES = [
    ("CROUS", "SURVEILLER_CROUS", source_crous),
    ("Fac-Habitat", "SURVEILLER_FAC_HABITAT", source_fac_habitat),
    ("ARPEJ", "SURVEILLER_ARPEJ", source_arpej),
    ("Stud'City", "SURVEILLER_STUDCITY", source_studcity),
    ("ALJT", "SURVEILLER_ALJT", source_aljt),
    ("Pages en plus", None, source_pages),
]


def passage(simulation=False):
    RAPPORT["sources"].clear()
    DETAILS.clear()
    etat = charger_etat()
    sources_etat = etat.setdefault("sources", {})
    stats = etat.setdefault("stats", {"passages": 0, "alertes": 0})
    stats["passages"] += 1
    resume_actuel = []          # pour le message de bienvenue
    a_envoyer = []
    dispo_actuelles = []        # toutes les offres dans tes critères en ce moment

    for nom, reglage, fonction in SOURCES:
        if reglage and not getattr(R, reglage, True):
            continue
        if nom == "Pages en plus" and not R.PAGES_EN_PLUS:
            continue
        s = sources_etat.setdefault(nom, {})
        try:
            brutes = fonction()
        except Exception as e:
            s["echecs"] = s.get("echecs", 0) + 1
            log(f"{nom} : ÉCHEC ({s['echecs']} d'affilée) — {e}")
            RAPPORT["sources"].append({"nom": nom, "ok": False, "erreur": str(e)[:150]})
            if s["echecs"] == SEUIL_PANNE and not simulation:
                envoyer(f"⚠️ {nom} ne répond plus",
                        f"⚠️ <b>{esc(nom)}</b> ne répond plus depuis ~1 h.\n"
                        f"Je continue d'essayer. Pense à vérifier le site à la main.\n<i>{esc(e)}</i>",
                        f"{nom} ne répond plus depuis environ 1 h ({e}). Le bot continue d'essayer.")
            continue
        if s.get("echecs", 0) >= SEUIL_PANNE and not simulation:
            envoyer(f"✅ {nom} répond de nouveau", f"✅ <b>{esc(nom)}</b> répond de nouveau.",
                    f"{nom} répond de nouveau, la surveillance a repris.")
        s["echecs"] = 0
        offres = [o for o in brutes if evaluer(o)]
        offres.sort(key=lambda o: (o.get("prix") or 9999, o["trajet"] if o["trajet"] is not None else 99))
        log(f"{nom} : {len(brutes)} offre(s) en ligne, {len(offres)} dans tes critères")
        premiere_fois = not s.get("initialise")
        nouvelles = nouveautes(s, offres)
        s["initialise"] = True
        RAPPORT["sources"].append({"nom": nom, "ok": True, "en_ligne": len(brutes),
                                   "criteres": len(offres), "nouvelles": len(nouvelles)})
        dispo_actuelles.extend(offres)
        if premiere_fois and not etat.get("bienvenue"):
            resume_actuel.append((nom, offres))
        else:
            a_envoyer.extend(nouvelles)

    # Message de bienvenue (une seule fois)
    if resume_actuel and not etat.get("bienvenue"):
        lignes_tg, lignes_txt = [], []
        for nom, offres in resume_actuel:
            if offres:
                for o in offres[:8]:
                    prix = f"{o['prix']} €" if o.get("prix") else "?"
                    lignes_tg.append(f"• {esc(o['source'])} — {esc(o['titre'])} — <b>{prix}</b> — "
                                     f"{esc(o['trajet_txt'].split('(')[0].strip())}\n  {esc(o['lien'])}")
                    lignes_txt.append(f"- {o['source']} — {o['titre']} — {prix} — {o['trajet_txt']}\n  {o['lien']}")
        deja = "\n".join(lignes_tg) if lignes_tg else "Rien pour l'instant dans tes critères."
        deja_txt = "\n".join(lignes_txt) if lignes_txt else "Rien pour l'instant dans tes critères."
        envoyer("✅ Ton bot logement est lancé",
                "✅ <b>Ton bot logement est lancé !</b>\n"
                f"Je surveille CROUS, Fac-Habitat, ARPEJ, Stud'City et ALJT autour de l'ESILV "
                f"(≤ {R.TRAJET_MAX_MIN} min, ≤ {R.LOYER_MAX} €).\n"
                "Je t'écris dès qu'un NOUVEAU logement apparaît.\n\n"
                f"<b>Déjà disponible en ce moment :</b>\n{deja}",
                "Ton bot logement est lancé ! Je surveille CROUS, Fac-Habitat, ARPEJ, Stud'City et ALJT "
                f"autour de l'ESILV (≤ {R.TRAJET_MAX_MIN} min, ≤ {R.LOYER_MAX} €).\n\n"
                f"Déjà disponible en ce moment :\n{deja_txt}",
                simulation=simulation)
        if not simulation:
            etat["bienvenue"] = maintenant().isoformat()

    # Alertes
    for o in a_envoyer:
        sujet, tg, txt, h = formater(o)
        log(f"NOUVEAU : {o['titre']} ({o.get('prix')} €, {o.get('trajet_txt')})")
        envoyer(sujet, tg, txt, h, lien=o["lien"],
                urgent=bool(o.get("a_pied") or o.get("super_prix") or o.get("defense")), simulation=simulation)
        stats["alertes"] += 1

    # Résumé quotidien (preuve que tout tourne + ce qui est dispo en ce moment)
    loc = datetime.now(PARIS)
    jour = loc.strftime("%Y-%m-%d")
    if FORCER_RESUME:
        envoyer_resume(stats, dispo_actuelles, simulation)
    elif (getattr(R, "RESUME_QUOTIDIEN", True) and loc.hour >= getattr(R, "HEURE_RESUME", 20)
            and etat.get("dernier_resume_jour") != jour):
        envoyer_resume(stats, dispo_actuelles, simulation)
        if not simulation:
            etat["dernier_resume_jour"] = jour
            etat["stats"] = {"passages": 0, "alertes": 0}

    etat["dernier_passage"] = maintenant().isoformat()
    if not simulation:
        sauver_etat(etat)
    ecrire_rapport_github()


def ligne_source(r):
    """Texte clair de l'état d'une source pour le point du jour."""
    if not r["ok"]:
        return "❌ ne répond pas"
    d = DETAILS.get(r["nom"], {})
    if r["nom"] == "CROUS":
        return (f"✅ {r.get('en_ligne', 0)} logements en ligne dans toute la France, "
                f"{r.get('criteres', 0)} dans tes critères")
    n = d.get("verifiees", 0)
    dispo = d.get("dispo", [])
    base = f"✅ {n} résidence(s) proche(s) vérifiée(s)"
    if not dispo:
        return base + " — tout est complet"
    return base + f" — {len(dispo)} dispo, {r.get('criteres', 0)} dans tes critères : " + " ; ".join(dispo[:4])


def envoyer_resume(stats, dispo, simulation=False):
    sante_tg, sante_txt = [], []
    for r in RAPPORT["sources"]:
        etat_txt = ligne_source(r)
        sante_tg.append(f"• {esc(r['nom'])} : {esc(etat_txt)}")
        sante_txt.append(f"- {r['nom']} : {etat_txt}")
    dispo = sorted(dispo, key=lambda o: o.get("prix") or 9999)
    if dispo:
        lignes_tg = [f"• <b>{o['prix'] or '?'} €</b> — {esc(o['titre'])} "
                     f"({esc(o['trajet_txt'].split('(')[0].strip())})\n  {esc(o['lien'])}"
                     for o in dispo[:8]]
        lignes_txt = [f"- {o['prix'] or '?'} € — {o['titre']} ({o['trajet_txt']})\n  {o['lien']}"
                      for o in dispo[:8]]
        dispo_tg = "\n".join(lignes_tg)
        dispo_txt = "\n".join(lignes_txt)
    else:
        dispo_tg = dispo_txt = ("Rien dans tes critères pour l'instant (c'est normal, tout est "
                                "complet en ce moment). Je te préviens dès que ça bouge.")
    envoyer("🌙 Bot logement : point du jour",
            f"🌙 <b>Point du jour — toujours en veille ✅</b>\n"
            f"{stats['passages']} vérifications depuis hier, {stats['alertes']} alerte(s) envoyée(s).\n\n"
            f"<b>Les sites :</b>\n" + "\n".join(sante_tg) +
            f"\n\n<b>Disponible en ce moment dans tes critères :</b>\n{dispo_tg}",
            f"Point du jour — toujours en veille.\n{stats['passages']} vérifications depuis hier, "
            f"{stats['alertes']} alerte(s) envoyée(s).\n\nLes sites :\n" + "\n".join(sante_txt) +
            f"\n\nDisponible en ce moment dans tes critères :\n{dispo_txt}",
            simulation=simulation)


def ecrire_rapport_github():
    """Écrit un résumé lisible sur la page du passage GitHub (visible sans se connecter)."""
    chemin = os.environ.get("GITHUB_STEP_SUMMARY")
    lignes = [f"## 🏠 Veille logement — {datetime.now(PARIS):%d/%m %H:%M}", "",
              "| Site | État | En ligne | Dans tes critères | Nouveaux |", "|---|---|---|---|---|"]
    for r in RAPPORT["sources"]:
        if r["ok"]:
            lignes.append(f"| {r['nom']} | ✅ {r.get('info', 'répond')} | {r.get('en_ligne', '')} | "
                          f"{r.get('criteres', '')} | {r.get('nouvelles', '')} |")
        else:
            lignes.append(f"| {r['nom']} | ❌ {r['erreur'].replace('|', '/')} | | | |")
    canaux = [n for n, v in (("Telegram", env("TELEGRAM_TOKEN") and env("TELEGRAM_CHAT_ID")),
                             ("Email", env("GMAIL_ADRESSE") and env("GMAIL_MOT_DE_PASSE_APP")),
                             ("ntfy", env("NTFY_TOPIC"))) if v]
    lignes += ["", f"**Canaux configurés :** {', '.join(canaux) or '⚠️ aucun'}", ""]
    if RAPPORT["envois"]:
        lignes += ["**Messages envoyés pendant ce passage :**", ""]
        lignes += [f"- {canal} : {res} — {titre.replace('|', '/')}" for titre, canal, res in RAPPORT["envois"]]
    else:
        lignes.append("_Aucun message envoyé pendant ce passage (rien de nouveau)._")
    texte = "\n".join(lignes) + "\n"
    log("\n" + texte)
    if chemin:
        try:
            with open(chemin, "a", encoding="utf-8") as f:
                f.write(texte)
        except Exception:
            pass


def diagnostic_telegram():
    """Explique clairement où en est la configuration Telegram."""
    token, chat = env("TELEGRAM_TOKEN"), env("TELEGRAM_CHAT_ID")
    log("----- Diagnostic Telegram -----")
    if not token:
        log("❌ Secret TELEGRAM_TOKEN introuvable. Vérifie dans Settings > Secrets and variables > "
            "Actions qu'il s'appelle EXACTEMENT TELEGRAM_TOKEN (majuscules, sans espace).")
        return
    try:
        code, rep = http(f"https://api.telegram.org/bot{token}/getMe", accepter_erreur=True)
        moi = json.loads(rep)
    except Exception as e:
        log(f"❌ Impossible de joindre Telegram : {e}")
        return
    if not moi.get("ok"):
        log("❌ TELEGRAM_TOKEN refusé par Telegram : le jeton est mal copié. Recopie-le depuis "
            "@BotFather (tout, y compris la partie avant les deux-points).")
        return
    log(f"✅ Jeton OK : ton bot est @{moi['result'].get('username')}")
    if chat:
        log(f"✅ TELEGRAM_CHAT_ID est renseigné (finit par …{chat[-3:]}).")
        return
    code, rep = http(f"https://api.telegram.org/bot{token}/getUpdates", accepter_erreur=True)
    ids = sorted({str(u["message"]["chat"]["id"])
                  for u in json.loads(rep).get("result", []) if u.get("message")})
    if ids:
        log("")
        log(f"👉👉 TON TELEGRAM_CHAT_ID EST : {', '.join(ids)}")
        log("     Copie ce nombre dans un nouveau secret GitHub nommé TELEGRAM_CHAT_ID.")
        log("")
    else:
        log(f"⚠️ Ton bot @{moi['result'].get('username')} n'a reçu aucun message récent. Ouvre "
            "Telegram, cherche ce nom, envoie-lui « bonjour », puis relance le test dans "
            "les 24 h (Telegram n'en garde la trace que 24 h).")


def test():
    log("Envoi d'un message de test sur chaque canal configuré…")
    diagnostic_telegram()
    token, chat = env("TELEGRAM_TOKEN"), env("TELEGRAM_CHAT_ID")
    configures = [n for n, v in (("Telegram", token and chat),
                                 ("Email", env("GMAIL_ADRESSE") and env("GMAIL_MOT_DE_PASSE_APP")),
                                 ("ntfy", env("NTFY_TOPIC"))) if v]
    log(f"Canaux configurés : {', '.join(configures) or 'aucun'}")
    exemple = {"source": "TEST", "titre": "Résidence Exemple — T1", "adresse": "92400 Courbevoie",
               "prix": 480, "details": "18 m²", "lien": "https://trouverunlogement.lescrous.fr/",
               "lat": 48.8975, "lon": 2.2400, "statut": "Disponible"}
    evaluer(exemple)
    sujet, tg, txt, h = formater(exemple)
    envoyer("[TEST] " + sujet, "🧪 <b>Ceci est un TEST</b> — si tu le lis, ça marche !\n\n" + tg,
            "CECI EST UN TEST — si tu le lis, ça marche !\n\n" + txt, h, lien=exemple["lien"])


if __name__ == "__main__":
    if "--test" in sys.argv or env("MODE_TEST").lower() == "true":
        log("MODE TEST activé")
        test()
        FORCER_RESUME = True
    elif env("TELEGRAM_TOKEN") and not env("TELEGRAM_CHAT_ID"):
        diagnostic_telegram()
    passage(simulation="--simulation" in sys.argv)
