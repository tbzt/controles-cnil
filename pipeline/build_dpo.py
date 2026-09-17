"""Étape 21 : agrégats du jeu DPO pour le site.

Entrées : `data/processed/dpo/organismes.csv`, l'agrégat SIRENE
`data/referentiels-source/sirene-sieges-par-commune.csv` (dénominateur du
taux de désignation, facultatif : sans lui, les taux sont absents), les
référentiels départements et communes, `flux-mensuels.csv` s'il existe.

Sorties déterministes :
- `data/processed/dpo/stats-dpo.json` : couverture, répartitions (type,
  section NAF, pays, année, mois), départements (effectifs, sièges SIRENE,
  taux, par section, structure mutualisée dominante), structures
  mutualisées les plus désignées, couverture des communes, interne/externe
  par section et par année ;
- `data/processed/dpo/dpo-communes.json` : une ligne par commune ayant au
  moins une désignation, arrondissements repliés sur leur commune :
  effectif, personnes morales, sièges SIRENE, coordonnées.

Le fichier complet des 111 000 organismes n'est jamais servi au navigateur ;
tout ce que le site affiche vient de ces deux agrégats (quelques centaines
de Ko).

Usage :
    python3 pipeline/build_dpo.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import METADATA, PROCESSED, RACINE, REFERENTIELS_SOURCE, ecrire_json, erreur_fatale, journal, lire_json  # noqa: E402

ORGANISMES = PROCESSED / "dpo" / "organismes.csv"
FLUX = PROCESSED / "dpo" / "flux-mensuels.csv"
SIRENE = REFERENTIELS_SOURCE / "sirene-sieges-par-commune.csv"
SIRENE_META = REFERENTIELS_SOURCE / "sirene-sieges-par-commune.meta.json"
STATS = PROCESSED / "dpo" / "stats-dpo.json"
COMMUNES_SORTIE = PROCESSED / "dpo" / "dpo-communes.json"
MAPPINGS = RACINE / "pipeline" / "mappings"
NB_STRUCTURES = 30
NB_MOIS_MIN = 1
# Les communes qui déclarent : administration publique générale et un nom
# qui commence par commune, mairie ou ville (approximation assumée).
NOM_COMMUNE = re.compile(r"^(COMMUNE|MAIRIE|VILLE)\b")


def lire_csv(chemin: Path, delimiter: str = ",") -> list[dict]:
    if not chemin.exists():
        return []
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def commune_parente(code: str) -> str:
    """Arrondissements de Paris, Lyon et Marseille → commune : les deux
    sources (CNIL, SIRENE) les emploient inégalement."""
    if code.startswith("751") and len(code) == 5:
        return "75056"
    if code.startswith("6938") and len(code) == 5:
        return "69123"
    if code.startswith("132") and len(code) == 5:
        return "13055"
    return code


def departement_du_code(code_insee: str) -> str:
    if code_insee[:2] in ("97", "98"):
        return code_insee[:3]
    return code_insee[:2]


# ------------------------------------------------------------- SIRENE ---

def charger_sirene() -> tuple[dict, dict, dict | None]:
    """Sièges de personnes morales par commune (repliée) et par (commune,
    section) ; métadonnées. Vide si l'agrégat n'a pas été produit."""
    par_commune: dict = defaultdict(int)
    par_commune_section: dict = defaultdict(int)
    for r in lire_csv(SIRENE, ";"):
        if r["code_insee"] == "?":
            continue
        c = commune_parente(r["code_insee"])
        n = int(r["personnes_morales"])
        par_commune[c] += n
        par_commune_section[(c, r["section"])] += n
    return par_commune, par_commune_section, lire_json(SIRENE_META)


# -------------------------------------------------------------- stats ---

def taux(numerateur: int, denominateur: int) -> float | None:
    """Désignations pour 1 000 sièges de personnes morales ; None sans dénominateur."""
    return round(1000 * numerateur / denominateur, 2) if denominateur else None


def construire(organismes: list[dict], sirene_commune: dict, sirene_commune_section: dict, sirene_meta: dict | None,
               departements: list[dict], communes: dict, manifeste: dict, flux: list[dict], sections_naf: dict) -> tuple[dict, list]:
    france = [o for o in organismes if o["pays"] == "FR"]
    snapshot = organismes[0]["snapshot"] if organismes else ""
    # Les arrondissements sont repliés ici aussi, pour que la fonction ne
    # dépende pas de la forme exacte de l'agrégat SIRENE reçu.
    replie: dict = defaultdict(int)
    for c, n in sirene_commune.items():
        replie[commune_parente(c)] += n
    sirene_commune = replie
    replie_section: dict = defaultdict(int)
    for (c, s), n in sirene_commune_section.items():
        replie_section[(commune_parente(c), s)] += n
    sirene_commune_section = replie_section
    codes_dept = {d["code"] for d in departements}
    population = {d["code"]: d["population"] for d in departements}
    noms_dept = {d["code"]: d["nom"] for d in departements}

    # Sièges SIRENE par département et par (département, section).
    sirene_dept: dict = defaultdict(int)
    sirene_dept_section: dict = defaultdict(int)
    for c, n in sirene_commune.items():
        sirene_dept[departement_du_code(c)] += n
    for (c, s), n in sirene_commune_section.items():
        sirene_dept_section[(departement_du_code(c), s)] += n

    # Départements.
    par_dept: dict = defaultdict(lambda: {"total": 0, "personne_morale": 0, "par_section": Counter(), "par_section_pm": Counter(), "structures": Counter()})
    for o in france:
        d = o["departement"]
        if not d:
            continue
        e = par_dept[d]
        e["total"] += 1
        if o["type_dpo"] == "personne_morale":
            e["personne_morale"] += 1
            if o["nom_designe_norm"]:
                e["structures"][o["nom_designe_norm"]] += 1
        if o["section_naf"]:
            e["par_section"][o["section_naf"]] += 1
            if o["type_dpo"] == "personne_morale":
                e["par_section_pm"][o["section_naf"]] += 1

    # Graphie d'affichage des structures : la plus fréquente.
    graphies: dict = defaultdict(Counter)
    for o in organismes:
        if o["nom_designe_norm"]:
            graphies[o["nom_designe_norm"]][o["nom_designe"]] += 1
    libelle_structure = {k: v.most_common(1)[0][0] for k, v in graphies.items()}

    departements_sortie = {}
    for d in sorted(par_dept):
        e = par_dept[d]
        dominante = e["structures"].most_common(1)[0] if e["structures"] else None
        sieges = sirene_dept.get(d, 0)
        departements_sortie[d] = {
            "nom": noms_dept.get(d, d),
            "total": e["total"],
            "personne_morale": e["personne_morale"],
            "sieges_pm": sieges,
            "taux": taux(e["total"], sieges),
            "population": population.get(d),
            "par_section": {s: {"n": n, "personne_morale": e["par_section_pm"][s], "sieges_pm": sirene_dept_section.get((d, s), 0),
                                "taux": taux(n, sirene_dept_section.get((d, s), 0))}
                            for s, n in sorted(e["par_section"].items())},
            "structure_dominante": {"nom": libelle_structure[dominante[0]], "cle": dominante[0], "n": dominante[1],
                                    "part_externes": round(dominante[1] / e["personne_morale"], 3)} if dominante else None,
        }

    # Structures mutualisées.
    structures: dict = defaultdict(lambda: {"n": 0, "sections": Counter(), "departements": Counter(), "pays": Counter()})
    for o in organismes:
        k = o["nom_designe_norm"]
        if not k:
            continue
        s = structures[k]
        s["n"] += 1
        if o["section_naf"]:
            s["sections"][o["section_naf"]] += 1
        if o["departement"]:
            s["departements"][o["departement"]] += 1
    externes = sum(s["n"] for s in structures.values())
    top = sorted(structures.items(), key=lambda kv: (-kv[1]["n"], kv[0]))[:NB_STRUCTURES]
    structures_sortie = []
    cumul = 0
    for k, s in top:
        cumul += s["n"]
        structures_sortie.append({
            "nom": libelle_structure[k], "cle": k, "n": s["n"], "part_externes": round(s["n"] / externes, 4) if externes else None,
            "part_cumulee": round(cumul / externes, 4) if externes else None,
            "section_dominante": s["sections"].most_common(1)[0][0] if s["sections"] else "",
            "nb_departements": len(s["departements"]),
            "departements_principaux": [c for c, _ in s["departements"].most_common(5)],
        })

    # Couverture des communes (approximation par nom et code NAF).
    communes_declarantes: dict = defaultdict(set)
    for o in france:
        if o["code_naf"] == "8411Z" and o["code_insee"] and NOM_COMMUNE.match(o["nom_norm"]):
            communes_declarantes[o["departement"]].add(commune_parente(o["code_insee"]))
    communes_par_dept: Counter = Counter()
    for c in communes.values():
        if c["type"] == "commune":
            communes_par_dept[c["departement"]] += 1
    couverture_communes = {d: {"communes": communes_par_dept[d], "declarantes": len(communes_declarantes.get(d, ())),
                               "taux": round(len(communes_declarantes.get(d, ())) / communes_par_dept[d], 3) if communes_par_dept[d] else None}
                           for d in sorted(codes_dept) if communes_par_dept[d]}

    # Répartitions simples.
    par_mois: Counter = Counter()
    par_mois_type: dict = defaultdict(Counter)
    par_annee_type: dict = defaultdict(Counter)
    par_section_type: dict = defaultdict(Counter)
    for o in organismes:
        m = o["date_designation"][:7]
        if m:
            par_mois[m] += 1
            par_mois_type[m][o["type_dpo"]] += 1
            par_annee_type[m[:4]][o["type_dpo"]] += 1
        if o["section_naf"]:
            par_section_type[o["section_naf"]][o["type_dpo"]] += 1
    mois = sorted(par_mois)

    stats = {
        "couverture": {
            "snapshot": snapshot,
            "nb_designations": len(organismes),
            "nb_france": len(france),
            "nb_communes_resolues": sum(1 for o in france if o["code_insee"]),
            "nb_sans_siren": sum(1 for o in organismes if not o["siren"]),
            "nb_structures_designees": len(structures),
            "premier_mois": mois[0] if mois else None,
            "dernier_mois": mois[-1] if mois else None,
            "derniere_publication_source": (manifeste.get("dataset") or {}).get("last_modified_source"),
            "source": (manifeste.get("dataset") or {}).get("page"),
            "nb_snapshots": sum(len(e.get("versions", [])) for e in manifeste.get("ressources", {}).values()),
            "sirene": {"date_stock": sirene_meta.get("date_stock"), "sieges_pm": sirene_meta.get("mesures", {}).get("sieges_personnes_morales"),
                       "sieges_total": sirene_meta.get("mesures", {}).get("sieges_actifs")} if sirene_meta else None,
        },
        "libelles": {
            "sections": {k: v["libelle"] for k, v in sections_naf.items()},
            "types": {"personne_physique": "DPO interne (personne physique)", "personne_morale": "DPO externe (personne morale)"},
        },
        "par_type": dict(sorted(Counter(o["type_dpo"] for o in organismes).items())),
        "par_section": {s: {"n": n, "sieges_pm": sum(v for (c, sec), v in sirene_commune_section.items() if sec == s),
                            "personne_morale": par_section_type[s]["personne_morale"]}
                        for s, n in sorted(Counter(o["section_naf"] for o in organismes if o["section_naf"]).items())},
        "sans_section": sum(1 for o in organismes if not o["section_naf"]),
        "par_pays": [{"pays": p, "n": n} for p, n in Counter(o["pays"] or "?" for o in organismes if o["pays"] != "FR").most_common()],
        "par_annee": {a: dict(sorted(c.items())) for a, c in sorted(par_annee_type.items())},
        "par_mois": [{"mois": m, "n": par_mois[m], "personne_physique": par_mois_type[m]["personne_physique"],
                      "personne_morale": par_mois_type[m]["personne_morale"]} for m in mois],
        "par_section_type": {s: dict(sorted(c.items())) for s, c in sorted(par_section_type.items())},
        "departements": departements_sortie,
        "structures": structures_sortie,
        "nb_externes": externes,
        "couverture_communes": couverture_communes,
        "flux": [{k: (int(v) if v.lstrip("-").isdigit() else v) for k, v in r.items()} for r in flux],
    }
    for s in stats["par_section"].values():
        s["taux"] = taux(s["n"], s["sieges_pm"])

    # Communes.
    par_commune: dict = defaultdict(lambda: [0, 0])
    for o in france:
        if o["code_insee"]:
            c = commune_parente(o["code_insee"])
            par_commune[c][0] += 1
            if o["type_dpo"] == "personne_morale":
                par_commune[c][1] += 1
    lignes = []
    for c in sorted(par_commune):
        ref = communes.get(c)
        if not ref:
            continue
        n, pm = par_commune[c]
        lignes.append([c, ref["nom"], ref["departement"], ref["lon"], ref["lat"], n, pm, sirene_commune.get(c, 0)])
    communes_sortie = {"_champs": ["code_insee", "commune", "departement", "lon", "lat", "designations", "personne_morale", "sieges_pm"],
                       "_note": "Une ligne par commune ayant au moins une désignation ; arrondissements repliés sur la commune ; sieges_pm = sièges actifs de personnes morales (SIRENE).",
                       "snapshot": snapshot, "communes": lignes}
    return stats, communes_sortie


def main(argv=None) -> int:
    if not ORGANISMES.exists():
        erreur_fatale(f"{ORGANISMES.relative_to(RACINE)} absent : lancez dpo.py")
    organismes = lire_csv(ORGANISMES)
    sirene_commune, sirene_commune_section, sirene_meta = charger_sirene()
    if not sirene_commune:
        journal("agrégat SIRENE absent : taux de désignation non calculés (lancez outils/agreger-sirene.py)")
    departements = (lire_json(PROCESSED / "referentiels" / "departements.json") or {}).get("departements", [])
    ref_communes = lire_json(REFERENTIELS_SOURCE / "communes.json") or {"_champs": [], "communes": []}
    communes = {}
    for ligne in ref_communes["communes"]:
        c = dict(zip(ref_communes["_champs"], ligne))
        communes[c["code"]] = c
    manifeste = lire_json(METADATA / "manifest-dpo.json", {}) or {}
    flux = lire_csv(FLUX)
    sections = lire_json(MAPPINGS / "naf-sections.json")["sections"]

    stats, communes_sortie = construire(organismes, sirene_commune, sirene_commune_section, sirene_meta, departements, communes, manifeste, flux, sections)
    change = ecrire_json(STATS, stats)
    change = ecrire_json(COMMUNES_SORTIE, communes_sortie) or change
    journal(f"{stats['couverture']['nb_designations']} désignations, {len(stats['departements'])} départements, "
            f"{len(communes_sortie['communes'])} communes, {len(stats['structures'])} structures ; "
            + ("mis à jour" if change else "inchangés") + f" : {STATS.name}, {COMMUNES_SORTIE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
