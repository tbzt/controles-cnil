/* Chargement des données publiées.

   Le site lit `data/processed/` en fetch(). Avec `?version=donnees-AAAA-MM-JJ`
   dans l'URL, il lit la même arborescence à ce tag du dépôt, servie par
   raw.githubusercontent.com (qui envoie les en-têtes CORS nécessaires) :
   c'est ainsi qu'une ancienne version de la carte se reproduit sans copier
   un seul fichier. */

const DEPOT = "tbzt/controles-cnil";

export function baseDonnees() {
  const version = new URLSearchParams(location.search).get("version");
  if (version && /^[\w.-]+$/.test(version)) {
    return `https://raw.githubusercontent.com/${DEPOT}/${version}/data/`;
  }
  return "data/";
}

async function lireJson(url) {
  const reponse = await fetch(url, { cache: "no-cache" });
  if (!reponse.ok) throw new Error(`${url} : ${reponse.status}`);
  return reponse.json();
}

export async function chargerDonnees() {
  const base = baseDonnees();
  const [stats, geojson, familles, libelles, verification] = await Promise.all([
    lireJson(base + "processed/stats.json"),
    lireJson(base + "processed/controles.geojson"),
    lireJson(base + "processed/referentiels/familles.json"),
    lireJson(base + "processed/referentiels/libelles.json"),
    lireJson(base + "metadata/derniere-verification.json").catch(() => null),
  ]);
  return { stats, geojson, familles: familles.familles, libelles, verification, version: base === "data/" ? null : base };
}

/* Formats d'affichage. */

const formatEntier = new Intl.NumberFormat("fr-FR");
const formatDate = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" });

export function nombre(n) {
  return formatEntier.format(n);
}

export function date(iso) {
  if (!iso) return "";
  return formatDate.format(new Date(iso));
}
