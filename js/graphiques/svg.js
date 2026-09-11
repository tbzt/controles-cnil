/* Primitives de graphiques en SVG, sans bibliothèque.

   Cinq formes suffisent au projet : barres verticales (une par année),
   barres horizontales (répartition), barres empilées par année (absolues ou
   en parts), et des tuiles de chiffres. Chaque fonction renvoie une chaîne
   SVG ; les couleurs viennent des tokens CSS (currentColor, variables), les
   valeurs sont accessibles par <title> et un tableau caché pour les lecteurs
   d'écran est laissé au composant appelant. Les éléments cliquables portent
   des attributs data-* que la vue écoute par délégation. */

const formatEntier = new Intl.NumberFormat("fr-FR");
const formatPour = new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 0 });

export const nombre = (n) => formatEntier.format(n);
export const pourcentage = (p) => formatPour.format(p);

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Pas « joli » d'axe : 1, 2, 5 × 10^k, pour au plus ~5 graduations. */
function pas(max) {
  if (max <= 0) return 1;
  const brut = max / 4;
  const puissance = 10 ** Math.floor(Math.log10(brut));
  for (const m of [1, 2, 5, 10]) if (m * puissance >= brut) return m * puissance;
  return 10 * puissance;
}

/* ---------------------------------------------------- barres verticales -- */

/* series : [{cle, libelle, valeur, fond?}] ; fond = valeur de référence dessinée en gris derrière. */
export function barresVerticales({ series, largeur = 640, hauteur = 220, couleur = "var(--accent)", dataCle = "annee", rupture = null }) {
  const marge = { haut: 12, droite: 8, bas: 28, gauche: 40 };
  const w = largeur - marge.gauche - marge.droite;
  const h = hauteur - marge.haut - marge.bas;
  const max = Math.max(1, ...series.map((s) => Math.max(s.valeur, s.fond || 0)));
  const p = pas(max);
  const plafond = Math.ceil(max / p) * p;
  const y = (v) => marge.haut + h - (v / plafond) * h;
  const largeurBande = w / series.length;
  const largeurBarre = Math.max(4, largeurBande * 0.62);

  let s = `<svg class="graphique" viewBox="0 0 ${largeur} ${hauteur}" role="img" aria-hidden="true">`;
  for (let v = 0; v <= plafond; v += p) {
    s += `<line class="graphique__grille" x1="${marge.gauche}" x2="${largeur - marge.droite}" y1="${y(v)}" y2="${y(v)}"/>`;
    s += `<text class="graphique__axe" x="${marge.gauche - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle">${nombre(v)}</text>`;
  }
  series.forEach((it, i) => {
    const x = marge.gauche + i * largeurBande + (largeurBande - largeurBarre) / 2;
    if (it.fond != null && it.fond !== it.valeur) {
      s += `<rect class="graphique__fond" x="${x}" y="${y(it.fond)}" width="${largeurBarre}" height="${marge.haut + h - y(it.fond)}"><title>${echapper(it.libelle)} : ${nombre(it.fond)} au total</title></rect>`;
    }
    s += `<rect class="graphique__barre graphique__cliquable" data-${dataCle}="${echapper(it.cle)}" x="${x}" y="${y(it.valeur)}" width="${largeurBarre}" height="${marge.haut + h - y(it.valeur)}" fill="${couleur}"><title>${echapper(it.libelle)} : ${nombre(it.valeur)}</title></rect>`;
    if (it.valeur > 0) {
      s += `<text class="graphique__valeur" x="${x + largeurBarre / 2}" y="${y(it.valeur) - 4}" text-anchor="middle">${nombre(it.valeur)}</text>`;
    }
    s += `<text class="graphique__axe" x="${x + largeurBarre / 2}" y="${hauteur - 8}" text-anchor="middle">${echapper(it.libelle)}</text>`;
  });
  if (rupture != null) {
    const i = series.findIndex((it) => it.cle === rupture);
    if (i > 0) {
      const x = marge.gauche + i * largeurBande;
      s += `<line class="graphique__rupture" x1="${x}" x2="${x}" y1="${marge.haut}" y2="${marge.haut + h}"/>`;
    }
  }
  return s + "</svg>";
}

/* ---------------------------------------------------- barres horizontales */

