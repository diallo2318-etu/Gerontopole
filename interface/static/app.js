/* Boussole ICOPE : logique de la page (sans bibliothèque, à part Leaflet pour la carte). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const _nf = new Intl.NumberFormat("fr-FR");
const nf = { format: (v) => _nf.format(v).replace(/[\u202f\u00a0]/g, "\u00a0") };
const km = (d) => (d == null ? "–" : d < 0.5 ? "sur place" : `${nf.format(Math.round(d * 10) / 10)} km`);

const ICONES = {
  vision: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  audition: '<path d="M6 8.5a6 6 0 1 1 12 0c0 5.5-5.5 5.8-5.5 9.5a3 3 0 0 1-6 0"/><path d="M14.5 9a2.5 2.5 0 0 0-5 0"/>',
  cognition: '<path d="M9.5 4A3 3 0 0 0 6.6 6.2 3 3 0 0 0 4.5 11a3 3 0 0 0 1.4 4.9A3 3 0 0 0 9.5 20 2.5 2.5 0 0 0 12 17.5v-11A2.5 2.5 0 0 0 9.5 4z"/><path d="M14.5 4a3 3 0 0 1 2.9 2.2 3 3 0 0 1 2.1 4.8 3 3 0 0 1-1.4 4.9A3 3 0 0 1 14.5 20 2.5 2.5 0 0 1 12 17.5"/>',
  mobilite: '<circle cx="13" cy="4.5" r="2"/><path d="M9 21l2.5-6.5L14 17v4"/><path d="M7 12.5l2.5-4 3.5 1 2.5 3.5 2.5 1"/>',
  nutrition: '<path d="M12 7.5c-2-2-7-1.6-7 3.5 0 4.6 3.4 9.5 7 9.5s7-4.9 7-9.5c0-5.1-5-5.5-7-3.5z"/><path d="M12 7.5c0-2.2 1.1-3.8 3.2-4.5"/>',
  psychologie: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 2.8C19.5 15.4 12 20 12 20z"/>',
  incontinence: '<path d="M12 3.5s6 6.4 6 10.8a6 6 0 0 1-12 0C6 9.9 12 3.5 12 3.5z"/>',
  social: '<circle cx="9" cy="8" r="3"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><circle cx="17" cy="9.5" r="2.4"/><path d="M16.5 14.2A4.6 4.6 0 0 1 21 19"/>',
  aidant: '<path d="M12 9s-2.6-3-4.9-1.3C5 9.3 6.3 12.6 12 16c5.7-3.4 7-6.7 4.9-8.3C14.6 6 12 9 12 9z"/><path d="M3 21h4.5l3-2H17"/>',
};
const icone = (code, cls = "") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONES[code] || ""}</svg>`;
const SVG_TEL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h3.5l1.7 4.3-2.2 1.4a11 11 0 0 0 6.3 6.3l1.4-2.2L20 15.5V19a1.5 1.5 0 0 1-1.6 1.5A16.5 16.5 0 0 1 3.5 5.6 1.5 1.5 0 0 1 5 4z"/></svg>';
const SVG_CONSEIL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5h16v10H9l-5 4z"/><path d="M8.5 10.5h7"/></svg>';
const SVG_CHEVRON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';

const etat = { meta: null, commune: null, alertes: new Set(), carte: null, couches: {}, dernier: null };

/* ------------------------------------------------------------------ Démarrage */
async function demarrer() {
  try {
    etat.meta = await (await fetch("/api/meta")).json();
  } catch {
    montrerErreur("Le serveur ne répond pas. Lancez « python3 interface/serveur.py ».");
    return;
  }
  const c = etat.meta.chiffres;
  $("#chiffres").innerHTML = [
    ["Professionnels de santé", c.professionnels], ["Établissements", c.structures],
    ["Actions de prévention", c.actions], ["Communes", c.communes],
  ].map(([t, v]) => `<div><dt>${t}</dt><dd>${nf.format(v)}</dd></div>`).join("");

  $("#alertes").innerHTML = etat.meta.capacites.map((cap) => `
    <button type="button" class="alerte" data-code="${cap.code}" aria-pressed="false"
            title="${cap.a_parcours ? "" : "Parcours pas encore écrit (bloc 3) : métiers du référentiel"}">
      ${icone(cap.code)}<span>${esc(cap.nom.replace(/ \(.*\)/, ""))}</span>
      ${cap.a_parcours ? "" : '<i class="a-venir" aria-label="parcours à venir"></i>'}
    </button>`).join("");
  $("#alertes").addEventListener("click", (e) => {
    const b = e.target.closest(".alerte");
    if (!b) return;
    basculerAlerte(b.dataset.code, b.getAttribute("aria-pressed") !== "true");
  });

  $("#profils").innerHTML = etat.meta.profils.map((p, i) => `
    <button type="button" class="profil" data-i="${i}">
      <strong>${esc(p.titre)}</strong><small>${esc(p.pourquoi)}</small><span class="det">${esc(p.detail)}</span>
    </button>`).join("");
  $("#profils").addEventListener("click", (e) => {
    const b = e.target.closest(".profil");
    if (b) chargerProfil(etat.meta.profils[+b.dataset.i]);
  });

  brancherCommune();
  brancherAge();
  $("#formulaire").addEventListener("submit", (e) => { e.preventDefault(); lancer(); });
  majAideAge();
  depuisAdresse();
}

