/* État des filtres, unique et partageable.

   L'état vit dans le hash de l'URL, ce qui rend toute vue partageable et
   revient au même écran après rechargement. Forme :
   #annees=2019-2023&famille=sante_social,commerce&modalite=en_ligne&region=11&q=carrefour
   Un état vide donne un hash vide. */

const CLES_MULTIPLES = ["famille", "secteur", "fondement", "modalite"];
const CLES_SIMPLES = ["region", "departement", "commune", "q"];

export function etatVide(annees) {
  return {
    annees: [annees[0], annees[annees.length - 1]],
    famille: new Set(), secteur: new Set(), fondement: new Set(), modalite: new Set(),
    region: "", departement: "", commune: "", q: "",
  };
}

export function estVide(etat, annees) {
  return etat.annees[0] === annees[0] && etat.annees[1] === annees[annees.length - 1]
    && CLES_MULTIPLES.every((k) => etat[k].size === 0) && CLES_SIMPLES.every((k) => !etat[k]);
}

export function lireHash(annees) {
  const etat = etatVide(annees);
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  const a = params.get("annees");
  if (a && /^\d{4}-\d{4}$/.test(a)) {
    const [d, f] = a.split("-").map(Number);
    if (d <= f && d >= annees[0] && f <= annees[annees.length - 1]) etat.annees = [d, f];
  }
  for (const k of CLES_MULTIPLES) {
    const v = params.get(k);
    if (v) etat[k] = new Set(v.split(",").filter(Boolean));
  }
  for (const k of CLES_SIMPLES) {
    etat[k] = params.get(k) || "";
  }
  return etat;
}

export function ecrireHash(etat, annees) {
  const params = new URLSearchParams();
  if (etat.annees[0] !== annees[0] || etat.annees[1] !== annees[annees.length - 1]) {
    params.set("annees", `${etat.annees[0]}-${etat.annees[1]}`);
  }
  for (const k of CLES_MULTIPLES) if (etat[k].size) params.set(k, [...etat[k]].sort().join(","));
  for (const k of CLES_SIMPLES) if (etat[k]) params.set(k, etat[k]);
  const hash = params.toString().replace(/%2C/g, ",");
  const cible = hash ? `#${hash}` : location.pathname + location.search;
  if ((hash ? `#${hash}` : "") !== location.hash) history.replaceState(null, "", cible);
}

/* Petit bus : les vues s'abonnent, l'application publie. */
export function creerMagasin(etatInitial, annees) {
  let etat = etatInitial;
  const abonnes = new Set();
  return {
    get etat() { return etat; },
    modifier(changements) {
      etat = { ...etat, ...changements };
      ecrireHash(etat, annees);
      for (const fn of abonnes) fn(etat);
    },
    reinitialiser() { this.modifier(etatVide(annees)); },
    abonner(fn) { abonnes.add(fn); return () => abonnes.delete(fn); },
  };
}
