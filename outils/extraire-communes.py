"""Extrait le référentiel des communes depuis geo.api.gouv.fr.

Usage ponctuel, à relancer une fois par an environ (fusions de communes) :

    python3 outils/extraire-communes.py

Écrit `data/referentiels-source/communes.json` : un objet avec la provenance,
la date d'extraction, la liste des champs, puis une ligne compacte par
commune. Le format en tableaux (et non en objets) divise le poids par trois
tout en restant lisible. Le fichier est versionné : le géocodage hors ligne
de `pipeline/geocode.py` ne dépend d'aucun appel réseau.

Contenu : communes (dont Paris, Lyon, Marseille comme communes entières) et
arrondissements municipaux de ces trois villes (codes 751xx, 6938x, 132xx),
pour pouvoir résoudre « PARIS 15 » si la CNIL l'écrit un jour.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import PROCESSED, REFERENTIELS_SOURCE, ecrire_texte, journal, lire_json  # noqa: E402

BASE = "https://geo.api.gouv.fr/communes"
CHAMPS = "code,nom,codeDepartement,codeRegion,centre,population"
SORTIE = REFERENTIELS_SOURCE / "communes.json"


def charger(url: str) -> list[dict]:
    requete = urllib.request.Request(url, headers={"User-Agent": "controles-cnil (https://github.com/tbzt/controles-cnil)"})
    with urllib.request.urlopen(requete, timeout=120) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def ligne(c: dict, type_: str) -> list:
    lon, lat = c["centre"]["coordinates"]
    return [c["code"], c["nom"], c.get("codeDepartement", ""), c.get("codeRegion", ""),
            round(lon, 4), round(lat, 4), c.get("population"), type_]


def main() -> int:
    communes = charger(f"{BASE}?fields={CHAMPS}&format=json")
    arrondissements = charger(f"{BASE}?type=arrondissement-municipal&fields={CHAMPS}&format=json")
    journal(f"{len(communes)} communes, {len(arrondissements)} arrondissements municipaux")
    lignes = sorted([ligne(c, "commune") for c in communes] + [ligne(a, "arrondissement") for a in arrondissements])
    contenu = {
        "_source": BASE,
        "_extrait_le": dt.date.today().isoformat(),
        "_champs": ["code", "nom", "departement", "region", "lon", "lat", "population", "type"],
        "_note": "Centre = centroïde fourni par geo.api.gouv.fr, arrondi à 4 décimales (~10 m). Population : dernière connue par l'API, absente pour quelques communes.",
        "communes": lignes,
    }
    # Une ligne par commune : diff git lisibles, poids contenu.
    texte = ("{\n" + ",\n".join(
        f'  "{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in contenu.items() if k != "communes")
        + ',\n  "communes": [\n'
        + ",\n".join("    " + json.dumps(l, ensure_ascii=False) for l in lignes)
        + "\n  ]\n}\n")
    change = ecrire_texte(SORTIE, texte)
    journal(("mis à jour" if change else "inchangé") + f" : {SORTIE} ({len(texte.encode('utf-8')) // 1024} Ko)")

    # Population par département, somme des communes : sert à la lecture
    # « pour 100 000 habitants » du site.
    chemin_dep = PROCESSED / "referentiels" / "departements.json"
    dep = lire_json(chemin_dep)
    if dep:
        population = {}
        for l in lignes:
            if l[7] == "commune" and l[6]:
                population[l[2]] = population.get(l[2], 0) + int(l[6])
        for d in dep["departements"]:
            d["population"] = population.get(d["code"])
        dep["_note"] = "population : somme des populations communales de communes.json (geo.api.gouv.fr), même date d'extraction"
        texte_dep = json.dumps(dep, ensure_ascii=False, indent=1) + "\n"
        journal(("mis à jour" if ecrire_texte(chemin_dep, texte_dep) else "inchangé") + f" : {chemin_dep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
