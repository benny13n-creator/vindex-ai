// Vindex V2 NG — forenzika vernosti pozadine (NS002A). SAMO DIJAGNOSTIKA.
// Pokretanje: `node tests/diagnostics/background-forensic.mjs` (sam podiže server).
// Izlaz: shots/forensic/ (sirovi RGBA, PNG-ovi, heatmap, forensic.json) + sažetak.
//
// Faze:
//  1. stvarna tema i boje na OBE fiksture (instrumentisan canvas kontekst)
//  2. sirovi dokazi: RGBA SHA-256, statistika razlike, heatmap
//  3. ORIGINAL_MINUS_GLOW: original.html deterministički transformisan — uklonjen
//     ISKLJUČIVO D1 blok sjaja (createRadialGradient … fillRect), uz strukturnu proveru
//  4. ORIGINAL_MINUS_GLOW vs PRENOS: ceo canvas, egzaktno, dark + light, 3 ponavljanja
//  5. D1 negativna kontrola: ORIGINAL vs ORIGINAL_MINUS_GLOW mora se materijalno razlikovati
//
// Ne menja nijedan proizvodni fajl ni postojeći test. Exit 0 = CASE A dokazan.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import http from "node:http";
import { fileURLToPath } from "node:url";

const KOREN = fileURLToPath(new URL("../..", import.meta.url));
const OUT = fileURLToPath(new URL("../../shots/forensic/", import.meta.url));
await mkdir(OUT, { recursive: true });
const PORT = 4471;
const SEME = 42, W = 1440, H = 900;

// ── Faza 3a: ORIGINAL_MINUS_GLOW deterministički iz original.html ───────
const ORIGINAL = await readFile(KOREN + "tests/fixtures/original.html", "utf8");
const GLOW = "var g=ctx.createRadialGradient(mx,my,0,mx,my,420);g.addColorStop(0,'rgba('+rgb+','+(isL?'0.05':'0.07')+')');g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);";
const brojGlow = ORIGINAL.split(GLOW).length - 1;
const MINUS = ORIGINAL.replace(GLOW, "");
// Strukturna provera: MINUS == ORIGINAL bez tačno jednog D1 bloka, ništa drugo.
const i0 = ORIGINAL.indexOf(GLOW);
const strukturno = brojGlow === 1 &&
  MINUS === ORIGINAL.slice(0, i0) + ORIGINAL.slice(i0 + GLOW.length) &&
  MINUS.length === ORIGINAL.length - GLOW.length &&
  !/createRadialGradient|addColorStop/.test(MINUS) &&
  (ORIGINAL.match(/fillRect/g) || []).length - 1 === (MINUS.match(/fillRect/g) || []).length;

const srv = spawn(process.execPath, ["serve.mjs", String(PORT)], { cwd: KOREN, stdio: "ignore" });
for (let i = 0; i < 100; i++) {
  const ok = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/" }, s => { s.resume(); r(true); }).on("error", () => r(false)));
  if (ok) break; await new Promise(r => setTimeout(r, 50));
}
const BASE = `http://127.0.0.1:${PORT}/`;
const browser = await chromium.launch();

/* Beleži svaku boju/stil i addColorStop koje stranica postavi na 2D kontekst. */
const INSTRUMENT = () => {
  window.__stilovi = [];
  // Koren (NS002A): sjaj originala prati mousemove. Beleži svaki stvaran događaj.
  window.__mis = [];
  window.addEventListener("mousemove", e => window.__mis.push([e.clientX, e.clientY, e.isTrusted, Math.round(performance.now())]), true);
  const P = CanvasRenderingContext2D.prototype;
  for (const k of ["fillStyle", "strokeStyle"]) {
    const d = Object.getOwnPropertyDescriptor(P, k);
    Object.defineProperty(P, k, { configurable: true, get() { return d.get.call(this); },
      set(v) { window.__stilovi.push(k + "=" + (typeof v === "string" ? v : "[" + (v && v.constructor && v.constructor.name) + "]")); d.set.call(this, v); } });
  }
  const ac = CanvasGradient.prototype.addColorStop;
  CanvasGradient.prototype.addColorStop = function (o, c) { window.__stilovi.push("addColorStop(" + o + "," + c + ")"); return ac.call(this, o, c); };
};

