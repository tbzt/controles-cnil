/* Vue Évolution : le temps, avec la granularité honnête de la source (l'année).

   Pas d'animation : dix images animées de données annuelles ne racontent
   rien. À la place, des petits multiples (une carte par année, même
   échelle), la comparaison de deux périodes par choroplèthe divergent, et
   l'évolution des familles en courbes. Les cartes se lisent par département,
   en effectifs ou pour 100 000 habitants. Tout suit les filtres du panneau ;
   la période du panneau sert de période « B » par défaut. */

import { courbes, legende, nombre, pourcentage } from "../graphiques/svg.js";
import { preparerContours, carteDepartements, echelleSequentielle, echelleDivergente } from "../graphiques/carte-svg.js";
import { baseDonnees } from "../donnees.js";

const $ = (id) => document.getElementById(id);

function couleursTokens() {
  const s = getComputedStyle(document.documentElement);
  const lire = (n) => s.getPropertyValue(n).trim();
  return { vide: lire("--surface-2"), plein: lire("--accent"), neg: lire("--alerte"), neutre: lire("--surface-2"), pos: lire("--accent") };
}

function compterParDept(features) {
  const c = {};
  for (const f of features) {
    const d = f.properties.departement;
    if (d) c[d] = (c[d] || 0) + 1;
  }
  return c;
}