function basculerAlerte(code, actif) {
  const b = $(`.alerte[data-code="${code}"]`);
  if (!b) return;
  b.setAttribute("aria-pressed", actif ? "true" : "false");
  actif ? etat.alertes.add(code) : etat.alertes.delete(code);
  const n = etat.alertes.size;
  $("#compteur").textContent = n ? `${n} sélectionnée${n > 1 ? "s" : ""}` : "";
}

/* ------------------------------------------------------------------ Commune (suggestions) */
function brancherCommune() {
  const champ = $("#commune"), liste = $("#suggestions");
  let minuteur, actif = -1, resultats = [];

  const fermer = () => { liste.hidden = true; champ.setAttribute("aria-expanded", "false"); actif = -1; };
  const afficher = () => {
    liste.innerHTML = resultats.length
      ? resultats.map((r, i) => `<li role="option" id="sugg-${i}" data-i="${i}" aria-selected="${i === actif}">
           <span>${esc(r.nom)}</span><span class="cp">${esc(r.codes_postaux)} · ${esc(r.departement)}</span></li>`).join("")
      : '<li class="vide">Aucune commune de Normandie trouvée</li>';
    liste.hidden = false;
    champ.setAttribute("aria-expanded", "true");
    champ.setAttribute("aria-activedescendant", actif >= 0 ? `sugg-${actif}` : "");
  };

  champ.addEventListener("input", () => {
    if (etat.commune) choisirCommune(null, false);
    clearTimeout(minuteur);
    const q = champ.value.trim();
    if (q.length < 2) { fermer(); return; }
    minuteur = setTimeout(async () => {
      try {
        resultats = await (await fetch(`/api/communes?q=${encodeURIComponent(q)}`)).json();
      } catch { resultats = []; }
      actif = resultats.length ? 0 : -1;
      afficher();
    }, 140);
  });
  champ.addEventListener("keydown", (e) => {
    if (liste.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      actif = (actif + (e.key === "ArrowDown" ? 1 : -1) + resultats.length) % resultats.length;
      afficher();
    } else if (e.key === "Enter" && actif >= 0) {
      e.preventDefault();
      choisirCommune(resultats[actif]);
      fermer();
    } else if (e.key === "Escape") fermer();
  });
  liste.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-i]");
    if (!li) return;
    e.preventDefault();
    choisirCommune(resultats[+li.dataset.i]);
    fermer();
  });
  champ.addEventListener("blur", () => setTimeout(fermer, 120));
  $("#effacer").addEventListener("click", () => { choisirCommune(null); champ.value = ""; champ.focus(); });
}

function choisirCommune(c, ecrire = true) {
  etat.commune = c;
  const champ = $("#commune");
  champ.classList.toggle("choisie", !!c);
  $("#effacer").hidden = !c;
  if (c && ecrire) champ.value = `${c.nom} (${c.codes_postaux.split(", ")[0]})`;
  $("#valider").disabled = !c;
  $("#aide-commune").textContent = c
    ? `Code INSEE ${c.code_insee} · département ${c.departement}`
    : "Ex. « Saint-Lô », « 14400 » (plusieurs communes) ou un code INSEE.";
  masquerErreur();
}

