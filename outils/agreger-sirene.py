"""Dénominateur du taux de désignation de DPO : sièges actifs par commune et
section NAF, depuis les stocks SIRENE de l'INSEE.

    python3 outils/agreger-sirene.py [--dossier-temporaire <dir>] [--limite N] [--garder]

Lit deux fichiers du jeu data.gouv.fr « Base Sirene des entreprises et de
leurs établissements » (identifiant 5b7ffc618b4c4169d30727e0), lourds
(~1 Go et ~3 Go zippés), et n'en garde qu'un agrégat de quelques Mo :

1. `StockUniteLegale` : pour chaque unité légale active, on retient si elle
   est une personne morale (catégorie juridique différente de 1000,
   entrepreneur individuel). Deux tableaux de bits indexés par SIREN
   (125 Mo chacun) évitent de garder des millions de chaînes en mémoire.
2. `StockEtablissement` : pour chaque établissement siège actif d'une unité
   légale active, on compte par (commune, section NAF de l'établissement).

Sortie : `data/referentiels-source/sirene-sieges-par-commune.csv`
(`code_insee;section;personnes_morales;total`) et un fichier de métadonnées
à côté (date des stocks, URL, effectifs). Le taux de désignation du site
utilise `personnes_morales` par défaut : les entrepreneurs individuels ne
sont pratiquement jamais soumis à l'obligation de désigner un DPO, et ils
sont 40 % du stock ; les compter écraserait tous les taux.

Ce script tourne hors du build (workflow trimestriel `agreger-sirene.yml`,
ou à la main) ; le pipeline lit seulement son résultat commité. Aucun
horodatage n'est écrit dans le CSV, seulement dans le fichier de
métadonnées, et la date retenue est celle des stocks INSEE, pas celle de
l'exécution.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import REFERENTIELS_SOURCE, ecrire_json, ecrire_texte, erreur_fatale, journal  # noqa: E402

DATASET_ID = "5b7ffc618b4c4169d30727e0"
API_DATASET = f"https://www.data.gouv.fr/api/1/datasets/{DATASET_ID}/"
USER_AGENT = "controles-cnil (https://github.com/tbzt/controles-cnil)"
SORTIE = REFERENTIELS_SOURCE / "sirene-sieges-par-commune.csv"
META = REFERENTIELS_SOURCE / "sirene-sieges-par-commune.meta.json"
CATEGORIE_ENTREPRENEUR_INDIVIDUEL = "1000"
DATE_STOCK = re.compile(r"(\d{1,2})(?:er)?\s+([a-zéû]+)\s+(\d{4})", re.IGNORECASE)
MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}

# Section NAF rév. 2 d'après la division (deux premiers chiffres du code).
SECTIONS = [("A", 1, 3), ("B", 5, 9), ("C", 10, 33), ("D", 35, 35), ("E", 36, 39), ("F", 41, 43), ("G", 45, 47),
            ("H", 49, 53), ("I", 55, 56), ("J", 58, 63), ("K", 64, 66), ("L", 68, 68), ("M", 69, 75), ("N", 77, 82),
            ("O", 84, 84), ("P", 85, 85), ("Q", 86, 88), ("R", 90, 93), ("S", 94, 96), ("T", 97, 98), ("U", 99, 99)]
_SECTION_PAR_DIVISION = {d: s for s, a, b in SECTIONS for d in range(a, b + 1)}


def section_naf(code: str) -> str:
    """« 8411Z » → « O » ; vide si le code est absent ou inconnu."""
    if not code or len(code) < 2 or not code[:2].isdigit():
        return ""
    return _SECTION_PAR_DIVISION.get(int(code[:2]), "")


# --------------------------------------------------------- tableaux de bits ---

class Bits:
    """Un bit par SIREN possible (10^9) : 125 Mo, accès O(1)."""

    def __init__(self):
        self.octets = bytearray(10**9 // 8)
        self.n = 0

    def poser(self, siren: str) -> None:
        i = int(siren)
        self.octets[i >> 3] |= 1 << (i & 7)
        self.n += 1

    def __contains__(self, siren: str) -> bool:
        i = int(siren)
        return bool(self.octets[i >> 3] & (1 << (i & 7)))


# ----------------------------------------------------------------- réseau ---

def telecharger(url: str, destination: Path) -> None:
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(requete, timeout=120) as reponse, open(destination, "wb") as f:
        lu = 0
        for bloc in iter(lambda: reponse.read(1 << 22), b""):
            f.write(bloc)
            lu += len(bloc)
    journal(f"téléchargé {destination.name} ({lu // (1 << 20)} Mo)")


def ressources_stock() -> dict:
    """URL et titre des deux fichiers zip courants, depuis l'API data.gouv.fr."""
    requete = urllib.request.Request(API_DATASET, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(requete, timeout=60) as r:
        d = json.load(r)
    trouve = {}
    for res in d.get("resources", []):
        titre = res.get("title") or ""
        if (res.get("format") or "").lower() != "zip":
            continue
        for cle, motif in (("unites_legales", "StockUniteLegale "), ("etablissements", "StockEtablissement ")):
            if motif in titre and cle not in trouve:
                trouve[cle] = {"titre": titre, "url": res["url"], "taille": res.get("filesize"),
                               "last_modified": res.get("last_modified"), "date_stock": date_stock(titre)}
    manquants = [k for k in ("unites_legales", "etablissements") if k not in trouve]
    if manquants:
        erreur_fatale(f"ressources introuvables sur data.gouv.fr : {manquants}")
    return trouve


def date_stock(titre: str) -> str:
    """« Sirene : Fichier StockUniteLegale - 01 septembre 2026 » → « 2026-09-01 »."""
    m = DATE_STOCK.search(titre)
    if not m or m.group(2).lower() not in MOIS:
        return ""
    return f"{int(m.group(3)):04d}-{MOIS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


# ------------------------------------------------------------- lecture ---

def lignes_du_zip(chemin: Path):
    """Itère les lignes CSV du premier fichier du zip, en flux."""
    with zipfile.ZipFile(chemin) as z:
        noms = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not noms:
            erreur_fatale(f"{chemin.name} : aucun CSV dans l'archive")
        with z.open(noms[0]) as brut:
            texte = io.TextIOWrapper(brut, encoding="utf-8", newline="")
            yield from csv.reader(texte)


def indices(entete: list[str], *noms: str) -> list[int]:
    manquants = [n for n in noms if n not in entete]
    if manquants:
        erreur_fatale(f"colonnes absentes du stock SIRENE : {manquants} ; l'INSEE a changé son format")
    return [entete.index(n) for n in noms]


def passe_unites_legales(chemin: Path, limite: int | None = None) -> tuple[Bits, Bits]:
    """Renvoie (actives, personnes_morales_actives)."""
    actives, morales = Bits(), Bits()
    it = lignes_du_zip(chemin)
    i_siren, i_etat, i_cat = indices(next(it), "siren", "etatAdministratifUniteLegale", "categorieJuridiqueUniteLegale")
    n = 0
    for ligne in it:
        n += 1
        if limite and n > limite:
            break
        if ligne[i_etat] != "A" or not ligne[i_siren].isdigit():
            continue
        actives.poser(ligne[i_siren])
        if ligne[i_cat] != CATEGORIE_ENTREPRENEUR_INDIVIDUEL:
            morales.poser(ligne[i_siren])
        if n % 5_000_000 == 0:
            journal(f"unités légales : {n:,} lignes lues".replace(",", " "))
    journal(f"unités légales : {n:,} lignes, {actives.n:,} actives, {morales.n:,} personnes morales actives".replace(",", " "))
    return actives, morales


def passe_etablissements(chemin: Path, actives: Bits, morales: Bits, limite: int | None = None) -> tuple[Counter, Counter, dict]:
    """Compte les sièges actifs par (commune, section) : total et personnes morales."""
    total, morales_c = Counter(), Counter()
    it = lignes_du_zip(chemin)
    i_siren, i_siege, i_etat, i_commune, i_naf = indices(
        next(it), "siren", "etablissementSiege", "etatAdministratifEtablissement", "codeCommuneEtablissement", "activitePrincipaleEtablissement")
    n = sieges = sans_commune = 0
    for ligne in it:
        n += 1
        if limite and n > limite:
            break
        if ligne[i_siege] != "true" or ligne[i_etat] != "A" or not ligne[i_siren].isdigit():
            continue
        if ligne[i_siren] not in actives:
            continue
        sieges += 1
        commune = ligne[i_commune]
        if not commune:
            sans_commune += 1
            commune = "?"
        cle = (commune, section_naf(ligne[i_naf]))
        total[cle] += 1
        if ligne[i_siren] in morales:
            morales_c[cle] += 1
        if n % 5_000_000 == 0:
            journal(f"établissements : {n:,} lignes lues, {sieges:,} sièges actifs retenus".replace(",", " "))
    journal(f"établissements : {n:,} lignes, {sieges:,} sièges actifs, {sans_commune:,} sans commune".replace(",", " "))
    return total, morales_c, {"lignes_etablissements": n, "sieges_actifs": sieges, "sieges_sans_commune": sans_commune}


# -------------------------------------------------------------- écriture ---

def ecrire_agregat(total: Counter, morales: Counter) -> bool:
    lignes = ["code_insee;section;personnes_morales;total"]
    for (commune, section) in sorted(total):
        lignes.append(f"{commune};{section};{morales.get((commune, section), 0)};{total[(commune, section)]}")
    return ecrire_texte(SORTIE, "\n".join(lignes) + "\n")


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--dossier-temporaire", help="où poser les zips (4 Go) ; par défaut un dossier temporaire")
    parseur.add_argument("--limite", type=int, help="ne lire que N lignes de chaque stock (essai)")
    parseur.add_argument("--garder", action="store_true", help="ne pas supprimer les zips téléchargés")
    parseur.add_argument("--fichiers-locaux", nargs=2, metavar=("UL.zip", "ETAB.zip"), help="utiliser des zips déjà téléchargés")
    args = parseur.parse_args(argv)

    if args.fichiers_locaux:
        ul, etab = Path(args.fichiers_locaux[0]), Path(args.fichiers_locaux[1])
        ressources = {"unites_legales": {"titre": ul.name, "url": "", "date_stock": ""}, "etablissements": {"titre": etab.name, "url": "", "date_stock": ""}}
    else:
        ressources = ressources_stock()
        journal(f"stocks : {ressources['unites_legales']['titre']} ; {ressources['etablissements']['titre']}")
        dossier = Path(args.dossier_temporaire) if args.dossier_temporaire else Path(tempfile.mkdtemp(prefix="sirene-"))
        dossier.mkdir(parents=True, exist_ok=True)
        ul, etab = dossier / "StockUniteLegale.zip", dossier / "StockEtablissement.zip"
        if not ul.exists():
            telecharger(ressources["unites_legales"]["url"], ul)

    actives, morales = passe_unites_legales(ul, args.limite)
    if not args.fichiers_locaux and not args.garder:
        ul.unlink()
    if not args.fichiers_locaux and not etab.exists():
        telecharger(ressources["etablissements"]["url"], etab)
    total, morales_c, mesures = passe_etablissements(etab, actives, morales, args.limite)
    if not args.fichiers_locaux and not args.garder:
        etab.unlink()
    del actives, morales

    change = ecrire_agregat(total, morales_c)
    meta = {
        "_commentaire": "Sièges actifs d'unités légales actives, par commune (code INSEE) et section NAF rév. 2 de l'établissement ; personnes_morales exclut la catégorie juridique 1000 (entrepreneurs individuels).",
        "source": {"jeu": f"https://www.data.gouv.fr/datasets/{DATASET_ID}", "unites_legales": ressources["unites_legales"], "etablissements": ressources["etablissements"]},
        "date_stock": ressources["etablissements"]["date_stock"] or ressources["unites_legales"]["date_stock"],
        "limite_lignes": args.limite,
        "mesures": {**mesures, "sieges_personnes_morales": sum(morales_c.values()), "communes": len({c for c, _ in total}),
                    "sections": sorted({s for _, s in total})},
    }
    ecrire_json(META, meta)
    journal(f"{SORTIE.name} : {len(total)} couples commune × section, {sum(total.values()):,} sièges dont {sum(morales_c.values()):,} personnes morales ; "
            .replace(",", " ") + ("mis à jour" if change else "inchangé"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
