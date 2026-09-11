"""Étape 7 : construire les fichiers publiés à partir des tables normalisées.

Entrées : `controles.csv`, `localisations.csv`, référentiels, manifeste.
Sorties, toutes déterministes (même entrée → mêmes octets) :

- `data/processed/controles.geojson` : une Feature par contrôle localisé, en
  point au **lieu de l'organisme**, avec les propriétés utiles à la carte et
  aux filtres. Le lieu du contrôle n'est pas répété : la propriété
  `lieu_controle` vaut `cnil` ou `organisme`, et le point du siège de la CNIL
  est donné une fois dans `stats.json` (`lieux.cnil`). Les contrôles sans
  aucune coordonnée (précision `aucune`) n'y figurent pas, ils sont comptés
  dans `stats.json`.
- `data/processed/stats.json` : effectifs par année, famille, secteur,
  modalité, fondement, département, région, commune, pays, précision, lieu du
  contrôle ; croisements par année ; organismes récurrents ; couverture.
- `data/metadata/schema.json` : descripteur Data Package (Table Schema) des
  deux tables CSV publiées.

Usage :
    python3 pipeline/build.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import GEOCODING, METADATA, PROCESSED, RACINE, ecrire_json, ecrire_texte, erreur_fatale, journal, lire_json  # noqa: E402

GEOJSON = PROCESSED / "controles.geojson"
STATS = PROCESSED / "stats.json"
SCHEMA = METADATA / "schema.json"
LIBELLES = PROCESSED / "referentiels" / "libelles.json"
MAPPINGS = RACINE / "pipeline" / "mappings"

PROPRIETES = ("id", "annee", "fondement", "modalite", "famille", "secteur", "organisme", "organisme_cle",
              "commune", "code_insee", "departement", "region", "pays", "precision", "lieu_controle")


def lire_csv(chemin: Path) -> list[dict]:
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------ GeoJSON ---

def feature(c: dict, l: dict) -> dict | None:
    if not l["org_lon"]:
        return None
    props = {
        "id": c["id"], "annee": int(c["annee"]), "fondement": c["fondement"], "modalite": c["modalite"],
        "famille": c["famille"], "secteur": c["secteur"], "organisme": c["organisme"], "organisme_cle": c["organisme_cle"],
        "commune": l["commune"], "code_insee": l["code_insee"], "departement": l["departement"],
        "region": l["region"], "pays": l["pays"], "precision": l["org_precision"], "lieu_controle": l["ctrl_lieu"],
    }
    return {"type": "Feature", "id": c["id"],
            "geometry": {"type": "Point", "coordinates": [float(l["org_lon"]), float(l["org_lat"])]},
            "properties": props}


def ecrire_geojson(features: list[dict]) -> bool:
    """Une Feature par ligne : lisible, diff git par contrôle."""
    lignes = [json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in features]
    texte = '{"type":"FeatureCollection","features":[\n' + ",\n".join(lignes) + "\n]}\n"
    return ecrire_texte(GEOJSON, texte)


# -------------------------------------------------------------- stats ---

def compter(controles: list[dict], champ: str) -> dict:
    return dict(sorted(Counter(c[champ] for c in controles).items()))


def croiser(controles: list[dict], champ: str) -> dict:
    """{annee: {valeur: n}} trié."""
    tab: dict = defaultdict(Counter)
    for c in controles:
        tab[c["annee"]][c[champ]] += 1
    return {a: dict(sorted(v.items())) for a, v in sorted(tab.items())}


def organismes_recurrents(controles: list[dict], minimum: int = 3) -> list[dict]:
    """Organismes contrôlés sur au moins `minimum` années distinctes
    (rapprochement par nom normalisé : approximatif, assumé)."""
    annees: dict = defaultdict(set)
    n: Counter = Counter()
    graphies: dict = defaultdict(Counter)
    for c in controles:
        cle = c["organisme_cle"]
        if not cle:
            continue
        annees[cle].add(int(c["annee"]))
        n[cle] += 1
        # Libellé affiché : la graphie la plus fréquente, en privilégiant celles
        # qui portent la clé elle-même plutôt qu'un alias (« Google » avant
        # « Google Ireland Limited »).
        graphies[cle][c["organisme"]] += 1000 if c["organisme_norm"] == cle else 1
    rows = [{"organisme": graphies[k].most_common(1)[0][0], "organisme_cle": k, "annees": sorted(a), "nb_annees": len(a), "nb_controles": n[k]}
            for k, a in annees.items() if len(a) >= minimum]
    return sorted(rows, key=lambda r: (-r["nb_annees"], -r["nb_controles"], r["organisme_cle"]))


def construire_stats(controles: list[dict], loc: dict, manifeste: dict, lieux: dict) -> dict:
    fusion = []
    for c in controles:
        l = loc[c["id"]]
        fusion.append({**c, "commune": l["commune"], "code_insee": l["code_insee"], "departement_loc": l["departement"],
                       "region": l["region"], "pays_loc": l["pays"], "precision": l["org_precision"],
                       "lieu_controle": l["ctrl_lieu"]})
    annees = sorted({int(c["annee"]) for c in controles})
    par_commune = Counter((f["code_insee"], f["commune"], f["departement_loc"]) for f in fusion if f["code_insee"])
    return {
        "couverture": {
            "annee_min": annees[0], "annee_max": annees[-1], "annees": annees,
            "nb_controles": len(controles),
            "nb_localises": sum(1 for f in fusion if f["precision"] != "aucune"),
            "nb_cartographies": sum(1 for f in fusion if loc[f["id"]]["org_lon"]),
            "derniere_publication_source": (manifeste.get("dataset") or {}).get("last_modified_source"),
            "source": (manifeste.get("dataset") or {}).get("page"),
        },
        "lieux": {"cnil": {"lon": lieux["cnil"]["lon"], "lat": lieux["cnil"]["lat"], "nom": lieux["cnil"]["nom"],
                           "adresse": lieux["cnil"]["adresse"]}},
        "par_annee": compter(fusion, "annee"),
        "par_famille": compter(fusion, "famille"),
        "par_secteur": compter(fusion, "secteur"),
        "par_modalite": compter(fusion, "modalite"),
        "par_fondement": compter(fusion, "fondement"),
        "par_lieu_controle": compter(fusion, "lieu_controle"),
        "par_precision": compter(fusion, "precision"),
        "par_pays": compter(fusion, "pays_loc"),
        "par_region": compter(fusion, "region"),
        "par_departement": compter(fusion, "departement_loc"),
        "par_commune": [{"code_insee": k[0], "commune": k[1], "departement": k[2], "n": n}
                        for k, n in sorted(par_commune.items(), key=lambda x: (-x[1], x[0]))],
        "annee_x_famille": croiser(fusion, "famille"),
        "annee_x_secteur": croiser(fusion, "secteur"),
        "annee_x_modalite": croiser(fusion, "modalite"),
        "annee_x_fondement": croiser(fusion, "fondement"),
        "annee_x_lieu_controle": croiser(fusion, "lieu_controle"),
        "annee_x_region": croiser(fusion, "region"),
        "annee_x_departement": croiser(fusion, "departement_loc"),
        "annee_x_pays": croiser(fusion, "pays_loc"),
        "organismes_recurrents": organismes_recurrents(controles),
    }


# ------------------------------------------------------------- schéma ---

def schema() -> dict:
    enum_fond = ["loi78", "rgpd", "directive_police_justice", "rgpd_ou_directive", "videoprotection"]
    enum_mod = ["sur_place", "en_ligne", "sur_pieces", "sur_audition", "non_renseignee"]
    enum_prec = ["adresse", "commune", "departement", "pays", "institution", "aucune"]
    champ = lambda n, t, d, **k: {"name": n, "type": t, "description": d, **k}  # noqa: E731
    controles = [
        champ("id", "string", "Identifiant stable : année, hachage SHA-1 court du contenu source, rang parmi les lignes identiques.", constraints={"required": True, "unique": True, "pattern": "^20[0-9]{2}-[0-9a-f]{8}-[0-9]+$"}),
        champ("annee", "integer", "Année du contrôle, déduite du fichier source.", constraints={"required": True, "minimum": 2014}),
        champ("fondement", "string", "Fondement juridique harmonisé.", constraints={"required": True, "enum": enum_fond}),
        champ("fondement_source", "string", "Libellé brut de la colonne type ou catégorie de contrôle."),
        champ("modalite", "string", "Modalité harmonisée ; non_renseignee avant 2017 sauf « contrôle en ligne ».", constraints={"required": True, "enum": enum_mod}),
        champ("modalite_source", "string", "Libellé brut de la modalité."),
        champ("organisme", "string", "Nom de l'organisme contrôlé tel que publié, espaces normalisées.", constraints={"required": True}),
        champ("organisme_norm", "string", "Nom en majuscules sans accents ni ponctuation."),
        champ("organisme_cle", "string", "Clé de rapprochement : nom normalisé sans forme juridique ni suffixe de domaine, puis table d'alias referentiels/organismes-alias.csv. Deux contrôles d'un même organisme partagent cette clé."),
        champ("ville_source", "string", "Ville telle que publiée par la CNIL."),
        champ("departement", "string", "Code département après corrections formelles (zéro initial, valeur multiple) ; 20 et 97 restent à préciser par la ville."),
        champ("departement_source", "string", "Code département tel que publié."),
        champ("pays", "string", "Code ISO 3166-1 alpha-2 ; FR par défaut avant 2021 (drapeau pays_deduit).", constraints={"required": True}),
        champ("pays_source", "string", "Pays tel que publié (colonne présente depuis 2021)."),
        champ("secteur", "string", "Secteur fin harmonisé (orthographe unifiée), voir referentiels/secteurs.csv.", constraints={"required": True}),
        champ("famille", "string", "Famille de secteurs comparable sur toute la période, voir referentiels/familles.json.", constraints={"required": True}),
        champ("secteur_source", "string", "Libellé de secteur tel que publié."),
        champ("source_fichier", "string", "Nom du fichier brut dans data/raw/."),
        champ("source_ligne", "integer", "Numéro de la ligne physique de début de l'enregistrement dans le fichier brut (l'en-tête est la ligne 1)."),
        champ("qualite", "string", "Drapeaux séparés par | : ce qui a été déduit, corrigé ou signalé sur cette ligne."),
    ]
    localisations = [
        champ("id", "string", "Identifiant du contrôle (clé vers controles.csv).", constraints={"required": True, "unique": True}),
        champ("pays", "string", "Pays de l'organisme après alias (ISO 3166-1 alpha-2)."),
        champ("code_insee", "string", "Commune de l'organisme (code INSEE), vide si non résolue."),
        champ("commune", "string", "Nom officiel de la commune."),
        champ("departement", "string", "Code département de la commune résolue."),
        champ("region", "string", "Code région."),
        champ("org_lon", "number", "Longitude WGS84 du lieu de l'organisme (4 décimales pour une commune, 6 pour une adresse)."),
        champ("org_lat", "number", "Latitude WGS84 du lieu de l'organisme."),
        champ("org_precision", "string", "Précision du lieu de l'organisme.", constraints={"enum": enum_prec}),
        champ("org_methode", "string", "Comment le lieu de l'organisme a été obtenu (surcouche, alias, referentiel_communes, centroide_departement, centroide_pays, aucune)."),
        champ("org_adresse", "string", "Adresse, seulement si la précision est l'adresse."),
        champ("org_source", "string", "Origine de la position (référentiel daté, carte uMap, annuaire des entreprises avec SIREN…)."),
        champ("ctrl_lieu", "string", "Où le contrôle a eu lieu : cnil (en ligne, sur pièces, sur audition) ou organisme.", constraints={"enum": ["cnil", "organisme"]}),
        champ("ctrl_lon", "number", "Longitude WGS84 du lieu du contrôle."),
        champ("ctrl_lat", "number", "Latitude WGS84 du lieu du contrôle."),
        champ("ctrl_precision", "string", "Précision du lieu du contrôle ; institution pour le siège de la CNIL.", constraints={"enum": enum_prec}),
        champ("drapeaux", "string", "Drapeaux séparés par | (departement_contredit_par_ville, commune_homonyme, ville_non_resolue, lieu_controle_inconnu…)."),
    ]
    dialecte = {"delimiter": ",", "quoteChar": '"', "header": True, "lineTerminator": "\n"}
    return {
        "profile": "tabular-data-package",
        "name": "controles-cnil",
        "title": "Contrôles réalisés par la CNIL, 2014 et suivantes, normalisés et localisés",
        "homepage": "https://github.com/tbzt/controles-cnil",
        "licenses": [{"name": "etalab-2.0", "title": "Licence Ouverte / Open Licence 2.0", "path": "https://www.etalab.gouv.fr/licence-ouverte-open-licence"}],
        "sources": [{"title": "CNIL, Contrôles réalisés par la CNIL (data.gouv.fr)", "path": "https://www.data.gouv.fr/datasets/controles-realises-par-la-cnil"},
                    {"title": "geo.api.gouv.fr, référentiel des communes", "path": "https://geo.api.gouv.fr/"},
                    {"title": "Annuaire des entreprises (SIRENE)", "path": "https://recherche-entreprises.api.gouv.fr/"}],
        "resources": [
            {"name": "controles", "path": "../processed/controles.csv", "format": "csv", "encoding": "utf-8", "dialect": dialecte,
             "description": "Un contrôle par ligne, valeurs brutes conservées dans les colonnes *_source.", "schema": {"fields": controles, "primaryKey": "id"}},
            {"name": "localisations", "path": "../processed/localisations.csv", "format": "csv", "encoding": "utf-8", "dialect": dialecte,
             "description": "Deux localisations par contrôle, lieu de l'organisme et lieu du contrôle, avec précision et méthode.",
             "schema": {"fields": localisations, "primaryKey": "id", "foreignKeys": [{"fields": "id", "reference": {"resource": "controles", "fields": "id"}}]}},
            {"name": "controles-geojson", "path": "../processed/controles.geojson", "format": "geojson",
             "description": "Points au lieu de l'organisme avec les propriétés de filtrage ; voir stats.json pour le siège de la CNIL."},
            {"name": "stats", "path": "../processed/stats.json", "format": "json", "description": "Agrégats précalculés."},
        ],
    }


# ----------------------------------------------------------- libellés ---

def libelles() -> dict:
    """Libellés d'affichage des valeurs codées, pour le site et les
    réutilisateurs : le site n'a ainsi rien à connaître de pipeline/."""
    secteurs = {}
    with open(PROCESSED / "referentiels" / "secteurs.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            secteurs.setdefault(r["secteur"], {"libelle": r["secteur_libelle"], "famille": r["famille"]})
    return {
        "secteurs": dict(sorted(secteurs.items())),
        "fondements": lire_json(MAPPINGS / "fondements.json")["libelles"],
        "modalites": lire_json(MAPPINGS / "modalites.json")["libelles"],
        "pays": lire_json(MAPPINGS / "pays.json")["libelles"],
        "precisions": {"adresse": "à l'adresse", "commune": "à la commune", "departement": "au département",
                       "pays": "au pays", "institution": "au siège de la CNIL", "aucune": "non localisé"},
        "lieux_controle": {"cnil": "dans les locaux de la CNIL", "organisme": "chez l'organisme"},
    }


# ---------------------------------------------------------- exécution ---

def main(argv=None) -> int:
    for f in (PROCESSED / "controles.csv", PROCESSED / "localisations.csv"):
        if not f.exists():
            erreur_fatale(f"{f.relative_to(RACINE)} absent : lancez transform.py puis geocode.py")
    controles = lire_csv(PROCESSED / "controles.csv")
    loc = {l["id"]: l for l in lire_csv(PROCESSED / "localisations.csv")}
    manifeste = lire_json(METADATA / "manifest.json", {}) or {}
    lieux = lire_json(GEOCODING / "lieux-institution.json")

    features = [f for f in (feature(c, loc[c["id"]]) for c in controles) if f]
    change = ecrire_geojson(features)
    stats = construire_stats(controles, loc, manifeste, lieux)
    change = ecrire_json(STATS, stats) or change
    change = ecrire_json(SCHEMA, schema()) or change
    change = ecrire_json(LIBELLES, libelles()) or change
    journal(f"{len(features)} features GeoJSON ({GEOJSON.stat().st_size // 1024} Ko), {len(stats['par_commune'])} communes, "
            f"{len(stats['organismes_recurrents'])} organismes récurrents")
    journal(("mis à jour" if change else "inchangés") + f" : {GEOJSON.name}, {STATS.name}, {SCHEMA.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