/* ------------------------------------------------------------------ Âge */
function brancherAge() {
  const champ = $("#age");
  champ.addEventListener("input", majAideAge);
  document.querySelectorAll(".pas").forEach((b) => b.addEventListener("click", () => {
    champ.value = Math.min(110, Math.max(18, (+champ.value || 70) + +b.dataset.pas));
    majAideAge();
  }));
}

function majAideAge() {
  const a = +$("#age").value, aide = $("#aide-age");
  let texte, couleur;
  if (!a || a < 18 || a > 110) { texte = "Âge entre 18 et 110 ans."; couleur = "var(--plan-c)"; }
  else if (a < 60) { texte = "Moins de 60 ans : un conseil seulement, pas d'orientation (décision du Gérontopôle)."; couleur = "var(--plan-b)"; }
  else if ((a >= 60 && a <= 65) || (a >= 70 && a <= 75)) { texte = "Mon bilan prévention est pris en charge à cet âge : c'est le plan A de la levée de doute."; couleur = "var(--plan-a)"; }
  else { texte = "Mon bilan prévention n'est pas pris en charge à cet âge : la levée de doute passe par un autre lieu."; couleur = "var(--plan-b)"; }
  aide.textContent = texte;
  aide.style.setProperty("--point", couleur);
}

/* ------------------------------------------------------------------ Profils et adresse partageable */
async function chargerProfil(p) {
  const [c] = await (await fetch(`/api/communes?q=${p.code_insee}`)).json();
  if (!c) return;
  choisirCommune(c);
  $("#age").value = p.age;
  majAideAge();
  etat.alertes.forEach((code) => basculerAlerte(code, false));
  p.alertes.forEach((code) => basculerAlerte(code, true));
  lancer();
}

async function depuisAdresse() {
  // #50502/84/cognition,mobilite : un parcours se partage ou se rouvre avec son adresse
  const [code, age, alertes] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (!/^\d{5}$|^2[AB]\d{3}$/.test(code || "")) return;
  await chargerProfil({ code_insee: code, age: +age || 70, alertes: (alertes || "").split(",").filter(Boolean) });
}

/* ------------------------------------------------------------------ Lancer le calcul */
async function lancer() {
  if (!etat.commune) { montrerErreur("Choisissez d'abord une commune dans la liste."); return; }
  const age = +$("#age").value;
  if (!(age >= 18 && age <= 110)) { montrerErreur("L'âge doit être compris entre 18 et 110 ans."); return; }
  masquerErreur();
  const demande = { code_insee: etat.commune.code_insee, age, alertes: [...etat.alertes] };
  history.replaceState(null, "", `#${demande.code_insee}/${age}/${demande.alertes.join(",")}`);

  const zone = $("#resultats");
  detruireCarte();
  zone.setAttribute("aria-busy", "true");
  zone.innerHTML = '<div class="squelette" aria-label="Calcul en cours"><div></div><div></div><div></div></div>';
  const bouton = $("#valider");
  bouton.disabled = true;
  try {
    const rep = await fetch("/api/parcours", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(demande) });
    if (!rep.ok) throw new Error((await rep.json()).detail || rep.statusText);
    etat.dernier = await rep.json();
    afficherResultat(etat.dernier);
    if (window.matchMedia("(max-width: 900px)").matches) zone.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    zone.innerHTML = `<div class="carte accueil"><p class="surtitre">Erreur</p><h2>Le parcours n'a pas pu être calculé.</h2><p class="accueil-pied">${esc(err.message)}</p></div>`;
  } finally {
    zone.setAttribute("aria-busy", "false");
    bouton.disabled = !etat.commune;
  }
}

const montrerErreur = (m) => { const e = $("#erreur"); e.textContent = m; e.hidden = false; };
const masquerErreur = () => { $("#erreur").hidden = true; };

/* ------------------------------------------------------------------ Affichage */
const PLAN_VAR = { A: "a", B: "b", C: "c" };
const couleurs = (plan) => plan && PLAN_VAR[plan]
  ? `--c: var(--plan-${PLAN_VAR[plan]}); --c-doux: var(--plan-${PLAN_VAR[plan]}-doux);`
  : "--c: var(--neutre); --c-doux: var(--neutre-doux);";
const couleurCalculee = (plan) => getComputedStyle(document.documentElement)
  .getPropertyValue(plan && PLAN_VAR[plan] ? `--plan-${PLAN_VAR[plan]}` : "--neutre").trim();

