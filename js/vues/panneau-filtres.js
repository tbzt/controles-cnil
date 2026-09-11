/* Panneau des filtres : construit les contrôles, les tient à jour depuis
   l'état, et publie les changements dans le magasin. */

import { compterFacette, suggestions } from "../filtres.js";
import { nombre, majuscules } from "../donnees.js";

const $ = (id) => document.getElementById(id);

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function creerPanneauFiltres({ magasin, features, annees, familles, libelles, departements, regions, communes, couleurs, surRecadrer }) {
  const conteneur = $("filtres");
  const communesParDepartement = {};
  for (const c of communes) (communesParDepartement[c.departement] ||= []).push(c);
  for (const liste of Object.values(communesParDepartement)) liste.sort((a, b) => a.commune.localeCompare(b.commune, "fr"));
  const departementsParRegion = {};
  for (const d of departements) (departementsParRegion[d.region] ||= []).push(d);
  const secteursParFamille = {};
  for (const [code, s] of Object.entries(libelles.secteurs)) (secteursParFamille[s.famille] ||= []).push({ code, ...s });

  conteneur.innerHTML = `
    <div class="filtres__compteur" aria-live="polite">
      <span id="compteur"></span>
      <span class="filtres__actions">
        <button type="button" class="lien" id="recadrer" hidden>Recadrer</button>
        <button type="button" class="lien" id="reinitialiser" hidden>Tout réinitialiser</button>
      </span>
    </div>

    <section class="section" aria-labelledby="t-recherche">
      <label class="visuellement-cache" id="t-recherche" for="recherche">Rechercher un organisme ou une commune</label>
      <div class="recherche">
        <div class="champ-recherche">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="m10.5 10.5 3 3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          <input id="recherche" type="search" placeholder="Organisme ou commune…" autocomplete="off" spellcheck="false"
                 role="combobox" aria-expanded="false" aria-controls="suggestions" aria-autocomplete="list">
        </div>
        <ul class="suggestions" id="suggestions" role="listbox" hidden></ul>
        <div class="jeton" id="jeton-organisme" hidden>
          <span class="jeton__etiquette">Organisme</span>
          <span class="jeton__valeur" id="jeton-organisme-nom"></span>
          <button type="button" class="jeton__retirer" id="jeton-organisme-retirer" aria-label="Retirer le filtre organisme">×</button>
        </div>
      </div>
    </section>

    <section class="section" aria-labelledby="t-periode">
      <div class="section__titre"><h2 id="t-periode">Période</h2><span class="etiquette num" id="periode-libelle"></span></div>
      <div class="double-curseur" role="group" aria-label="Années">
        <div class="double-curseur__piste"><div class="double-curseur__plage" id="plage"></div></div>
        <input type="range" id="annee-min" min="${annees[0]}" max="${annees[annees.length - 1]}" step="1" aria-label="Première année">
        <input type="range" id="annee-max" min="${annees[0]}" max="${annees[annees.length - 1]}" step="1" aria-label="Dernière année">
      </div>
      <div class="double-curseur__bornes num"><span>${annees[0]}</span><span>${annees[annees.length - 1]}</span></div>
    </section>

    <section class="section" aria-labelledby="t-familles">
      <div class="section__titre"><h2 id="t-familles">Secteurs d'activité</h2><span class="etiquette">familles</span></div>
      <ul class="legende legende--interactive" id="legende-familles"></ul>
      <details class="details" id="details-secteurs">
        <summary>Secteurs fins <span class="discret">(nomenclature CNIL)</span></summary>
        <ul class="cases" id="secteurs"></ul>
      </details>
    </section>

    <section class="section" aria-labelledby="t-fondement">
      <h2 id="t-fondement">Fondement juridique</h2>
      <div class="puces" id="fondements" role="group" aria-labelledby="t-fondement"></div>
    </section>

    <section class="section" aria-labelledby="t-modalite">
      <h2 id="t-modalite">Modalité</h2>
      <div class="puces" id="modalites" role="group" aria-labelledby="t-modalite"></div>
    </section>

    <section class="section" aria-labelledby="t-territoire">
      <h2 id="t-territoire">Territoire</h2>
      <div class="selects">
        <label><span class="etiquette">Région</span><select id="region"><option value="">Toutes</option></select></label>
        <label><span class="etiquette">Département</span><select id="departement"><option value="">Tous</option></select></label>
        <label><span class="etiquette">Commune</span><select id="commune"><option value="">Toutes</option></select></label>
      </div>
    </section>`;

  /* ---------------------------------------------------- rendu ------ */

  function rendreFamilles(etat) {
    const comptes = compterFacette(features, etat, "famille");
    /* Toutes les familles restent visibles, même à zéro : on doit pouvoir en
       changer sans d'abord retirer les autres filtres. */
    $("legende-familles").innerHTML = familles.map((f) => {
      const actif = etat.famille.has(f.code);
      return `<li class="legende__item ${comptes[f.code] ? "" : "legende__item--vide"}" style="--couleur:${couleurs[f.code]}">
        <label class="legende__label">
          <input type="checkbox" class="visuellement-cache" data-famille="${f.code}" ${actif ? "checked" : ""}>
          <span class="legende__pastille" aria-hidden="true"></span>
          <span class="legende__nom">${echapper(f.libelle)}</span>
          <span class="legende__n num">${nombre(comptes[f.code] || 0)}</span>
        </label></li>`;
    }).join("");
  }

  function rendreSecteurs(etat) {
    const comptes = compterFacette(features, etat, "secteur");
    const visibles = familles.filter((f) => !etat.famille.size || etat.famille.has(f.code));
    $("secteurs").innerHTML = visibles.flatMap((f) => (secteursParFamille[f.code] || [])
      .filter((s) => comptes[s.code] || etat.secteur.has(s.code))
      .map((s) => `<li><label class="case">
        <input type="checkbox" data-secteur="${s.code}" ${etat.secteur.has(s.code) ? "checked" : ""}>
        <span class="case__nom">${echapper(s.libelle)}</span>
        <span class="case__n num">${nombre(comptes[s.code] || 0)}</span>
      </label></li>`)).join("");
  }

  function rendrePuces(id, cle, lib, etat, ordre) {
    const comptes = compterFacette(features, etat, cle);
    $(id).innerHTML = ordre.filter((v) => comptes[v] || etat[cle].has(v)).map((v) => {
      const actif = etat[cle].has(v);
      return `<button type="button" class="puce" data-${cle}="${v}" aria-pressed="${actif}">
        <span>${echapper(lib[v] || v)}</span><span class="puce__n num">${nombre(comptes[v] || 0)}</span>
      </button>`;
    }).join("");
  }

  function rendreTerritoire(etat) {
    const comptesR = compterFacette(features, etat, "region");
    const comptesD = compterFacette(features, etat, "departement");
    const comptesC = compterFacette(features, etat, "code_insee");
    const optRegion = regions.filter((r) => comptesR[r.code] || etat.region === r.code)
      .map((r) => `<option value="${r.code}" ${etat.region === r.code ? "selected" : ""}>${echapper(r.nom)} (${nombre(comptesR[r.code] || 0)})</option>`);
    $("region").innerHTML = `<option value="">Toutes</option>${optRegion.join("")}`;
    const deps = (etat.region ? departementsParRegion[etat.region] || [] : departements)
      .filter((d) => comptesD[d.code] || etat.departement === d.code);
    $("departement").innerHTML = `<option value="">Tous</option>` + deps
      .map((d) => `<option value="${d.code}" ${etat.departement === d.code ? "selected" : ""}>${d.code} · ${echapper(d.nom)} (${nombre(comptesD[d.code] || 0)})</option>`).join("");
    const coms = etat.departement ? (communesParDepartement[etat.departement] || []).filter((c) => comptesC[c.code_insee] || etat.commune === c.code_insee) : [];
    $("commune").innerHTML = `<option value="">${etat.departement ? "Toutes" : "Choisir un département"}</option>` + coms
      .map((c) => `<option value="${c.code_insee}" ${etat.commune === c.code_insee ? "selected" : ""}>${echapper(c.commune)} (${nombre(comptesC[c.code_insee] || 0)})</option>`).join("");
    $("commune").disabled = !etat.departement;
  }

  function rendrePeriode(etat) {
    const [d, f] = etat.annees;
    $("annee-min").value = d;
    $("annee-max").value = f;
    $("periode-libelle").textContent = d === f ? String(d) : `${d} – ${f}`;
    const min = annees[0], max = annees[annees.length - 1];
    $("plage").style.left = `${((d - min) / (max - min)) * 100}%`;
    $("plage").style.right = `${100 - ((f - min) / (max - min)) * 100}%`;
  }

  function rendre(etat, nbAffiches, nbTotal, vide) {
    $("compteur").innerHTML = vide
      ? `<b class="num">${nombre(nbTotal)}</b> contrôles localisés`
      : `<b class="num">${nombre(nbAffiches)}</b> contrôles sur ${nombre(nbTotal)}`;
    $("reinitialiser").hidden = vide;
    $("recadrer").hidden = vide || nbAffiches === 0;
    if (document.activeElement !== $("recherche") || !etat.q) $("recherche").value = etat.q;
    const jeton = $("jeton-organisme");
    jeton.hidden = !etat.organisme;
    if (etat.organisme) {
      const nom = features.find((f) => f.properties._on === etat.organisme)?.properties.organisme || etat.organisme;
      $("jeton-organisme-nom").textContent = majuscules(nom);
    }
    rendrePeriode(etat);
    rendreFamilles(etat);
    rendreSecteurs(etat);
    rendrePuces("fondements", "fondement", libelles.fondements, etat, ["loi78", "rgpd", "rgpd_ou_directive", "directive_police_justice", "videoprotection"]);
    rendrePuces("modalites", "modalite", libelles.modalites, etat, ["sur_place", "en_ligne", "sur_pieces", "sur_audition", "non_renseignee"]);
    rendreTerritoire(etat);
  }

  /* ---------------------------------------------------- écoute ----- */

  function basculer(cle, valeur) {
    const ens = new Set(magasin.etat[cle]);
    ens.has(valeur) ? ens.delete(valeur) : ens.add(valeur);
    const changements = { [cle]: ens };
    /* Décocher une famille retire ses secteurs fins encore cochés. */
    if (cle === "famille" && !ens.has(valeur)) {
      changements.secteur = new Set([...magasin.etat.secteur].filter((s) => libelles.secteurs[s]?.famille !== valeur));
    }
    magasin.modifier(changements);
  }

  conteneur.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.famille) basculer("famille", t.dataset.famille);
    else if (t.dataset.secteur) basculer("secteur", t.dataset.secteur);
    else if (t.id === "region") magasin.modifier({ region: t.value, departement: "", commune: "" });
    else if (t.id === "departement") magasin.modifier({ departement: t.value, commune: "" });
    else if (t.id === "commune") magasin.modifier({ commune: t.value });
  });
  conteneur.addEventListener("click", (e) => {
    const puce = e.target.closest(".puce");
    if (puce) {
      if (puce.dataset.fondement) basculer("fondement", puce.dataset.fondement);
      if (puce.dataset.modalite) basculer("modalite", puce.dataset.modalite);
    }
    if (e.target.id === "reinitialiser") magasin.reinitialiser();
    if (e.target.id === "recadrer") surRecadrer?.();
  });
  conteneur.addEventListener("input", (e) => {
    const t = e.target;
    if (t.id === "annee-min" || t.id === "annee-max") {
      let d = Number($("annee-min").value), f = Number($("annee-max").value);
      if (d > f) { if (t.id === "annee-min") f = d; else d = f; }
      magasin.modifier({ annees: [d, f] });
    }
  });
  /* ---------------------------------------------------- suggestions */

  const champ = $("recherche");
  const liste = $("suggestions");
  let actif = -1;

  function fermerSuggestions() {
    liste.hidden = true;
    liste.innerHTML = "";
    champ.setAttribute("aria-expanded", "false");
    champ.removeAttribute("aria-activedescendant");
    actif = -1;
  }

  function montrerSuggestions(q) {
    const s = suggestions(features, magasin.etat, q);
    if (!s.organismes.length && !s.communes.length) return fermerSuggestions();
    const items = [
      ...s.organismes.map((o) => ({ type: "organisme", cle: o.cle, libelle: majuscules(o.nom), n: o.n })),
      ...s.communes.map((c) => ({ type: "commune", cle: c.code_insee, departement: c.departement, libelle: `${c.commune} (${c.departement})`, n: c.n })),
    ];
    liste.innerHTML = items.map((it, i) => `<li id="sugg-${i}" role="option" class="suggestion" data-index="${i}"
        data-type="${it.type}" data-cle="${it.cle}" data-departement="${it.departement || ""}" aria-selected="false">
        <span class="suggestion__type">${it.type === "organisme" ? "Organisme" : "Commune"}</span>
        <span class="suggestion__nom">${echapper(it.libelle)}</span>
        <span class="suggestion__n num">${nombre(it.n)}</span>
      </li>`).join("");
    liste.hidden = false;
    champ.setAttribute("aria-expanded", "true");
    actif = -1;
  }

  function choisir(li) {
    if (!li) return;
    if (li.dataset.type === "organisme") {
      magasin.modifier({ organisme: li.dataset.cle, q: "" });
    } else {
      magasin.modifier({ departement: li.dataset.departement, commune: li.dataset.cle, region: "", q: "" });
    }
    fermerSuggestions();
    surRecadrer?.();
  }

  function surligner(delta) {
    const items = liste.querySelectorAll(".suggestion");
    if (!items.length) return;
    actif = (actif + delta + items.length) % items.length;
    items.forEach((el, i) => el.setAttribute("aria-selected", String(i === actif)));
    champ.setAttribute("aria-activedescendant", `sugg-${actif}`);
    items[actif].scrollIntoView({ block: "nearest" });
  }

  let minuterie;
  champ.addEventListener("input", (e) => {
    clearTimeout(minuterie);
    const q = e.target.value.trim();
    minuterie = setTimeout(() => {
      magasin.modifier({ q });
      q.length >= 2 ? montrerSuggestions(q) : fermerSuggestions();
    }, 120);
  });
  champ.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); surligner(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); surligner(-1); }
    else if ((e.key === "Enter" || e.keyCode === 13) && !liste.hidden) {
      e.preventDefault();
      /* Entrée sans surlignage : la première suggestion. */
      choisir(liste.querySelector(`[data-index="${Math.max(actif, 0)}"]`));
    }
    else if (e.key === "Escape") { fermerSuggestions(); if (!e.target.value) return; e.target.value = ""; magasin.modifier({ q: "" }); }
  });
  champ.addEventListener("blur", () => setTimeout(fermerSuggestions, 150));
  liste.addEventListener("mousedown", (e) => { e.preventDefault(); choisir(e.target.closest(".suggestion")); });
  $("jeton-organisme-retirer").addEventListener("click", () => magasin.modifier({ organisme: "" }));

  return { rendre };
}
