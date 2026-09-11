"""Étape 4 : localiser chaque contrôle, hors ligne.

Produit `data/processed/localisations.csv` : pour chaque enregistrement de
`controles.csv`, deux localisations et leur précision.

- **Lieu de l'organisme** (`org_*`) : où se trouve l'entité contrôlée, dans la
  ville indiquée par la CNIL. Résolu dans l'ordre :
    1. surcouche validée (`data/geocoding/surcouche.csv`, adresse → précision
       `adresse`) ;
    2. table d'alias (`data/geocoding/alias-villes.csv`, ville source →
       code INSEE ou pays, écrite à la main) ;
    3. référentiel des communes (`data/referentiels-source/communes.json`,
       par département et nom normalisé → précision `commune`) ;
    4. centroïde du département (précision `departement`) ;
    5. centroïde du pays pour l'étranger (précision `pays`) ;
    6. rien (précision `aucune`).
- **Lieu du contrôle** (`ctrl_*`) : dérivé de la modalité. En ligne, sur
  pièces et sur audition se déroulent dans les locaux de la CNIL
  (`data/geocoding/lieux-institution.json`, précision `institution`) ; sur
  place se déroule chez l'organisme ; modalité non renseignée → lieu de
  l'organisme, drapeau `lieu_controle_inconnu`.

Aucun appel réseau. Deux exécutions sur les mêmes entrées produisent le
même fichier. Les villes non résolues sont listées dans
`data/metadata/geocodage-rapport.json` pour alimenter la table d'alias.

Usage :
    python3 pipeline/geocode.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import (  # noqa: E402
    GEOCODING,
    METADATA,
    PROCESSED,
    RACINE,
    REFERENTIELS_SOURCE,
    ecrire_json,
    ecrire_texte,
    erreur_fatale,
    journal,
    lire_json,
    normaliser_nom,
)

ENTREE = PROCESSED / "controles.csv"
SORTIE = PROCESSED / "localisations.csv"
RAPPORT = METADATA / "geocodage-rapport.json"
COMMUNES = REFERENTIELS_SOURCE / "communes.json"
SURCOUCHE = GEOCODING / "surcouche.csv"
ALIAS = GEOCODING / "alias-villes.csv"
LIEUX = GEOCODING / "lieux-institution.json"
PAYS_CENTROIDES = GEOCODING / "pays-centroides.json"

MODALITES_A_LA_CNIL = {"en_ligne", "sur_pieces", "sur_audition"}
DEPARTEMENTS_AMBIGUS = {"20": ["2A", "2B"], "97": ["971", "972", "973", "974", "976"], "98": ["975", "977", "978", "986", "987", "988"]}

COLONNES = [
    "id", "pays", "code_insee", "commune", "departement", "region",
    "org_lon", "org_lat", "org_precision", "org_methode", "org_adresse", "org_source",
    "ctrl_lieu", "ctrl_lon", "ctrl_lat", "ctrl_precision",
    "drapeaux",
]


# ------------------------------------------------- normalisation ---

_ARRONDISSEMENT = re.compile(r"^(PARIS|LYON|MARSEILLE)\s+(\d{1,2})\s*(?:E|ER|EME|EM)?(?:\s+ARR(?:ONDISSEMENT)?)?$")
_CEDEX = re.compile(r"\bCEDEX\b.*$")


def cle_ville(texte: str) -> str:
    """Clé de rapprochement d'un nom de commune : majuscules sans accents,
    ponctuation → espace, SAINT → ST, CEDEX retiré, « PARIS 15E » → « PARIS 15 »."""
    n = normaliser_nom(texte)
    n = _CEDEX.sub("", n).strip()
    n = re.sub(r"\bSAINTE\b", "STE", n)
    n = re.sub(r"\bSAINT\b", "ST", n)
    m = _ARRONDISSEMENT.match(n)
    if m:
        n = f"{m.group(1)} {int(m.group(2))}"
    return n


def cle_arrondissement(nom_referentiel: str) -> str | None:
    """« Paris 15e Arrondissement » → « PARIS 15 » ; None si ce n'en est pas un."""
    m = re.match(r"^(Paris|Lyon|Marseille) (\d+)(?:er|e) Arrondissement$", nom_referentiel)
    return f"{m.group(1).upper()} {int(m.group(2))}" if m else None


