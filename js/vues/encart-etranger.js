/* Encart « Hors de France » : les organismes étrangers de la sélection,
   listés par pays. Sur la carte ils sont placés au centroïde de leur pays,
   précision « pays » ; la liste est plus utile qu'un point perdu. */

import { nombre, majuscules } from "../donnees.js";

const $ = (id) => document.getElementById(id);

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function creerEncartEtranger(libelles) {
  const section = $("section-etranger");
  const liste = $("liste-etranger");
  const titre = $("nb-etranger");
  return {
    rendre(selection) {
      const parPays = new Map();
      for (const f of selection) {
        const p = f.properties;
        if (p.pays === "FR") continue;
        const e = parPays.get(p.pays) || { pays: p.pays, n: 0, organismes: [] };
        e.n += 1;
        e.organismes.push({ organisme: p.organisme, annee: p.annee, commune: p.commune });
        parPays.set(p.pays, e);
      }
      const total = [...parPays.values()].reduce((s, e) => s + e.n, 0);
      section.hidden = total === 0;
      if (!total) return;
      titre.textContent = nombre(total);
      liste.innerHTML = [...parPays.values()].sort((a, b) => b.n - a.n).map((e) => `
        <details class="details etranger">
          <summary><span class="etranger__pays">${echapper(libelles.pays[e.pays] || e.pays)}</span><span class="etranger__n num">${nombre(e.n)}</span></summary>
          <ul class="etranger__liste">${e.organismes.sort((a, b) => b.annee - a.annee || a.organisme.localeCompare(b.organisme, "fr"))
            .map((o) => `<li><span class="num">${o.annee}</span> · ${echapper(majuscules(o.organisme))}${o.commune ? ` <span class="discret">(${echapper(o.commune)})</span>` : ""}</li>`).join("")}</ul>
        </details>`).join("");
    },
  };
}
