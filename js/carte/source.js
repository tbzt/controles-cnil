/* Source des données de la carte.

   Aujourd'hui : un GeoJSON unique avec le clustering natif de MapLibre
   (supercluster embarqué). `clusterProperties` calcule, pour chaque cluster,
   le nombre de contrôles par famille : c'est ce qui permet les anneaux.

   Si le volume dépassait un jour ~50 000 points ou ~5 Mo, ce module serait
   le seul à changer : une source `vector` sur un fichier PMTiles (avec le
   protocole pmtiles.js) et des clusters précalculés par tippecanoe. */

export const ID_SOURCE = "controles";
export const RAYON_CLUSTER = 48;
export const ZOOM_MAX_CLUSTER = 14; /* au-delà, points individuels ; les points d'une même commune restent superposés */

export function definitionSource(geojson, familles) {
  const proprietes = {};
  for (const f of familles) {
    proprietes[f.code] = ["+", ["case", ["==", ["get", "famille"], f.code], 1, 0]];
  }
  return {
    type: "geojson",
    data: geojson,
    cluster: true,
    clusterRadius: RAYON_CLUSTER,
    clusterMaxZoom: ZOOM_MAX_CLUSTER,
    clusterProperties: proprietes,
    promoteId: "id",
  };
}