# ---------------------------------------------------- référentiel ---

class Referentiel:
    """Index des communes par (département, clé de nom) et par clé de nom."""

    def __init__(self, contenu: dict, departements: dict):
        champs = contenu["_champs"]
        self.version = contenu.get("_extrait_le", "?")
        self.par_code: dict[str, dict] = {}
        self.par_dept_nom: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.par_nom: dict[str, list[dict]] = defaultdict(list)
        somme: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for ligne in contenu["communes"]:
            c = dict(zip(champs, ligne))
            self.par_code[c["code"]] = c
            cle = cle_arrondissement(c["nom"]) if c["type"] == "arrondissement" else cle_ville(c["nom"])
            c["cle"] = cle
            self.par_dept_nom[(c["departement"], cle)].append(c)
            self.par_nom[cle].append(c)
            if c["type"] == "commune":
                poids = float(c.get("population") or 1)
                s = somme[c["departement"]]
                s[0] += c["lon"] * poids
                s[1] += c["lat"] * poids
                s[2] += poids
        self.centroide_dept = {d: (round(s[0] / s[2], 4), round(s[1] / s[2], 4)) for d, s in somme.items() if s[2]}
        self.departements = departements

    def chercher(self, departement: str, cle: str) -> list[dict]:
        """Candidats pour un nom dans un département (ou dans une liste de
        départements possibles). Sans département : toute la France."""
        if not cle:
            return []
        if not departement:
            return self.par_nom.get(cle, [])
        candidats = []
        for d in DEPARTEMENTS_AMBIGUS.get(departement, [departement]):
            candidats += self.par_dept_nom.get((d, cle), [])
        return candidats


# --------------------------------------------------------- tables ---

def lire_csv(chemin: Path) -> list[dict]:
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def charger_tables() -> dict:
    communes = lire_json(COMMUNES)
    if not communes:
        erreur_fatale(f"{COMMUNES.relative_to(RACINE)} absent : lancez outils/extraire-communes.py")
    departements = {d["code"]: d for d in lire_json(PROCESSED / "referentiels" / "departements.json")["departements"]}
    lieux = lire_json(LIEUX) or {}
    if "cnil" not in lieux:
        erreur_fatale(f"{LIEUX.relative_to(RACINE)} doit définir le lieu « cnil »")
    surcouche = {r["id"]: r for r in lire_csv(SURCOUCHE) if r.get("statut", "valide") == "valide"}
    alias = {}
    for r in lire_csv(ALIAS):
        alias[(r["departement_source"].strip(), cle_ville(r["ville_source"]))] = r
    return {
        "referentiel": Referentiel(communes, departements),
        "lieux": lieux,
        "surcouche": surcouche,
        "alias": alias,
        "pays": (lire_json(PAYS_CENTROIDES) or {}).get("pays", {}),
    }


# ------------------------------------------------------ résolution ---

