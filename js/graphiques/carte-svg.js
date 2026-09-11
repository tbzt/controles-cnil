/* Cartes choroplèthes par département en SVG, pour les petits multiples et
   la comparaison de périodes.

   Pourquoi du SVG et pas dix cartes MapLibre : dix contextes WebGL seraient
   lourds, et à cette échelle un aplat par département suffit. Les contours
   simplifiés (métropole et Corse) sont projetés une fois en Mercator et mis
   en cache sous forme de chemins ; chaque carte ne fait ensuite que colorer. */

const LARGEUR = 300;
const HAUTEUR = 290;

function mercator([lon, lat]) {
  const x = (lon * Math.PI) / 180;
  const y = Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  return [x, y];
}

/* Projette les contours et renvoie {code → {d, nom}} plus le cadre. */
export function preparerContours(geojson) {
  const points = [];
  const parcourir = (coords, f) => {
    if (typeof coords[0] === "number") f(coords);
    else coords.forEach((c) => parcourir(c, f));
  };
  for (const feat of geojson.features) parcourir(feat.geometry.coordinates, (c) => points.push(mercator(c)));
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const marge = 6;
  const echelle = Math.min((LARGEUR - 2 * marge) / (maxX - minX), (HAUTEUR - 2 * marge) / (maxY - minY));
  const dx = (LARGEUR - (maxX - minX) * echelle) / 2, dy = (HAUTEUR - (maxY - minY) * echelle) / 2;
  const projeter = (c) => {
    const [x, y] = mercator(c);
    return [((x - minX) * echelle + dx).toFixed(1), ((maxY - y) * echelle + dy).toFixed(1)];
  };
  const chemins = {};
  for (const feat of geojson.features) {
    const anneaux = feat.geometry.type === "Polygon" ? [feat.geometry.coordinates] : feat.geometry.coordinates;
    let d = "";
    for (const poly of anneaux) {
      for (const anneau of poly) {
        d += "M" + anneau.map((c) => projeter(c).join(",")).join("L") + "Z";
      }
    }
    chemins[feat.properties.code] = { d, nom: feat.properties.nom };
  }
  return { chemins, largeur: LARGEUR, hauteur: HAUTEUR };
}

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Interpolation entre deux couleurs hex, t dans [0, 1]. */
export function melanger(hexA, hexB, t) {
  const a = hexA.match(/[0-9a-f]{2}/gi).map((h) => parseInt(h, 16));
  const b = hexB.match(/[0-9a-f]{2}/gi).map((h) => parseInt(h, 16));
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * Math.max(0, Math.min(1, t))));
  return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
}

/* Échelle séquentielle : 0 → couleur vide, max → couleur pleine (racine pour
   ne pas écraser tout sauf Paris). */
export function echelleSequentielle(max, couleurVide, couleurPleine) {
  const m = Math.sqrt(Math.max(1, max));
  return (v) => (v ? melanger(couleurVide, couleurPleine, Math.sqrt(v) / m) : couleurVide);
}

/* Échelle divergente : négatif → couleur A, positif → couleur B, zéro → neutre. */
export function echelleDivergente(amplitude, couleurNeg, couleurNeutre, couleurPos) {
  const m = Math.sqrt(Math.max(1, amplitude));
  return (v) => {
    if (!v) return couleurNeutre;
    const t = Math.sqrt(Math.abs(v)) / m;
    return v < 0 ? melanger(couleurNeutre, couleurNeg, t) : melanger(couleurNeutre, couleurPos, t);
  };
}

/* valeurs : {code → nombre} ; formater(v, code) pour le <title>. */
export function carteDepartements({ contours, valeurs, couleur, formater, titre, dataCle = "departement", classe = "" }) {
  let s = `<svg class="carte-svg ${classe}" viewBox="0 0 ${contours.largeur} ${contours.hauteur}" role="img" aria-label="${echapper(titre || "")}">`;
  for (const [code, { d, nom }] of Object.entries(contours.chemins)) {
    const v = valeurs[code] || 0;
    s += `<path class="carte-svg__departement graphique__cliquable" data-${dataCle}="${code}" d="${d}" fill="${couleur(v)}"><title>${echapper(nom)} (${code}) : ${echapper(formater(v, code))}</title></path>`;
  }
  return s + "</svg>";
}