function metier(valeur) {
  const [a, b] = String(valeur).split("|");
  return b ? `${a} · ${b}` : a;
}
function telephone(t) {
  const d = String(t || "").replace(/\D/g, "");
  if (d.length !== 10) return t ? esc(t) : "";
  return d.replace(/(\d{2})(?=\d)/g, "$1 ");
}

function enTete(e, numero, age) {
  const cap = e.domaine_nom ? e.domaine_nom.replace(/ \(.*\)/, "") : "";
  switch (e.type) {
    case "levee_de_doute": return { sur: `Étape ${numero} · Levée de doute`, titre: "Qui peut vérifier l'alerte ?" };
    case "orientation": return { sur: `Étape ${numero} · ${cap}`, titre: "Si l'alerte est confirmée : vers qui orienter ?", icone: e.domaine };
    case "etape2": return { sur: `Étape ${numero} · Step 2`, titre: "Qui peut faire l'évaluation approfondie ?" };
    case "moins_60": return { sur: `${age} ans · hors cible ICOPE`, titre: "Un conseil, sans orientation" };
    default: return { sur: `Étape ${numero}`, titre: e.titre };
  }
}

function raisonRepli(e, age) {
  if (!e.plan_retenu || e.plan_retenu === "A" || !e.a_parcours) return "";
  // Chaque plan essayé avant celui retenu, avec la raison pour laquelle il a été écarté
  const parties = [];
  if (e.plans[0] && e.plans[0].plan !== "A") parties.push(`plan A non proposé à ${age} ans`);
  for (const p of e.plans) {
    if (p.retenu) break;
    const raisons = p.propositions.map(raison).filter(Boolean);
    parties.push(`plan ${p.plan} écarté (${raisons.length ? raisons.join(", ") : "indisponible"})`);
  }
  const texte = parties.join(" ; ");
  return `<p class="repli"><strong>Plan ${e.plan_retenu} :</strong> ${esc(texte.charAt(0).toUpperCase() + texte.slice(1))}.</p>`;
}
function raison(pr) {
  const qui = metier(pr.valeur).replace(/^\p{Lu}(?!\p{Lu})/u, (c) => c.toLowerCase());
  if (pr.statut === "trop_loin") return `${qui} : le plus proche à ${km(pr.plus_proche_km)} (limite ${pr.distance_max_km} km)`;
  if (pr.statut === "absent") return `${qui} : aucun dans les données`;
  if (pr.statut === "a_obtenir") return `${qui} : liste à obtenir`;
  return "";
}

function listeOffres(pr, cleEtape) {
  return `<ul class="offres">${pr.offres.map((o, i) => {
    const cle = `${cleEtape}-${i}-${pr.valeur}`;
    etat.couches.offres.push({ ...o, cle, plan: pr._plan, metier: metier(pr.valeur) });
    const tel = telephone(o.telephone);
    return `<li class="offre" data-cle="${esc(cle)}">
      <span class="offre-nom">${esc(o.nom)}</span>
      <span class="offre-metier">${esc(o.detail || metier(pr.valeur))}</span>
      <span class="offre-lieu">${esc([o.adresse, [o.code_postal, o.commune].filter(Boolean).join(" ")].filter(Boolean).join(", "))}</span>
      <span class="offre-droite"><span class="distance">${km(o.distance_km)}</span>
        ${tel ? `<a class="tel" href="tel:${esc(String(o.telephone).replace(/\s/g, ""))}">${SVG_TEL}${tel}</a>` : ""}</span>
    </li>`;
  }).join("")}</ul>`;
}

function corpsPlan(plan, cleEtape, multiMetiers) {
  return plan.propositions.map((pr, j) => {
    pr._plan = plan.plan;
    if (pr.statut === "conseil") {
      return `<div class="conseil">${SVG_CONSEIL}<div><strong>${esc(pr.valeur)}</strong>${pr.remarque ? `<p>${esc(pr.remarque)}</p>` : ""}</div></div>`;
    }
    if (pr.statut === "a_obtenir") return `<p class="a-obtenir">${esc(metier(pr.valeur))} : liste pas encore disponible, à proposer dès qu'elle sera obtenue.</p>`;
    if (!pr.offres.length) return "";
    const titre = multiMetiers ? `<p class="groupe-metier">${esc(metier(pr.valeur))}</p>` : "";
    return titre + listeOffres(pr, `${cleEtape}-${j}`) + (pr.remarque ? `<p class="remarque">${esc(pr.remarque)}</p>` : "");
  }).join("");
}