/* Tačan postupak postojećeg testa (tests/signature-background.mjs) za svetlu temu. */
const SVETLO_ORIGINAL = () => { document.body.classList.add("light-theme"); ctx.clearRect(0, 0, W, H); for (const p of pts) { p.x -= p.vx; p.y -= p.vy; p.t -= .007; } drawBg(); };
const SVETLO_PRENOS = () => { document.documentElement.dataset.theme = "light"; inst.destroy(); window.inst = VindexSignatureBackground.mount(document.getElementById("pozadina-test"), { seed: 42, rucno: true }); inst.frejm(1); };

async function snimi(vrsta, tema) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, reducedMotion: "no-preference" });
  await ctx.addInitScript(INSTRUMENT);
  const p = await ctx.newPage();
  if (vrsta === "minus") {
    await p.route("**/tests/fixtures/__original-minus-glow.html*", r => r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: MINUS }));
  }
  const put = { original: "tests/fixtures/original.html", minus: "tests/fixtures/__original-minus-glow.html", prenos: "tests/fixtures/prenos.html" }[vrsta];
  await p.goto(`${BASE}${put}?seed=${SEME}&zamrzni=1`);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(120);
  let stiloviPre = await p.evaluate(() => window.__stilovi.slice());
  if (tema === "light") {
    await p.evaluate(() => { window.__stilovi = []; });
    if (vrsta === "prenos") await p.evaluate(SVETLO_PRENOS); else await p.evaluate(SVETLO_ORIGINAL);
  }
  const info = await p.evaluate(([vrsta]) => {
    const c = document.querySelector("canvas");
    const g = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
    let s = ""; for (let i = 0; i < g.length; i += 0x8000) s += String.fromCharCode.apply(null, g.subarray(i, i + 0x8000));
    return {
      rgba: btoa(s), w: c.width, h: c.height, dpr: devicePixelRatio,
      bodyClass: document.body.className, isL_original: document.body.classList.contains("light-theme"),
      dataTheme: document.documentElement.dataset.theme || "", tema_prenos: document.documentElement.dataset.theme === "light" ? "light" : "dark",
      stilovi: window.__stilovi.slice(),
      mis: window.__mis.slice(), mx: typeof window.mx === "number" ? window.mx : null, my: typeof window.my === "number" ? window.my : null,
      png: c.toDataURL("image/png"),
      vrsta,
    };
  }, [vrsta]);
  await ctx.close();
  const rgba = Buffer.from(info.rgba, "base64");
  const stilovi = info.stilovi.length ? info.stilovi : stiloviPre;
  return { ...info, rgba, sha: createHash("sha256").update(rgba).digest("hex"), stilovi };
}

