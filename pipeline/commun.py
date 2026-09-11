"""Fonctions partagées par les scripts du pipeline.

Bibliothèque standard uniquement. Tout ce qui touche aux chemins, aux
empreintes et à l'écriture déterministe des fichiers passe par ici, pour que
deux exécutions sur la même entrée produisent exactement les mêmes octets.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Racine du dépôt : ce fichier est dans pipeline/, donc un niveau au-dessus.
RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
GEOCODING = DATA / "geocoding"
METADATA = DATA / "metadata"
REFERENTIELS_SOURCE = DATA / "referentiels-source"


def sha256_octets(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def lire_json(chemin: Path, defaut=None):
    """Lit un JSON ; renvoie `defaut` si le fichier n'existe pas."""
    if not chemin.exists():
        return defaut
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def ecrire_json(chemin: Path, objet) -> bool:
    """Écrit un JSON déterministe (clés triées, UTF-8, indentation 2, saut de
    ligne final). Ne touche pas au fichier si le contenu est identique.
    Renvoie True si le fichier a été (ré)écrit."""
    texte = json.dumps(objet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return ecrire_texte(chemin, texte)


def ecrire_texte(chemin: Path, texte: str) -> bool:
    """Écrit un texte UTF-8 (fins de ligne LF) seulement s'il diffère de
    l'existant. Renvoie True si le fichier a été (ré)écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if chemin.exists() and chemin.read_text(encoding="utf-8") == texte:
        return False
    chemin.write_text(texte, encoding="utf-8", newline="\n")
    return True


def journal(message: str) -> None:
    """Trace lisible sur la sortie standard, préfixée pour être repérable
    dans les journaux GitHub Actions."""
    print(f"[pipeline] {message}", file=sys.stdout, flush=True)


def erreur_fatale(message: str, code: int = 1) -> None:
    """Arrête le script avec un message explicite. Utilisé quand continuer
    produirait une transformation douteuse."""
    print(f"[pipeline] ERREUR FATALE : {message}", file=sys.stderr, flush=True)
    sys.exit(code)
