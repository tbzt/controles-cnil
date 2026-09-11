/* Vue Analyse : chiffres et graphiques sur la sélection courante.

   Tout est recalculé depuis le tableau filtré à chaque changement d'état,
   comme la carte. Les graphiques posent des filtres au clic (une année, une
   famille, une modalité…) : ils sont une autre façon de manipuler le même
   état. La rupture de nomenclature CNIL de 2018 est dessinée sur les
   graphiques par famille plutôt que cachée. */

import { barresVerticales, barresHorizontales, barresEmpilees, legende, nombre, pourcentage } from "../graphiques/svg.js";
import { majuscules } from "../donnees.js";

const $ = (id) => document.getElementById(id);

const MODALITES = ["sur_place", "en_ligne", "sur_pieces", "sur_audition", "non_renseignee"];
const FONDEMENTS = ["loi78", "rgpd", "rgpd_ou_directive", "directive_police_justice", "videoprotection"];
const ZONES = [
  { code: "paris", libelle: "Paris", couleur: "var(--zone-paris)" },
  { code: "hauts_de_seine", libelle: "Hauts-de-Seine", couleur: "var(--zone-92)" },
  { code: "reste_idf", libelle: "Reste de l'Île-de-France", couleur: "var(--zone-idf)" },
  { code: "reste_france", libelle: "Reste de la France", couleur: "var(--zone-france)" },
  { code: "etranger", libelle: "Hors de France", couleur: "var(--zone-etranger)" },
];
const COULEURS_MODALITES = { sur_place: "var(--serie-1)", en_ligne: "var(--serie-2)", sur_pieces: "var(--serie-3)", sur_audition: "var(--serie-4)", non_renseignee: "var(--serie-vide)" };
const COULEURS_FONDEMENTS = { loi78: "var(--serie-3)", rgpd: "var(--serie-1)", rgpd_ou_directive: "var(--serie-2)", directive_police_justice: "var(--serie-4)", videoprotection: "var(--serie-5)" };

function zone(p) {
  if (p.pays !== "FR") return "etranger";
  if (p.departement === "75") return "paris";
  if (p.departement === "92") return "hauts_de_seine";
  if (p.region === "11") return "reste_idf";
  return "reste_france";
}

function compter(items, cle) {
  const c = {};
  for (const it of items) c[cle(it)] = (c[cle(it)] || 0) + 1;
  return c;
}