export function creerVueEvolution({ features, annees, familles, magasin, obtenirCouleurs, departements }) {
  const conteneur = $("vue-evolution");
  const population = Object.fromEntries(departements.map((d) => [d.code, d.population]));
  const nomsDept = Object.fromEntries(departements.map((d) => [d.code, d.nom]));
  let contours = null;
  let normaliser = false;                     /* effectifs ou pour 100 000 habitants */
  let periodeA = [annees[0], annees[Math.min(4, annees.length - 1)]];   /* 2014-2018 par défaut */
  let dernier = null;

  conteneur.innerHTML = `
    <div class="analyse">
      <header class="analyse__entete">
        <h2>Évolution dans le temps</h2>
        <p class="discret" id="evolution-sous-titre"></p>
      </header>

      <section class="carte-graphique carte-graphique--large" aria-labelledby="e-courbe">
        <div class="carte-graphique__titre"><h3 id="e-courbe">Contrôles par année</h3><span class="discret">la sélection en couleur, l'ensemble des contrôles en gris ; cliquer une année la sélectionne</span></div>
        <div id="e-courbe-svg"></div>
        <div id="e-courbe-legende"></div>
      </section>

      <section class="carte-graphique carte-graphique--large" aria-labelledby="e-familles">
        <div class="carte-graphique__titre"><h3 id="e-familles">Les familles de secteur dans le temps</h3><span class="discret">part de chaque famille dans les contrôles de l'année ; la ligne pointillée marque le changement de nomenclature CNIL de 2018 ; cliquer une famille dans la légende la sélectionne</span></div>
        <div id="e-familles-svg"></div>
        <div id="e-familles-legende"></div>
      </section>

      <section class="carte-graphique carte-graphique--large" aria-labelledby="e-multiples">
        <div class="carte-graphique__titre">
          <h3 id="e-multiples">Où la CNIL contrôle, année par année</h3>
          <span class="discret">une carte par année, même échelle de couleur ; départements de métropole ; cliquer une année la sélectionne</span>
        </div>
        <div class="periodes">
          <div class="commutateur" role="group" aria-label="Lecture">
            <button type="button" data-norm="0" aria-pressed="true">Effectifs</button>
            <button type="button" data-norm="1" aria-pressed="false">Pour 100 000 habitants</button>
          </div>
          <div class="echelle" id="e-echelle"></div>
        </div>
        <div class="multiples" id="e-multiples-cartes"></div>
      </section>

      <section class="carte-graphique carte-graphique--large" aria-labelledby="e-comparaison">
        <div class="carte-graphique__titre">
          <h3 id="e-comparaison">Comparer deux périodes</h3>
          <span class="discret">la période B est celle du panneau ; l'écart est calculé en moyenne annuelle pour comparer des périodes de longueurs différentes</span>
        </div>
        <div class="periodes">
          <div class="periode"><span class="etiquette">Période A</span>
            <div class="periode__selects"><select id="e-a-debut" aria-label="Début de la période A"></select><span>→</span><select id="e-a-fin" aria-label="Fin de la période A"></select></div>
          </div>
          <div class="periode"><span class="etiquette">Période B (panneau)</span>
            <div class="periode__selects"><select id="e-b-debut" aria-label="Début de la période B"></select><span>→</span><select id="e-b-fin" aria-label="Fin de la période B"></select></div>
          </div>
        </div>
        <div class="comparaison" id="e-comparaison-cartes"></div>
        <ul class="ecarts" id="e-ecarts"></ul>
      </section>
      <p class="discret analyse__note">Les cartes par département ne couvrent que la métropole ; les contrôles outre-mer et hors de France restent comptés dans les courbes. Un contrôle est rattaché au département de l'organisme contrôlé.</p>
    </div>`;

  /* Sélecteurs de périodes. */
  const options = (sel) => { sel.innerHTML = annees.map((a) => `<option value="${a}">${a}</option>`).join(""); };
  for (const id of ["e-a-debut", "e-a-fin", "e-b-debut", "e-b-fin"]) options($(id));

  conteneur.addEventListener("change", (e) => {
    const id = e.target.id;
    if (id === "e-a-debut" || id === "e-a-fin") {
      let d = Number($("e-a-debut").value), f = Number($("e-a-fin").value);
      if (d > f) { if (id === "e-a-debut") f = d; else d = f; }
      periodeA = [d, f];
      if (dernier) rendre(...dernier);
    } else if (id === "e-b-debut" || id === "e-b-fin") {
      let d = Number($("e-b-debut").value), f = Number($("e-b-fin").value);
      if (d > f) { if (id === "e-b-debut") f = d; else d = f; }
      magasin.modifier({ annees: [d, f] });
    }
  });
  conteneur.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("multiple")) {
      e.preventDefault();
      e.target.click();
    }
  });
  conteneur.addEventListener("click", (e) => {
    const norm = e.target.closest("[data-norm]");
    if (norm) { normaliser = norm.dataset.norm === "1"; if (dernier) rendre(...dernier); return; }
    const el = e.target.closest(".graphique__cliquable, .multiple");
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
    } else if (el.dataset.departement) {
      magasin.modifier({ departement: el.dataset.departement, region: "", commune: "" });
    }
  });

  async function chargerContours() {
    if (contours) return contours;
    const g = await (await fetch(baseDonnees() + "referentiels-source/contours-departements.geojson")).json();
    contours = preparerContours(g);
    return contours;
  }

  const valeur = (n, code) => (normaliser ? (population[code] ? (n / population[code]) * 100000 : 0) : n);
  const formater = (v) => (normaliser ? `${v.toFixed(1).replace(".", ",")} pour 100 000 hab.` : `${nombre(v)} contrôle${v > 1 ? "s" : ""}`);

  /* `selectionSansPeriode` : la sélection sous tous les filtres sauf la
     période, pour que courbes et petits multiples montrent toutes les années. */
  function rendre(selectionSansPeriode, etat, vide) {
    dernier = [selectionSansPeriode, etat, vide];
    const couleurs = obtenirCouleurs();
    const tok = couleursTokens();
    $("evolution-sous-titre").textContent = vide
      ? "Tous les contrôles localisés, 2014 à 2023."
      : `Sélection courante hors période : ${nombre(selectionSansPeriode.length)} contrôles sur ${nombre(features.length)} ; la période du panneau (${etat.annees[0]}–${etat.annees[1]}) sert de période B.`;
    for (const b of conteneur.querySelectorAll("[data-norm]")) b.setAttribute("aria-pressed", String((b.dataset.norm === "1") === normaliser));

    /* Courbe annuelle, sélection contre ensemble. */
    const parAnnee = {}, totalAnnee = {};
    for (const f of features) totalAnnee[f.properties.annee] = (totalAnnee[f.properties.annee] || 0) + 1;
    for (const f of selectionSansPeriode) parAnnee[f.properties.annee] = (parAnnee[f.properties.annee] || 0) + 1;
    const seriesCourbe = [];
    if (!vide) seriesCourbe.push({ cle: "total", libelle: "Tous les contrôles", couleur: tok.plein === "" ? "#999" : "var(--encre-3)", valeurs: annees.map((a) => totalAnnee[a] || 0) });
    seriesCourbe.push({ cle: "selection", libelle: vide ? "Tous les contrôles" : "Sélection", couleur: "var(--accent)", aire: true, valeurs: annees.map((a) => parAnnee[a] || 0) });
    $("e-courbe-svg").innerHTML = courbes({ series: seriesCourbe, annees, hauteur: 240 });
    $("e-courbe-legende").innerHTML = "";

    /* Familles dans le temps, en parts de l'année. */
    const parAnneeFamille = {};
    for (const f of selectionSansPeriode) {
      const p = f.properties;
      (parAnneeFamille[p.annee] ||= {})[p.famille] = ((parAnneeFamille[p.annee] ||= {})[p.famille] || 0) + 1;
    }
    const total = {};
    for (const f of familles) total[f.code] = annees.reduce((s, a) => s + (parAnneeFamille[a]?.[f.code] || 0), 0);
    const principales = familles.filter((f) => total[f.code]).sort((a, b) => total[b.code] - total[a.code]).slice(0, 8);
    const seriesFamilles = principales.map((f) => ({
      cle: f.code, libelle: f.libelle, couleur: couleurs[f.code],
      valeurs: annees.map((a) => (parAnnee[a] ? (parAnneeFamille[a]?.[f.code] || 0) / parAnnee[a] : 0)),
    }));
    $("e-familles-svg").innerHTML = courbes({ series: seriesFamilles, annees, hauteur: 260, rupture: 2018, parts: true });
    $("e-familles-legende").innerHTML = legende(principales.map((f) => ({ code: f.code, libelle: f.libelle, couleur: couleurs[f.code] })), "famille");

    chargerContours().then((ct) => {
      /* Petits multiples : une carte par année, échelle commune. */
      const parAnneeDept = {};
      for (const a of annees) parAnneeDept[a] = {};
      for (const f of selectionSansPeriode) {
        const p = f.properties;
        if (p.departement) parAnneeDept[p.annee][p.departement] = (parAnneeDept[p.annee][p.departement] || 0) + 1;
      }
      let max = 0;
      const valeursAnnee = {};
      for (const a of annees) {
        valeursAnnee[a] = Object.fromEntries(Object.entries(parAnneeDept[a]).map(([c, n]) => [c, valeur(n, c)]));
        max = Math.max(max, ...Object.values(valeursAnnee[a]));
      }
      const echelle = echelleSequentielle(max, tok.vide, tok.plein);
      $("e-echelle").innerHTML = `<span>0</span><span class="echelle__barre" style="background:linear-gradient(90deg,${tok.vide},${tok.plein})"></span><span>${normaliser ? max.toFixed(1).replace(".", ",") + " / 100 000 hab." : nombre(max)}</span>`;
      $("e-multiples-cartes").innerHTML = annees.map((a) => {
        const actif = etat.annees[0] === a && etat.annees[1] === a;
        return `<div class="multiple ${actif ? "multiple--actif" : ""}" data-annee="${a}" role="button" tabindex="0" aria-label="Année ${a}, ${nombre(parAnnee[a] || 0)} contrôles">
          <div class="multiple__titre"><span>${a}</span><b>${nombre(parAnnee[a] || 0)}</b></div>
          ${carteDepartements({ contours: ct, valeurs: valeursAnnee[a], couleur: echelle, formater, titre: `Contrôles en ${a}` })}
        </div>`;
      }).join("");

      /* Comparaison de périodes. */
      const [a0, a1] = periodeA;
      const [b0, b1] = etat.annees;
      $("e-a-debut").value = a0; $("e-a-fin").value = a1; $("e-b-debut").value = b0; $("e-b-fin").value = b1;
      const somme = (deb, fin) => {
        const c = {};
        for (const f of selectionSansPeriode) {
          const p = f.properties;
          if (p.annee >= deb && p.annee <= fin && p.departement) c[p.departement] = (c[p.departement] || 0) + 1;
        }
        return c;
      };
      const nA = a1 - a0 + 1, nB = b1 - b0 + 1;
      const brutA = somme(a0, a1), brutB = somme(b0, b1);
      const moyA = Object.fromEntries(Object.entries(brutA).map(([c, n]) => [c, valeur(n, c) / nA]));
      const moyB = Object.fromEntries(Object.entries(brutB).map(([c, n]) => [c, valeur(n, c) / nB]));
      const codes = new Set([...Object.keys(moyA), ...Object.keys(moyB)]);
      const delta = {};
      for (const c of codes) delta[c] = (moyB[c] || 0) - (moyA[c] || 0);
      const maxMoy = Math.max(1e-9, ...Object.values(moyA), ...Object.values(moyB));
      const ampl = Math.max(1e-9, ...Object.values(delta).map(Math.abs));
      const echSeq = echelleSequentielle(maxMoy, tok.vide, tok.plein);
      const echDiv = echelleDivergente(ampl, tok.neg, tok.neutre, tok.pos);
      const fmtMoy = (v) => (normaliser ? `${v.toFixed(1).replace(".", ",")} / 100 000 hab. par an` : `${v.toFixed(1).replace(".", ",")} par an`);
      const fmtDelta = (v) => `${v > 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")} par an`;
      const totalA = Object.values(brutA).reduce((s, n) => s + n, 0), totalB = Object.values(brutB).reduce((s, n) => s + n, 0);
      $("e-comparaison-cartes").innerHTML = `
        <div class="comparaison__carte"><div class="comparaison__titre"><span>A · ${a0}–${a1}</span><b>${nombre(totalA)}</b></div>${carteDepartements({ contours: ct, valeurs: moyA, couleur: echSeq, formater: fmtMoy, titre: `Période A` })}</div>
        <div class="comparaison__carte"><div class="comparaison__titre"><span>B · ${b0}–${b1}</span><b>${nombre(totalB)}</b></div>${carteDepartements({ contours: ct, valeurs: moyB, couleur: echSeq, formater: fmtMoy, titre: `Période B` })}</div>
        <div class="comparaison__carte"><div class="comparaison__titre"><span>Écart B − A, moyenne annuelle</span><span class="echelle"><span class="echelle__barre" style="flex-basis:80px;background:linear-gradient(90deg,${tok.neg},${tok.neutre},${tok.pos})"></span></span></div>${carteDepartements({ contours: ct, valeurs: delta, couleur: echDiv, formater: fmtDelta, titre: `Écart entre les périodes` })}</div>`;
      const tries = Object.entries(delta).filter(([c]) => nomsDept[c]).sort((x, y) => y[1] - x[1]);
      const hausses = tries.filter(([, v]) => v > 0).slice(0, 5);
      const baisses = tries.filter(([, v]) => v < 0).slice(-5).reverse();
      $("e-ecarts").innerHTML = [...hausses, ...baisses].map(([c, v]) => `<li><span>${nomsDept[c]} <span class="discret">(${c})</span></span><span class="ecarts__delta ${v > 0 ? "ecarts__delta--plus" : "ecarts__delta--moins"}">${fmtDelta(v)}</span></li>`).join("")
        || `<li class="discret">Aucun écart entre les deux périodes dans la sélection.</li>`;
    });
    void pourcentage;
  }

  return { rendre };
}
