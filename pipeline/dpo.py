"""Étape 19 : transformer le fichier « organismes ayant désigné un DPO ».

Lit la dernière version archivée par `fetch.py --jeu dpo` (manifeste
`data/metadata/manifest-dpo.json`) et produit
`data/processed/dpo/organismes.csv` : une désignation par ligne, dix-huit
colonnes d'organisme, **aucune colonne de contact**. Les huit colonnes
e-mail, URL, téléphone et adresse du DPO sont des données personnelles
couvertes par l'avertissement 2 du jeu : elles sont supprimées ici et ne
sont jamais republiées (`validate.py` le vérifie).

Ce que fait la transformation :
- reconnaissance des 26 colonnes par leur en-tête normalisé, jamais par
  position ; un en-tête inconnu ou absent arrête le script ;
- `null` / `NULL` → vide ; espaces et retours à la ligne normalisés ;
- code postal français à 4 chiffres → zéro initial rétabli (drapeau
  `code_postal_corrige`) ;
- pays → code ISO 3166-1 alpha-2 par `mappings/pays.json` ; pays vide avec un
  code postal français à 5 chiffres → FR (drapeau `pays_deduit`) ;
- département déduit du code postal (2A/2B tranchés par la commune, DOM sur
  trois chiffres), puis commune résolue dans le référentiel geo.api.gouv.fr
  par (département, nom de ville normalisé), avec les mêmes règles que
  `geocode.py` (CEDEX retiré, arrondissements) ;
- date `jj/mm/aaaa` → ISO 8601 ; type de DPO → `personne_physique` /
  `personne_morale` ; section NAF vérifiée dans A → U.

Sortie triée par (SIREN, nom normalisé, date, code postal) : deux
exécutions sur le même fichier produisent les mêmes octets. La colonne
`snapshot` porte la date de publication de la ressource par data.gouv.fr
(horodatage de l'URL), pas la date d'exécution.

Usage :
    python3 pipeline/dpo.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import geocode  # noqa: E402
from pipeline.commun import (  # noqa: E402
    METADATA, PROCESSED, RACINE, RAW, REFERENTIELS_SOURCE, cle_normalisee, ecrire_json, ecrire_texte,
    erreur_fatale, journal, lire_json, nettoyer_espaces, normaliser_nom,
)

MANIFESTE = METADATA / "manifest-dpo.json"
SORTIE = PROCESSED / "dpo" / "organismes.csv"
RAPPORT = METADATA / "dpo-rapport.json"
MAPPINGS = RACINE / "pipeline" / "mappings"

# En-têtes attendus (forme normalisée) → nom interne. Les huit colonnes de
# contact sont reconnues pour être écartées explicitement.
ENTETES = {
    "siren organisme designant": "siren",
    "nom organisme designant": "nom",
    "secteur activite organisme designant": "section_naf",
    "code naf organisme designant": "code_naf",
    "adresse postale organisme designant": "adresse",
    "code postal organisme designant": "code_postal",
    "ville organisme designant": "ville",
    "pays organisme designant": "pays",
    "type de dpo": "type_dpo",
    "date de la designation": "date_designation",
    "siren organisme designe": "siren_designe",
    "nom organisme designe": "nom_designe",
    "secteur activite organisme designe": "section_naf_designe",
    "code naf organisme designe": "code_naf_designe",
    "adresse postale organisme designe": "adresse_designe",
    "code postal organisme designe": "code_postal_designe",
    "ville organisme designe": "ville_designe",
    "pays organisme designe": "pays_designe",
    "moyen contact dpo email": "_contact_email",
    "moyen contact dpo url": "_contact_url",
    "moyen contact dpo telephone": "_contact_telephone",
    "moyen contact dpo adresse postale": "_contact_adresse",
    "moyen contact dpo code postal": "_contact_code_postal",
    "moyen contact dpo ville": "_contact_ville",
    "moyen contact dpo pays": "_contact_pays",
    "moyen contact dpo autre": "_contact_autre",
}
COLONNES_CONTACT = sorted(v for v in ENTETES.values() if v.startswith("_contact_"))

COLONNES = [
    "snapshot", "siren", "nom", "nom_norm", "section_naf", "code_naf", "adresse", "code_postal", "ville_source",
    "code_insee", "commune", "departement", "region", "pays", "type_dpo", "date_designation",
    "siren_designe", "nom_designe", "nom_designe_norm", "section_naf_designe", "code_naf_designe",
    "code_postal_designe", "ville_designe", "pays_designe", "drapeaux",
]
SECTIONS_NAF = set("ABCDEFGHIJKLMNOPQRSTU")
TYPES_DPO = {"personne physique": "personne_physique", "personne morale": "personne_morale"}
DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
DEPARTEMENTS_CORSE = ("2A", "2B")


# ----------------------------------------------------------- lecture ---

def fichier_courant(manifeste: dict) -> tuple[Path, str]:
    """Dernière version archivée du CSV DPO et sa date de publication."""
    for entree in manifeste.get("ressources", {}).values():
        versions = entree.get("versions") or []
        if entree.get("format") == "csv" and versions:
            v = versions[-1]
            return RAW / v["fichier"], (v.get("publie_le") or v.get("last_modified_source") or "")[:10]
    erreur_fatale("manifest-dpo.json ne référence aucun CSV ; lancez fetch.py --jeu dpo")


def lire_brut(chemin: Path) -> tuple[list[str], list[list[str]]]:
    """Lit le CSV (UTF-8 avec BOM, `;`, champs entre guillemets) et vérifie
    la signature d'en-têtes."""
    csv.field_size_limit(1 << 28)
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        lecteur = csv.reader(f, delimiter=";", quotechar='"')
        entete = [cle_normalisee(h) for h in next(lecteur)]
        lignes = list(lecteur)
    inconnus = [h for h in entete if h not in ENTETES]
    absents = [h for h in ENTETES if h not in entete]
    if inconnus or absents:
        erreur_fatale(f"en-têtes du fichier DPO non reconnus : inconnus {inconnus}, absents {absents} ; "
                      f"ajoutez une entrée dans ENTETES (pipeline/dpo.py)")
    mal_formees = [i + 2 for i, l in enumerate(lignes) if len(l) != len(entete)]
    if mal_formees:
        erreur_fatale(f"{len(mal_formees)} lignes n'ont pas {len(entete)} champs (premières : {mal_formees[:5]})")
    return entete, lignes


