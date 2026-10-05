// Vindex V2 NG — Workspace Refinement Pass 01: provere izmenjenog ponašanja.
// Pokretanje: server na 4317, pa `node tests/refinement.mjs`.
// Izlaz: shots/refinement-01/<VX_OUT|after>/*.png, refinement-results.{json,md}
//
// Stres-podaci (dugi nazivi, ćirilica, više stavki pažnje) ubacuju se SAMO u
// testu, presretanjem src/demo-data.js — prototip i demo scenariji se ne menjaju.
// Ovo dokazuje ponašanje i raspored, ne vizuelni kvalitet.

import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const BASE = process.env.VX_URL || "http://127.0.0.1:4317/";
const IZLAZ = process.env.VX_OUT || "after";
const OUT = new URL(`../shots/refinement-01/${IZLAZ}/`, import.meta.url);
await mkdir(OUT, { recursive: true });
const putanja = ime => fileURLToPath(new URL(ime + ".png", OUT));

const rezultati = [], greske = [];
function zapisi(grupa, naziv, prolazi, detalj = "") {
  rezultati.push({ grupa, naziv, prolazi: !!prolazi, detalj: String(detalj) });
  console.log(`${prolazi ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

/* ── Stres-podaci (samo test) ──────────────────────────────────────────── */
const DUG_LAT = "Utvrđenje ništavosti ugovora o kupoprodaji nepokretnosti zaključenog pod prinudom, uz naknadu štete zbog neosnovanog obogaćenja tuženog i troškova";
const DUG_CIR = "Накнада нематеријалне штете због повреде права личности и душевних болова услед објављивања нетачних информација у електронском медију";
const STRES = `
;(function () {
  var d = window.VX_DEMO;
  [
    { naziv: ${JSON.stringify(DUG_LAT)}, klijent: "Đ. Žarković i Č. Šćepanović", vrsta: "Parnica", broj: "P 5120/2026", sud: "Osnovni sud u Novom Sadu", stanje: "aktivan", izmenjeno: "2026-10-04" },
    { naziv: ${JSON.stringify(DUG_CIR)}, klijent: "Ђорђе Чолић", vrsta: "Накнада штете", broj: "П 2231/2026", sud: "Виши суд у Београду", stanje: "cekanje", izmenjeno: "2026-10-03" }
  ].forEach(function (p, i) { p.id = "stres-" + (i + 1); d.predmeti.unshift(p); });
  if (d.paznja.length) d.paznja = d.paznja.concat([
    { vrsta: "Interni rok", naslov: "Proveriti punomoćje za zastupanje", broj: "P 5120/2026", predmet: ${JSON.stringify(DUG_LAT)}, kada: "2026-10-14" },
    { vrsta: "Klijent", naslov: "Позвати клијента ради допуне доказа", broj: "П 2231/2026", predmet: ${JSON.stringify(DUG_CIR)}, kada: "2026-10-15" },
    { vrsta: "Ročište", naslov: "Pripremno ročište", broj: "P 1188/2026", predmet: "Naplata potraživanja po osnovu ugovora o isporuci robe", kada: "2026-10-20", vreme: "09:00" }
  ]);
})();`;

const browser = await chromium.launch();

async function otvori({ w = 1440, h = 900, tema = "dark", nav = "puna", upit = "", stres = false, motion = "reduce" } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: motion });
  await ctx.addInitScript(([t, n]) => {
    if (!sessionStorage.getItem("vx-test-init")) {
      localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", n); sessionStorage.setItem("vx-test-init", "1");
    }
  }, [tema, nav]);
  if (stres) await ctx.route("**/src/demo-data.js", async r => {
    const odg = await r.fetch(); await r.fulfill({ response: odg, body: (await odg.text()) + STRES });
  });
  const p = await ctx.newPage();
  p.on("console", m => { if (m.type() === "error") greske.push(m.text()); });
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(BASE + upit);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(120);
  return p;
}

/* Svaki vidljivi element sa sopstvenim tekstom: najmanja veličina fonta. */
const najmanjiFont = p => p.evaluate(() => {
  let min = { px: 99, el: "" };
  for (const e of document.querySelectorAll("body *")) {
    if (!e.offsetParent && getComputedStyle(e).position !== "fixed") continue;
    if (e.closest("[hidden], .sr-only, [inert] .panel:not(.is-open)")) continue;
    const r = e.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (getComputedStyle(e).visibility === "hidden") continue;
    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const px = parseFloat(getComputedStyle(e).fontSize);
    if (px < min.px) min = { px, el: (e.className || e.tagName) + " „" + e.textContent.trim().slice(0, 24) + "“" };
  }
  return min;
});
const bezHorizontalnog = p => p.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

// ── A. Gornja traka ─────────────────────────────────────────────────────
{
  const p = await otvori();
  zapisi("gornja traka", "nema breadcrumb-a koji ponavlja navigaciju i naslov", (await p.$$(".crumb")).length === 0);
  const tekst = await p.$$eval(".topbar > :not(.topbar__end), .topbar__end > *", es => es.filter(e => e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== "none")
    .map(e => e.textContent.trim().replace(/\s+/g, " ")).filter(Boolean));
  zapisi("gornja traka", "samo identitet, demo oznaka i sistemske kontrole", JSON.stringify(tekst) === JSON.stringify(["Vindex", "Demonstracioni podaci Demo", "Svetla tema", "Demo nalog"]) ||
    JSON.stringify(tekst) === JSON.stringify(["Vindex", "Demonstracioni podaciDemo", "Svetla tema", "Demo nalog"]), tekst.join(" | "));
  zapisi("gornja traka", "pretraga ostaje u radnoj površini, ne u gornjoj traci", await p.$eval("#pretraga", e => !!e.closest("#glavni")));
  const wm = await p.$eval(".wordmark", e => { const s = getComputedStyle(e); return { f: s.fontFamily, px: parseFloat(s.fontSize), ls: s.letterSpacing, ts: s.textShadow, bi: s.backgroundImage, c: s.color }; });
  const h1 = await p.$eval(".sheet__title", e => parseFloat(getComputedStyle(e).fontSize));
  zapisi("wordmark", "serif, 18–20px, podređen naslovu strane", wm.f.includes("Source Serif 4") && wm.px >= 18 && wm.px <= 20 && wm.px < h1, `${wm.px}px naspram h1 ${h1}px`);
  zapisi("wordmark", "bez sjaja, gradijenta i agresivnog praćenja", wm.ts === "none" && wm.bi === "none" && (wm.ls === "normal" || parseFloat(wm.ls) <= 0.4), `letter-spacing ${wm.ls}`);
  await p.context().close();
}

// ── B. Tipografija ──────────────────────────────────────────────────────
for (const tema of ["dark", "light"]) {
  const p = await otvori({ tema });
  const t = await p.evaluate(() => {
    const f = s => { const e = document.querySelector(s), c = getComputedStyle(e); return { px: parseFloat(c.fontSize), lh: parseFloat(c.lineHeight) / parseFloat(c.fontSize), fam: c.fontFamily }; };
    return { h1: f(".sheet__title"), naziv: f(".case__name"), telo: f(".ref__no"), nav: f(".sidenav__item"), input: f("#pretraga"),
      meta: [".case__meta", ".ref__court", ".sheet__count", ".att__case"].map(f), body: f("body"),
      velika: [...document.querySelectorAll("body *")].filter(e => getComputedStyle(e).textTransform === "uppercase" && e.textContent.trim()).length,
      sirokoPracenje: [...document.querySelectorAll("body *")].filter(e => { const c = getComputedStyle(e); return c.letterSpacing !== "normal" && parseFloat(c.letterSpacing) / parseFloat(c.fontSize) > 0.02; }).length };
  });
  const g = `tipografija ${tema}`;
  zapisi(g, "naslov strane 28–30px, Source Serif 4", t.h1.px >= 28 && t.h1.px <= 30 && t.h1.fam.includes("Source Serif 4"), `${t.h1.px}px`);
  zapisi(g, "naziv predmeta 15–16px, IBM Plex Sans", t.naziv.px >= 15 && t.naziv.px <= 16 && t.naziv.fam.includes("IBM Plex Sans"), `${t.naziv.px}px`);
  zapisi(g, "radni tekst 14,5–15px (broj, navigacija, pretraga)", [t.telo, t.nav, t.input].every(x => x.px >= 14.5 && x.px <= 15), [t.telo, t.nav, t.input].map(x => x.px).join("/"));
  zapisi(g, "sekundarni podaci 13,5–14px", t.meta.every(x => x.px >= 13.5 && x.px <= 14), t.meta.map(x => x.px).join("/"));
  zapisi(g, "line-height osnovnog teksta 1,4–1,5", t.body.lh >= 1.4 && t.body.lh <= 1.5, t.body.lh.toFixed(2));
  const min = await najmanjiFont(p);
  zapisi(g, "nijedan vidljiv tekst ispod 13px", min.px >= 13, `najmanji: ${min.px}px ${min.el}`);
  zapisi(g, "bez velikih slova kao sistema i bez širokog praćenja", t.velika === 0 && t.sirokoPracenje === 0, `uppercase ${t.velika}, praćenje ${t.sirokoPracenje}`);
  await p.context().close();
}

// ── C. Dugi nazivi, ćirilica (stres) ───────────────────────────────────
for (const [w, h] of [[1440, 900], [1280, 800], [1200, 800]]) {
  const p = await otvori({ w, h, stres: true });
  const g = `dugi nazivi ${w}`;
  const r = await p.evaluate(([lat, cir]) => {
    const as = [...document.querySelectorAll(".case__name")];
    const redova = a => Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight));
    const nadji = t => as.find(a => a.textContent === t);
    return { max: Math.max(...as.map(redova)), lat: nadji(lat) && { r: redova(nadji(lat)), odsecen: nadji(lat).scrollHeight > nadji(lat).clientHeight + 1, title: nadji(lat).title === lat },
      cir: nadji(cir) && { r: redova(nadji(cir)), title: nadji(cir).title === cir }, duzine: [lat.length, cir.length],
      prelivanje: document.getElementById("registry").scrollWidth > document.getElementById("registry").clientWidth };
  }, [DUG_LAT, DUG_CIR]);
  zapisi(g, `stres-nazivi ≥ 120 znakova (${r.duzine.join(" i ")})`, r.duzine.every(n => n >= 120));
  zapisi(g, "u listi najviše 2 reda po nazivu", r.max <= 2, `najviše ${r.max}`);
  zapisi(g, "dugi naziv je vizuelno skraćen, a podatak ceo (DOM + title)", r.lat && r.lat.r === 2 && r.lat.odsecen && r.lat.title && r.cir && r.cir.title);
  zapisi(g, "tabela ne izlazi iz radne površine", !r.prelivanje);
  if (w === 1440) {
    await p.screenshot({ path: putanja("05-dugi-nazivi-1440-dark") });
    zapisi("ćirilica", "Plex Sans i Source Serif 4 imaju ćirilične glifove (bez zamenskog fonta)", await p.evaluate(async t => {
      for (const f of ['500 15px "IBM Plex Sans"', '400 13.5px "IBM Plex Sans"', '500 28px "Source Serif 4"']) {
        const l = await document.fonts.load(f, t);
        if (!l.length || !l.every(x => x.status === "loaded") || !document.fonts.check(f, t)) return false;
      }
      return true;
    }, DUG_CIR));
    zapisi("ćirilica", "ćirilični naziv, klijent i sud prikazani u listi", await p.evaluate(() => [...document.querySelectorAll("#rows tr")].some(tr => tr.textContent.includes("Ђорђе Чолић") && tr.textContent.includes("Виши суд у Београду"))));
    // Pretraga: ceo podatak je pretraživ, i reči koje u listi nisu vidljive.
    await p.fill("#pretraga", "obogacenja");
    zapisi("dugi nazivi", "pretraga nalazi reč iz skrivenog dela naziva („obogacenja“)", (await p.$$eval("#rows tr", t => t.map(x => x.dataset.id))).join() === "stres-1");
    await p.fill("#pretraga", "душевних");
    zapisi("dugi nazivi", "ćirilična pretraga („душевних“)", (await p.$$eval("#rows tr", t => t.map(x => x.dataset.id))).join() === "stres-2");
    await p.fill("#pretraga", "zarkovic");
    zapisi("dugi nazivi", "„zarkovic“ pronalazi „Žarković“", (await p.$$eval("#rows tr", t => t.map(x => x.dataset.id))).join() === "stres-1");
    await p.fill("#pretraga", "");
    // Pass 01B: fokus tastature ne razvija naziv i ne menja visinu reda.
    const visine = () => p.evaluate(() => [...document.querySelectorAll("#rows tr")].map(t => t.getBoundingClientRect().height));
    const pre = await visine();
    await p.focus('th[data-kljuc="izmenjeno"] .sort'); await p.keyboard.press("Tab");
    const f = await p.evaluate(() => { const a = document.activeElement, s = getComputedStyle(a); return { id: a.closest("tr") && a.closest("tr").dataset.id, r: Math.round(a.getBoundingClientRect().height / parseFloat(s.lineHeight)), obris: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2, title: a.title.length, ime: a.textContent.length }; });
    const posle = await visine();
    zapisi("dugi nazivi", "Tab na dugi naziv: i dalje najviše 2 reda, vidljiv obris fokusa", f.id === "stres-1" && f.r === 2 && f.obris, `${f.r} reda`);
    zapisi("dugi nazivi", "fokus ne menja visinu nijednog reda (bez pomeranja rasporeda)", JSON.stringify(pre) === JSON.stringify(posle), `red 1: ${pre[0]}px → ${posle[0]}px`);
    zapisi("dugi nazivi", "ceo naziv i dalje dostupan (pristupačno ime + title)", f.ime === f.title && f.ime >= 120, `${f.ime} znakova`);
    await p.screenshot({ path: putanja("05b-dugi-naziv-fokus-tastature-1440-dark") });
    await p.keyboard.press("Tab");
    zapisi("dugi nazivi", "napuštanjem fokusa naziv se vraća na 2 reda", await p.evaluate(t => { const a = [...document.querySelectorAll(".case__name")].find(x => x.textContent === t); return Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight)) === 2; }, DUG_LAT));
    await p.keyboard.press("Enter");
    zapisi("dugi nazivi", "otvaranje predmeta i dalje prijavljuje da detalj nije deo prototipa", (await p.textContent("#status")).includes("nije deo ovog prototipa"));
  }
  await p.context().close();
}

// ── D. Panel „Zahteva pažnju“ ───────────────────────────────────────────
{
  const p = await otvori({ stres: true });
  const r = await p.evaluate(() => ({
    n: document.querySelectorAll("#attention li").length,
    vise: (m => !!m && !m.hidden && m.textContent)(document.getElementById("attention-more")),
    linkovi: [...document.querySelectorAll("#panel a")].map(a => a.textContent.trim()),
    struktura: [...document.querySelectorAll("#attention li")].every(li => li.querySelector(".att__kind") && li.querySelector(".att__when") && li.querySelector(".att__title") && li.querySelector(".att__case")),
  }));
  zapisi("panel više stavki", "8 stavki u podacima → prikazano najviše 5", r.n === 5, `${r.n} prikazano`);
  zapisi("panel više stavki", "jasno rečeno da ih ima više (bez izmišljenog „Prikaži sve“ odredišta)", r.vise === "Prikazano 5 od 8, po datumu." && !r.linkovi.some(t => /prikaži sve/i.test(t)), r.vise);
  zapisi("panel", "svaka stavka: vrsta, vreme, radnja, predmet", r.struktura);
  const boje = await p.evaluate(() => {
    const s = getComputedStyle(document.documentElement), v = k => s.getPropertyValue(k).trim();
    const rgb = hex => "rgb(" + [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)).join(", ") + ")";
    return [...document.querySelectorAll(".att__when")].map(t => ({ blizu: t.classList.contains("att__when--soon"), dani: Math.round((Date.parse(t.dateTime) - Date.parse(window.VX_DEMO.danas)) / 864e5), c: getComputedStyle(t).color, amber: rgb(v("--attention")), neutral: rgb(v("--text-2")) }));
  });
  zapisi("panel", "amber samo za blizak datum (≤ 2 dana), ostalo neutralno; bez crvene", boje.every(b => b.blizu ? (b.dani >= 0 && b.dani <= 2 && b.c === b.amber) : b.c === b.neutral),
    boje.map(b => `${b.dani}d:${b.blizu ? "amber" : "neutral"}`).join(" "));
  await p.screenshot({ path: putanja("06-panel-vise-stavki-1440-dark") });
  await p.context().close();
  const q = await otvori({ w: 1100, h: 800, stres: true });
  zapisi("panel više stavki", "dugme fioke pokazuje ukupan broj (8), ne samo prikazane", (await q.textContent("#panel-toggle-count")) === "8");
  await q.context().close();
  const e = await otvori({ upit: "?paznja=prazno" });
  const tekst = (await e.textContent("#attention-empty")).replace(/\s+/g, " ").trim();
  zapisi("panel prazan", "neutralno prazno stanje koje ne tvrdi da nema obaveza", /ne zamenjuje proveru rokova/.test(tekst) && !/nema (obaveza|rokova)/i.test(tekst), tekst);
  await e.screenshot({ path: putanja("07-panel-prazan-1440-dark") });
  await e.context().close();
}

// ── E. Lista predmeta ──────────────────────────────────────────────────
{
  const p = await otvori();
  zapisi("lista", "kolone nepromenjene: Predmet, Broj i sud, Stanje, Izmenjeno",
    JSON.stringify(await p.$$eval(".cases thead th", t => t.map(x => x.textContent.trim()))) === JSON.stringify(["Predmet", "Broj i sud", "Stanje", "↓Izmenjeno"].map(x => x)) ||
    JSON.stringify(await p.$$eval(".cases thead th .sort", t => t.map(x => x.firstChild.textContent.trim()))) === JSON.stringify(["Predmet", "Broj i sud", "Stanje", "Izmenjeno"]));
  zapisi("lista", "stanje: mala tačka + neutralan tekst, bez obojene pozadine", await p.$$eval(".state", s => s.every(x => {
    const c = getComputedStyle(x), d = getComputedStyle(x, "::before");
    return c.backgroundColor === "rgba(0, 0, 0, 0)" && parseFloat(d.width) <= 8 && c.color === getComputedStyle(document.querySelector(".case__meta")).color;
  })));
  const odst = await p.evaluate(() => {
    const dno = e => { const r = document.createRange(); r.selectNodeContents(e); return r.getClientRects()[0].bottom; };
    let max = 0;
    for (const tr of document.querySelectorAll("#rows tr")) {
      const b = [".case__name", ".ref__no", ".state", ".date"].map(s => dno(tr.querySelector(s)));
      max = Math.max(max, Math.max(...b) - Math.min(...b));
    }
    return max;
  });
  zapisi("lista", "prvi red naziva, broja, stanja i datuma na istoj osnovnoj liniji (±1,5px)", odst <= 1.5, `najveće odstupanje ${odst.toFixed(2)}px`);
  const kol = [];
  for (let w = 1200; w <= 1600; w += 10) { await p.setViewportSize({ width: w, height: 900 }); kol.push([w, await p.$eval('th[data-kljuc="naziv"]', t => t.getBoundingClientRect().width)]); }
  // Pass 01B: na 1280 panel ulazi u tok stranice — to je nameran prelaz režima.
  // Unutar svakog režima (panel-fioka < 1280, tri kolone ≥ 1280) kolona naziva samo raste.
  const pad = kol.filter((x, i) => i && x[0] !== 1280 && x[1] < kol[i - 1][1] - 0.5);
  zapisi("lista", "unutar istog rasporeda šira površina nikad ne daje užu kolonu naziva (1200–1600px)", pad.length === 0,
    `${Math.round(kol[0][1])}px @1200, prelaz na 1280 → ${Math.round(kol.find(x => x[0] === 1280)[1])}px (panel ulazi), ${Math.round(kol.at(-1)[1])}px @1600${pad.length ? "; pad na " + pad.map(x => x[0]).join(",") : ""}`);
  await p.context().close();
}

// ── F. Navigacija: bez automatskog skupljanja, sklonost se čuva ─────────
{
  const p = await otvori({ w: 1200, h: 800 });
  zapisi("navigacija", "na 1200px navigacija ostaje puna (nema automatskog skupljanja)", (await p.$eval("#nav", e => e.getBoundingClientRect().width)) >= 200);
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.click("#nav-collapse");
  await p.setViewportSize({ width: 800, height: 700 }); await p.waitForTimeout(50);
  zapisi("navigacija", "uska širina: navigacija je fioka", !(await p.$eval("#nav", e => getComputedStyle(e).visibility !== "hidden" && e.getBoundingClientRect().right > 0)));
  await p.setViewportSize({ width: 1440, height: 900 }); await p.waitForTimeout(50);
  zapisi("navigacija", "povratak na široko: korisnikova sklonost (skupljena) sačuvana", (await p.$eval("#nav", e => e.getBoundingClientRect().width)) <= 64);
  await p.screenshot({ path: putanja("04-nav-skupljena-1440-dark") });
  await p.context().close();
}

// ── F2. Pass 01B: panel je fioka ispod 1280 px ─────────────────────────
for (const w of [1279, 1280]) {
  const p = await otvori({ w, h: 800 });
  const r = await p.evaluate(() => {
    const pn = document.getElementById("panel"), s = getComputedStyle(pn), d = document.getElementById("panel-toggle");
    return { fiksan: s.position === "fixed", vidljiv: s.visibility !== "hidden" && pn.getBoundingClientRect().left < innerWidth,
      dugme: getComputedStyle(d).display !== "none", lista: Math.round(document.getElementById("glavni").getBoundingClientRect().width),
      naziv: Math.round(document.querySelector('th[data-kljuc="naziv"]').getBoundingClientRect().width) };
  });
  const g = `Pass 01B ${w}px`;
  if (w === 1279) {
    zapisi(g, "panel je fioka: van toka stranice, skriven, dugme „Zahteva pažnju“ vidljivo", r.fiksan && !r.vidljiv && r.dugme, `lista ${r.lista}px, kolona naziva ${r.naziv}px`);
    await p.screenshot({ path: putanja("12-1279-dark") });
    await p.click("#panel-toggle"); await p.waitForTimeout(80);
    zapisi(g, "dugme otvara panel kao fioku, fokus ulazi u nju", await p.evaluate(() => getComputedStyle(document.getElementById("panel")).visibility === "visible" && document.getElementById("panel").contains(document.activeElement)));
    await p.screenshot({ path: putanja("12b-1279-dark-panel-otvoren") });
  } else {
    zapisi(g, "tri kolone: panel u toku stranice, dugme fioke skriveno", !r.fiksan && r.vidljiv && !r.dugme, `lista ${r.lista}px, kolona naziva ${r.naziv}px`);
    await p.screenshot({ path: putanja("13-1280-dark") });
  }
  await p.context().close();
}

// ── G. Vizuelna uzdržanost ─────────────────────────────────────────────
for (const tema of ["dark", "light"]) {
  const p = await otvori({ tema, stres: true });
  const r = await p.evaluate(() => {
    const los = [];
    for (const e of document.querySelectorAll("body *")) {
      const c = getComputedStyle(e);
      if (c.boxShadow !== "none" || c.backdropFilter !== "none" || c.textShadow !== "none" || (c.backgroundImage !== "none" && !e.matches("input"))) los.push(e.className || e.tagName);
    }
    return los;
  });
  zapisi(`uzdržanost ${tema}`, "bez senki, zamućenja, sjaja i gradijenata", r.length === 0, r.slice(0, 5).join(", "));
  await p.context().close();
}

// ── H. Glavni snimci ────────────────────────────────────────────────────
for (const [w, h, tema, ime, upit] of [[1440, 900, "dark", "01-1440-dark", ""], [1440, 900, "light", "02-1440-light", ""], [1280, 800, "dark", "03-1280-dark", ""],
  [1280, 800, "light", "03b-1280-light", ""], [1200, 800, "dark", "03c-1200-dark", ""], [1440, 900, "dark", "08-240-predmeta-1440-dark", "?predmeti=veliko"], [1440, 900, "dark", "09-prazna-lista-1440-dark", "?predmeti=prazno"]]) {
  const p = await otvori({ w, h, tema, upit });
  if (upit === "?predmeti=veliko") {
    zapisi("240 predmeta", "240 redova, nijedan naziv preko 2 reda, bez horizontalnog skrola", await p.evaluate(() => {
      const as = [...document.querySelectorAll(".case__name")];
      return as.length === 240 && as.every(a => Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight)) <= 2);
    }) && await bezHorizontalnog(p));
  }
  await p.screenshot({ path: putanja(ime) });
  await p.context().close();
}

// ── I. STVARNI zoom pregledača 200% i Windows skaliranje ───────────────
// Zoom: chrome.tabs.setZoom kroz test-proširenje = isti mehanizam kao Ctrl+ u pregledaču.
// Skaliranje: --force-device-scale-factor = isti put kao Windows „Scale“ u Chrome-u.
const EXT = fileURLToPath(new URL("./fixtures/zoom-ext/", import.meta.url));
async function cdpSnimak(p, ime) {
  const s = await p.context().newCDPSession(p);
  const { data } = await s.send("Page.captureScreenshot", { format: "png" });
  await writeFile(putanja(ime), Buffer.from(data, "base64"));
  await s.detach();
}
for (const [ww, wh, tema] of [[1440, 900, "dark"], [1280, 800, "dark"], [1440, 900, "light"]]) {
  const ctx = await chromium.launchPersistentContext("", { channel: "chromium", headless: true, viewport: null, reducedMotion: "reduce",
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, `--window-size=${ww},${wh}`] });
  let [sw] = ctx.serviceWorkers(); if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
  await ctx.addInitScript(t => localStorage.setItem("vx-ng-tema", t), tema);
  const p = await ctx.newPage();
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(BASE); await p.evaluate(() => document.fonts.ready);
  const pre = await p.evaluate(() => [innerWidth, innerHeight, devicePixelRatio]);
  const zoom = await sw.evaluate(async () => { const [t] = await chrome.tabs.query({ url: "http://127.0.0.1/*" }).then(a => a.length ? a : chrome.tabs.query({})); await chrome.tabs.setZoom(t.id, 2); return chrome.tabs.getZoom(t.id); });
  await p.waitForTimeout(400);
  const posle = await p.evaluate(() => [innerWidth, innerHeight, devicePixelRatio]);
  const g = `stvarni zoom 200% (prozor ${ww}×${wh}, ${tema})`;
  zapisi(g, "zoom pregledača zaista 200% (CSS širina prepolovljena, DPR 2)", zoom === 2 && posle[2] === 2 && Math.abs(posle[0] - pre[0] / 2) <= 1, `pre ${pre.join("×")}, posle ${posle.join("×")}`);
  zapisi(g, "bez horizontalnog skrola (reflow, ne pomeranje)", await bezHorizontalnog(p));
  const min = await najmanjiFont(p);
  zapisi(g, "nijedan vidljiv tekst ispod 13 CSS px (fontovi se ne smanjuju zbog kolona)", min.px >= 13, `najmanji: ${min.px}px ${min.el}`);
  zapisi(g, "lista je glavni sadržaj preko cele širine; panel i navigacija na zahtev", await p.evaluate(() =>
    document.getElementById("glavni").getBoundingClientRect().width >= innerWidth - 2 && getComputedStyle(document.getElementById("panel")).position === "fixed"));
  await cdpSnimak(p, `10-stvarni-zoom-200-${ww}-${tema}`);
  await p.keyboard.press("Tab"); await p.keyboard.press("Tab");
  const fokus = await p.evaluate(() => document.activeElement.id);
  await p.keyboard.press("Enter"); await p.waitForTimeout(80);
  zapisi(g, "tastatura: Tab → ☰ → Enter otvara navigaciju i fokus ulazi u nju", fokus === "nav-toggle" && await p.evaluate(() => document.getElementById("nav").contains(document.activeElement)));
  await cdpSnimak(p, `10b-stvarni-zoom-200-${ww}-${tema}-navigacija`);
  await p.keyboard.press("Escape");
  await p.click("#panel-toggle"); await p.waitForTimeout(80);
  zapisi(g, "panel „Zahteva pažnju“ otvara se kao fioka", await p.evaluate(() => getComputedStyle(document.getElementById("panel")).visibility === "visible"));
  await cdpSnimak(p, `10c-stvarni-zoom-200-${ww}-${tema}-panel`);
  await ctx.close();
}
for (const [dsf, ww, wh] of [[1.25, 1920, 1080], [1.5, 1920, 1080], [1.25, 1366, 768]]) {
  // --window-size je u DIP jedinicama: fizički ekran ww×wh pri skaliranju dsf = prozor (ww/dsf)×(wh/dsf).
  const b2 = await chromium.launch({ channel: "chromium", args: [`--force-device-scale-factor=${dsf}`, `--window-size=${Math.round(ww / dsf)},${Math.round(wh / dsf)}`] });
  const ctx = await b2.newContext({ viewport: null, reducedMotion: "reduce" });
  const p = await ctx.newPage(); await p.goto(BASE); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(100);
  const r = await p.evaluate(() => ({ w: innerWidth, dpr: devicePixelRatio, panel: getComputedStyle(document.getElementById("panel")).position === "fixed" ? "fioka" : "kolona", nav: getComputedStyle(document.getElementById("nav")).position === "fixed" ? "fioka" : "kolona" }));
  const min = await najmanjiFont(p);
  zapisi(`Windows skaliranje ${Math.round(dsf * 100)}% (ekran ${ww}×${wh})`, "CSS širina odgovara skaliranju; bez horizontalnog skrola; tekst ≥ 13 CSS px",
    Math.abs(r.w - ww / dsf) <= 20 && r.dpr === dsf && (await bezHorizontalnog(p)) && min.px >= 13,
    `CSS širina ${r.w}px, DPR ${r.dpr}, navigacija: ${r.nav}, panel: ${r.panel}, najmanji tekst ${min.px}px`);
  await cdpSnimak(p, `11-windows-${Math.round(dsf * 100)}-${ww}x${wh}`);
  await b2.close();
}

zapisi("konzola", "bez grešaka u konzoli", greske.length === 0, greske.slice(0, 3).join(" | "));
await browser.close();

const prolazi = rezultati.filter(r => r.prolazi).length;
const dir = new URL("../shots/refinement-01/", import.meta.url);
await writeFile(new URL(`refinement-results-${IZLAZ}.json`, dir), JSON.stringify({ base: BASE, prolazi, ukupno: rezultati.length, rezultati }, null, 2));
await writeFile(new URL(`refinement-results-${IZLAZ}.md`, dir), [`# Refinement 01 — provere (${IZLAZ})`, ``, `**${prolazi}/${rezultati.length} prolazi.** Ponašanje i raspored, ne vizuelni kvalitet.`, ``,
  `| Grupa | Provera | Ishod | Detalj |`, `|---|---|---|---|`,
  ...rezultati.map(r => `| ${r.grupa} | ${r.naziv} | ${r.prolazi ? "PASS" : "**FAIL**"} | ${r.detalj.replace(/\|/g, "/")} |`)].join("\n"));
console.log(`\n${prolazi}/${rezultati.length} prolazi`);
process.exit(prolazi === rezultati.length ? 0 : 1);
