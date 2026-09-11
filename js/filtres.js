/* Filtrage : fonctions pures sur le tableau des contrôles.

   À 3 600 lignes, tout se recalcule à chaque changement en quelques
   millisecondes : aucun index, aucun worker. Chaque contrôle est enrichi une
   fois d'une chaîne normalisée `_n` (organisme + commune, sans accents) pour
   la recherche. */

export function normaliser(texte) {
  return String(texte || "")
    .replace(/œ/g, "oe").replace(/Œ/g, "OE").replace(/æ/g, "ae").replace(/Æ/g, "AE")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toUpperCase().replace(/[^A-Z0-9]+/g, " ").trim();
}

export function preparer(features) {
  for (const f of features) {
    const p = f.properties;
    /* Clé de rapprochement calculée par le pipeline (formes juridiques,
       domaines et alias retirés) ; repli sur la normalisation locale. */
    p._on = p.organisme_cle || normaliser(p.organisme);
    p._n = `${normaliser(p.organisme)} ${p._on} ${normaliser(p.commune)}`;
  }
  return features;
}

/* Un prédicat par critère ; `sauf` permet d'ignorer un critère pour compter
   une facette sous les autres filtres seulement. */
function predicats(etat, sauf) {
  const termes = etat.q ? normaliser(etat.q).split(" ").filter(Boolean) : [];
  const liste = [];
  if (sauf !== "annees") liste.push((p) => p.annee >= etat.annees[0] && p.annee <= etat.annees[1]);
  for (const k of ["famille", "secteur", "fondement", "modalite"]) {
    if (sauf !== k && etat[k].size) liste.push((p) => etat[k].has(p[k]));
  }
  if (sauf !== "region" && etat.region) liste.push((p) => p.region === etat.region);
  if (sauf !== "departement" && etat.departement) liste.push((p) => p.departement === etat.departement);
  if (sauf !== "commune" && etat.commune) liste.push((p) => p.code_insee === etat.commune);
  if (sauf !== "organisme" && etat.organisme) liste.push((p) => p._on === etat.organisme);
  if (sauf !== "q" && termes.length) liste.push((p) => termes.every((t) => p._n.includes(t)));
  return liste;
}

export function filtrer(features, etat, sauf) {
  const liste = predicats(etat, sauf);
  return features.filter((f) => liste.every((test) => test(f.properties)));
}

/* Effectifs d'une facette (ex. famille) sous tous les autres filtres. */
export function compterFacette(features, etat, cle) {
  const comptes = {};
  for (const f of filtrer(features, etat, cle)) {
    const v = f.properties[cle];
    comptes[v] = (comptes[v] || 0) + 1;
  }
  return comptes;
}

/* Suggestions pour la recherche : organismes et communes dont le nom contient
   tous les mots tapés, comptés sous les autres filtres, les plus fréquents
   d'abord. */
export function suggestions(features, etat, q, max = 6) {
  const termes = normaliser(q).split(" ").filter(Boolean);
  if (!termes.length) return { organismes: [], communes: [] };
  const base = filtrer(features, { ...etat, q: "", organisme: "" });
  const organismes = new Map();
  const communes = new Map();
  for (const f of base) {
    const p = f.properties;
    if (termes.every((t) => p._on.includes(t))) {
      const o = organismes.get(p._on) || { nom: p.organisme, cle: p._on, n: 0 };
      o.n += 1;
      organismes.set(p._on, o);
    }
    if (p.code_insee && termes.every((t) => normaliser(p.commune).includes(t))) {
      const c = communes.get(p.code_insee) || { commune: p.commune, code_insee: p.code_insee, departement: p.departement, n: 0 };
      c.n += 1;
      communes.set(p.code_insee, c);
    }
  }
  const tri = (a, b) => b.n - a.n || a.nom?.localeCompare(b.nom, "fr") || a.commune?.localeCompare(b.commune, "fr");
  return {
    organismes: [...organismes.values()].sort(tri).slice(0, max),
    communes: [...communes.values()].sort(tri).slice(0, Math.max(2, max - 3)),
  };
}
