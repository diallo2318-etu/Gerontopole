/* Boussole ICOPE : onglets « Couverture du territoire » et « Statistiques ICOPE ».
   Graphiques dessinés en SVG, sans bibliothèque. Palette validée (daltonisme) avec l'outil dataviz. */
"use strict";

(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const _nf = new Intl.NumberFormat("fr-FR");
  const nb = (v) => (v == null ? "–" : _nf.format(v).replace(/[  ]/g, " "));
  const pc = (v) => (v == null ? "–" : `${nb(v)} %`);
  const css = (nom) => getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
  const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  const moisLisible = (m) => { const [a, n] = m.split("-"); return `${MOIS[+n - 1]} ${a}`; };
  const SERIES = { "Auto-évaluation": "--s1", "Avec un aidant": "--s2", "Par un professionnel": "--s3" };
  const PLANS = { A: "--p-a", B: "--p-b", C: "--p-c", aucun: "--p-aucun" };
  const NOM_PLAN = { A: "Plan A", B: "Plan B", C: "Plan C", aucun: "Aucune offre dans les distances" };

  /* ------------------------------------------------------------------ Infobulle commune */
  const bulle = $("#infobulle");
  function montrer(e, html) {
    bulle.innerHTML = html;
    bulle.hidden = false;
    const r = bulle.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    bulle.style.left = `${x}px`;
    bulle.style.top = `${y}px`;
  }
  const cacher = () => { bulle.hidden = true; };

  /* ------------------------------------------------------------------ Navigation */
  const vues = { parcours: $("#vue-parcours"), couverture: $("#vue-couverture"), statistiques: $("#vue-statistiques") };
  const charge = {};
  function afficherVue() {
    const h = location.hash.slice(1);
    const vue = h === "couverture" || h === "statistiques" ? h : "parcours";
    Object.entries(vues).forEach(([k, el]) => { el.hidden = k !== vue; });
    document.querySelectorAll(".onglets a").forEach((a) => {
      a.toggleAttribute("aria-current", a.dataset.vue === vue);
      if (a.dataset.vue === vue) a.setAttribute("aria-current", "page");
    });
    cacher();
    if (vue === "couverture" && !charge.couverture) { charge.couverture = true; initCouverture(); }
    if (vue === "statistiques" && !charge.statistiques) { charge.statistiques = true; initStatistiques(); }
    if (vue === "couverture" && etatC.carte) setTimeout(() => etatC.carte.invalidateSize(), 0);
  }
  document.querySelectorAll(".onglets a").forEach((a) => a.addEventListener("click", (e) => {
    if (a.dataset.vue === "parcours") { e.preventDefault(); history.pushState(null, "", location.pathname); afficherVue(); }
  }));
  addEventListener("hashchange", afficherVue);
  addEventListener("popstate", afficherVue);

  /* ================================================================== COUVERTURE */
  const etatC = { carte: null, couche: null, options: [] };

  async function initCouverture() {
    const v = vues.couverture;
    v.innerHTML = `
      <div class="vue-tete">
        <p class="surtitre">Couverture du territoire</p>
        <h2 id="titre-couverture">Où le parcours trouve-t-il le professionnel idéal, et où faut-il se replier ?</h2>
        <p class="chapo">Chaque point est une commune de Normandie, coloré selon le plan obtenu par une personne qui y habite.
          Uniquement des données publiques (annuaires) : c'est la carte des manques de l'offre.</p>
      </div>
      <div class="filtres carte">
        <label>Étape du parcours <select id="c-etape"></select></label>
        <label id="c-age-champ">Âge de la personne <select id="c-age">
          <option value="62">62 ans</option><option value="68">68 ans</option>
          <option value="72">72 ans</option><option value="80" selected>80 ans</option></select></label>
        <p class="aide" id="c-aide"></p>
      </div>
      <div class="couverture">
        <div class="carte carte-geo grande"><div id="c-carte" role="img" aria-label="Carte des communes selon le plan obtenu"></div>
          <div class="legende" id="c-legende"></div></div>
        <div class="couverture-cote" id="c-cote"><div class="squelette"><div></div></div></div>
      </div>`;
    etatC.options = await (await fetch("/api/couverture/options")).json();
    $("#c-etape").innerHTML = etatC.options.map((o) => `<option value="${esc(o.cle)}">${esc(o.nom)}</option>`).join("");
    $("#c-etape").addEventListener("change", majCouverture);
    $("#c-age").addEventListener("change", majCouverture);
    $("#c-legende").innerHTML = ["A", "B", "C", "aucun"].map((p) =>
      `<span><i class="pt pt-${p}" style="--c: var(${PLANS[p]})"></i>${NOM_PLAN[p]}</span>`).join("");

    etatC.carte = L.map("c-carte", { scrollWheelZoom: false, preferCanvas: true, zoomSnap: 0.25 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom: 14,
    }).addTo(etatC.carte);
    etatC.carte.fitBounds([[48.18, -1.95], [50.07, 1.80]]);
    majCouverture();
  }

  async function majCouverture() {
    const cle = $("#c-etape").value;
    const opt = etatC.options.find((o) => o.cle === cle);
    $("#c-age-champ").hidden = !opt.age;
    const age = opt.age ? $("#c-age").value : 72;
    $("#c-aide").textContent = opt.age
      ? "La levée de doute dépend de l'âge : Mon bilan prévention n'est proposé qu'à 60-65 et 70-75 ans."
      : "";
    $("#c-cote").innerHTML = '<div class="squelette"><div></div></div>';
    const r = await (await fetch(`/api/couverture?etape=${encodeURIComponent(cle)}&age=${age}`)).json();
    dessinerCouverture(r, opt, age);
  }

  function dessinerCouverture(r, opt, age) {
    const carte = etatC.carte;
    if (etatC.couche) etatC.couche.remove();
    const couleurs = Object.fromEntries(Object.entries(PLANS).map(([p, v]) => [p, css(v)]));
    const surface = css("--surface");
    const couche = L.layerGroup();
    // Plan A d'abord (le plus fréquent), les replis par-dessus : ils restent visibles
    const ordre = { A: 0, B: 1, C: 2, aucun: 3 };
    [...r.communes].sort((x, y) => ordre[x[5]] - ordre[y[5]]).forEach(([code, nom, lat, lon, pop, plan]) => {
      const repli = plan !== "A";
      const rayon = Math.max(2.5, Math.min(11, 1.6 + Math.sqrt(pop) / 22)) + (repli ? 1.5 : 0);
      L.circleMarker([lat, lon], {
        radius: rayon, color: repli ? css("--encre") : surface, weight: repli ? 1.4 : 0.6,
        fillColor: couleurs[plan], fillOpacity: repli ? 0.95 : 0.7,
      }).on("mouseover", (e) => montrer(e.originalEvent,
        `<strong>${esc(nom)}</strong>${nb(pop)} habitants<br><span class="ib-plan" style="--c: var(${PLANS[plan]})">${NOM_PLAN[plan]}</span>`))
        .on("mousemove", (e) => montrer(e.originalEvent, bulle.innerHTML))
        .on("mouseout", cacher).addTo(couche);
    });
    couche.addTo(carte);
    etatC.couche = couche;

    const res = Object.fromEntries(r.resume.map((x) => [x.plan, x]));
    const segments = ["A", "B", "C", "aucun"].filter((p) => res[p].population_pct > 0);
    const descr = r.plans.map((p) => `<li><span class="lettre" style="--c: var(${PLANS[p.plan]})">${p.plan}</span><span>${
      p.propositions.map((x) => `${esc(x.valeur.replace("|", " · "))}${x.distance_max_km ? ` <em>(≤ ${x.distance_max_km} km)</em>` : ""}`).join(" ou ")}</span></li>`).join("");
    $("#c-cote").innerHTML = `
      <div class="carte bloc">
        <h3>Part de la population</h3>
        <p class="bloc-aide">${esc(opt.nom)}${opt.age ? `, personne de ${age} ans` : ""}</p>
        <div class="barre-segments" role="img" aria-label="${segments.map((p) => `${NOM_PLAN[p]} ${res[p].population_pct} %`).join(", ")}">
          ${segments.map((p) => `<span style="flex:${res[p].population_pct}; --c: var(${PLANS[p]})" title="${NOM_PLAN[p]} : ${res[p].population_pct} %"></span>`).join("")}
        </div>
        <ul class="resume-plans">${["A", "B", "C", "aucun"].map((p) => `
          <li><i class="pt pt-${p}" style="--c: var(${PLANS[p]})"></i><span>${NOM_PLAN[p]}</span>
          <strong>${pc(res[p].population_pct)}</strong><small>${nb(res[p].communes)} communes</small></li>`).join("")}</ul>
        ${r.conseil_toujours_possible ? '<p class="bloc-aide">Dans tous les cas, un conseil reste possible : en parler au médecin traitant.</p>' : ""}
      </div>
      <div class="carte bloc"><h3>Les plans de cette étape</h3><ul class="plans-liste">${descr}</ul></div>
      <div class="carte bloc">
        <h3>Communes les plus peuplées sans plan A</h3>
        ${r.sans_plan_a.length ? `<table class="tableau"><thead><tr><th>Commune</th><th class="nb">Habitants</th><th>Plan</th><th class="nb">Plan A le plus proche</th></tr></thead><tbody>
          ${r.sans_plan_a.map((c) => `<tr><td>${esc(c.commune)} <small>(${esc(c.departement)})</small></td><td class="nb">${nb(c.population)}</td>
            <td><span class="lettre petite" style="--c: var(${PLANS[c.plan]})">${c.plan === "aucun" ? "–" : c.plan}</span></td>
            <td class="nb">${c.distance_plan_a == null ? "non proposé" : `${nb(c.distance_plan_a)} km`}</td></tr>`).join("")}
          </tbody></table>` : '<p class="bloc-aide">Toutes les communes ont le plan A : rien à signaler.</p>'}
      </div>`;
  }

  /* ================================================================== STATISTIQUES */
  async function initStatistiques() {
    const v = vues.statistiques;
    v.innerHTML = '<div class="squelette"><div></div><div></div></div>';
    const s = await (await fetch("/api/statistiques")).json();
    const c = s.chiffres;
    const ref = new Date(s.reference).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
    v.innerHTML = `
      <div class="vue-tete">
        <p class="surtitre">Statistiques ICOPE · Normandie</p>
        <h2 id="titre-statistiques">Qui fait le test ICOPE, qui le refait, et que deviennent les alertes ?</h2>
        <p class="chapo">Tests jusqu'au ${esc(ref)}. Un test par personne et par jour, sans les essais (moins de 50 ans).
          Chiffres agrégés uniquement ; un pourcentage calculé sur moins de 30 tests n'est pas affiché.</p>
      </div>
      <div class="tuiles">
        ${tuile("Tests analysés", nb(c.tests), `${nb(c.personnes)} personnes`, "--s1")}
        ${tuile("Auto-évaluation depuis 2025", pc(c.auto_2025_pct), "des tests faits seul(e)", "--s1")}
        ${tuile("Refont le test", pc(c.suivi_1an_pct), "après un an ou plus (60 ans et plus)", "--s3")}
        ${tuile("Alertes analysées", nb(c.alertes), `délai médian de prise en charge : ${nb(c.delai_median_jours)} jours`, "--s2")}
        ${tuile("Alertes prises en charge", pc(c.alertes_prises_pct), `dont ${pc(c.alertes_orientees_pct)} orientées vers un professionnel`, "--s2")}
      </div>

      <h3 class="section-titre"><span>Partie 2</span>Les tests et les personnes</h3>
      <div class="carte graphe">
        <div class="graphe-tete"><div><h4>Tests ICOPE par mois, selon qui fait le test</h4>
          <p class="bloc-aide">Depuis janvier 2022. Les pics sont presque uniquement des auto-évaluations.</p></div>
          <div class="legende-graphe">${Object.keys(SERIES).map((k) => `<span><i style="--c: var(${SERIES[k]})"></i>${k}</span>`).join("")}</div></div>
        <div id="g-mois" class="g-svg"></div>
        <details class="donnees"><summary>Voir les données</summary>${tableMois(s.par_mois)}</details>
      </div>
      <div class="grille-2">
        <div class="carte graphe"><h4>Qui fait le test : avant et après 2025</h4>
          <p class="bloc-aide">Part des tests ; âge médian ${nb(s.periodes[0].age_median)} ans avant 2025, ${nb(s.periodes[1].age_median)} ans ensuite.</p>
          ${s.periodes.map((p) => `<div class="ligne-segments"><span class="ls-nom">${esc(p.periode)}<small>${nb(p.tests)} tests</small></span>
            <div class="barre-segments haute">${Object.keys(SERIES).map((k) => p.modalites[k] ? `<span style="flex:${p.modalites[k]}; --c: var(${SERIES[k]})"
              data-ib="<strong>${esc(p.periode)}</strong>${esc(k)} : ${pc(p.modalites[k])}">${p.modalites[k] >= 8 ? `${Math.round(p.modalites[k])} %` : ""}</span>` : "").join("")}</div></div>`).join("")}
          <div class="legende-graphe">${Object.keys(SERIES).map((k) => `<span><i style="--c: var(${SERIES[k]})"></i>${k}</span>`).join("")}</div>
        </div>
        <div class="carte graphe"><h4>Les trois cohortes</h4>
          <p class="bloc-aide">Personnes de 60 ans et plus, selon leur premier test.</p>
          ${barres(s.cohortes.map((x) => ({ nom: x.cohorte, valeur: x.pct, texte: `${pc(x.pct)} · ${nb(x.personnes)} pers.` })), 100, "--s1")}
          <h4 class="h4-suite">Refont le test après un an, selon le premier test</h4>
          <p class="bloc-aide">${nb(s.suivi_eligibles)} personnes dont le premier test date de plus d'un an.</p>
          ${barres(s.suivi.map((x) => ({ nom: x.modalite, valeur: x.suivi_pct, texte: `${pc(x.suivi_pct)} · sur ${nb(x.personnes)}` })), 100, "--s3")}
        </div>
      </div>

      <h3 class="section-titre"><span>Partie 1</span>Le devenir des alertes</h3>
      <div class="grille-2">
        <div class="carte graphe"><h4>Alertes par capacité</h4>
          <p class="bloc-aide">Une alerte qui touche plusieurs capacités compte dans chacune.</p>
          <div class="deux-colonnes"><span></span><span class="col-titre">Alertes</span><span class="col-titre">Prises en charge</span></div>
          ${s.par_domaine.map((d) => `<div class="deux-colonnes" data-cap="${esc(d.domaine)}">
            <span class="dc-nom">${esc(d.nom.replace(/ \(.*\)/, ""))}</span>
            ${barreSimple(d.alertes, Math.max(...s.par_domaine.map((x) => x.alertes)), nb(d.alertes), "--s2", `<strong>${esc(d.nom)}</strong>${nb(d.alertes)} alertes`)}
            ${barreSimple(d.prise_pct, 100, pc(d.prise_pct), "--s3", `<strong>${esc(d.nom)}</strong>Prises en charge : ${pc(d.prise_pct)}<br>Orientées : ${pc(d.orientee_pct)}`)}
          </div>`).join("")}
        </div>
        <div class="carte graphe"><h4>Ce que deviennent les alertes</h4>
          <p class="bloc-aide">Une ligne par alerte ; ${nb(c.alertes)} alertes analysées.</p>
          ${barres(s.issues.map((x) => ({ nom: x.issue.replace(/^\d\.\s*/, ""), valeur: x.pct, texte: `${pc(x.pct)} · ${nb(x.alertes)}` })), 100, "--s2")}
        </div>
      </div>`;
    graphiqueMois($("#g-mois"), s.par_mois);
    v.querySelectorAll("[data-ib]").forEach((el) => {
      el.addEventListener("mousemove", (e) => montrer(e, el.dataset.ib));
      el.addEventListener("mouseleave", cacher);
    });
    addEventListener("resize", () => { if (!vues.statistiques.hidden) graphiqueMois($("#g-mois"), s.par_mois); });
  }

  const tuile = (titre, valeur, sous, couleur) =>
    `<div class="carte tuile" style="--k: var(${couleur})"><dt>${esc(titre)}</dt><dd>${valeur}</dd><p>${esc(sous)}</p></div>`;

  function barreSimple(v, max, texte, couleur, ib) {
    const l = v == null ? 0 : Math.max(0.5, (100 * v) / max);
    return `<span class="bs" data-ib="${esc(ib)}"><span class="bs-fond"><span style="width:${l}%; --c: var(${couleur})"></span></span><em>${texte}</em></span>`;
  }

  function barres(lignes, max, couleur) {
    return `<div class="barres">${lignes.map((l) => `<div class="barre-ligne">
      <span class="bl-nom">${esc(l.nom)}</span>${barreSimple(l.valeur, max, esc(l.texte), couleur, `<strong>${esc(l.nom)}</strong>${esc(l.texte)}`)}</div>`).join("")}</div>`;
  }

  function tableMois(pm) {
    const cles = Object.keys(SERIES);
    return `<div class="table-defile"><table class="tableau"><thead><tr><th>Mois</th>${cles.map((k) => `<th class="nb">${k}</th>`).join("")}<th class="nb">Total</th></tr></thead>
      <tbody>${pm.mois.map((m, i) => `<tr><td>${moisLisible(m)}</td>${cles.map((k) => `<td class="nb">${nb((pm.series[k] || [])[i] || 0)}</td>`).join("")}
      <td class="nb">${nb(cles.reduce((s, k) => s + ((pm.series[k] || [])[i] || 0), 0))}</td></tr>`).join("")}</tbody></table></div>`;
  }

  /* Barres empilées par mois : marques fines, écart de 2 px entre segments, grille discrète, info-bulle au survol */
  function graphiqueMois(el, pm) {
    const cles = Object.keys(SERIES);
    const n = pm.mois.length;
    const totaux = pm.mois.map((_, i) => cles.reduce((s, k) => s + ((pm.series[k] || [])[i] || 0), 0));
    const W = Math.max(520, el.clientWidth), H = 280, m = { g: 44, d: 12, h: 26, b: 34 };
    const iw = W - m.g - m.d, ih = H - m.h - m.b;
    const max = Math.max(...totaux);
    const pas = max > 400 ? 200 : max > 150 ? 100 : 50;
    const ymax = Math.ceil(max / pas) * pas;
    const y = (v) => m.h + ih - (ih * v) / ymax;
    const bw = iw / n, larg = Math.max(2, bw - 2);
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Tests ICOPE par mois et par modalité">`;
    for (let v = 0; v <= ymax; v += pas) {
      svg += `<line x1="${m.g}" x2="${W - m.d}" y1="${y(v)}" y2="${y(v)}" class="grille"/><text x="${m.g - 8}" y="${y(v) + 4}" class="axe" text-anchor="end">${nb(v)}</text>`;
    }
    pm.mois.forEach((mo, i) => {
      const x = m.g + i * bw + (bw - larg) / 2;
      let base = 0;
      const visibles = cles.filter((k) => (pm.series[k] || [])[i] > 0);
      visibles.forEach((k, j) => {
        const v = pm.series[k][i];
        const y0 = y(base), y1 = y(base + v);
        const h = Math.max(0, y0 - y1 - (j < visibles.length - 1 ? 2 : 0));
        svg += j === visibles.length - 1 && h > 3
          ? `<path d="M${x},${y0}v${-(h - 2)}q0,-2 2,-2h${larg - 4}q2,0 2,2v${h - 2}z" fill="var(${SERIES[k]})"/>`
          : `<rect x="${x}" y="${y0 - h}" width="${larg}" height="${h}" fill="var(${SERIES[k]})"/>`;
        base += v;
      });
      svg += `<rect class="cible" x="${m.g + i * bw}" y="${m.h}" width="${bw}" height="${ih}" data-i="${i}"/>`;
      if (mo.endsWith("-01")) svg += `<text x="${x + larg / 2}" y="${H - 12}" class="axe" text-anchor="middle">${mo.slice(0, 4)}</text>`;
    });
    // Étiquettes directes sélectives : les deux plus grands pics
    [...totaux.keys()].sort((a, b) => totaux[b] - totaux[a]).slice(0, 2).forEach((i) => {
      svg += `<text x="${m.g + i * bw + bw / 2}" y="${y(totaux[i]) - 8}" class="etiquette" text-anchor="middle">${moisLisible(pm.mois[i])} : ${nb(totaux[i])}</text>`;
    });
    svg += `<line x1="${m.g}" x2="${W - m.d}" y1="${y(0)}" y2="${y(0)}" class="axe-ligne"/></svg>`;
    el.innerHTML = svg;
    el.querySelectorAll(".cible").forEach((r) => {
      const i = +r.dataset.i;
      r.addEventListener("mousemove", (e) => {
        el.querySelectorAll(".cible.actif").forEach((x) => x.classList.remove("actif"));
        r.classList.add("actif");
        montrer(e, `<strong>${moisLisible(pm.mois[i])} · ${nb(totaux[i])} tests</strong>${cles.map((k) =>
          `<span class="ib-ligne"><i style="--c: var(${SERIES[k]})"></i>${k}<b>${nb((pm.series[k] || [])[i] || 0)}</b></span>`).join("")}`);
      });
      r.addEventListener("mouseleave", () => { r.classList.remove("actif"); cacher(); });
    });
  }

  afficherVue();
})();
