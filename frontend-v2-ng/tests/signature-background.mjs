// Vindex V2 NG — ciljane provere potpisne pozadine (Phase B).
// Pokretanje: `node serve.mjs`, pa `node tests/signature-background.mjs`.
// Rezultat: shots/background-results.json|md + snimci/video poređenja u shots/pozadina/

import { chromium } from "playwright";
import { mkdir, writeFile, rename, readdir, rm, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const BASE = process.env.VX_URL || "http://127.0.0.1:4317/";
const OUT = fileURLToPath(new URL("../shots/pozadina/", import.meta.url));
await mkdir(OUT, { recursive: true });
const rezultati = [];
const greske = [];
function zapisi(grupa, naziv, prolazi, detalj = "") {
  rezultati.push({ grupa, naziv, prolazi: !!prolazi, detalj: String(detalj) });
  console.log(`${prolazi ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

const browser = await chromium.launch();

/* Brojanje slušalaca: koliko ih je modul dodao i da li ih je sve uklonio. */
const SPIJUN = () => {
  const zivi = new Map(); let id = 0;
  const kljuc = (c, t, f) => { if (!f.__vxId) f.__vxId = ++id; const ime = c === window ? "window" : c === document ? "document" : c instanceof MediaQueryList ? "mql:" + c.media : "drugo"; return ime + "|" + t + "|" + f.__vxId; };
  const add = EventTarget.prototype.addEventListener, rem = EventTarget.prototype.removeEventListener;
  window.__vxSlusaoci = { aktivni: () => [...zivi.keys()], snimak: null };
  EventTarget.prototype.addEventListener = function (t, f, o) { if (f) zivi.set(kljuc(this, t, f), 1); return add.call(this, t, f, o); };
  EventTarget.prototype.removeEventListener = function (t, f, o) { if (f) zivi.delete(kljuc(this, t, f)); return rem.call(this, t, f, o); };
  const MO = window.MutationObserver; let aktivniMO = 0;
  window.MutationObserver = class extends MO { observe(...a) { aktivniMO++; this.__ziv = true; return super.observe(...a); } disconnect() { if (this.__ziv) { aktivniMO--; this.__ziv = false; } return super.disconnect(); } };
  window.__vxMO = () => aktivniMO;
};

async function stranica({ w = 1440, h = 900, dpr = 1, motion = "no-preference", seme, tema = "dark", spijun = false, put = "", rafHz, pre } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr, reducedMotion: motion });
  await ctx.addInitScript(([t]) => { try { localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", "puna"); } catch (e) {} }, [tema]);
  if (seme !== undefined) await ctx.addInitScript(s => { window.VX_BG_SEED = s; }, seme);
  if (spijun) await ctx.addInitScript(SPIJUN);
  if (rafHz) await ctx.addInitScript(hz => {
    // Simulirani monitor od `hz` Hz: rAF okida na 1000/hz ms sa stvarnim vremenom.
    const per = 1000 / hz; let sledeci = 1; const cekaju = new Map();
    window.requestAnimationFrame = f => { const id = sledeci++; cekaju.set(id, setTimeout(() => { cekaju.delete(id); f(performance.now()); }, per)); return id; };
    window.cancelAnimationFrame = id => { clearTimeout(cekaju.get(id)); cekaju.delete(id); };
  }, rafHz);
  const p = await ctx.newPage();
  p.on("pageerror", e => greske.push(String(e)));
  p.on("console", m => { if (m.type() === "error") greske.push(m.text()); });
  if (pre) await pre(p);
  await p.goto(BASE + put);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(120);
  return p;
}
const pikseli = (p, sel = "canvas") => p.$eval(sel, c => Array.from(c.getContext("2d").getImageData(0, 0, c.width, c.height).data));
const snimakPlatna = (p, sel = "#pozadina") => p.$eval(sel, c => c.toDataURL());
const instanca = (p, izraz) => p.evaluate(izraz);

// ── 1. Vernost originalu (piksel po piksel) ─────────────────────────────
// Odobreni ugovor: PRENOS == ORIGINAL BEZ odobrenog D1 bloka sjaja — ceo canvas,
// egzaktno, isto seme, prvi frejm. Referenca ORIGINAL_MINUS_GLOW se pravi
// deterministički iz original.html uklanjanjem TAČNO tog bloka (proverava se).
//
// Zašto ne „van kruga r=422 oko centra“ (stari oracle): sjaj originala je
// centriran na (mx,my) koje prati `mousemove`. Na Linux Chromium-u stiže
// sintetički mousemove u (0,0) pre svetlog frejma, pa je sjaj originala u uglu,
// a stari oracle je merio pogrešnu zonu (NS002A, run 37659688255: 128071 razlika
// van kruga, 0 unutra). Prenos je i tamo bio piksel-identičan ORIGINAL_MINUS_GLOW.
const ORIGINAL_HTML = await readFile(fileURLToPath(new URL("./fixtures/original.html", import.meta.url)), "utf8");
const D1_SJAJ = "var g=ctx.createRadialGradient(mx,my,0,mx,my,420);g.addColorStop(0,'rgba('+rgb+','+(isL?'0.05':'0.07')+')');g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);";
const iSjaj = ORIGINAL_HTML.indexOf(D1_SJAJ);
const BEZ_SJAJA = ORIGINAL_HTML.slice(0, iSjaj) + ORIGINAL_HTML.slice(iSjaj + D1_SJAJ.length);
// Strukturni uslov je deo provere vernosti: bez ispravne reference nema prolaza.
const referencaIspravna = iSjaj >= 0 && ORIGINAL_HTML.split(D1_SJAJ).length === 2 &&
  BEZ_SJAJA.length === ORIGINAL_HTML.length - D1_SJAJ.length && !/createRadialGradient|addColorStop/.test(BEZ_SJAJA);
const SVETLO_ORIGINAL = () => { document.body.classList.add("light-theme"); ctx.clearRect(0, 0, W, H); for (const p of pts) { p.x -= p.vx; p.y -= p.vy; p.t -= .007; } drawBg(); };
const bezSjaja = (p) => p.route("**/tests/fixtures/__original-bez-sjaja.html*", r => r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: BEZ_SJAJA }));
const razlicitih = (a, b) => { let r = 0; for (let i = 0; i < a.length; i += 4) if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2] || a[i + 3] !== b[i + 3]) r++; return r; };
for (const tema of ["dark", "light"]) {
  const svetla = tema === "light";
  const pm = await stranica({ put: `tests/fixtures/__original-bez-sjaja.html?seed=42&zamrzni=1`, pre: bezSjaja });
  if (svetla) await pm.evaluate(SVETLO_ORIGINAL);
  const po = await stranica({ put: `tests/fixtures/original.html?seed=42&zamrzni=1` });
  if (svetla) await po.evaluate(SVETLO_ORIGINAL);
  const pn = await stranica({ put: `tests/fixtures/prenos.html?seed=42&zamrzni=1` });
  if (svetla) await pn.evaluate(() => { document.documentElement.dataset.theme = "light"; inst.destroy(); window.inst = VindexSignatureBackground.mount(document.getElementById("pozadina-test"), { seed: 42, rucno: true }); inst.frejm(1); });
  const [m, o, n] = [await pikseli(pm), await pikseli(po), await pikseli(pn)];
  const razl = razlicitih(m, n), sjaj = razlicitih(o, m);
  zapisi(`vernost ${tema}`, "prenos == original bez D1 sjaja: CEO canvas piksel-identičan (isto seme, prvi frejm)", referencaIspravna && m.length === 1440 * 900 * 4 && razl === 0, `referenca ${referencaIspravna ? "ispravna" : "NEISPRAVNA"}; ${razl} različitih od ${m.length / 4} piksela`);
  zapisi(`vernost ${tema}`, "D1 negativna kontrola: original sa sjajem se materijalno razlikuje od originala bez sjaja", sjaj > 10000, `${sjaj} piksela`);
  await pm.context().close(); await po.context().close(); await pn.context().close();
}

// ── 2. Determinizam: seme samo u testu ─────────────────────────────────
{
  const a = await stranica({ motion: "reduce", seme: 7 }); const b = await stranica({ motion: "reduce", seme: 7 });
  zapisi("determinizam", "isto seme → identična statična tekstura", (await snimakPlatna(a)) === (await snimakPlatna(b)));
  await a.context().close(); await b.context().close();
  const c = await stranica({ motion: "reduce" }); const d = await stranica({ motion: "reduce" });
  zapisi("determinizam", "bez semena (produkcioni režim) → Math.random, raspored se razlikuje", (await snimakPlatna(c)) !== (await snimakPlatna(d)));
  await c.context().close(); await d.context().close();
}

// ── 3. Nezavisnost od frekvencije osvežavanja ──────────────────────────
{
  const p = await stranica({ put: "tests/fixtures/prenos.html?seed=9&zamrzni=1" });
  const r = await p.evaluate(() => {
    const mk = () => VindexSignatureBackground.mount(document.createElement("canvas"), { seed: 9, rucno: true });
    const res = {}; const pocetak = mk().tacke();
    for (const hz of [60, 120, 144, 30]) { const i = mk(); i.napreduj(3000, 1000 / hz); res[hz] = i.tacke(); }
    // Originalno pravilo prelaska ivice (x>W → 0) odbacuje ostatak koraka, pa tačka koja pređe
    // ivicu može odstupiti najviše za jedan korak. Ostale tačke i faze moraju biti identične.
    const presla = res[60].map((p, k) => Math.abs(p.x - pocetak[k].x) > 20 || Math.abs(p.y - pocetak[k].y) > 20);
    const out = { faza: 0, cele: 0, ivica: 0, brojIvica: presla.filter(Boolean).length };
    for (const hz of [120, 144, 30]) res[hz].forEach((p, k) => {
      const q = res[60][k]; const dpos = Math.max(Math.abs(p.x - q.x), Math.abs(p.y - q.y));
      out.faza = Math.max(out.faza, Math.abs(p.t - q.t));
      if (presla[k]) out.ivica = Math.max(out.ivica, dpos); else out.cele = Math.max(out.cele, dpos);
    });
    return out;
  });
  zapisi("frekvencija", "posle 3 s: 60/120/144/30 Hz — faze treperenja identične", r.faza < 1e-9, `najveće odstupanje faze ${r.faza.toExponential(1)}`);
  zapisi("frekvencija", "posle 3 s: pozicije tačaka koje nisu prešle ivicu identične", r.cele < 1e-6, `najveće odstupanje ${r.cele.toExponential(1)} px`);
  zapisi("frekvencija", "tačke koje pređu ivicu: odstupanje ≤ jedan korak originala (0,09 px) — posledica originalnog pravila prelaska", r.ivica <= 0.09,
    `${r.brojIvica} tačaka prešlo ivicu, najveće odstupanje ${r.ivica.toFixed(3)} px`);
  await p.context().close();

  // Stvarna petlja sa simuliranim monitorom: brzina faze po milisekundi mora biti ista.
  const brzine = {};
  for (const hz of [60, 120]) {
    const q = await stranica({ seme: 3, rafHz: hz });
    await q.waitForTimeout(300);
    const a = await q.evaluate(() => ({ t: __vxPozadinaInstanca.tacke()[0].t, f: __vxPozadina.frames, ms: performance.now() }));
    await q.waitForTimeout(2000);
    const b = await q.evaluate(() => ({ t: __vxPozadinaInstanca.tacke()[0].t, f: __vxPozadina.frames, ms: performance.now() }));
    brzine[hz] = { poMs: (b.t - a.t) / (b.ms - a.ms), frejmova: b.f - a.f };
    await q.context().close();
  }
  const ocek = 0.007 / (1000 / 60);
  const odst = Math.max(...[60, 120].map(h => Math.abs(brzine[h].poMs / ocek - 1)));
  zapisi("frekvencija", "stvarna petlja: 120 Hz crta ~2× više frejmova, ali kretanje je iste brzine", brzine[120].frejmova > 1.5 * brzine[60].frejmova && odst < 0.08,
    `60 Hz: ${brzine[60].frejmova} frejmova, 120 Hz: ${brzine[120].frejmova}; odstupanje brzine od originala pri 60 Hz ≤ ${(odst * 100).toFixed(1)}%`);
}

// ── 4. Teme ─────────────────────────────────────────────────────────────
/* Špijun na nivou prototipa: koje rgb boje modul stvarno zadaje platnu. */
const SPIJUN_BOJA = () => {
  window.__vxBoje = new Set();
  for (const prop of ["fillStyle", "strokeStyle"]) {
    const d = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, prop);
    Object.defineProperty(CanvasRenderingContext2D.prototype, prop, { configurable: true, get() { return d.get.call(this); },
      set(v) { if (this.canvas && this.canvas.id === "pozadina" && typeof v === "string") { const m = v.match(/^rgba\((\d+,\d+,\d+),/); if (m) window.__vxBoje.add(m[1]); } d.set.call(this, v); } });
  }
};
for (const motion of ["no-preference", "reduce"]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: motion });
  await ctx.addInitScript(() => { try { localStorage.setItem("vx-ng-tema", "dark"); } catch (e) {} window.VX_BG_SEED = 5; });
  await ctx.addInitScript(SPIJUN_BOJA);
  const p = await ctx.newPage(); await p.goto(BASE); await p.waitForTimeout(200);
  const tamna = await p.evaluate(() => [...__vxBoje]);
  const platnoTamno = await snimakPlatna(p);
  if (motion === "reduce") {
    // Statičan režim: jedini novi frejm nastaje u trenutku promene teme.
    await p.evaluate(() => __vxBoje.clear());
    await p.click("#theme-toggle");
  } else {
    await p.click("#theme-toggle");
    // Frejm koji je već bio u toku pre klika sme biti tamni; meri se tek od sledećih frejmova.
    await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    await p.evaluate(() => __vxBoje.clear());
  }
  await p.waitForTimeout(200);
  const svetla = await p.evaluate(() => [...__vxBoje]);
  const g = `tema (${motion === "reduce" ? "reduced-motion" : "animacija"})`;
  zapisi(g, "Dark crta isključivo originalnim cyan-om 0,212,255", JSON.stringify(tamna) === '["0,212,255"]', JSON.stringify(tamna));
  zapisi(g, "posle prebacivanja Light crta isključivo originalnim 0,153,187", JSON.stringify(svetla) === '["0,153,187"]', JSON.stringify(svetla));
  zapisi(g, "slika na platnu se promenila sa temom", (await snimakPlatna(p)) !== platnoTamno);
  await ctx.close();
}
{
  // Tačne vrednosti boja i prozirnosti iz koda modula (nema pojačanja cyan-a).
  const p = await stranica({ put: "tests/fixtures/prenos.html?seed=1&zamrzni=1" });
  const stilovi = await p.evaluate(() => {
    const c = document.createElement("canvas"); const ctx = c.getContext("2d"); const vidjeno = new Set();
    const fs = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, "fillStyle");
    const ss = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, "strokeStyle");
    Object.defineProperty(ctx, "fillStyle", { set(v) { vidjeno.add("fill " + v.replace(/,[0-9.]+\)$/, ",α)")); fs.set.call(this, v); }, get() { return fs.get.call(this); } });
    Object.defineProperty(ctx, "strokeStyle", { set(v) { vidjeno.add("stroke " + v.replace(/,[0-9.e-]+\)$/, ",α)")); ss.set.call(this, v); }, get() { return ss.get.call(this); } });
    c.getContext = () => ctx;
    const out = {};
    for (const t of ["dark", "light"]) { vidjeno.clear(); document.documentElement.dataset.theme = t; const i = VindexSignatureBackground.mount(c, { seed: 1, rucno: true }); i.frejm(1); out[t] = [...vidjeno].sort(); }
    return out;
  });
  zapisi("tema", "korišćene samo originalne boje, bez gradijenata/sjaja",
    JSON.stringify(stilovi.dark) === JSON.stringify(["fill rgba(0,212,255,α)", "stroke rgba(0,212,255,α)"]) &&
    JSON.stringify(stilovi.light) === JSON.stringify(["fill rgba(0,153,187,α)", "stroke rgba(0,153,187,α)"]), JSON.stringify(stilovi));
  await p.context().close();
}

// ── 5. Reduced-motion ──────────────────────────────────────────────────
{
  const p = await stranica({ motion: "reduce", seme: 11 });
  const a = await snimakPlatna(p); const f1 = await p.evaluate(() => __vxPozadina.frames);
  await p.waitForTimeout(1500);
  const b = await snimakPlatna(p); const f2 = await p.evaluate(() => __vxPozadina.frames);
  zapisi("reduced-motion", "nema petlje; statična tekstura nepromenjena 1,5 s", f1 === f2 && a === b && !(await p.evaluate(() => __vxPozadina.animira)), `frejmova: ${f1} → ${f2}`);
  zapisi("reduced-motion", "tekstura vidljiva (mreža + tačke + linije, nije prazno)", await p.$eval("#pozadina", c => { const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n > 5000; }));
  await p.click("#theme-toggle"); await p.waitForTimeout(100);
  zapisi("reduced-motion", "promena teme ponovo iscrta statičnu teksturu (jedan frejm, bez pokreta)", (await snimakPlatna(p)) !== b && (await p.evaluate(() => __vxPozadina.frames)) === f2 + 1);
  await p.setViewportSize({ width: 1280, height: 800 }); await p.waitForTimeout(150);
  zapisi("reduced-motion", "promena veličine ponovo iscrta statičnu teksturu u novoj veličini", (await p.$eval("#pozadina", c => c.width)) === 1280 && !(await p.evaluate(() => __vxPozadina.animira)));
  await p.context().close();
  const q = await stranica({ motion: "no-preference", seme: 11 });
  await q.emulateMedia({ reducedMotion: "reduce" }); await q.waitForTimeout(100);
  const g1 = await q.evaluate(() => __vxPozadina.frames); await q.waitForTimeout(800);
  zapisi("reduced-motion", "uključivanje reduced-motion u toku rada zaustavlja animaciju", !(await q.evaluate(() => __vxPozadina.animira)) && (await q.evaluate(() => __vxPozadina.frames)) === g1);
  await q.emulateMedia({ reducedMotion: "no-preference" }); await q.waitForTimeout(500);
  zapisi("reduced-motion", "isključivanje vraća animaciju", (await q.evaluate(() => __vxPozadina.animira)) && (await q.evaluate(() => __vxPozadina.frames)) > g1);
  await q.context().close();
}

// ── 6. Vidljivost stranice: pauza i nastavak bez skoka ─────────────────
{
  const p = await stranica({ seme: 13 });
  const sakrij = async v => p.evaluate(h => { Object.defineProperty(document, "hidden", { configurable: true, get: () => h }); document.dispatchEvent(new Event("visibilitychange")); }, v);
  await p.waitForTimeout(300);
  await sakrij(true);
  const pre = await p.evaluate(() => ({ t: __vxPozadinaInstanca.tacke().map(x => x.t), f: __vxPozadina.frames }));
  await p.waitForTimeout(1500);
  const tokom = await p.evaluate(() => ({ f: __vxPozadina.frames, a: __vxPozadina.animira }));
  zapisi("vidljivost", "skrivena stranica: nema crtanja", tokom.f === pre.f && !tokom.a, `frejmova tokom 1,5 s: ${tokom.f - pre.f}`);
  // Napredak posle povratka mora odgovarati SAMO vremenu proteklom od povratka.
  // (Zaštita od 100 ms bi i bez reseta ograničila skok na 6 frejmova — zato se meri precizno.)
  const posle = await p.evaluate(() => new Promise(res => {
    const t0 = performance.now();
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
    requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() =>
      res({ t: __vxPozadinaInstanca.tacke().map(x => x.t), a: __vxPozadina.animira, ms: performance.now() - t0 }))));
  }));
  const pomak = Math.max(...posle.t.map((t, k) => t - pre.t[k])) / 0.007;   // u frejmovima originala
  const dozvoljeno = posle.ms / (1000 / 60) + 1.5;
  zapisi("vidljivost", "nastavak bez vremenskog skoka: napredak ≤ vreme od povratka (+1,5 frejma tolerancije)", posle.a && pomak > 0 && pomak <= dozvoljeno,
    `napredak ${pomak.toFixed(2)} frejma za ${posle.ms.toFixed(0)} ms posle povratka (dozvoljeno ≤ ${dozvoljeno.toFixed(2)}); pauza je trajala 1,5 s ≈ 90 frejmova`);
  await p.context().close();
}

// ── 7. Oslobađanje resursa (destroy) ───────────────────────────────────
{
  const p = await stranica({ seme: 17, spijun: true });
  const prije = await p.evaluate(() => ({ s: __vxSlusaoci.aktivni(), mo: __vxMO() }));
  // Samo slušaoci ovog modula; app.js ima svoje (max-width) za fioke i oni nisu predmet provere.
  const nase = prije.s.filter(k => /^window\|resize\||^document\|visibilitychange\||^mql:\(prefers-reduced-motion|^mql:\(resolution/.test(k));
  await p.evaluate(() => __vxPozadinaInstanca.destroy());
  const posle = await p.evaluate(() => ({ s: __vxSlusaoci.aktivni(), mo: __vxMO(), f: __vxPozadina.frames, a: __vxPozadina.animira }));
  const preostali = nase.filter(k => posle.s.includes(k));
  zapisi("destroy", "svi slušaoci modula uklonjeni (resize, visibilitychange, reduced-motion, DPR)", nase.length >= 4 && preostali.length === 0, `registrovano ${nase.length}, preostalo ${preostali.length}: ${preostali.join(", ")}`);
  zapisi("destroy", "MutationObserver teme odjavljen", posle.mo === prije.mo - 1, `aktivnih: ${prije.mo} → ${posle.mo}`);
  zapisi("destroy", "modul ne registruje `mousemove` (D1: nema praćenja kursora)", !prije.s.some(k => k.includes("|mousemove|")));
  await p.waitForTimeout(600);
  const f2 = await p.evaluate(() => __vxPozadina.frames);
  zapisi("destroy", "animaciona petlja zaustavljena", !posle.a && f2 === posle.f, `frejmova posle destroy: ${f2 - posle.f}`);
  zapisi("destroy", "platno očišćeno", await p.$eval("#pozadina", c => { const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < d.length; i += 4) if (d[i]) return false; return true; }));
  await p.setViewportSize({ width: 1200, height: 800 }); await p.click("#theme-toggle"); await p.waitForTimeout(200);
  zapisi("destroy", "posle destroy ni resize ni promena teme ne crtaju", (await p.evaluate(() => __vxPozadina.frames)) === f2);
  await p.evaluate(() => { window.__nova = VindexSignatureBackground.mount(document.getElementById("pozadina"), { seed: 17 }); });
  await p.waitForTimeout(300);
  zapisi("destroy", "ponovno montiranje radi", await p.evaluate(() => __nova.stat.animira && __nova.stat.frames > 5));
  await p.context().close();
}

// ── 8. Interakcije: platno ništa ne presreće ───────────────────────────
{
  const p = await stranica({ seme: 19 });
  const r = await p.evaluate(() => {
    const c = document.getElementById("pozadina"); let pogodaka = 0, tacaka = 0;
    for (let x = 5; x < innerWidth; x += 37) for (let y = 5; y < innerHeight; y += 29) { tacaka++; if (document.elementFromPoint(x, y) === c) pogodaka++; }
    return { pe: getComputedStyle(c).pointerEvents, pogodaka, tacaka, tab: c.tabIndex, aria: c.getAttribute("aria-hidden") };
  });
  zapisi("interakcije", "pointer-events: none; nijedna tačka ekrana ne pogađa platno", r.pe === "none" && r.pogodaka === 0, `${r.tacaka} uzoraka, pogodaka: ${r.pogodaka}`);
  zapisi("interakcije", "platno nije fokusabilno i skriveno je od čitača ekrana", r.tab === -1 && r.aria === "true");
  await p.mouse.click(60, 162);
  zapisi("interakcije", "klik u ljusci (preko teksture) stiže do navigacije", (await p.textContent("#status")).includes("Znanje"));
  await p.context().close();
}

// ── 9. DPR i rezolucija platna ─────────────────────────────────────────
for (const [w, h, dpr, ocek] of [[1440, 900, 1, [1440, 900]], [1440, 900, 2, [2880, 1800]], [1920, 1080, 2, null], [2560, 1440, 2, null]]) {
  const p = await stranica({ w, h, dpr, motion: "reduce", seme: 23 });
  const s = await p.evaluate(() => ({ dpr: __vxPozadina.dpr, px: __vxPozadina.platnoPx, css: [innerWidth, innerHeight] }));
  const ukupno = s.px[0] * s.px[1];
  const ok = ocek ? s.px[0] === ocek[0] && s.px[1] === ocek[1] : ukupno <= 1440 * 900 * 4 + 5000 && s.dpr >= 1 && s.dpr < dpr;
  zapisi("DPR", `${w}×${h} pri DPR ${dpr}`, ok, `platno ${s.px[0]}×${s.px[1]} (${(ukupno / 1e6).toFixed(2)} Mpx), efektivni DPR ${s.dpr.toFixed(2)}`);
  await p.context().close();
}
{
  const p = await stranica({ seme: 29 });
  await p.setViewportSize({ width: 1100, height: 700 }); await p.waitForTimeout(150);
  zapisi("DPR", "promena veličine prozora prilagođava platno", (await p.$eval("#pozadina", c => [c.width, c.height].join("×"))) === "1100×700");
  await p.context().close();
}

// ── 10. D4: tekstura samo u ljusci ─────────────────────────────────────
for (const tema of ["dark", "light"]) {
  const p = await stranica({ seme: 31, tema });
  const r = await p.evaluate(() => {
    const ocekivano = { glavni: getComputedStyle(document.getElementById("glavni")).backgroundColor, panel: getComputedStyle(document.getElementById("panel")).backgroundColor };
    return ocekivano;
  });
  // Uzorci iz praznih delova radnih površina na stvarnom snimku ekrana.
  const png = await p.screenshot();
  const zone = await p.evaluate(() => {
    const g = document.getElementById("glavni").getBoundingClientRect(), pn = document.querySelector(".panel__foot").getBoundingClientRect();
    return { glavni: [g.left + 260, 92, g.right - 380, 98], panel: [pn.left, pn.bottom + 20, pn.right, pn.bottom + 60] };
  });
  const st = await p.evaluate(async ({ b64, zone }) => {
    const img = new Image(); img.src = "data:image/png;base64," + b64; await img.decode();
    const c = new OffscreenCanvas(img.width, img.height); const x = c.getContext("2d"); x.drawImage(img, 0, 0);
    const out = {};
    for (const [k, [x0, y0, x1, y1]] of Object.entries(zone)) {
      const d = x.getImageData(x0, y0, x1 - x0, y1 - y0).data; const boje = new Set();
      for (let i = 0; i < d.length; i += 4) boje.add(d[i] + "," + d[i + 1] + "," + d[i + 2]);
      out[k] = [...boje];
    }
    return out;
  }, { b64: png.toString("base64"), zone });
  const rgb = s => s.match(/\d+/g).slice(0, 3).join(",");
  zapisi(`D4 ${tema}`, "lista predmeta: čista neprozirna površina (jedna boja, bez tačaka/linija)", st.glavni.length === 1 && st.glavni[0] === rgb(r.glavni), `boje u uzorku: ${st.glavni.join(" | ")}`);
  zapisi(`D4 ${tema}`, "panel: čista neprozirna površina", st.panel.length === 1 && st.panel[0] === rgb(r.panel), `boje u uzorku: ${st.panel.join(" | ")}`);
  await p.context().close();
}

// ── 11. Snimci i video za vizuelno poređenje ───────────────────────────
for (const tema of ["dark", "light"]) {
  const p = await stranica({ seme: 42, tema });
  await p.waitForTimeout(1500);
  await p.screenshot({ path: OUT + `ui-1440x900-${tema}.png` });
  await p.setViewportSize({ width: 1280, height: 800 }); await p.waitForTimeout(400);
  await p.screenshot({ path: OUT + `ui-1280x800-${tema}.png` });
  await p.context().close();
}
{
  const po = await stranica({ put: "tests/fixtures/original.html?seed=42&zamrzni=1" });
  await po.screenshot({ path: OUT + "poredjenje-original-1440x900.png" }); await po.context().close();
  const pn = await stranica({ put: "tests/fixtures/prenos.html?seed=42&zamrzni=1" });
  await pn.screenshot({ path: OUT + "poredjenje-prenos-1440x900.png" }); await pn.context().close();
  // Uvećan isečak: ugao gde nema sjaja — treba da izgleda isto.
  for (const [ime, put] of [["original", "tests/fixtures/original.html"], ["prenos", "tests/fixtures/prenos.html"]]) {
    const q = await stranica({ put: put + "?seed=42&zamrzni=1", dpr: 2 });
    await q.screenshot({ path: OUT + `poredjenje-${ime}-isecak-2x.png`, clip: { x: 0, y: 0, width: 360, height: 225 } });
    await q.context().close();
  }
}
// Video (pokret se ne vidi na PNG-u). Snimljeno u headless Chromium-u, 1440×900.
async function video(ime, put, sek, tema = "dark") {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: OUT + "_tmp/", size: { width: 1440, height: 900 } } });
  await ctx.addInitScript(([t]) => { try { localStorage.setItem("vx-ng-tema", t); } catch (e) {} }, [tema]);
  const p = await ctx.newPage(); await p.goto(BASE + put); await p.waitForTimeout(sek * 1000);
  const v = p.video(); await ctx.close();
  await rename(await v.path(), OUT + ime + ".webm");
}
await video("video-ui-dark-8s", "", 8);
await video("video-ui-light-8s", "", 8, "light");
await video("video-original-8s", "tests/fixtures/original.html", 8);
await rm(OUT + "_tmp/", { recursive: true, force: true });

zapisi("konzola", "bez grešaka u konzoli", greske.length === 0, greske.slice(0, 3).join(" | "));
await browser.close();

const prolazi = rezultati.filter(r => r.prolazi).length;
await writeFile(OUT + "../background-results.json", JSON.stringify({ prolazi, ukupno: rezultati.length, rezultati }, null, 2));
await writeFile(OUT + "../background-results.md", [`# Potpisna pozadina — rezultati`, ``, `**${prolazi}/${rezultati.length} prolazi.** Ponašanje i vernost, ne vizuelni kvalitet.`, ``,
  `| Grupa | Provera | Ishod | Detalj |`, `|---|---|---|---|`, ...rezultati.map(r => `| ${r.grupa} | ${r.naziv} | ${r.prolazi ? "PASS" : "**FAIL**"} | ${r.detalj.replace(/\|/g, "/")} |`)].join("\n"));
console.log(`\n${prolazi}/${rezultati.length} prolazi`);
process.exit(prolazi === rezultati.length ? 0 : 1);