def localiser_organisme(e: dict, tables: dict) -> dict:
    """Renvoie les champs org_* et les champs de commune pour un enregistrement."""
    ref: Referentiel = tables["referentiel"]
    resultat = {"pays": e["pays"], "code_insee": "", "commune": "", "departement": e["departement"],
                "region": "", "org_lon": "", "org_lat": "", "org_precision": "aucune",
                "org_methode": "aucune", "org_adresse": "", "org_source": "", "drapeaux": []}

    def poser_commune(c: dict, methode: str):
        resultat.update(code_insee=c["code"], commune=c["nom"], departement=c["departement"],
                        region=c["region"], org_lon=f"{c['lon']:.4f}", org_lat=f"{c['lat']:.4f}",
                        org_precision="commune", org_methode=methode,
                        org_source=f"geo.api.gouv.fr {ref.version}")
        if e["departement"] and c["departement"] != e["departement"] and e["departement"] not in DEPARTEMENTS_AMBIGUS:
            resultat["drapeaux"].append("departement_contredit_par_ville")

    # 1. Alias écrit à la main (peut aussi corriger le pays).
    alias = tables["alias"].get((e["departement_source"].strip(), cle_ville(e["ville_source"])))
    if alias is None:
        alias = tables["alias"].get(("*", cle_ville(e["ville_source"])))
    if alias and alias.get("pays") and alias["pays"] != "FR":
        resultat["pays"] = alias["pays"]
        resultat["drapeaux"].append("pays_corrige_par_alias")
    elif alias and alias.get("code_insee"):
        c = ref.par_code.get(alias["code_insee"])
        if c is None:
            erreur_fatale(f"alias-villes.csv : code INSEE inconnu {alias['code_insee']} pour « {alias['ville_source']} »")
        poser_commune(c, "alias")
        if alias.get("precision") == "departement":
            resultat["org_precision"] = "departement"
            resultat["drapeaux"].append("localisation_approximative")

    # 2. Référentiel des communes.
    if resultat["org_methode"] == "aucune" and resultat["pays"] == "FR":
        cle = cle_ville(e["ville_source"])
        candidats = ref.chercher(e["departement"], cle)
        if not candidats and e["departement"]:
            # La ville prime si elle est unique en France (département erroné à la source).
            partout = ref.par_nom.get(cle, [])
            if len(partout) == 1:
                candidats = partout
        if len(candidats) == 1:
            poser_commune(candidats[0], "referentiel_communes")
        elif len(candidats) > 1:
            # Plusieurs communes homonymes dans le département : la plus peuplée, signalé.
            candidats = sorted(candidats, key=lambda c: -(c.get("population") or 0))
            poser_commune(candidats[0], "referentiel_communes")
            resultat["drapeaux"].append("commune_homonyme")

    # 3. Surcouche d'adresses validées (affine une commune déjà trouvée ou la remplace).
    s = tables["surcouche"].get(e["id"])
    if s and s.get("lon") and s.get("lat"):
        resultat.update(org_lon=f"{float(s['lon']):.6f}", org_lat=f"{float(s['lat']):.6f}",
                        org_precision="adresse", org_methode="surcouche",
                        org_adresse=s.get("adresse", ""), org_source=s.get("source", "surcouche"))
        if s.get("code_insee") and s["code_insee"] in ref.par_code:
            c = ref.par_code[s["code_insee"]]
            resultat.update(code_insee=c["code"], commune=c["nom"], departement=c["departement"], region=c["region"])

    # 4. Replis.
    if resultat["org_methode"] == "aucune":
        if resultat["pays"] != "FR":
            p = tables["pays"].get(resultat["pays"])
            if p:
                resultat.update(org_lon=f"{p['lon']:.4f}", org_lat=f"{p['lat']:.4f}",
                                org_precision="pays", org_methode="centroide_pays", org_source="centroide pays")
        else:
            depts = DEPARTEMENTS_AMBIGUS.get(e["departement"], [e["departement"]]) if e["departement"] else []
            if len(depts) == 1 and depts[0] in ref.centroide_dept:
                lon, lat = ref.centroide_dept[depts[0]]
                d = ref.departements.get(depts[0], {})
                resultat.update(departement=depts[0], region=d.get("region", ""),
                                org_lon=f"{lon:.4f}", org_lat=f"{lat:.4f}", org_precision="departement",
                                org_methode="centroide_departement", org_source=f"geo.api.gouv.fr {ref.version}")
            resultat["drapeaux"].append("ville_non_resolue")
    if resultat["departement"] and not resultat["region"]:
        resultat["region"] = ref.departements.get(resultat["departement"], {}).get("region", "")
    return resultat


def localiser_controle(e: dict, org: dict, lieux: dict) -> dict:
    """Champs ctrl_* : où l'opération de contrôle a eu lieu."""
    if e["modalite"] in MODALITES_A_LA_CNIL:
        cnil = lieux["cnil"]
        return {"ctrl_lieu": "cnil", "ctrl_lon": f"{cnil['lon']:.6f}", "ctrl_lat": f"{cnil['lat']:.6f}",
                "ctrl_precision": "institution", "drapeaux": []}
    drapeaux = [] if e["modalite"] == "sur_place" else ["lieu_controle_inconnu"]
    return {"ctrl_lieu": "organisme", "ctrl_lon": org["org_lon"], "ctrl_lat": org["org_lat"],
            "ctrl_precision": org["org_precision"], "drapeaux": drapeaux}


