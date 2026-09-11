"""Étape 1 : récupérer les ressources CSV du jeu de données CNIL.

Interroge l'API data.gouv.fr, compare chaque ressource CSV au manifeste
(`data/metadata/manifest.json`), télécharge ce qui est nouveau ou modifié et
l'archive dans `data/raw/` sans jamais écraser une version précédente.

Règles :
- une ressource est téléchargée si elle est inconnue du manifeste, si sa date
  de modification ou son empreinte déclarée côté data.gouv.fr a changé, ou
  si `--forcer` est passé ;
- le fichier téléchargé est identifié par son SHA-256 ; s'il est identique à
  une version déjà archivée, rien n'est écrit ;
- le manifeste ne change que lorsque quelque chose a réellement changé, pour
  qu'une exécution sans nouveauté laisse le dépôt propre ;
- seules les ressources CSV sont prises ; les XLSX sont comptés mais ignorés.

Usage :
    python3 pipeline/fetch.py [--forcer] [--hors-ligne]

Code de sortie : 0 si tout s'est bien passé (même sans changement), 1 sur
erreur réseau ou ressource incohérente.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Permet `python3 pipeline/fetch.py` comme `python3 -m pipeline.fetch`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import (  # noqa: E402
    METADATA,
    RAW,
    ecrire_json,
    erreur_fatale,
    journal,
    lire_json,
    sha256_octets,
)

DATASET_ID = "555c431bc751df5800190c78"
API_DATASET = f"https://www.data.gouv.fr/api/1/datasets/{DATASET_ID}/"
MANIFESTE = METADATA / "manifest.json"
USER_AGENT = "controles-cnil (https://github.com/tbzt/controles-cnil)"
DELAI_SECONDES = 60

ANNEE = re.compile(r"(20\d\d)")


# ---------------------------------------------------------------- réseau ---

def telecharger(url: str) -> bytes:
    """Télécharge une URL et renvoie ses octets. Lève urllib.error.URLError."""
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(requete, timeout=DELAI_SECONDES) as reponse:
        return reponse.read()


def lire_dataset(telechargeur=telecharger) -> dict:
    """Métadonnées du jeu de données depuis l'API data.gouv.fr."""
    try:
        return json.loads(telechargeur(API_DATASET).decode("utf-8"))
    except (urllib.error.URLError, ValueError) as exc:
        erreur_fatale(f"API data.gouv.fr injoignable ou réponse illisible : {exc}")


# --------------------------------------------------------- fonctions pures ---

def annee_de(ressource: dict) -> str:
    """Dossier de rangement d'une ressource : l'année trouvée dans le nom de
    fichier (prioritaire) ou dans le titre, sinon un dossier dédié pour le
    tableau « nombre de contrôles depuis 1990 »."""
    nom = nom_original(ressource)
    if "1990" in nom or "1990" in ressource.get("title", ""):
        return "nombre-controles-1990"
    for source in (nom, ressource.get("title", "")):
        m = ANNEE.search(source)
        if m:
            return m.group(1)
    return "autre"


def nom_original(ressource: dict) -> str:
    """Nom de fichier tel que servi par data.gouv.fr (dernier segment de
    l'URL, décodé)."""
    chemin = urllib.parse.urlparse(ressource["url"]).path
    return urllib.parse.unquote(chemin.rsplit("/", 1)[-1])


def nom_fichier_brut(ressource: dict, sha256: str) -> str:
    """`<8 premiers hex du SHA-256>__<nom original>` : lisible, unique par
    contenu, et le nom original reste visible."""
    return f"{sha256[:8]}__{nom_original(ressource)}"


def est_csv(ressource: dict) -> bool:
    return (ressource.get("format") or "").lower() == "csv"


def signature_source(ressource: dict) -> dict:
    """Ce que data.gouv.fr déclare sur la ressource, et qui suffit à détecter
    un changement sans télécharger."""
    checksum = ressource.get("checksum") or {}
    return {
        "last_modified": ressource.get("last_modified"),
        "checksum_type": checksum.get("type"),
        "checksum_value": checksum.get("value"),
        "filesize": ressource.get("filesize"),
    }


def doit_telecharger(entree: dict | None, ressource: dict, forcer: bool) -> bool:
    """Décide si une ressource doit être (re)téléchargée."""
    if forcer or entree is None or not entree.get("versions"):
        return True
    return entree.get("signature_source") != signature_source(ressource)


def version_connue(entree: dict | None, sha256: str) -> dict | None:
    if not entree:
        return None
    for version in entree.get("versions", []):
        if version["sha256"] == sha256:
            return version
    return None


# ----------------------------------------------------------- traitement ---