# ------------------------------------------------------ normalisation ---

def vide_si_null(valeur: str) -> str:
    v = nettoyer_espaces(valeur)
    return "" if v.lower() == "null" else v


def code_iso_pays(libelle: str, table: dict) -> str:
    """Libellé de pays → ISO ; vide si inconnu (signalé dans le rapport)."""
    cle = cle_normalisee(libelle)
    if not cle:
        return ""
    return table.get(cle, "")


def date_iso(valeur: str) -> str:
    m = DATE.match(valeur)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def departement_du_code_postal(cp: str) -> str:
    """« 75008 » → « 75 », « 97400 » → « 974 », « 20000 » → « 20 » (à trancher)."""
    if not re.fullmatch(r"\d{5}", cp):
        return ""
    if cp[:2] in ("97", "98"):
        return cp[:3]
    return cp[:2]


def resoudre_commune(ref: geocode.Referentiel, departement: str, ville: str, alias: dict | None = None) -> tuple[dict | None, list[str]]:
    """Commune du référentiel pour (département du code postal, nom de ville).
    La table d'alias des contrôles (`data/geocoding/alias-villes.csv`) est
    consultée d'abord : « PARIS LA DEFENSE », « CERGY PONTOISE »… y sont déjà."""
    drapeaux = []
    cle = geocode.cle_ville(ville)
    if not cle:
        return None, ["ville_absente"]
    if alias:
        a = alias.get((departement, cle)) or alias.get(("*", cle)) or alias.get(("", cle))
        if a and a.get("code_insee") and a["code_insee"] in ref.par_code:
            return ref.par_code[a["code_insee"]], ["alias"]
    candidats = ref.chercher(departement, cle)
    if not candidats and departement:
        partout = ref.par_nom.get(cle, [])
        if len(partout) == 1:
            candidats = partout
            drapeaux.append("departement_contredit_par_ville")
    if not candidats:
        return None, ["ville_non_resolue"]
    if len(candidats) > 1:
        candidats = sorted(candidats, key=lambda c: -(c.get("population") or 0))
        drapeaux.append("commune_homonyme")
    return candidats[0], drapeaux