/* items : [{cle, libelle, valeur, couleur}] ; total pour les parts. */
export function barresHorizontales({ items, total, largeur = 640, dataCle = "famille" }) {
  const ligne = 26;
  const marge = { gauche: Math.round(largeur * 0.3), droite: 84 };
  const hauteur = items.length * ligne + 4;
  const max = Math.max(1, ...items.map((i) => i.valeur));
  const w = largeur - marge.gauche - marge.droite;
  let s = `<svg class="graphique" viewBox="0 0 ${largeur} ${hauteur}" role="img" aria-hidden="true">`;
  items.forEach((it, i) => {
    const y = 2 + i * ligne;
    const lg = (it.valeur / max) * w;
    s += `<g class="graphique__cliquable" data-${dataCle}="${echapper(it.cle)}">`;
    s += `<rect class="graphique__zone" x="0" y="${y}" width="${largeur}" height="${ligne}"/>`;
    s += `<text class="graphique__libelle" x="${marge.gauche - 10}" y="${y + ligne / 2}" text-anchor="end" dominant-baseline="middle">${echapper(it.libelle)}</text>`;
    s += `<rect class="graphique__barre" x="${marge.gauche}" y="${y + 5}" width="${Math.max(lg, it.valeur ? 2 : 0)}" height="${ligne - 10}" rx="2" fill="${it.couleur || "var(--accent)"}"><title>${echapper(it.libelle)} : ${nombre(it.valeur)} (${pourcentage(it.valeur / (total || 1))})</title></rect>`;
    s += `<text class="graphique__valeur" x="${marge.gauche + Math.max(lg, it.valeur ? 2 : 0) + 8}" y="${y + ligne / 2}" dominant-baseline="middle">${nombre(it.valeur)} <tspan class="graphique__part">${total ? pourcentage(it.valeur / total) : ""}</tspan></text>`;
    s += `</g>`;
  });
  return s + "</svg>";
}

/* ---------------------------------------------------- barres empilées ---- */

/* colonnes : [{cle, libelle, parts: {code: valeur}}] ; categories : [{code, libelle, couleur}] ;
   parts = true pour normaliser à 100 %. */
export function barresEmpilees({ colonnes, categories, parts = false, largeur = 640, hauteur = 240, rupture = null, dataCle = "annee" }) {
  const marge = { haut: 12, droite: 8, bas: 28, gauche: 40 };
  const w = largeur - marge.gauche - marge.droite;
  const h = hauteur - marge.haut - marge.bas;
  const totaux = colonnes.map((c) => Object.values(c.parts).reduce((a, b) => a + b, 0));
  const max = parts ? 1 : Math.max(1, ...totaux);
  const p = parts ? 0.25 : pas(max);
  const plafond = parts ? 1 : Math.ceil(max / p) * p;
  const y = (v) => marge.haut + h - (v / plafond) * h;
  const largeurBande = w / colonnes.length;
  const largeurBarre = Math.max(4, largeurBande * 0.66);

  let s = `<svg class="graphique" viewBox="0 0 ${largeur} ${hauteur}" role="img" aria-hidden="true">`;
  for (let v = 0; v <= plafond + 1e-9; v += p) {
    s += `<line class="graphique__grille" x1="${marge.gauche}" x2="${largeur - marge.droite}" y1="${y(v)}" y2="${y(v)}"/>`;
    s += `<text class="graphique__axe" x="${marge.gauche - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle">${parts ? pourcentage(v) : nombre(v)}</text>`;
  }
  colonnes.forEach((c, i) => {
    const x = marge.gauche + i * largeurBande + (largeurBande - largeurBarre) / 2;
    const total = totaux[i] || 1;
    let cumul = 0;
    for (const cat of categories) {
      const v = c.parts[cat.code] || 0;
      if (!v) continue;
      const v0 = parts ? cumul / total : cumul;
      const v1 = parts ? (cumul + v) / total : cumul + v;
      s += `<rect class="graphique__segment graphique__cliquable" data-${dataCle}="${echapper(c.cle)}" data-categorie="${echapper(cat.code)}" x="${x}" y="${y(v1)}" width="${largeurBarre}" height="${Math.max(0, y(v0) - y(v1))}" fill="${cat.couleur}"><title>${echapper(c.libelle)} · ${echapper(cat.libelle)} : ${nombre(v)} (${pourcentage(v / total)})</title></rect>`;
      cumul += v;
    }
    s += `<text class="graphique__axe" x="${x + largeurBarre / 2}" y="${hauteur - 8}" text-anchor="middle">${echapper(c.libelle)}</text>`;
  });
  if (rupture != null) {
    const i = colonnes.findIndex((c) => c.cle === rupture);
    if (i > 0) {
      const x = marge.gauche + i * largeurBande;
      s += `<line class="graphique__rupture" x1="${x}" x2="${x}" y1="${marge.haut}" y2="${marge.haut + h}"/>`;
    }
  }
  return s + "</svg>";
}

