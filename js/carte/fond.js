/* Fond de carte.

   Premier choix : le style vectoriel « positron » d'OpenFreeMap (données
   OpenStreetMap, gratuit, sans clé ni compte), sobre et gris, qui laisse la
   couleur aux données. Repli : les tuiles raster d'OpenStreetMap, si le style
   ne se charge pas. Changer de fond se fait ici et nulle part ailleurs. */

export const STYLE_VECTORIEL = "https://tiles.openfreemap.org/styles/positron";

export const ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · '
  + '<a href="https://openfreemap.org/">OpenFreeMap</a> · données '
  + '<a href="https://www.data.gouv.fr/datasets/controles-realises-par-la-cnil">CNIL</a> (Licence Ouverte)';

export function styleRepli() {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: ATTRIBUTION,
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  };
}

/* Vérifie que le style vectoriel répond ; renvoie le style à passer à
   MapLibre (URL ou objet de repli) et un indicateur de repli. */
export async function choisirStyle() {
  try {
    const controleur = new AbortController();
    const minuterie = setTimeout(() => controleur.abort(), 6000);
    const reponse = await fetch(STYLE_VECTORIEL, { signal: controleur.signal, cache: "force-cache" });
    clearTimeout(minuterie);
    if (reponse.ok) return { style: STYLE_VECTORIEL, repli: false };
  } catch (_) {
    /* réseau ou délai : on passe au repli */
  }
  return { style: styleRepli(), repli: true };
}
