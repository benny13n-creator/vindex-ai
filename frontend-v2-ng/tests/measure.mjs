// Vindex V2 NG — merenje stvarnih computed vrednosti (Refinement Pass 01).
// Pokretanje: `node tests/measure.mjs <oznaka>` → shots/refinement-01/measure-<oznaka>.json i .md
// Ništa ne menja; samo čita getComputedStyle i getBoundingClientRect.

import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";

const BASE = process.env.VX_URL || "http://127.0.0.1:4317/";
const oznaka = process.argv[2] || "trenutno";
const OUT = new URL("../shots/refinement-01/", import.meta.url);
await mkdir(OUT, { recursive: true });

const SELEKTORI = {
  "wordmark": ".wordmark",
  "breadcrumb": ".crumb",
  "naslov strane (h1)": ".sheet__title",
  "brojač": ".sheet__count",
  "pretraga (input)": "#pretraga",
  "zaglavlje kolone": ".cases thead .sort",
  "naziv predmeta": ".case__name",
  "klijent · vrsta": ".case__meta",
  "broj predmeta": ".ref__no",
  "sud": ".ref__court",
  "stanje": ".state",
  "datum izmene": ".date",
  "ćelija tabele (td)": ".cases td",
  "stavka navigacije": ".sidenav__item",
  "dugme skupljanja": ".sidenav__collapse",
  "naslov panela": ".panel__title",
  "napomena panela": ".panel__note",
  "pažnja: vrsta/vreme": ".att__top",
  "pažnja: naslov": ".att__title",
  "pažnja: predmet": ".att__case",
  "pažnja: stavka (li)": ".att",
  "demo oznaka": ".demo-badge",
  "dugme teme": "#theme-toggle",
  "nalog": ".account",
  "podnožje panela": ".panel__foot",
};

const browser = await chromium.launch();
const izlaz = { oznaka, base: BASE, prikazi: {} };

for (const [w, h, nav] of [[1440, 900, "puna"], [1280, 800, "puna"], [1440, 900, "skupljena"], [1100, 800, "puna"]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  await ctx.addInitScript(n => { localStorage.setItem("vx-ng-tema", "dark"); localStorage.setItem("vx-ng-nav", n); }, nav);
  const p = await ctx.newPage();
  await p.goto(BASE);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(120);
  izlaz.prikazi[`${w}x${h} nav=${nav}`] = await p.evaluate(sel => {
    const r = {};
    for (const [ime, s] of Object.entries(sel)) {
      const e = document.querySelector(s);
      if (!e) { r[ime] = null; continue; }
      const c = getComputedStyle(e), b = e.getBoundingClientRect();
      r[ime] = {
        prikazan: c.display !== "none" && b.width > 0,
        font: c.fontFamily.split(",")[0].replace(/"/g, ""), fontSize: c.fontSize, fontWeight: c.fontWeight,
        lineHeight: c.lineHeight, letterSpacing: c.letterSpacing,
        padding: c.padding, w: Math.round(b.width), h: Math.round(b.height), boja: c.color,
      };
    }
    const sir = id => Math.round(document.getElementById(id).getBoundingClientRect().width);
    const redovi = [...document.querySelectorAll("#rows tr")].map(t => Math.round(t.getBoundingClientRect().height));
    const nazivi = [...document.querySelectorAll(".case__name")].map(a => Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight)));
    r._raspored = {
      viewport: innerWidth + "×" + innerHeight,
      navigacija: sir("nav"), lista: sir("glavni"), panel: getComputedStyle(document.getElementById("panel")).position === "fixed" ? "fioka" : sir("panel"),
      topbar: Math.round(document.querySelector(".topbar").getBoundingClientRect().height),
      visinaReda: { min: Math.min(...redovi), max: Math.max(...redovi), medijana: redovi.slice().sort((a, b) => a - b)[Math.floor(redovi.length / 2)] },
      najviseRedovaNaziva: Math.max(...nazivi),
      kolone: [...document.querySelectorAll(".cases thead th")].map(t => Math.round(t.getBoundingClientRect().width)),
      vidljivihRedovaBezSkrola: redovi.length ? [...document.querySelectorAll("#rows tr")].filter(t => t.getBoundingClientRect().bottom <= innerHeight).length : 0,
    };
    return r;
  }, SELEKTORI);
  await ctx.close();
}

// Breakpoint-i se čitaju iz učitanih stilova, ne iz pretpostavke.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage(); await p.goto(BASE);
  izlaz.breakpointi = await p.evaluate(() => {
    const out = new Set();
    for (const sh of document.styleSheets) { try { for (const r of sh.cssRules) if (r.media) out.add(r.media.mediaText); } catch (e) {} }
    return [...out];
  });
  izlaz.tokeni = await p.evaluate(() => {
    const s = getComputedStyle(document.documentElement);
    return Object.fromEntries(["--fs-title", "--fs-heading", "--fs-body", "--fs-row-title", "--fs-meta", "--fs-small", "--lh-body", "--topbar-h", "--nav-w", "--nav-w-collapsed", "--panel-w", "--bg-shell", "--bg-sheet", "--bg-panel", "--line"].map(k => [k, s.getPropertyValue(k).trim()]));
  });
  await ctx.close();
}
await browser.close();

await writeFile(new URL(`measure-${oznaka}.json`, OUT), JSON.stringify(izlaz, null, 2));

const md = [`# Merenje — ${oznaka}`, ``, `Izvor: getComputedStyle / getBoundingClientRect u Chromium-u (Playwright), tema Dark.`, ``];
for (const [ime, r] of Object.entries(izlaz.prikazi)) {
  md.push(`## ${ime}`, ``, "```", JSON.stringify(r._raspored), "```", ``, `| Element | font | size | weight | line-height | letter-sp. | padding | w×h |`, `|---|---|---|---|---|---|---|---|`);
  for (const [k, v] of Object.entries(r)) if (k !== "_raspored") md.push(v ? `| ${k}${v.prikazan ? "" : " (skriveno)"} | ${v.font} | ${v.fontSize} | ${v.fontWeight} | ${v.lineHeight} | ${v.letterSpacing} | ${v.padding} | ${v.w}×${v.h} |` : `| ${k} | — nema elementa — |||||||`);
  md.push(``);
}
md.push(`## Breakpoint-i`, ``, ...izlaz.breakpointi.map(b => `- \`${b}\``), ``, `## Tokeni`, ``, ...Object.entries(izlaz.tokeni).map(([k, v]) => `- \`${k}\`: ${v}`));
await writeFile(new URL(`measure-${oznaka}.md`, OUT), md.join("\n"));
console.log(`measure-${oznaka}: ${Object.keys(izlaz.prikazi).length} prikaza zapisano`);