export function creerVueAnalyse({ features, annees, familles, libelles, magasin, obtenirCouleurs }) {
  const conteneur = $("vue-analyse");
  const totalParAnnee = compter(features, (f) => f.properties.annee);

  conteneur.innerHTML = `
    <div class="analyse">
      <header class="analyse__entete">
        <h2>Analyse de la sélection</h2>
        <p class="discret" id="analyse-sous-titre"></p>
      </header>
      <div class="tuiles" id="tuiles"></div>
      <section class="carte-graphique" aria-labelledby="g-annees">
        <div class="carte-graphique__titre"><h3 id="g-annees">Contrôles par année</h3><span class="discret">la sélection en couleur, le total de l'année en gris</span></div>
        <div id="g-annees-svg"></div>
      </section>
      <section class="carte-graphique" aria-labelledby="g-familles">
        <div class="carte-graphique__titre"><h3 id="g-familles">Répartition par famille de secteur</h3><span class="discret">cliquer une famille la sélectionne</span></div>
        <div id="g-familles-svg"></div>
      </section>
      <section class="carte-graphique carte-graphique--large" aria-labelledby="g-familles-annees">
        <div class="carte-graphique__titre"><h3 id="g-familles-annees">Familles par année</h3><span class="discret">la ligne pointillée marque le changement de nomenclature de la CNIL en 2018</span></div>
        <div id="g-familles-annees-svg"></div>
        <div id="g-familles-annees-legende"></div>
      </section>
      <section class="carte-graphique" aria-labelledby="g-modalites">
        <div class="carte-graphique__titre"><h3 id="g-modalites">Modalité de contrôle par année</h3><span class="discret">parts ; la modalité n'est publiée que depuis 2017</span></div>
        <div id="g-modalites-svg"></div>
        <div id="g-modalites-legende"></div>
      </section>
      <section class="carte-graphique" aria-labelledby="g-fondements">
        <div class="carte-graphique__titre"><h3 id="g-fondements">Fondement juridique par année</h3><span class="discret">parts ; la bascule vers le RGPD se lit en 2018-2019</span></div>
        <div id="g-fondements-svg"></div>
        <div id="g-fondements-legende"></div>
      </section>
      <section class="carte-graphique carte-graphique--large" aria-labelledby="g-zones">
        <div class="carte-graphique__titre"><h3 id="g-zones">Où sont les organismes contrôlés</h3><span class="discret">parts par année ; Paris seul pèse près de la moitié</span></div>
        <div id="g-zones-svg"></div>
        <div id="g-zones-legende"></div>
      </section>
      <section class="carte-graphique carte-graphique--large" aria-labelledby="g-organismes">
        <div class="carte-graphique__titre"><h3 id="g-organismes">Organismes les plus contrôlés dans la sélection</h3><span class="discret">rapprochement par nom, approximatif</span></div>
        <div id="g-organismes-svg"></div>
      </section>
      <p class="discret analyse__note">Chaque graphique se lit sur la sélection courante (filtres du panneau). Les données et leur méthode sont décrites dans la page Données.</p>
    </div>`;

  /* Clics sur les graphiques : ils modifient l'état. */
  conteneur.addEventListener("click", (e) => {
    const el = e.target.closest(".graphique__cliquable");
    if (!el) return;
    const etat = magasin.etat;
    if (el.dataset.annee) {
      const a = Number(el.dataset.annee);
      const deja = etat.annees[0] === a && etat.annees[1] === a;
      magasin.modifier({ annees: deja ? [annees[0], annees[annees.length - 1]] : [a, a] });
    } else if (el.dataset.famille) {
      const ens = new Set(etat.famille);
      ens.has(el.dataset.famille) ? ens.delete(el.dataset.famille) : ens.add(el.dataset.famille);
      magasin.modifier({ famille: ens });
    } else if (el.dataset.modalite) {
      const ens = new Set(etat.modalite);
      ens.has(el.dataset.modalite) ? ens.delete(el.dataset.modalite) : ens.add(el.dataset.modalite);
      magasin.modifier({ modalite: ens });
    } else if (el.dataset.fondement) {
      const ens = new Set(etat.fondement);
      ens.has(el.dataset.fondement) ? ens.delete(el.dataset.fondement) : ens.add(el.dataset.fondement);
      magasin.modifier({ fondement: ens });
    } else if (el.dataset.organisme) {
      magasin.modifier({ organisme: el.dataset.organisme, q: "" });
    }
  });

  function rendre(selection, etat, vide) {
    const couleurs = obtenirCouleurs();
    const n = selection.length;
    const anneesSel = annees.filter((a) => a >= etat.annees[0] && a <= etat.annees[1]);
    $("analyse-sous-titre").textContent = vide
      ? "Tous les contrôles localisés, 2014 à 2023."
      : `${nombre(n)} contrôles retenus par les filtres, sur ${nombre(features.length)}.`;

    /* Tuiles. */
    const organismes = new Set(selection.map((f) => f.properties._on));
    const communes = new Set(selection.map((f) => f.properties.code_insee).filter(Boolean));
    const surPlace = selection.filter((f) => f.properties.modalite === "sur_place").length;
    const renseignees = selection.filter((f) => f.properties.modalite !== "non_renseignee").length;
    const adresse = selection.filter((f) => f.properties.precision === "adresse").length;
    $("tuiles").innerHTML = [
      { v: nombre(n), l: "contrôles" },
      { v: nombre(organismes.size), l: "organismes distincts" },
      { v: nombre(communes.size), l: "communes" },
      { v: renseignees ? pourcentage(surPlace / renseignees) : "–", l: "sur place, quand la modalité est connue" },
      { v: n ? pourcentage(adresse / n) : "–", l: "localisés à l'adresse" },
    ].map((t) => `<div class="tuile"><b class="tuile__valeur num">${t.v}</b><span class="tuile__libelle">${t.l}</span></div>`).join("");

    /* Par année, avec le total en fond. */
    const parAnnee = compter(selection, (f) => f.properties.annee);
    /* Les cartes en demi-largeur sont dessinées sur une base de 480 px pour que
       les textes restent lisibles une fois le SVG mis à l'échelle. */
    $("g-annees-svg").innerHTML = barresVerticales({
      largeur: 480, hauteur: 200,
      series: annees.map((a) => ({ cle: a, libelle: String(a), valeur: parAnnee[a] || 0, fond: vide ? null : totalParAnnee[a] || 0 })),
    });

    /* Par famille. */
    const parFamille = compter(selection, (f) => f.properties.famille);
    $("g-familles-svg").innerHTML = barresHorizontales({
      total: n, largeur: 480,
      items: familles.filter((f) => parFamille[f.code]).sort((a, b) => parFamille[b.code] - parFamille[a.code])
        .map((f) => ({ cle: f.code, libelle: f.libelle, valeur: parFamille[f.code], couleur: couleurs[f.code] })),
    });

    /* Familles par année, absolu, avec la rupture 2018. */
    const catFamilles = familles.filter((f) => parFamille[f.code]).map((f) => ({ code: f.code, libelle: f.libelle, couleur: couleurs[f.code] }));
    const colonnesFamilles = annees.map((a) => ({ cle: a, libelle: String(a), parts: compter(selection.filter((f) => f.properties.annee === a), (f) => f.properties.famille) }));
    $("g-familles-annees-svg").innerHTML = barresEmpilees({ colonnes: colonnesFamilles, categories: catFamilles, rupture: 2018, largeur: 900, hauteur: 260 });
    $("g-familles-annees-legende").innerHTML = legende(catFamilles, "famille");

    /* Modalités par année, en parts. */
    const catModalites = MODALITES.map((m) => ({ code: m, libelle: libelles.modalites[m] || m, couleur: COULEURS_MODALITES[m] }));
    const colonnesModalites = annees.map((a) => ({ cle: a, libelle: String(a), parts: compter(selection.filter((f) => f.properties.annee === a), (f) => f.properties.modalite) }));
    $("g-modalites-svg").innerHTML = barresEmpilees({ colonnes: colonnesModalites, categories: catModalites, parts: true, largeur: 480, hauteur: 210 });
    $("g-modalites-legende").innerHTML = legende(catModalites, "modalite");

    /* Fondements par année, en parts. */
    const catFondements = FONDEMENTS.map((c) => ({ code: c, libelle: libelles.fondements[c] || c, couleur: COULEURS_FONDEMENTS[c] }));
    const colonnesFondements = annees.map((a) => ({ cle: a, libelle: String(a), parts: compter(selection.filter((f) => f.properties.annee === a), (f) => f.properties.fondement) }));
    $("g-fondements-svg").innerHTML = barresEmpilees({ colonnes: colonnesFondements, categories: catFondements, parts: true, largeur: 480, hauteur: 210 });
    $("g-fondements-legende").innerHTML = legende(catFondements, "fondement");

    /* Zones géographiques par année, en parts. */
    const colonnesZones = annees.map((a) => ({ cle: a, libelle: String(a), parts: compter(selection.filter((f) => f.properties.annee === a), (f) => zone(f.properties)) }));
    $("g-zones-svg").innerHTML = barresEmpilees({ colonnes: colonnesZones, categories: ZONES, parts: true, largeur: 900, hauteur: 240 });
    $("g-zones-legende").innerHTML = legende(ZONES);

    /* Organismes les plus contrôlés. */
    const parOrganisme = new Map();
    for (const f of selection) {
      const p = f.properties;
      const o = parOrganisme.get(p._on) || { cle: p._on, libelle: p.organisme, valeur: 0, annees: new Set() };
      o.valeur += 1;
      o.annees.add(p.annee);
      parOrganisme.set(p._on, o);
    }
    const top = [...parOrganisme.values()].filter((o) => o.valeur > 1).sort((a, b) => b.valeur - a.valeur || b.annees.size - a.annees.size).slice(0, 15)
      .map((o) => ({ ...o, libelle: `${majuscules(o.libelle)} (${o.annees.size} an${o.annees.size > 1 ? "s" : ""})` }));
    $("g-organismes-svg").innerHTML = top.length
      ? barresHorizontales({ items: top, total: n, largeur: 900, dataCle: "organisme" })
      : `<p class="discret">Aucun organisme contrôlé plus d'une fois dans la sélection.</p>`;
    void anneesSel;
  }

  return { rendre };
}