/* ---------------------------------------------------- légende ------------ */

export function legende(categories, dataCle) {
  return `<ul class="graphique__legende">${categories.map((c) => `<li class="graphique__legende-item ${dataCle ? "graphique__cliquable" : ""}" ${dataCle ? `data-${dataCle}="${echapper(c.code)}"` : ""}><span class="graphique__pastille" style="background:${c.couleur}"></span>${echapper(c.libelle)}</li>`).join("")}</ul>`;
}

/* ---------------------------------------------------- courbes ------------ */

/* series : [{cle, libelle, couleur, valeurs: [n par année]}] ; annees : [..]. */
export function courbes({ series, annees, largeur = 900, hauteur = 260, rupture = null, dataCle = "annee", parts = false }) {
  const marge = { haut: 14, droite: 16, bas: 28, gauche: 44 };
  const w = largeur - marge.gauche - marge.droite;
  const h = hauteur - marge.haut - marge.bas;
  const max = parts ? 1 : Math.max(1, ...series.flatMap((s) => s.valeurs));
  const p = parts ? 0.25 : pas(max);
  const plafond = parts ? Math.min(1, Math.ceil(Math.max(...series.flatMap((s) => s.valeurs), 0.01) / p) * p) : Math.ceil(max / p) * p;
  const x = (i) => marge.gauche + (annees.length > 1 ? (i / (annees.length - 1)) * w : w / 2);
  const y = (v) => marge.haut + h - (v / plafond) * h;

  let s = `<svg class="graphique" viewBox="0 0 ${largeur} ${hauteur}" role="img" aria-hidden="true">`;
  for (let v = 0; v <= plafond + 1e-9; v += p) {
    s += `<line class="graphique__grille" x1="${marge.gauche}" x2="${largeur - marge.droite}" y1="${y(v)}" y2="${y(v)}"/>`;
    s += `<text class="graphique__axe" x="${marge.gauche - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle">${parts ? pourcentage(v) : nombre(v)}</text>`;
  }
  annees.forEach((a, i) => {
    s += `<text class="graphique__axe" x="${x(i)}" y="${hauteur - 8}" text-anchor="middle">${a}</text>`;
    s += `<rect class="graphique__colonne graphique__cliquable" data-${dataCle}="${a}" x="${x(i) - (w / Math.max(1, annees.length - 1)) / 2}" y="${marge.haut}" width="${w / Math.max(1, annees.length - 1)}" height="${h}" fill="transparent"/>`;
  });
  if (rupture != null) {
    const i = annees.indexOf(rupture);
    if (i > 0) s += `<line class="graphique__rupture" x1="${x(i) - (w / (annees.length - 1)) / 2}" x2="${x(i) - (w / (annees.length - 1)) / 2}" y1="${marge.haut}" y2="${marge.haut + h}"/>`;
  }
  for (const serie of series) {
    const pts = serie.valeurs.map((v, i) => `${x(i)},${y(v)}`);
    if (serie.aire) {
      s += `<path class="graphique__aire" d="M${x(0)},${y(0)}L${pts.join("L")}L${x(annees.length - 1)},${y(0)}Z" fill="${serie.couleur}"/>`;
    }
    s += `<polyline class="graphique__courbe" points="${pts.join(" ")}" fill="none" stroke="${serie.couleur}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;
    serie.valeurs.forEach((v, i) => {
      s += `<circle class="graphique__point" cx="${x(i)}" cy="${y(v)}" r="3.2" fill="${serie.couleur}"><title>${echapper(serie.libelle)} · ${annees[i]} : ${parts ? pourcentage(v) : nombre(v)}</title></circle>`;
    });
  }
  return s + "</svg>";
}
