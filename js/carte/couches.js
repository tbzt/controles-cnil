/* Couches de la carte : points individuels (couche MapLibre) et clusters en
   anneau (marqueurs HTML, un SVG par cluster). */

import { Marker } from "../../vendor/maplibre-gl.mjs";
import { ID_SOURCE } from "./source.js";

export const ID_POINTS = "controles-points";

/* Lit les couleurs de famille dans les tokens CSS, une seule source de
   vérité. À rappeler si le thème change. */
export function couleursFamilles(familles) {
  const style = getComputedStyle(document.documentElement);
  const couleurs = {};
  for (const f of familles) {
    couleurs[f.code] = style.getPropertyValue(`--fam-${f.code}`).trim() || style.getPropertyValue("--fam-autres").trim();
  }
  return couleurs;
}

export function expressionCouleur(couleurs, propriete = "famille") {
  const expression = ["match", ["get", propriete]];
  for (const [code, couleur] of Object.entries(couleurs)) expression.push(code, couleur);
  expression.push(couleurs.autres || "#a8adb5");
  return expression;
}

export function ajouterCouchePoints(map, couleurs) {
  const contour = getComputedStyle(document.documentElement).getPropertyValue("--point-contour").trim() || "#fff";
  map.addLayer({
    id: ID_POINTS,
    type: "circle",
    source: ID_SOURCE,
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": expressionCouleur(couleurs),
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 3, 10, 5, 14, 7, 18, 10],
      "circle-opacity": 0.92,
      /* La précision se voit : contour net à l'adresse, fin à la commune, discret au-delà. */
      "circle-stroke-color": contour,
      "circle-stroke-width": ["match", ["get", "precision"], "adresse", 2, "commune", 1, 0.5],
    },
  });
}

export function actualiserCouleurs(map, couleurs) {
  if (!map.getLayer(ID_POINTS)) return;
  map.setPaintProperty(ID_POINTS, "circle-color", expressionCouleur(couleurs));
  const contour = getComputedStyle(document.documentElement).getPropertyValue("--point-contour").trim() || "#fff";
  map.setPaintProperty(ID_POINTS, "circle-stroke-color", contour);
}

/* ------------------------------------------------------ clusters --- */

function diametre(total) {
  /* 30 px pour 2 contrôles, 76 px pour 1 600 : croissance en racine. */
  return Math.round(Math.min(76, 28 + 1.2 * Math.sqrt(total)));
}

function arc(cx, cy, r, debut, fin) {
  const a0 = 2 * Math.PI * debut - Math.PI / 2;
  const a1 = 2 * Math.PI * fin - Math.PI / 2;
  const grand = fin - debut > 0.5 ? 1 : 0;
  return `M${cx + r * Math.cos(a0)} ${cy + r * Math.sin(a0)}A${r} ${r} 0 ${grand} 1 ${cx + r * Math.cos(a1)} ${cy + r * Math.sin(a1)}`;
}

function svgAnneau(proprietes, familles, couleurs) {
  const total = proprietes.point_count;
  const d = diametre(total);
  const r = d / 2 - 3;
  /* Anneau fin : les parts se lisent, le fond reste aéré. */
  const epaisseur = Math.max(3.5, Math.round(d / 12));
  let cumul = 0;
  const arcs = [];
  for (const f of familles) {
    const n = proprietes[f.code] || 0;
    if (!n) continue;
    const debut = cumul / total;
    cumul += n;
    const fin = cumul / total;
    if (fin - debut >= 0.999) {
      arcs.push(`<circle cx="${d / 2}" cy="${d / 2}" r="${r}" fill="none" stroke="${couleurs[f.code]}" stroke-width="${epaisseur}"/>`);
    } else {
      arcs.push(`<path d="${arc(d / 2, d / 2, r, debut, fin)}" fill="none" stroke="${couleurs[f.code]}" stroke-width="${epaisseur}"/>`);
    }
  }
  const taillePolice = d >= 64 ? 15 : d >= 48 ? 13.5 : 12;
  return `<svg width="${d}" height="${d}" viewBox="0 0 ${d} ${d}" aria-hidden="true">`
    + `<circle class="cluster__fond" cx="${d / 2}" cy="${d / 2}" r="${r - epaisseur / 2}"/>`
    + arcs.join("")
    + `<text class="cluster__total" x="${d / 2}" y="${d / 2}" text-anchor="middle" dominant-baseline="central" font-size="${taillePolice}">${total.toLocaleString("fr-FR")}</text>`
    + `</svg>`;
}

/* Maintient un marqueur HTML par cluster visible. Appelé à chaque rendu :
   les clusters changent avec le zoom et le déplacement. */
export function gererClusters(map, familles, obtenirCouleurs) {
  const marqueurs = new Map();
  let visibles = new Set();
  let actifs = true;

  function actualiser() {
    if (!actifs || !map.getSource(ID_SOURCE) || !map.isSourceLoaded(ID_SOURCE)) return;
    const couleurs = obtenirCouleurs();
    const features = map.querySourceFeatures(ID_SOURCE, { filter: ["has", "point_count"] });
    const nouveaux = new Set();
    for (const feature of features) {
      const id = feature.properties.cluster_id;
      if (nouveaux.has(id)) continue;
      nouveaux.add(id);
      let marqueur = marqueurs.get(id);
      const coords = feature.geometry.coordinates;
      if (!marqueur) {
        const element = document.createElement("button");
        element.type = "button";
        element.className = "cluster";
        element.setAttribute("aria-label", `${feature.properties.point_count} contrôles, zoomer`);
        element.innerHTML = svgAnneau(feature.properties, familles, couleurs);
        element.addEventListener("click", () => {
          map.getSource(ID_SOURCE).getClusterExpansionZoom(id).then((zoom) => {
            map.easeTo({ center: coords, zoom: Math.min(zoom, 17), duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
          });
        });
        marqueur = new Marker({ element }).setLngLat(coords).addTo(map);
        marqueurs.set(id, marqueur);
      } else {
        marqueur.setLngLat(coords);
      }
    }
    for (const id of visibles) {
      if (!nouveaux.has(id)) {
        marqueurs.get(id)?.remove();
        marqueurs.delete(id);
      }
    }
    visibles = nouveaux;
  }

  function toutRedessiner() {
    for (const m of marqueurs.values()) m.remove();
    marqueurs.clear();
    visibles = new Set();
    actualiser();
  }

  function activer(valeur) {
    actifs = valeur;
    if (!actifs) {
      for (const m of marqueurs.values()) m.remove();
      marqueurs.clear();
      visibles = new Set();
    } else {
      actualiser();
    }
  }

  map.on("render", actualiser);
  map.on("sourcedata", (e) => { if (e.sourceId === ID_SOURCE && e.isSourceLoaded) actualiser(); });
  return { actualiser, toutRedessiner, activer };
}