def transformer_ligne(brut: dict, snapshot: str, tables: dict) -> dict:
    ref: geocode.Referentiel = tables["referentiel"]
    d: list[str] = []
    e = {k: vide_si_null(v) for k, v in brut.items() if not k.startswith("_contact_")}

    siren = e["siren"]
    if siren and not re.fullmatch(r"\d{9}", siren):
        d.append("siren_mal_forme")
    section = e["section_naf"].upper()
    if section and section not in SECTIONS_NAF:
        d.append("section_naf_inconnue")
        section = ""
    section_designe = e["section_naf_designe"].upper()
    if section_designe not in SECTIONS_NAF:
        section_designe = ""

    pays = code_iso_pays(e["pays"], tables["pays"])
    if e["pays"] and not pays:
        d.append("pays_inconnu")
    cp = e["code_postal"]
    if re.fullmatch(r"\d{4}", cp) and pays in ("FR", ""):
        cp = "0" + cp
        d.append("code_postal_corrige")
    if not e["pays"] and re.fullmatch(r"\d{5}", cp):
        pays = "FR"
        d.append("pays_deduit")

    departement = region = code_insee = commune = ""
    if pays == "FR":
        departement = departement_du_code_postal(cp)
        if departement == "20":
            # Corse : le nom de la commune tranche entre 2A et 2B ; sinon la
            # convention postale (2A au sud de 20200) avec un drapeau.
            c, dr = resoudre_commune(ref, "20", e["ville"], tables.get("alias"))
            if c is None:
                departement = "2A" if cp < "20200" else "2B"
                d.append("corse_departement_postal")
                d += dr
            else:
                departement = c["departement"]
                d += dr
                code_insee, commune, region = c["code"], c["nom"], c["region"]
        elif departement:
            c, dr = resoudre_commune(ref, departement, e["ville"], tables.get("alias"))
            d += dr
            if c is not None:
                code_insee, commune, region = c["code"], c["nom"], c["region"]
                if c["departement"] != departement:
                    departement = c["departement"]
        else:
            d.append("code_postal_invalide")
        if departement and not region:
            region = ref.departements.get(departement, {}).get("region", "")

    type_dpo = TYPES_DPO.get(e["type_dpo"].lower(), "")
    if not type_dpo:
        d.append("type_dpo_inconnu")
    date = date_iso(e["date_designation"])
    if not date:
        d.append("date_invalide")

    return {
        "snapshot": snapshot, "siren": siren, "nom": e["nom"], "nom_norm": normaliser_nom(e["nom"]),
        "section_naf": section, "code_naf": e["code_naf"].upper(), "adresse": e["adresse"], "code_postal": cp,
        "ville_source": e["ville"], "code_insee": code_insee, "commune": commune, "departement": departement,
        "region": region, "pays": pays, "type_dpo": type_dpo, "date_designation": date,
        "siren_designe": e["siren_designe"], "nom_designe": e["nom_designe"], "nom_designe_norm": normaliser_nom(e["nom_designe"]),
        "section_naf_designe": section_designe, "code_naf_designe": e["code_naf_designe"].upper(),
        "code_postal_designe": e["code_postal_designe"], "ville_designe": e["ville_designe"],
        "pays_designe": code_iso_pays(e["pays_designe"], tables["pays"]),
        "drapeaux": "|".join(sorted(set(d))),
    }