function razlika(a, b) {
  const s = { ukupno: a.length / 4, razlicitih: 0, unutra: 0, van: 0, alfa: 0, samoRGB: 0, maks: 0, zbir: 0, kanala: 0, hist: {}, bbox: null,
    providnihA: 0, providnihB: 0 };
  let x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1;
  for (let i = 0; i < a.length; i += 4) {
    if (a[i + 3] === 0) s.providnihA++; if (b[i + 3] === 0) s.providnihB++;
    const d = [Math.abs(a[i] - b[i]), Math.abs(a[i + 1] - b[i + 1]), Math.abs(a[i + 2] - b[i + 2]), Math.abs(a[i + 3] - b[i + 3])];
    const m = Math.max(...d);
    if (!m) continue;
    s.razlicitih++;
    const k = i / 4, x = k % W, y = (k / W) | 0;
    if (Math.hypot(x - 720, y - 450) > 422) s.van++; else s.unutra++;
    if (d[3]) s.alfa++; else s.samoRGB++;
    if (m > s.maks) s.maks = m;
    s.zbir += d[0] + d[1] + d[2] + d[3]; s.kanala += 4;
    const korpa = m <= 2 ? String(m) : m <= 8 ? "3-8" : m <= 32 ? "9-32" : m <= 128 ? "33-128" : "129-255";
    s.hist[korpa] = (s.hist[korpa] || 0) + 1;
    if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y;
  }
  s.srednja = s.kanala ? +(s.zbir / s.kanala).toFixed(3) : 0;
  s.bbox = s.razlicitih ? [x0, y0, x1, y1] : null;
  delete s.zbir; delete s.kanala;
  return s;
}

async function heatmap(a, b, ime) {
  const p = await (await browser.newContext({ viewport: { width: 400, height: 300 } })).newPage();
  const mask = Buffer.alloc(W * H);
  for (let i = 0, k = 0; i < a.length; i += 4, k++) {
    const m = Math.max(Math.abs(a[i] - b[i]), Math.abs(a[i + 1] - b[i + 1]), Math.abs(a[i + 2] - b[i + 2]), Math.abs(a[i + 3] - b[i + 3]));
    mask[k] = m ? Math.min(255, 64 + m * 4) : 0;
  }
  const png = await p.evaluate(([m64, W, H]) => {
    const m = Uint8Array.from(atob(m64), c => c.charCodeAt(0));
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const g = c.getContext("2d"); const img = g.createImageData(W, H);
    for (let k = 0; k < m.length; k++) { const v = m[k]; img.data[k * 4] = v; img.data[k * 4 + 1] = v ? 0 : 20; img.data[k * 4 + 2] = v ? 0 : 20; img.data[k * 4 + 3] = 255; }
    g.putImageData(img, 0, 0); return c.toDataURL("image/png");
  }, [mask.toString("base64"), W, H]);
  await writeFile(OUT + ime, Buffer.from(png.split(",")[1], "base64"));
  await p.context().close();
}

const izvestaj = { platforma: process.platform, seme: SEME, viewport: [W, H], strukturno, brojGlow, faze: {} };
let caseA = strukturno;
const log = (...a) => console.log(...a);
log(`Faza 3a: ORIGINAL_MINUS_GLOW strukturno = ${strukturno} (D1 blok nađen ${brojGlow}x)`);

// ── Faze 1 + 2 ───────────────────────────────────────────────────────────
const snimci = {};
for (const tema of ["dark", "light"]) {
  for (const vrsta of ["original", "minus", "prenos"]) {
    const s = await snimi(vrsta, tema);
    snimci[vrsta + "-" + tema] = s;
    await writeFile(OUT + `${vrsta}-${tema}.rgba`, s.rgba);
    await writeFile(OUT + `${vrsta}-${tema}.png`, Buffer.from(s.png.split(",")[1], "base64"));
  }
}
izvestaj.faze.tema = {};
for (const [k, s] of Object.entries(snimci)) {
  const jedinstveni = [...new Set(s.stilovi)];
  izvestaj.faze.tema[k] = { mx: s.mx, my: s.my, mousemove: s.mis, canvas: [s.w, s.h], dpr: s.dpr, bodyClass: s.bodyClass, isL_original: s.isL_original, dataTheme: s.dataTheme,
    tema_prenos: s.tema_prenos, sha256: s.sha, stilovaJedinstvenih: jedinstveni.length, uzorakStilova: jedinstveni.slice(0, 8) };
  log(`Koren    ${k.padEnd(15)} (mx,my)=(${s.mx},${s.my}) mousemove događaja: ${s.mis.length}${s.mis.length ? " prvi " + JSON.stringify(s.mis[0]) : ""}`);
  log(`Faza 1/2 ${k.padEnd(15)} canvas ${s.w}x${s.h} dpr ${s.dpr} body="${s.bodyClass}" data-theme="${s.dataTheme}" sha=${s.sha.slice(0, 16)}`);
  log(`           stilovi: ${jedinstveni.slice(0, 5).join(" | ")}`);
}

