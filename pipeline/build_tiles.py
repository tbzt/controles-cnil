"""Étape optionnelle, non branchée : tuiles vectorielles PMTiles.

Aujourd'hui inutile : 3 617 points tiennent dans un GeoJSON de 150 Ko
compressé, et le clustering natif de MapLibre suffit. Ce script existe pour
que la migration soit un chemin balisé, pas une réécriture, le jour où l'un
des seuils du README est franchi (GeoJSON > 5 Mo, plus de 50 000 points, ou
setData trop lent sur mobile).

    sudo apt install tippecanoe        # runner Ubuntu : paquet disponible
    python3 pipeline/build_tiles.py    # → data/processed/controles.pmtiles

Côté site, seul `js/carte/source.js` change : une source `vector` sur le
fichier PMTiles via le protocole pmtiles.js (jsDelivr), et les couches
pointent vers `source-layer: "controles"`. Les clusters sont alors calculés
par tippecanoe par niveau de zoom (`--cluster-distance`), avec des
`--accumulate-attribute` pour conserver les sous-totaux par famille.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.commun import PROCESSED, erreur_fatale, journal  # noqa: E402

ENTREE = PROCESSED / "controles.geojson"
SORTIE = PROCESSED / "controles.pmtiles"


def main(argv=None) -> int:
    if not shutil.which("tippecanoe"):
        erreur_fatale("tippecanoe introuvable : `sudo apt install tippecanoe`")
    if not ENTREE.exists():
        erreur_fatale(f"{ENTREE} absent : lancez pipeline/build.py")
    commande = [
        "tippecanoe", "-o", str(SORTIE), "--force",
        "--layer", "controles", "--name", "Contrôles CNIL",
        "--minimum-zoom", "3", "--maximum-zoom", "14",
        "--cluster-distance", "48", "--cluster-densest-as-needed",
        "--accumulate-attribute", "annee:comma",
        "--no-feature-limit", "--no-tile-size-limit",
        str(ENTREE),
    ]
    journal(" ".join(commande))
    subprocess.run(commande, check=True)
    journal(f"écrit : {SORTIE} ({SORTIE.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