def transformer(entete: list[str], lignes: list[list[str]], snapshot: str, tables: dict) -> list[dict]:
    noms = [ENTETES[h] for h in entete]
    sorties = [transformer_ligne(dict(zip(noms, l)), snapshot, tables) for l in lignes]
    sorties.sort(key=lambda r: (r["siren"] or "~", r["nom_norm"], r["date_designation"], r["code_postal"], r["type_dpo"]))
    return sorties


# --------------------------------------------------------- tables ---

def charger_tables() -> dict:
    communes = lire_json(REFERENTIELS_SOURCE / "communes.json")
    if not communes:
        erreur_fatale("data/referentiels-source/communes.json absent")
    departements = {d["code"]: d for d in (lire_json(PROCESSED / "referentiels" / "departements.json") or {}).get("departements", [])}
    pays = lire_json(MAPPINGS / "pays.json")["pays"]
    alias = {}
    for r in geocode.lire_csv(geocode.ALIAS):
        alias[(r["departement_source"].strip(), geocode.cle_ville(r["ville_source"]))] = r
    return {"referentiel": geocode.Referentiel(communes, departements), "pays": pays, "alias": alias}


# --------------------------------------------------------- rapport ---

def rapport(sorties: list[dict], snapshot: str, source: Path) -> dict:
    total = len(sorties)
    france = [s for s in sorties if s["pays"] == "FR"]
    drapeaux: Counter = Counter()
    for s in sorties:
        for dr in s["drapeaux"].split("|"):
            if dr:
                drapeaux[dr] += 1
    return {
        "snapshot": snapshot,
        "source_fichier": source.name,
        "total": total,
        "colonnes_contact_supprimees": COLONNES_CONTACT,
        "par_type": dict(sorted(Counter(s["type_dpo"] for s in sorties).items())),
        "par_pays": dict(Counter(s["pays"] or "?" for s in sorties).most_common()),
        "par_section": dict(sorted(Counter(s["section_naf"] or "?" for s in sorties).items())),
        "france": total and len(france),
        "france_commune_resolue": sum(1 for s in france if s["code_insee"]),
        "sans_siren": sum(1 for s in sorties if not s["siren"]),
        "drapeaux": dict(sorted(drapeaux.items())),
        "annees": dict(sorted(Counter(s["date_designation"][:4] or "?" for s in sorties).items())),
        "structures_designees_distinctes": len({s["nom_designe_norm"] for s in sorties if s["nom_designe_norm"]}),
    }


# --------------------------------------------------------- écriture ---

def ecrire_sortie(sorties: list[dict]) -> bool:
    lignes = [",".join(COLONNES)]
    import io
    tampon = io.StringIO(newline="")
    w = csv.writer(tampon, lineterminator="\n")
    for s in sorties:
        w.writerow([s[c] for c in COLONNES])
    return ecrire_texte(SORTIE, lignes[0] + "\n" + tampon.getvalue())


def main(argv=None) -> int:
    manifeste = lire_json(MANIFESTE, {}) or {}
    chemin, snapshot = fichier_courant(manifeste)
    if not chemin.exists():
        erreur_fatale(f"{chemin.relative_to(RACINE)} absent de data/raw/")
    entete, lignes = lire_brut(chemin)
    tables = charger_tables()
    sorties = transformer(entete, lignes, snapshot, tables)
    change = ecrire_sortie(sorties)
    r = rapport(sorties, snapshot, chemin)
    change = ecrire_json(RAPPORT, r) or change
    journal(f"{r['total']} désignations (snapshot {snapshot}), {r['france_commune_resolue']} communes résolues sur {r['france']} en France, "
            f"{r['sans_siren']} sans SIREN ; {len(COLONNES_CONTACT)} colonnes de contact supprimées")
    journal(("mis à jour" if change else "inchangés") + f" : {SORTIE.relative_to(RACINE)}, {RAPPORT.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
