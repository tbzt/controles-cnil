# Bibliothèques vendorisées

Fichiers copiés tels quels, sans build. MapLibre GL JS 6 est distribué en modules ES : `maplibre-gl.mjs` importe `maplibre-gl-shared.mjs` et charge `maplibre-gl-worker.mjs` par URL relative, les trois doivent rester dans le même dossier. Pour mettre à jour : télécharger la nouvelle version depuis la même origine, recalculer les empreintes (`sha256sum`), mettre à jour ce tableau et vérifier la carte localement.

| Fichier | Bibliothèque | Version | Origine | SHA-256 |
|---|---|---|---|---|
| `maplibre-gl.mjs` | MapLibre GL JS | 6.9.0 | https://cdn.jsdelivr.net/npm/maplibre-gl@6.9.0/dist/maplibre-gl.mjs | `0197eee4c6e8fd5d8b68f5f94a23e1c77e0c8fd054c377a280bcd08117aadfc4` |
| `maplibre-gl-shared.mjs` | MapLibre GL JS | 6.9.0 | https://cdn.jsdelivr.net/npm/maplibre-gl@6.9.0/dist/maplibre-gl-shared.mjs | `0aa7432c2d4644e8f46158cc99d0a05e0bf5db98afe6ded2b258a68dcc91bb90` |
| `maplibre-gl-worker.mjs` | MapLibre GL JS | 6.9.0 | https://cdn.jsdelivr.net/npm/maplibre-gl@6.9.0/dist/maplibre-gl-worker.mjs | `836616cb05bef91f9c7f3920ee2aeef648b81cee0645a037e70365286009ac98` |
| `maplibre-gl.css` | MapLibre GL JS | 6.9.0 | https://cdn.jsdelivr.net/npm/maplibre-gl@6.9.0/dist/maplibre-gl.css | `8e2dbbab312dc57656fbb76e9fa5308c75c9d7c7ba5808a7d55bcdb64cc813fa` |
| `maplibre-gl-LICENSE.txt` | MapLibre GL JS | 6.9.0 | https://cdn.jsdelivr.net/npm/maplibre-gl@6.9.0/LICENSE.txt | `ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2` |

Licence MapLibre GL JS : BSD-3-Clause. Récupéré le 2026-09-11.
