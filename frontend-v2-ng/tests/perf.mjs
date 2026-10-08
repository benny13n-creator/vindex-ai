// Vindex V2 NG — merenje performansi potpisne pozadine.
// Pokretanje: `node serve.mjs`, pa `node tests/perf.mjs`. Rezultat: shots/perf-results.json|md
//
// Meri: vreme crtanja jednog frejma (samo pozadina) i razmak između frejmova
// na stvarnom ekranu aplikacije, uz uporednu meru originalnog koda.
// Ovo je JEDNO merenje na JEDNOJ mašini u headless Chromium-u — nije garancija.

import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";
import os from "node:os";

const BASE = process.env.VX_URL || "http://127.0.0.1:4317/";
const TRAJANJE = 5000;
const browser = await chromium.launch();

const kvant = (a, q) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(q * s.length))] : NaN; };
const r2 = x => Math.round(x * 100) / 100;

async function meri({ w, h, dpr, cpu, original = false }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
  await ctx.addInitScript(() => {
    window.__intervali = []; let pre = null;
    const raf = window.requestAnimationFrame.bind(window);
    (function tik(t) { if (pre !== null) window.__intervali.push(t - pre); pre = t; raf(tik); })(performance.now());
  });
  if (original) await ctx.addInitScript(() => {
    // Original nema merni kanal; obavija se globalna funkcija drawBg (rAF je poziva po imenu).
    window.__crtanje = [];
    addEventListener("DOMContentLoaded", () => {
      const o = window.drawBg; window.drawBg = function () { const t = performance.now(); o(); window.__crtanje.push(performance.now() - t); };
    });
  });
  const p = await ctx.newPage();
  const cdp = await ctx.newCDPSession(p);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: cpu });
  await p.goto(BASE + (original ? "tests/fixtures/original.html" : ""));
  await p.waitForTimeout(1000);                                   // zagrevanje
  await p.evaluate(o => { window.__intervali.length = 0; if (o) window.__crtanje.length = 0; else window.__vxPozadina.crtanjeMs.length = 0; }, original);
  await p.waitForTimeout(TRAJANJE);
  const d = await p.evaluate(o => ({ c: o ? window.__crtanje.slice() : window.__vxPozadina.crtanjeMs.slice(), i: window.__intervali.slice(),
    px: o ? [document.getElementById("cv").width, document.getElementById("cv").height] : window.__vxPozadina.platnoPx }), original);
  await ctx.close();
  return {
    scenario: `${original ? "ORIGINAL" : "prenos"} ${w}×${h} DPR ${dpr}, CPU ${cpu}×`,
    platno: d.px.join("×"), frejmova: d.c.length,
    crtanje_median_ms: r2(kvant(d.c, 0.5)), crtanje_p95_ms: r2(kvant(d.c, 0.95)), crtanje_max_ms: r2(Math.max(...d.c)),
    interval_median_ms: r2(kvant(d.i, 0.5)), interval_p95_ms: r2(kvant(d.i, 0.95)),
    preko_25ms_pct: r2(100 * d.i.filter(x => x > 25).length / Math.max(1, d.i.length)),
  };
}

const scenariji = [
  { w: 1440, h: 900, dpr: 1, cpu: 1 }, { w: 1440, h: 900, dpr: 1, cpu: 1, original: true },
  { w: 1440, h: 900, dpr: 2, cpu: 1 }, { w: 1920, h: 1080, dpr: 2, cpu: 1 },
  { w: 1440, h: 900, dpr: 1, cpu: 4 }, { w: 1440, h: 900, dpr: 1, cpu: 4, original: true },
  { w: 1440, h: 900, dpr: 2, cpu: 4 },
];
const rez = [];
for (const s of scenariji) { const r = await meri(s); rez.push(r); console.log(JSON.stringify(r)); }

const uslovi = {
  datum: new Date().toISOString(), browser: `Chromium ${browser.version()} (Playwright, headless)`, os: `${os.type()} ${os.release()}`,
  cpu: `${os.cpus()[0]?.model} × ${os.cpus().length}`, ram_gb: Math.round(os.totalmem() / 2 ** 30),
  napomena: "Headless Chromium crta softverski/bez stvarnog ekrana; 60 Hz je ritam headless režima. CPU 4× = CDP usporavanje procesora (simulacija slabijeg uređaja). Vreme crtanja meri samo JS deo pozadine, ne kompoziciju GPU-a.",
};
await browser.close();
await writeFile(new URL("../shots/perf-results.json", import.meta.url), JSON.stringify({ uslovi, rez }, null, 2));
await writeFile(new URL("../shots/perf-results.md", import.meta.url), [
  "# Performanse potpisne pozadine", "", "**Uslovi merenja:**", "", ...Object.entries(uslovi).map(([k, v]) => `- ${k}: ${v}`), "",
  `Svaki scenario: 1 s zagrevanja, ${TRAJANJE / 1000} s merenja, stvaran ekran aplikacije (osim ORIGINAL = referentna fikstura).`, "",
  "| Scenario | Platno | Frejmova | Crtanje median | p95 | max | Interval median | p95 | Intervala > 25 ms |", "|---|---|---|---|---|---|---|---|---|",
  ...rez.map(r => `| ${r.scenario} | ${r.platno} | ${r.frejmova} | ${r.crtanje_median_ms} ms | ${r.crtanje_p95_ms} ms | ${r.crtanje_max_ms} ms | ${r.interval_median_ms} ms | ${r.interval_p95_ms} ms | ${r.preko_25ms_pct}% |`),
  "", "Ovo je jedno merenje na jednoj mašini; nije univerzalna garancija.",
].join("\n"));