// Stari oracle (ORIGINAL sa sjajem vs PRENOS), radi poređenja sa CI nalazom.
izvestaj.faze.stariOracle = {};
for (const tema of ["dark", "light"]) {
  const d = razlika(snimci["original-" + tema].rgba, snimci["prenos-" + tema].rgba);
  izvestaj.faze.stariOracle[tema] = d;
  await heatmap(snimci["original-" + tema].rgba, snimci["prenos-" + tema].rgba, `heatmap-stari-oracle-${tema}.png`);
  log(`Stari oracle ${tema}: različitih ${d.razlicitih} (unutra ${d.unutra}, van ${d.van}), maks ${d.maks}, srednja ${d.srednja}, alfa ${d.alfa}, samo RGB ${d.samoRGB}, bbox ${JSON.stringify(d.bbox)}, hist ${JSON.stringify(d.hist)}, providnih ${d.providnihA}/${d.providnihB}`);
}

// ── Faza 4: ORIGINAL_MINUS_GLOW vs PRENOS, ceo canvas, 3 ponavljanja ──────
izvestaj.faze.noviOracle = {};
for (const tema of ["dark", "light"]) {
  const rezultati = [];
  for (let r = 0; r < 3; r++) {
    const m = r === 0 ? snimci["minus-" + tema] : await snimi("minus", tema);
    const n = r === 0 ? snimci["prenos-" + tema] : await snimi("prenos", tema);
    const d = razlika(m.rgba, n.rgba);
    rezultati.push({ razlicitih: d.razlicitih, maks: d.maks, shaMinus: m.sha.slice(0, 16), shaPrenos: n.sha.slice(0, 16) });
    if (d.razlicitih) { caseA = false; await heatmap(m.rgba, n.rgba, `heatmap-novi-oracle-${tema}-${r}.png`); izvestaj.faze.noviOracle[tema + "-detalj-" + r] = d; }
  }
  izvestaj.faze.noviOracle[tema] = rezultati;
  log(`Faza 4 ${tema}: ORIGINAL_MINUS_GLOW vs PRENOS (ceo canvas) → ${rezultati.map(x => x.razlicitih).join(", ")} različitih piksela u 3 ponavljanja`);
}

// ── Faza 5: D1 negativna kontrola ────────────────────────────────────────
izvestaj.faze.d1 = {};
for (const tema of ["dark", "light"]) {
  const d = razlika(snimci["original-" + tema].rgba, snimci["minus-" + tema].rgba);
  izvestaj.faze.d1[tema] = d;
  await heatmap(snimci["original-" + tema].rgba, snimci["minus-" + tema].rgba, `heatmap-d1-${tema}.png`);
  const materijalno = d.razlicitih > 10000;
  if (!materijalno) caseA = false;
  log(`Faza 5 ${tema}: ORIGINAL vs ORIGINAL_MINUS_GLOW → ${d.razlicitih} različitih (unutra ${d.unutra}, van ${d.van}), maks ${d.maks} — ${materijalno ? "sjaj detektovan" : "SJAJ NIJE DETEKTOVAN"}`);
}

izvestaj.caseA = caseA;
await writeFile(OUT + "forensic.json", JSON.stringify(izvestaj, null, 2));
await browser.close(); srv.kill();
log(`\nCASE ${caseA ? "A: ORIGINAL_MINUS_GLOW == PRENOS (dark+light, ceo canvas, 3x) i D1 detektovan" : "B/nerešeno — vidi shots/forensic/forensic.json"}`);
process.exit(caseA ? 0 : 1);