def traiter(dataset: dict, manifeste: dict, telechargeur, aujourdhui: str,
            forcer: bool = False, racine_raw: Path = RAW) -> dict:
    """Met à jour le manifeste (en place) et archive les fichiers. Renvoie un
    résumé : listes de titres par catégorie."""
    resume = {"nouvelles": [], "modifiees": [], "inchangees": [],
              "identiques_apres_telechargement": [], "ignorees_non_csv": [],
              "disparues": []}
    ressources = manifeste.setdefault("ressources", {})
    presentes = set()

    for ressource in sorted(dataset.get("resources", []), key=lambda r: r["id"]):
        if not est_csv(ressource):
            resume["ignorees_non_csv"].append(ressource.get("title", ressource["id"]))
            continue
        rid = ressource["id"]
        presentes.add(rid)
        entree = ressources.get(rid)
        if not doit_telecharger(entree, ressource, forcer):
            resume["inchangees"].append(ressource["title"])
            continue

        try:
            octets = telechargeur(ressource["url"])
        except urllib.error.URLError as exc:
            erreur_fatale(f"téléchargement impossible pour « {ressource['title']} » ({ressource['url']}) : {exc}")
        if not octets:
            erreur_fatale(f"ressource vide : « {ressource['title']} » ({ressource['url']})")

        sha = sha256_octets(octets)
        if entree is None:
            entree = ressources[rid] = {"versions": []}
        entree["titre"] = ressource["title"]
        entree["url"] = ressource["url"]
        entree["format"] = "csv"
        entree["dossier"] = annee_de(ressource)
        entree["signature_source"] = signature_source(ressource)
        entree.pop("disparue_le", None)

        deja = version_connue(entree, sha)
        if deja:
            # Même contenu qu'une version archivée : on n'écrit rien de plus.
            resume["identiques_apres_telechargement"].append(ressource["title"])
            continue

        nom = nom_fichier_brut(ressource, sha)
        dossier = racine_raw / entree["dossier"]
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / nom).write_bytes(octets)
        entree["versions"].append({
            "fichier": f"{entree['dossier']}/{nom}",
            "sha256": sha,
            "taille": len(octets),
            "recupere_le": aujourdhui,
            "last_modified_source": ressource.get("last_modified"),
        })
        (resume["nouvelles"] if len(entree["versions"]) == 1 else resume["modifiees"]).append(ressource["title"])

    for rid, entree in ressources.items():
        if rid not in presentes and not entree.get("disparue_le"):
            entree["disparue_le"] = aujourdhui
            resume["disparues"].append(entree.get("titre", rid))

    manifeste["dataset"] = {
        "id": dataset.get("id"),
        "titre": dataset.get("title"),
        "page": dataset.get("page"),
        "licence": dataset.get("license"),
        "organisation": (dataset.get("organization") or {}).get("name"),
        "last_modified_source": dataset.get("last_modified"),
    }
    manifeste["source_api"] = API_DATASET
    return resume


def afficher_resume(resume: dict) -> None:
    for cle, libelle in (("nouvelles", "ressources nouvelles"),
                         ("modifiees", "ressources modifiées"),
                         ("identiques_apres_telechargement", "retéléchargées mais identiques"),
                         ("inchangees", "inchangées"),
                         ("disparues", "disparues de data.gouv.fr")):
        if resume[cle]:
            journal(f"{len(resume[cle])} {libelle} : " + " ; ".join(resume[cle]))
    journal(f"{len(resume['ignorees_non_csv'])} ressources non CSV ignorées")


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--forcer", action="store_true",
                         help="retélécharger toutes les ressources même si data.gouv.fr ne signale aucun changement")
    parseur.add_argument("--hors-ligne", action="store_true",
                         help="ne rien télécharger ; vérifier seulement que les fichiers du manifeste existent")
    args = parseur.parse_args(argv)

    manifeste = lire_json(MANIFESTE, {}) or {}

    if args.hors_ligne:
        manquants = [v["fichier"] for e in manifeste.get("ressources", {}).values()
                     for v in e.get("versions", []) if not (RAW / v["fichier"]).exists()]
        if manquants:
            erreur_fatale("fichiers du manifeste absents de data/raw/ : " + ", ".join(manquants))
        journal(f"hors ligne : {sum(len(e.get('versions', [])) for e in manifeste.get('ressources', {}).values())} versions archivées, toutes présentes")
        return 0

    dataset = lire_dataset()
    aujourdhui = dt.date.today().isoformat()
    resume = traiter(dataset, manifeste, telecharger, aujourdhui, forcer=args.forcer)
    afficher_resume(resume)
    if ecrire_json(MANIFESTE, manifeste):
        journal(f"manifeste mis à jour : {MANIFESTE.relative_to(MANIFESTE.parents[2])}")
    else:
        journal("manifeste inchangé")
    return 0


if __name__ == "__main__":
    sys.exit(main())
