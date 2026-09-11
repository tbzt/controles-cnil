/* Page Données : remplit les dates, les ressources, la précision, la qualité
   et les versions depuis les métadonnées produites par le pipeline. */

import { nombre, date } from "./donnees.js";

const $ = (id) => document.getElementById(id);

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function json(url) {
  try {
    const r = await fetch(url, { cache: "no-cache" });
    return r.ok ? await r.json() : null;
  } catch (_) {
    return null;
  }
}

const LIBELLES_PRECISION = {
  adresse: "à l'adresse (siège ou établissement identifié)",
  commune: "à la commune",
  departement: "au département (ville non résolue ou territoire plus large qu'une commune)",
  pays: "au pays (organisme hors de France)",
  aucune: "sans localisation (ville absente à la source)",
};
const LIBELLES_METHODE = {
  surcouche: "adresse validée (carte uMap, annuaire des entreprises ou saisie manuelle)",
  referentiel_communes: "référentiel des communes (geo.api.gouv.fr)",
  alias: "table d'alias écrite à la main (communes renommées, fautes de frappe, quartiers)",
  centroide_departement: "centroïde du département",
  centroide_pays: "centroïde du pays",
  aucune: "aucune",
};

async function demarrer() {
  const [manifeste, qualite, releases, verification, geocodage, stats, propositions] = await Promise.all([
    json("data/metadata/manifest.json"), json("data/metadata/quality-report.json"), json("data/metadata/releases.json"),
    json("data/metadata/derniere-verification.json"), json("data/metadata/geocodage-rapport.json"), json("data/processed/stats.json"),
    json("data/metadata/propositions-rapport.json"),
  ]);

  /* Dates. */
  const versions = Object.values(manifeste?.ressources || {}).flatMap((r) => r.versions || []);
  const derniereRecuperation = versions.map((v) => v.recupere_le).sort().pop();
  $("d-publication").textContent = date(manifeste?.dataset?.last_modified_source) || "inconnue";
  $("d-recuperation").textContent = date(derniereRecuperation) || "inconnue";
  $("d-maj").textContent = date(releases?.releases?.[0]?.date) || "inconnue";
  $("d-verification").textContent = date(verification?.derniere_verification) || "inconnue";

  /* Ressources archivées. */
  if (manifeste) {
    const lignes = Object.values(manifeste.ressources)
      .sort((a, b) => (a.dossier > b.dossier ? 1 : -1))
      .map((r) => {
        const v = r.versions[r.versions.length - 1];
        return `<tr><td>${echapper(r.dossier === "nombre-controles-1990" ? "1990 →" : r.dossier)}</td><td><a href="${echapper(r.url)}">${echapper(r.titre)}</a></td><td class="num">${nombre(v.taille)} o</td><td>${date(v.last_modified_source)}</td><td>${date(v.recupere_le)}</td><td class="num">${r.versions.length}</td></tr>`;
      });
    $("ressources").innerHTML = `<div class="tableau"><table>
      <caption>Fichiers CSV archivés dans <code>data/raw/</code></caption>
      <thead><tr><th>Année</th><th>Ressource data.gouv.fr</th><th>Taille</th><th>Modifiée par la CNIL</th><th>Récupérée</th><th>Versions</th></tr></thead>
      <tbody>${lignes.join("")}</tbody></table></div>`;
  }

  /* Précision de la localisation. */
  if (geocodage) {
    const total = geocodage.total;
    const prec = Object.entries(geocodage.par_precision_organisme).sort((a, b) => b[1] - a[1]);
    const meth = Object.entries(geocodage.par_methode_organisme).sort((a, b) => b[1] - a[1]);
    $("precision").innerHTML = `<div class="deux-colonnes">
      <div class="tableau"><table><caption>Précision du lieu de l'organisme</caption><tbody>
        ${prec.map(([k, v]) => `<tr><td>${echapper(LIBELLES_PRECISION[k] || k)}</td><td class="num">${nombre(v)}</td><td class="num discret">${Math.round((v / total) * 100)} %</td></tr>`).join("")}
      </tbody></table></div>
      <div class="tableau"><table><caption>Méthode</caption><tbody>
        ${meth.map(([k, v]) => `<tr><td>${echapper(LIBELLES_METHODE[k] || k)}</td><td class="num">${nombre(v)}</td></tr>`).join("")}
      </tbody></table></div></div>
      <p class="discret">${nombre(geocodage.par_lieu_controle?.cnil || 0)} contrôles ont pour lieu du contrôle le siège de la CNIL (en ligne, sur pièces, sur audition).${propositions ? ` ${nombre(propositions.propositions_en_attente)} propositions d'adresse à score moyen attendent une validation humaine.` : ""}</p>`;
    const nr = (geocodage.villes_non_resolues || []).filter((v) => v.ville_source);
    $("non-resolues").innerHTML = nr.length
      ? `<p>Villes non résolues (${nr.length}) : ${nr.map((v) => `<code>${echapper(v.departement_source)} ${echapper(v.ville_source)}</code>`).join(", ")}.</p>`
      : `<p class="discret">Toutes les villes écrites par la CNIL ont été résolues ; seules ${nombre(geocodage.par_precision_organisme.aucune || 0)} lignes sans ville restent sans localisation.</p>`;
  }

  /* Qualité. */
  if (qualite) {
    const icone = { ok: "✓", alerte: "!", fatal: "✕" };
    $("constats").innerHTML = `<p>Résultat du dernier passage : <span class="badge badge--${qualite.resultat}">${qualite.resultat}</span> · ${qualite.nb_ok} ok, ${qualite.nb_alerte} alerte${qualite.nb_alerte > 1 ? "s" : ""}, ${qualite.nb_fatal} fatal.</p>
      <ul class="constats">${qualite.constats.map((c) => `<li class="constat constat--${c.niveau}"><span class="constat__icone" aria-hidden="true">${icone[c.niveau]}</span><span class="constat__regle">${echapper(c.regle)}</span><span>${echapper(c.message)}</span></li>`).join("")}</ul>`;
  }

  /* Versions. */
  if (releases?.releases?.length) {
    $("releases").innerHTML = `<div class="tableau"><table>
      <thead><tr><th>Publication</th><th>Tag</th><th>Contrôles</th><th>Jusqu'à</th><th>Changement</th><th></th></tr></thead>
      <tbody>${releases.releases.map((r) => `<tr>
        <td>${date(r.date)}</td>
        <td><a href="https://github.com/tbzt/controles-cnil/releases/tag/${echapper(r.tag)}"><code>${echapper(r.tag)}</code></a></td>
        <td class="num">${nombre(r.controles)}</td><td class="num">${echapper(r.annee_max)}</td><td>${echapper(r.resume)}</td>
        <td><a href="index.html?version=${echapper(r.tag)}">ouvrir la carte de cette version</a></td></tr>`).join("")}</tbody></table></div>`;
  } else {
    $("releases").innerHTML = `<p class="discret">Aucune version publiée pour l'instant.</p>`;
  }

  if (stats) {
    const c = stats.couverture;
    document.title = `Données et méthode · Contrôles de la CNIL ${c.annee_min}–${c.annee_max}`;
  }
}

demarrer();
