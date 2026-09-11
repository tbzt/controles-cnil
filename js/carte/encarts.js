/* Encarts outre-mer : un contour SVG par territoire, le nombre de contrôles de
   la sélection, et un clic qui recadre la carte principale sur le territoire.

   Pourquoi pas cinq mini-cartes MapLibre : six contextes WebGL sur un mobile,
   c'est trop cher pour cinq territoires qui totalisent une vingtaine de
   contrôles. Les vrais points et clusters s'affichent dans la carte
   principale une fois recadrée. */

import { baseDonnees } from "../donnees.js";

const TAILLE = 56;

function mercator([lon, lat]) {
  return [(lon * Math.PI) / 180, Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))];
}

function chemin(geometrie) {
  const anneaux = geometrie.type === "Polygon" ? [geometrie.coordinates] : geometrie.coordinates;
  const points = [];
  for (const poly of anneaux) for (const anneau of poly) for (const c of anneau) points.push(mercator(c));
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const marge = 4;
  const echelle = Math.min((TAILLE - 2 * marge) / (maxX - minX || 1), (TAILLE - 2 * marge) / (maxY - minY || 1));
  const dx = (TAILLE - (maxX - minX) * echelle) / 2, dy = (TAILLE - (maxY - minY) * echelle) / 2;
  let d = "";
  for (const poly of anneaux) {
    for (const anneau of poly) {
      d += "M" + anneau.map((c) => {
        const [x, y] = mercator(c);
        return `${((x - minX) * echelle + dx).toFixed(1)},${((maxY - y) * echelle + dy).toFixed(1)}`;
      }).join("L") + "Z";
    }
  }
  return d;
}

export async function creerEncarts(map, conteneur, mouvementReduit) {
  let territoires = [];
  try {
    const g = await (await fetch(baseDonnees() + "referentiels-source/contours-outre-mer.geojson")).json();
    territoires = g.features.map((f) => ({ code: f.properties.code, nom: f.properties.nom, bbox: f.properties.bbox, d: chemin(f.geometry) }));
  } catch (_) {
    return { rendre() {} };
  }
  conteneur.innerHTML = `<p class="encarts__titre">Outre-mer</p>` + territoires.map((t) => `
    <button type="button" class="encart" data-code="${t.code}" title="Recadrer sur ${t.nom}" aria-label="${t.nom}, recadrer la carte">
      <svg viewBox="0 0 ${TAILLE} ${TAILLE}" width="${TAILLE}" height="${TAILLE}" aria-hidden="true"><path class="encart__contour" d="${t.d}"/></svg>
      <span class="encart__nom">${t.nom}</span>
      <span class="encart__n num" data-n="${t.code}">0</span>
    </button>`).join("")
    + `<button type="button" class="encart encart--retour" data-code="metropole" title="Revenir à la métropole" aria-label="Revenir à la vue de la France métropolitaine">
      <span class="encart__nom">Métropole</span></button>`;
  conteneur.hidden = false;

  conteneur.addEventListener("click", (e) => {
    const b = e.target.closest(".encart");
    if (!b) return;
    const duree = mouvementReduit ? 0 : 800;
    if (b.dataset.code === "metropole") {
      map.fitBounds([[-5.3, 41.3], [9.7, 51.2]], { padding: 20, duration: duree });
      return;
    }
    const t = territoires.find((x) => x.code === b.dataset.code);
    if (t) map.fitBounds([[t.bbox[0], t.bbox[1]], [t.bbox[2], t.bbox[3]]], { padding: 40, duration: duree, maxZoom: 11 });
  });

  return {
    /* Compte les contrôles de la sélection par territoire (département de l'organisme). */
    rendre(selection) {
      const comptes = {};
      for (const f of selection) {
        const d = f.properties.departement;
        if (d && d.startsWith("97")) comptes[d] = (comptes[d] || 0) + 1;
      }
      for (const t of territoires) {
        const el = conteneur.querySelector(`[data-n="${t.code}"]`);
        const n = comptes[t.code] || 0;
        el.textContent = n.toLocaleString("fr-FR");
        el.closest(".encart").classList.toggle("encart--vide", n === 0);
      }
    },
  };
}