function echelle(e) {
  let vu = false;
  return `<ol class="echelle">${e.plans.map((p) => {
    const classe = p.retenu ? "retenu" : vu ? "ignore" : "";
    if (p.retenu) vu = true;
    const items = p.propositions.map((pr) => {
      let badge, texte;
      if (vu && !p.retenu) { badge = '<span class="etat">non nécessaire</span>'; texte = metier(pr.valeur); }
      else if (pr.statut === "trouve") { badge = '<span class="etat ok">trouvé</span>'; texte = `${metier(pr.valeur)}, le plus proche ${km(pr.offres[0]?.distance_km)}${pr.distance_max_km ? ` (limite ${pr.distance_max_km} km)` : ""}`; }
      else if (pr.statut === "trop_loin") { badge = '<span class="etat loin">trop loin</span>'; texte = `${metier(pr.valeur)} : le plus proche à ${km(pr.plus_proche_km)}, limite ${pr.distance_max_km} km`; }
      else if (pr.statut === "a_obtenir") { badge = '<span class="etat attente">à obtenir</span>'; texte = `${metier(pr.valeur)} : liste pas encore disponible`; }
      else if (pr.statut === "conseil") { badge = '<span class="etat ok">conseil</span>'; texte = pr.valeur; }
      else { badge = '<span class="etat">absent</span>'; texte = `${metier(pr.valeur)} : aucun dans les données`; }
      return `<li>${badge}<span>${esc(texte)}</span></li>`;
    }).join("");
    return `<li class="echelon ${classe}" style="${couleurs(p.plan)}"><span class="echelon-lettre">${esc(p.plan)}</span><ul>${items}</ul></li>`;
  }).join("")}</ol>`;
}

function carteEtape(e, i, numero, age) {
  const t = enTete(e, numero, age);
  const cle = `e${i}`;
  const retenu = e.plans.find((p) => p.retenu);
  let badge, corps;
  if (!e.a_parcours) {
    badge = '<span class="badge-plan" style="--c: var(--plan-b); --c-doux: var(--plan-b-doux)">Parcours à venir</span>';
    corps = corpsPlan(e.plans[0], cle, true);
  } else if (retenu) {
    badge = `<span class="badge-plan">Plan ${esc(e.plan_retenu)}</span>`;
    const metiers = retenu.propositions.filter((p) => p.offres.length).length > 1;
    corps = corpsPlan(retenu, cle, metiers);
  } else {
    badge = '<span class="badge-plan">Aucun plan</span>';
    corps = '<p class="repli">Aucune offre dans les distances prévues : en parler au médecin traitant.</p>';
  }
  const rayon = Math.max(0, ...(retenu?.propositions || []).map((p) => p.distance_max_km || 0));
  const pourquoi = e.a_parcours && e.plans.length > 1
    ? `<details class="pourquoi"><summary>${SVG_CHEVRON}Pourquoi le plan ${esc(e.plan_retenu || "–")} ?</summary>${echelle(e)}</details>` : "";
  return `<li class="etape" style="${couleurs(e.a_parcours ? e.plan_retenu : null)}">
    <div class="etape-rail"><span class="etape-noeud">${t.icone ? icone(t.icone) : esc(e.plan_retenu || "·")}</span></div>
    <article class="carte etape-carte" data-rayon="${rayon}" data-plan="${esc(e.plan_retenu || "")}">
      <div class="etape-tete"><div><p class="etape-sur">${esc(t.sur)}</p><h3 class="etape-titre">${esc(t.titre)}</h3>
        ${e.note && e.type !== "levee_de_doute" ? `<p class="etape-note">${esc(e.note)}</p>` : ""}</div>${badge}</div>
      ${raisonRepli(e, age)}${corps}${pourquoi}
    </article></li>`;
}

function nomEtape(e) {
  return { levee_de_doute: "Levée de doute", etape2: "Step 2", moins_60: "Conseil" }[e.type]
    || (e.domaine_nom ? e.domaine_nom.replace(/ \(.*\)/, "") : "Orientation");
}

