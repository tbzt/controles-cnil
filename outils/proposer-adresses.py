"""Propose une adresse aux contrôles qui n'en ont pas, via l'annuaire des
entreprises (recherche-entreprises.api.gouv.fr, sans clé, données SIRENE).

    python3 outils/proposer-adresses.py [--limite N] [--seulement-annee 2023]

Reproduit la règle manuelle : chercher l'entité par son nom dans le
département, retenir le siège s'il est dans la commune indiquée par la CNIL,
sinon un établissement de l'entité dans cette commune. Trois niveaux :

- **haut** : nom quasi identique (similarité ≥ 0,97), siège dans la commune,
  une seule entité candidate → écrit directement dans
  `data/geocoding/surcouche.csv`, statut `valide`, méthode `siege_auto` ;
- **moyen** : nom proche (≥ 0,80) avec siège dans la commune, ou nom quasi
  identique avec seulement un établissement dans la commune, ou plusieurs
  entités plausibles → écrit dans `data/geocoding/propositions.csv`, statut
  `a_verifier`, la ligne reste à la commune ;
- **rien** : pas de candidat crédible, la ligne reste à la commune.

Ne sont pas interrogés : les organismes hors de France, sans commune
résolue, déjà pourvus d'une adresse validée, ni les noms de domaine, les
particuliers et les noms anonymisés. Environ sept requêtes par seconde au
plus, conformément à la politique de l'API. Aucun appel réseau ailleurs que
dans cet outil.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import GEOCODING, METADATA, PROCESSED, ecrire_json, ecrire_texte, journal, normaliser_nom  # noqa: E402

API = "https://recherche-entreprises.api.gouv.fr/search"
SURCOUCHE = GEOCODING / "surcouche.csv"
PROPOSITIONS = GEOCODING / "propositions.csv"
RAPPORT = METADATA / "propositions-rapport.json"
SEUIL_HAUT, SEUIL_MOYEN = 0.97, 0.80
COL_SURCOUCHE = ["id", "adresse", "lon", "lat", "code_insee", "precision", "methode", "source", "statut", "commentaire"]
COL_PROPOSITIONS = ["id", "annee", "organisme", "ville_source", "commune", "niveau", "methode", "score", "nom_trouve",
                    "siren", "siret", "adresse", "lon", "lat", "code_insee", "statut", "commentaire"]

_DOMAINE = re.compile(r"(\.(fr|com|org|net|eu|io|co|info|gouv)\b|\bwww\b|https?:)", re.I)
_PERSONNE = re.compile(r"\b(PARTICULIER|MONSIEUR|MADAME|MR|MME)\b|\.\.\.")


# ------------------------------------------------- fonctions pures ---

def interrogeable(organisme: str) -> bool:
    """Faux pour les noms de domaine, les particuliers et les anonymisés.
    Travaille sur le nom brut : la normalisation efface les points."""
    organisme = (organisme or "").strip()
    if len(organisme) < 3:
        return False
    if _DOMAINE.search(organisme) or _PERSONNE.search(organisme.upper()):
        return False
    return True


def nettoyer_requete(organisme: str) -> str:
    """Retire les parenthèses et les mentions de ville ajoutées à la main."""
    q = re.sub(r"\([^)]*\)", " ", organisme)
    q = re.sub(r"\s*-\s+[A-ZÉÈÀ' ]+$", " ", q)  # « X - PARIS », « X SAS- PARIS »
    return re.sub(r"\s+", " ", q).strip()[:120]


def similarite(requete_norm: str, resultat: dict) -> float:
    """Meilleure similarité entre le nom cherché et les noms de l'entité
    (nom complet, raison sociale, sigle, enseignes des établissements)."""
    noms = [resultat.get("nom_complet", ""), resultat.get("nom_raison_sociale", ""), resultat.get("sigle", "") or ""]
    for e in resultat.get("matching_etablissements", []) or []:
        noms += e.get("liste_enseignes") or []
        noms.append(e.get("nom_commercial") or "")
    meilleur = 0.0
    for nom in noms:
        n = normaliser_nom(nom)
        if not n:
            continue
        n_sans_forme = re.sub(r"\b(SAS|SA|SARL|SASU|EURL|SCI|SNC|SE|GIE|SCOP|SEM|EPIC|ETS)\b", " ", n).strip()
        n_sans_forme = re.sub(r"\s+", " ", n_sans_forme)
        for variante in (n, n_sans_forme):
            meilleur = max(meilleur, difflib.SequenceMatcher(None, requete_norm, variante).ratio())
            if requete_norm and variante.startswith(requete_norm + " "):
                meilleur = max(meilleur, 0.9)
    return round(meilleur, 3)


def coord(valeur) -> float | None:
    """Coordonnée SIRENE en float ; None si absente ou « [NON-DIFFUSIBLE] »."""
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def meme_commune(code_a: str, code_b: str) -> bool:
    """Égalité de codes INSEE, en ramenant les arrondissements municipaux
    (751xx, 6938x, 132xx) à leur commune."""
    def mere(c):
        c = c or ""
        if c.startswith("751") and len(c) == 5:
            return "75056"
        if c.startswith("6938") and len(c) == 5:
            return "69123"
        if c.startswith("132") and len(c) == 5:
            return "13055"
        return c
    return bool(code_a) and mere(code_a) == mere(code_b)


def classer(requete_norm: str, code_insee: str, resultats: list[dict]) -> dict | None:
    """Renvoie la meilleure proposition {niveau, methode, score, ...} ou None."""
    candidats = []
    for r in resultats:
        score = similarite(requete_norm, r)
        if score < SEUIL_MOYEN:
            continue
        siege = r.get("siege") or {}
        lon, lat = coord(siege.get("longitude")), coord(siege.get("latitude"))
        if meme_commune(siege.get("commune"), code_insee) and lon is not None and lat is not None:
            candidats.append({"score": score, "methode": "siege", "siren": r.get("siren", ""),
                              "siret": siege.get("siret", ""), "nom_trouve": r.get("nom_complet", ""),
                              "adresse": siege.get("adresse", ""), "lon": lon, "lat": lat,
                              "code_insee": siege.get("commune", "")})
            continue
        for e in r.get("matching_etablissements", []) or []:
            lon, lat = coord(e.get("longitude")), coord(e.get("latitude"))
            if meme_commune(e.get("commune"), code_insee) and lon is not None and lat is not None:
                candidats.append({"score": score, "methode": "etablissement", "siren": r.get("siren", ""),
                                  "siret": e.get("siret", ""), "nom_trouve": r.get("nom_complet", ""),
                                  "adresse": e.get("adresse", ""), "lon": lon, "lat": lat,
                                  "code_insee": e.get("commune", "")})
                break
    if not candidats:
        return None
    candidats.sort(key=lambda c: (-c["score"], c["methode"] != "siege"))
    meilleur = dict(candidats[0])
    sieges_hauts = {c["siren"] for c in candidats if c["methode"] == "siege" and c["score"] >= SEUIL_HAUT}
    if meilleur["methode"] == "siege" and meilleur["score"] >= SEUIL_HAUT and len(sieges_hauts) == 1:
        meilleur["niveau"] = "haut"
    else:
        meilleur["niveau"] = "moyen"
        if len(sieges_hauts) > 1:
            meilleur["commentaire"] = f"{len(sieges_hauts)} entités homonymes avec siège dans la commune"
    return meilleur


# ------------------------------------------------------- réseau ---

def interroger(requete: str, departement: str) -> list[dict]:
    params = {"q": requete, "per_page": 10}
    if departement:
        params["departement"] = departement
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "controles-cnil (https://github.com/tbzt/controles-cnil)"})
    for tentative in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as reponse:
                return json.loads(reponse.read().decode("utf-8")).get("results", [])
        except Exception as exc:  # noqa: BLE001
            if tentative == 2:
                journal(f"  échec réseau pour « {requete} » : {exc}")
                return []
            time.sleep(2 * (tentative + 1))
    return []


def lire_csv(chemin):
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--limite", type=int, default=0, help="nombre maximal de requêtes (0 = toutes)")
    parseur.add_argument("--seulement-annee", type=int, default=0)
    args = parseur.parse_args(argv)

    controles = lire_csv(PROCESSED / "controles.csv")
    loc = {l["id"]: l for l in lire_csv(PROCESSED / "localisations.csv")}
    surcouche = {r["id"]: r for r in lire_csv(SURCOUCHE)}
    propositions = {r["id"]: r for r in lire_csv(PROPOSITIONS)}
    aujourdhui = dt.date.today().isoformat()

    cibles = []
    ignores = Counter()
    for r in controles:
        l = loc[r["id"]]
        if args.seulement_annee and int(r["annee"]) != args.seulement_annee:
            continue
        if surcouche.get(r["id"], {}).get("statut") == "valide":
            ignores["deja_adresse_validee"] += 1
        elif r["pays"] != "FR" or not l["code_insee"]:
            ignores["hors_france_ou_sans_commune"] += 1
        elif not interrogeable(r["organisme"]):
            ignores["non_interrogeable"] += 1
        else:
            cibles.append(r)
    journal(f"{len(cibles)} contrôles à traiter, ignorés : {dict(ignores)}")

    # Une requête par (nom, département, commune), les résultats sont partagés.
    groupes = defaultdict(list)
    for r in cibles:
        groupes[(r["organisme_norm"], loc[r["id"]]["departement"], loc[r["id"]]["code_insee"])].append(r)
    cles = sorted(groupes)
    if args.limite:
        cles = cles[:args.limite]
    journal(f"{len(cles)} requêtes distinctes")

    compte = Counter()
    for i, cle in enumerate(cles, 1):
        nom_norm, departement, code_insee = cle
        exemplaire = groupes[cle][0]
        resultats = interroger(nettoyer_requete(exemplaire["organisme"]), departement[:2] if departement and not departement.startswith("97") else departement)
        time.sleep(0.15)
        prop = classer(nom_norm, code_insee, resultats)
        for r in groupes[cle]:
            l = loc[r["id"]]
            if prop is None:
                compte["rien"] += 1
                continue
            compte[prop["niveau"]] += 1
            if prop["niveau"] == "haut":
                surcouche[r["id"]] = {
                    "id": r["id"], "adresse": prop["adresse"], "lon": f"{prop['lon']:.6f}", "lat": f"{prop['lat']:.6f}",
                    "code_insee": l["code_insee"], "precision": "adresse", "methode": "siege_auto",
                    "source": f"annuaire-entreprises SIREN {prop['siren']} ({aujourdhui})", "statut": "valide",
                    "commentaire": f"score {prop['score']:.2f} ; {prop['nom_trouve']}",
                }
                propositions.pop(r["id"], None)
            else:
                propositions[r["id"]] = {
                    "id": r["id"], "annee": r["annee"], "organisme": r["organisme"], "ville_source": r["ville_source"],
                    "commune": l["commune"], "niveau": prop["niveau"], "methode": prop["methode"], "score": f"{prop['score']:.2f}",
                    "nom_trouve": prop["nom_trouve"], "siren": prop["siren"], "siret": prop["siret"],
                    "adresse": prop["adresse"], "lon": f"{prop['lon']:.6f}", "lat": f"{prop['lat']:.6f}",
                    "code_insee": l["code_insee"], "statut": "a_verifier", "commentaire": prop.get("commentaire", ""),
                }
        if i % 100 == 0:
            journal(f"  {i}/{len(cles)} requêtes, {dict(compte)}")

    for chemin, colonnes, lignes in ((SURCOUCHE, COL_SURCOUCHE, surcouche), (PROPOSITIONS, COL_PROPOSITIONS, propositions)):
        tampon = io.StringIO()
        w = csv.DictWriter(tampon, fieldnames=colonnes, lineterminator="\n")
        w.writeheader()
        for rid in sorted(lignes):
            w.writerow({c: lignes[rid].get(c, "") for c in colonnes})
        ecrire_texte(chemin, tampon.getvalue())

    rapport = {"date": aujourdhui, "cibles": len(cibles), "requetes": len(cles), "ignores": dict(ignores),
               "resultats": dict(compte),
               "surcouche_par_methode": dict(Counter(r["methode"] for r in surcouche.values() if r["statut"] == "valide")),
               "propositions_en_attente": sum(1 for p in propositions.values() if p["statut"] == "a_verifier")}
    ecrire_json(RAPPORT, rapport)
    journal(f"terminé : {dict(compte)} ; surcouche validée par méthode : {rapport['surcouche_par_methode']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
