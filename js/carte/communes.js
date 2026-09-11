/* Mode « Communes » : un cercle par commune, aire proportionnelle au nombre
   de contrôles, couleur de la famille dominante.

   C'est le mode honnête quand la précision est la commune : il ne fait pas
   semblant de placer des points, et il rend Paris lisible par rapport au
   reste (1 640 contrôles dans le seul département 75). */

import { expressionCouleur } from "./couches.js";

export const ID_SOURCE_COMMUNES = "communes";
export const ID_CERCLES = "communes-cercles";
export const ID_NOMBRES = "communes-nombres";

/* Agrège la sélection par commune. Le point d'une commune est la moyenne des
   points sélectionnés (les adresses connues tirent le cercle vers le centre
   réel de l'activité). */
export function agregerCommunes(features, familles) {
  const parCommune = new Map();
  for (const f of features) {
    const p = f.properties;
    if (!p.code_insee) continue;
    let c = parCommune.get(p.code_insee);
    if (!c) {
      c = { code_insee: p.code_insee, commune: p.commune, departement: p.departement, n: 0, lon: 0, lat: 0, familles: {} };
      parCommune.set(p.code_insee, c);
    }
    c.n += 1;
    c.lon += f.geometry.coordinates[0];
    c.lat += f.geometry.coordinates[1];
    c.familles[p.famille] = (c.familles[p.famille] || 0) + 1;
  }
  const ordre = familles.map((f) => f.code);
  const out = [];
  for (const c of parCommune.values()) {
    const dominante = Object.entries(c.familles).sort((a, b) => b[1] - a[1] || ordre.indexOf(a[0]) - ordre.indexOf(b[0]))[0][0];
    out.push({
      type: "Feature",
      id: c.code_insee,
      geometry: { type: "Point", coordinates: [c.lon / c.n, c.lat / c.n] },
      properties: { code_insee: c.code_insee, commune: c.commune, departement: c.departement, n: c.n,
                    famille_dominante: dominante, familles: JSON.stringify(c.familles) },
    });
  }
  /* Les petits cercles au-dessus des grands : on trie par effectif décroissant, MapLibre dessine dans l'ordre. */
  out.sort((a, b) => b.properties.n - a.properties.n);
  return { type: "FeatureCollection", features: out };
}

export function ajouterCouchesCommunes(map, couleurs) {
  const contour = getComputedStyle(document.documentElement).getPropertyValue("--point-contour").trim() || "#fff";
  map.addSource(ID_SOURCE_COMMUNES, { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "code_insee" });
  map.addLayer({
    id: ID_CERCLES,
    type: "circle",
    source: ID_SOURCE_COMMUNES,
    layout: { visibility: "none" },
    paint: {
      /* Aire proportionnelle : rayon en racine de l'effectif, borné pour rester lisible. */
      "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 5, 2, 8, 5, 15, 10, 24, 20, 34, 40, 46],
      "circle-color": expressionCouleur(couleurs, "famille_dominante"),
      "circle-opacity": 0.72,
      "circle-stroke-color": contour,
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: ID_NOMBRES,
    type: "symbol",
    source: ID_SOURCE_COMMUNES,
    layout: {
      visibility: "none",
      "text-field": ["case", [">=", ["get", "n"], 4], ["to-string", ["get", "n"]], ""],
      "text-size": ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 2, 10, 40, 14],
      "text-font": ["Noto Sans Bold"],
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: { "text-color": "#ffffff", "text-halo-color": "rgba(0,0,0,0.35)", "text-halo-width": 1 },
  });
}

export function afficherCommunes(map, visible) {
  for (const id of [ID_CERCLES, ID_NOMBRES]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  }
}

export function actualiserCouleursCommunes(map, couleurs) {
  if (map.getLayer(ID_CERCLES)) map.setPaintProperty(ID_CERCLES, "circle-color", expressionCouleur(couleurs, "famille_dominante"));
}