function indicateurs(r) {
  const avecPlan = r.etapes.filter((e) => e.a_parcours && e.type !== "moins_60");
  const n = { A: 0, B: 0, C: 0, aucun: 0 };
  avecPlan.forEach((e) => { n[e.plan_retenu || "aucun"] = (n[e.plan_retenu || "aucun"] || 0) + 1; });
  let loin = null;
  r.etapes.forEach((e) => {
    const p = e.plans.find((x) => x.retenu);
    const d = Math.min(...(p?.propositions || []).flatMap((x) => x.offres.map((o) => o.distance_km)));
    if (Number.isFinite(d) && (!loin || d > loin.d)) loin = { d, e };
  });
  const nbActions = r.prevention.reduce((s, p) => s + p.actions.length, 0);
  const total = avecPlan.length || 1;
  const barre = ["A", "B", "C"].map((p) => n[p] ? `<span style="--c: ${couleurCalculee(p)}; flex: ${n[p]}"></span>` : "").join("")
    + (n.aucun ? `<span style="--c: ${couleurCalculee(null)}; flex: ${n.aucun}"></span>` : "");
  const blocs = [];
  if (avecPlan.length) blocs.push(`<div class="carte indicateur"><dt>Solution idéale (plan A)</dt>
    <dd>${n.A} <small>sur ${avecPlan.length} étape${avecPlan.length > 1 ? "s" : ""}</small></dd>
    <div class="barre-plans" aria-hidden="true">${barre}</div>
    <p>${n.B + n.C ? `${n.B + n.C} repli${n.B + n.C > 1 ? "s" : ""} vers un plan B ou C` : "Aucun repli nécessaire"}</p></div>`);
  if (loin) blocs.push(loin.d < 0.5
    ? `<div class="carte indicateur"><dt>Distance à parcourir</dt><dd>0 <small>km</small></dd>
       <p>Chaque étape a une solution dans sa commune</p></div>`
    : `<div class="carte indicateur"><dt>Le plus loin à aller</dt><dd>${km(loin.d)}</dd>
       <p>pour : ${esc(nomEtape(loin.e).toLowerCase())}</p></div>`);
  blocs.push(`<div class="carte indicateur"><dt>Actions de prévention proches</dt><dd>${nbActions}</dd>
    <p>${r.prevention.length ? `pour ${r.prevention.length} capacité${r.prevention.length > 1 ? "s" : ""} sans alerte` : "aucune trouvée pour cette commune"}</p></div>`);
  return `<dl class="indicateurs">${blocs.join("")}</dl>`;
}

function afficherResultat(r) {
  etat.couches = { offres: [] };
  const p = r.personne;
  const caps = Object.fromEntries(etat.meta.capacites.map((c) => [c.code, c.nom.replace(/ \(.*\)/, "")]));
  let numero = 0;
  const frise = r.etapes.map((e, i) => carteEtape(e, i, e.type === "moins_60" ? "" : ++numero, p.age)).join("");
  const prevention = p.age >= 60 ? `
    <div><h3 class="bloc-titre">Prévention près de chez elle</h3>
    <p class="bloc-sous">Pour les capacités sans alerte : les actions qui couvrent le plus petit territoire d'abord.</p></div>
    ${r.prevention.length ? `<div class="prevention">${r.prevention.map((b) => `
      <article class="carte action-carte">
        <div class="action-tete">${icone(b.domaine)}<strong>${esc(caps[b.domaine] || b.domaine_nom)}</strong>${b.generique ? '<span class="tag">générale</span>' : ""}</div>
        <ul>${b.actions.map((a) => `<li><strong>${esc(a.action)}</strong><span>${esc([a.porteur, a.lieu && a.lieu.length < 90 ? a.lieu : ""].filter(Boolean).join(" · "))}</span></li>`).join("")}</ul>
      </article>`).join("")}</div>` : '<p class="bloc-sous">Aucune action de prévention trouvée pour cette commune.</p>'}` : "";

  $("#resultats").innerHTML = `
    <p class="fiche-entete">Fiche parcours ICOPE · ${esc(p.commune)} · ${p.age} ans · ${new Date().toLocaleDateString("fr-FR")}</p>
    <div class="entete-resultat">
      <div><p class="surtitre">Parcours proposé</p><h2>${esc(p.commune)}, ${p.age} ans</h2>
        <div class="puces">${p.alertes.length ? p.alertes.map((a) => `<span class="puce alerte-puce">${icone(a)}${esc(caps[a])}</span>`).join("")
          : '<span class="puce">Aucune alerte</span>'}</div></div>
      <div class="actions-entete">
        <button type="button" class="bouton-secondaire" id="imprimer"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="2"/><path d="M7 14h10v6.5H7z"/></svg>Imprimer la fiche</button>
        <button type="button" class="bouton-secondaire" id="nouvelle"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/></svg>Nouvelle recherche</button>
      </div>
    </div>
    <div class="synthese">
      <div class="carte carte-geo"><div id="carte" role="img" aria-label="Carte de la commune et des professionnels proposés"></div>
        <div class="legende"><span><i style="--c: var(--marque)"></i>La personne</span><span><i style="--c: var(--plan-a)"></i>Plan A</span>
          <span><i style="--c: var(--plan-b)"></i>Plan B</span><span><i style="--c: var(--plan-c)"></i>Plan C</span></div></div>
      ${indicateurs(r)}
    </div>
    <ol class="frise">${frise}</ol>
    ${prevention}`;

  $("#imprimer").addEventListener("click", () => window.print());
  $("#nouvelle").addEventListener("click", () => { window.scrollTo({ top: 0, behavior: "smooth" }); $("#commune").focus(); $("#commune").select(); });
  dessinerCarte(p);
}

