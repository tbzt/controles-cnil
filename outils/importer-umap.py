"""Importe la surcouche d'adresses depuis un export uMap (usage ponctuel).

    python3 outils/importer-umap.py data/referentiels-source/umap-export-2026-09-11.umap [--adresse-inverse]

Ce que fait l'import :

1. lit chaque objet de l'export (une couche par année et par secteur) ;
2. écarte les objets posés au siège de la CNIL : ce sont les contrôles à
   distance, dont l'adresse de l'organisme n'a pas été cherchée ;
3. apparie chaque objet à un contrôle de `data/processed/controles.csv` par
   année et nom d'organisme normalisé (exact, puis approché), et, quand un
   organisme a plusieurs contrôles la même année, par proximité entre le
   point uMap et la commune du contrôle ;
4. écrit `data/geocoding/surcouche.csv` : une adresse par identifiant,
   statut `valide` si le point est à moins de 30 km de la commune indiquée
   par la CNIL, `a_verifier` sinon ;
5. avec `--adresse-inverse`, complète le libellé d'adresse manquant par
   géocodage inverse (api-adresse.data.gouv.fr). C'est le seul appel réseau
   du dépôt en dehors de fetch.py, et il n'a lieu que dans cet outil.

Le rapport `data/metadata/import-umap-rapport.json` liste les objets non
appariés et les contrôles restés sans adresse.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import GEOCODING, METADATA, PROCESSED, ecrire_json, ecrire_texte, journal, normaliser_nom  # noqa: E402

SURCOUCHE = GEOCODING / "surcouche.csv"
RAPPORT = METADATA / "import-umap-rapport.json"
CNIL = (2.307276, 48.850654)
SEUIL_KM = 30
COLONNES = ["id", "adresse", "lon", "lat", "code_insee", "precision", "methode", "source", "statut", "commentaire"]


def distance_km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * math.cos(math.radians(a[1])) * 111.32, (a[1] - b[1]) * 110.57)


def lire_csv(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def objets_umap(export: dict) -> list[dict]:
    objets = []
    for couche in export["layers"]:
        m = re.match(r"(20\d\d)", couche["_umap_options"].get("name", ""))
        if not m:
            continue
        for f in couche["features"]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            objets.append({
                "annee": int(m.group(1)),
                "nom": p.get("name") or p.get("nom") or p.get("Organismes") or "",
                "adresse": (p.get("adresse") or p.get("Adresse") or p.get("result_label") or "").strip(),
                "lon": float(lon), "lat": float(lat),
                "couche": couche["_umap_options"]["name"],
            })
    return objets


def adresse_inverse(lon: float, lat: float) -> str:
    url = f"https://api-adresse.data.gouv.fr/reverse/?lon={lon:.6f}&lat={lat:.6f}"
    requete = urllib.request.Request(url, headers={"User-Agent": "controles-cnil (https://github.com/tbzt/controles-cnil)"})
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            feats = json.loads(reponse.read().decode("utf-8")).get("features", [])
    except Exception:  # noqa: BLE001 — outil ponctuel : on continue sans libellé
        return ""
    if not feats:
        return ""
    p = feats[0]["properties"]
    return p.get("label", "") if p.get("distance", 0) <= 300 else ""


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("export", type=Path)
    parseur.add_argument("--adresse-inverse", action="store_true", help="compléter les adresses manquantes via api-adresse.data.gouv.fr")
    args = parseur.parse_args(argv)

    export = json.loads(args.export.read_text(encoding="utf-8"))
    objets = objets_umap(export)
    controles = lire_csv(PROCESSED / "controles.csv")
    loc = {l["id"]: l for l in lire_csv(PROCESSED / "localisations.csv")}
    existants = {r["id"]: r for r in lire_csv(SURCOUCHE)} if SURCOUCHE.exists() else {}

    au_siege = [o for o in objets if distance_km((o["lon"], o["lat"]), CNIL) < 0.05]
    candidats = [o for o in objets if distance_km((o["lon"], o["lat"]), CNIL) >= 0.05]
    journal(f"{len(objets)} objets uMap, {len(au_siege)} au siège de la CNIL écartés, {len(candidats)} à apparier")

    par_cle = defaultdict(list)
    for r in controles:
        par_cle[(int(r["annee"]), r["organisme_norm"])].append(r)
    noms_par_annee = defaultdict(set)
    for (annee, nom) in par_cle:
        noms_par_annee[annee].add(nom)

    groupes = defaultdict(list)
    non_apparies, approches = [], 0
    for o in candidats:
        cle = (o["annee"], normaliser_nom(o["nom"]))
        if cle not in par_cle:
            proches = difflib.get_close_matches(cle[1], noms_par_annee[o["annee"]], n=2, cutoff=0.85)
            if len(proches) == 1 or (len(proches) == 2 and difflib.SequenceMatcher(None, cle[1], proches[0]).ratio() > difflib.SequenceMatcher(None, cle[1], proches[1]).ratio() + 0.05):
                cle = (o["annee"], proches[0])
                approches += 1
            else:
                non_apparies.append({"annee": o["annee"], "nom": o["nom"], "couche": o["couche"], "proches": proches})
                continue
        groupes[cle].append(o)

    # Affectation dans chaque groupe : le point uMap va au contrôle dont la commune est la plus proche.
    lignes, pris = {}, set()
    for cle, objs in groupes.items():
        rangs = par_cle[cle]
        paires = []
        for o in objs:
            for r in rangs:
                l = loc[r["id"]]
                d = distance_km((o["lon"], o["lat"]), (float(l["org_lon"]), float(l["org_lat"]))) if l["org_lon"] else 9999
                paires.append((d, id(o), r["id"], o))
        for d, _, rid, o in sorted(paires, key=lambda x: (x[0], x[1])):
            if rid in pris or o.get("_pris"):
                continue
            pris.add(rid)
            o["_pris"] = True
            l = loc[rid]
            valide = d <= SEUIL_KM
            lignes[rid] = {
                "id": rid, "adresse": o["adresse"], "lon": f"{o['lon']:.6f}", "lat": f"{o['lat']:.6f}",
                "code_insee": l["code_insee"] if valide else "",
                "precision": "adresse",
                "methode": "umap_adresse" if o["adresse"] else "umap_coordonnees",
                "source": f"carte uMap, export {args.export.name}",
                "statut": "valide" if valide else "a_verifier",
                "commentaire": "" if valide else f"point à {d:.0f} km de la commune indiquée par la CNIL ({l['commune']})",
            }

    if args.adresse_inverse:
        a_completer = [l for l in lignes.values() if not l["adresse"]]
        journal(f"géocodage inverse de {len(a_completer)} adresses manquantes…")
        for i, l in enumerate(a_completer, 1):
            l["adresse"] = adresse_inverse(float(l["lon"]), float(l["lat"]))
            if l["adresse"]:
                l["methode"] = "umap_coordonnees+adresse_inverse"
            time.sleep(0.03)
            if i % 200 == 0:
                journal(f"  {i}/{len(a_completer)}")

    # Les lignes déjà présentes et validées à la main ne sont jamais écrasées.
    for rid, r in existants.items():
        if r.get("statut") == "valide" and not r.get("source", "").startswith("carte uMap"):
            lignes[rid] = r

    tampon = io.StringIO()
    w = csv.DictWriter(tampon, fieldnames=COLONNES, lineterminator="\n")
    w.writeheader()
    for rid in sorted(lignes):
        w.writerow({c: lignes[rid].get(c, "") for c in COLONNES})
    ecrire_texte(SURCOUCHE, tampon.getvalue())

    sans_adresse = Counter(int(r["annee"]) for r in controles if r["id"] not in lignes)
    rapport = {
        "export": args.export.name,
        "objets": len(objets), "au_siege_cnil_ecartes": len(au_siege),
        "apparies": len(lignes), "dont_par_nom_approche": approches,
        "statuts": dict(Counter(l["statut"] for l in lignes.values())),
        "methodes": dict(Counter(l["methode"] for l in lignes.values())),
        "objets_non_apparies": sorted(non_apparies, key=lambda x: (x["annee"], x["nom"])),
        "controles_sans_adresse_par_annee": dict(sorted(sans_adresse.items())),
    }
    ecrire_json(RAPPORT, rapport)
    journal(f"{len(lignes)} adresses écrites dans {SURCOUCHE.name} ({rapport['statuts']}), "
            f"{len(non_apparies)} objets uMap non appariés, {approches} appariés par nom approché")
    return 0


if __name__ == "__main__":
    sys.exit(main())