def localiser_tout(enregistrements: list[dict], tables: dict) -> list[dict]:
    sorties = []
    for e in enregistrements:
        org = localiser_organisme(e, tables)
        ctrl = localiser_controle(e, org, tables["lieux"])
        ligne = {"id": e["id"], **{k: v for k, v in org.items() if k != "drapeaux"},
                 **{k: v for k, v in ctrl.items() if k != "drapeaux"},
                 "drapeaux": "|".join(org["drapeaux"] + ctrl["drapeaux"])}
        sorties.append(ligne)
    return sorties


# --------------------------------------------------------- sorties ---

def rapport(enregistrements: list[dict], sorties: list[dict]) -> dict:
    par_id = {e["id"]: e for e in enregistrements}
    france = [s for s in sorties if s["pays"] == "FR"]
    precis = sum(1 for s in france if s["org_precision"] in ("commune", "adresse"))
    non_resolues: Counter = Counter()
    for s in sorties:
        if "ville_non_resolue" in s["drapeaux"]:
            e = par_id[s["id"]]
            non_resolues[(e["departement_source"], e["ville_source"], e["pays"])] += 1
    return {
        "total": len(sorties),
        "france": len(france),
        "france_resolus_commune_ou_adresse": precis,
        "taux_france": round(precis / len(france), 4) if france else None,
        "par_precision_organisme": dict(sorted(Counter(s["org_precision"] for s in sorties).items())),
        "par_methode_organisme": dict(sorted(Counter(s["org_methode"] for s in sorties).items())),
        "par_lieu_controle": dict(sorted(Counter(s["ctrl_lieu"] for s in sorties).items())),
        "drapeaux": dict(sorted(Counter(d for s in sorties for d in s["drapeaux"].split("|") if d).items())),
        "villes_non_resolues": [{"departement_source": d, "ville_source": v, "pays": p, "occurrences": n}
                                for (d, v, p), n in sorted(non_resolues.items(), key=lambda x: (-x[1], x[0]))],
    }


def main(argv=None) -> int:
    enregistrements = lire_csv(ENTREE)
    if not enregistrements:
        erreur_fatale(f"{ENTREE.relative_to(RACINE)} absent : lancez d'abord pipeline/transform.py")
    tables = charger_tables()
    journal(f"référentiel communes du {tables['referentiel'].version}, {len(tables['alias'])} alias, "
            f"{len(tables['surcouche'])} adresses validées en surcouche")
    sorties = localiser_tout(enregistrements, tables)

    tampon = io.StringIO()
    w = csv.DictWriter(tampon, fieldnames=COLONNES, lineterminator="\n")
    w.writeheader()
    for s in sorties:
        w.writerow(s)
    change = ecrire_texte(SORTIE, tampon.getvalue())
    r = rapport(enregistrements, sorties)
    change = ecrire_json(RAPPORT, r) or change
    journal(f"organisme : {r['par_precision_organisme']} ; méthodes : {r['par_methode_organisme']}")
    journal(f"lieu du contrôle : {r['par_lieu_controle']} ; drapeaux : {r['drapeaux']}")
    journal(f"France : {r['france_resolus_commune_ou_adresse']}/{r['france']} à la commune ou à l'adresse ({r['taux_france']:.1%})")
    if r["villes_non_resolues"]:
        journal(f"{len(r['villes_non_resolues'])} villes non résolues (voir {RAPPORT.relative_to(RACINE)}), premières : "
                + " ; ".join(f"{v['departement_source']} {v['ville_source']} ×{v['occurrences']}" for v in r["villes_non_resolues"][:8]))
    journal(("mis à jour" if change else "inchangés") + f" : {SORTIE.relative_to(RACINE)}, {RAPPORT.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