/* ------------------------------------------------------------------ Carte */
function detruireCarte() {
  if (etat.carte) { etat.carte.remove(); etat.carte = null; }
}

function dessinerCarte(p) {
  if (typeof L === "undefined") { $(".carte-geo").hidden = true; return; }
  const carte = L.map("carte", { zoomControl: true, scrollWheelZoom: false, attributionControl: true });
  etat.carte = carte;
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom: 18,
  }).addTo(carte);

  const centre = [p.latitude, p.longitude];
  L.marker(centre, { icon: L.divIcon({ className: "", html: '<div class="pin-personne"></div>', iconSize: [22, 22], iconAnchor: [11, 11] }), zIndexOffset: 1000 })
    .addTo(carte).bindPopup(`<strong>${esc(p.commune)}</strong>Domicile de la personne`);

  // Un marqueur par lieu et par plan (plusieurs professionnels peuvent exercer dans la même commune)
  const groupes = new Map();
  etat.couches.offres.forEach((o) => {
    if (o.latitude == null) return;
    const k = `${o.latitude},${o.longitude},${o.plan || ""}`;
    if (!groupes.has(k)) groupes.set(k, []);
    groupes.get(k).push(o);
  });
  const parCle = {}, points = [centre];
  groupes.forEach((liste) => {
    const o0 = liste[0];
    const m = L.circleMarker([o0.latitude, o0.longitude], {
      radius: Math.min(7 + liste.length, 13), color: "#fff", weight: 2, fillColor: couleurCalculee(o0.plan || null), fillOpacity: .95,
    }).addTo(carte).bindPopup(`<strong>${esc(o0.commune)} · ${km(o0.distance_km)}</strong>`
      + liste.slice(0, 6).map((o) => `${esc(o.nom)} <span style="opacity:.7">(${esc(o.metier)})</span>`).join("<br>")
      + (liste.length > 6 ? `<br>… et ${liste.length - 6} autres` : ""));
    liste.forEach((o) => { parCle[o.cle] = m; });
    points.push([o0.latitude, o0.longitude]);
  });

  carte.fitBounds(L.latLngBounds(points).pad(0.25), { maxZoom: 11 });
  if (points.length === 1) carte.setView(centre, 10);

  // Survol d'un professionnel : son marqueur s'ouvre ; survol d'une étape : son rayon de recherche
  let cercle = null;
  document.querySelectorAll(".offre").forEach((li) => {
    li.addEventListener("mouseenter", () => { const m = parCle[li.dataset.cle]; if (m) m.openPopup(); li.classList.add("actif"); });
    li.addEventListener("mouseleave", () => li.classList.remove("actif"));
  });
  document.querySelectorAll(".etape-carte").forEach((art) => {
    art.addEventListener("mouseenter", () => {
      art.classList.add("survol");
      const r = +art.dataset.rayon;
      if (cercle) { cercle.remove(); cercle = null; }
      if (r > 0) cercle = L.circle(centre, { radius: r * 1000, color: couleurCalculee(art.dataset.plan || null), weight: 1.5, dashArray: "6 6", fillOpacity: .05 }).addTo(carte);
    });
    art.addEventListener("mouseleave", () => { art.classList.remove("survol"); if (cercle) { cercle.remove(); cercle = null; } });
  });
}

demarrer();
