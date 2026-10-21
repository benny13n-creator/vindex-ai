// Vindex V2 NG — NS003 Task 4: kanonski Vindex identitet (samo V2).
// Pokretanje: `node tests/brand-identity.mjs` (sam podiže HEAD i foundation server; treba git).
//
// Dokazuje, u stvarnom Chromium-u, za svaku temu i stanje ekrana:
//   • bajtovi runtime logoa = kanonski fajlovi (SHA-256), u brand/ nema ničeg drugog;
//   • tamna tema → ceo znak u zlatu, svetla → originalne boje (oba providni PNG izdvojen
//     1:1 iz slike osnivača, Website V3 2026-10-21; scripts/brand/izdvoji_logo.py);
//   • bez rastezanja, isecanja, filtera, sjaja, senke, maske, transformacije;
//   • gornja traka i sve kontrole: isti okviri kao foundation 1eb20976;
//   • svetla traka #F6F7F8, kontrole čitljive; tamna traka nepromenjena;
//   • providne oblasti SVG-a = površina trake u obe teme (nema kutije ni oreola);
//   • nema preliva; link, ime za čitač ekrana i tastatura nepromenjeni.

import { chromium } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { LOGO, SVETLA_TRAKA, brendUgovor, proveriBrend, proveriKontrast } from "./fixtures/brand-contract.mjs";

const KOREN = fileURLToPath(new URL("..", import.meta.url));
const REPO = fileURLToPath(new URL("../..", import.meta.url));
const FOUNDATION = "1eb20976";
const EXT = fileURLToPath(new URL("./fixtures/zoom-ext", import.meta.url));
const OUT = fileURLToPath(new URL("../shots/brand/", import.meta.url));
await mkdir(OUT, { recursive: true });

let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

// ── 1. Integritet izvora (bez pregledača) ───────────────────────────────
const KANON = {
  "vindex-logo-tamna.png": "b075aba3a0eb8c3a303e64e4b7f9b594090e2f2bce1e7d0dae6f7a072f81bb71",
  "vindex-logo-svetla.png": "8ef61a5accd6a276db94ac69f05b2ab1e680587bc6355d79dce3154c87476b5d",
};
const brand = (await readdir(join(KOREN, "brand"))).sort();
zapisi("integritet", "brand/ sadrži SAMO dva runtime fajla (bez reference, vektora, ikonica, PDF-a, manifesta)", JSON.stringify(brand) === JSON.stringify(Object.keys(KANON).sort()), brand.join(","));
for (const [ime, sha] of Object.entries(KANON)) {
  const h = createHash("sha256").update(await readFile(join(KOREN, "brand", ime))).digest("hex");
  zapisi("integritet", `${ime}: SHA-256 = kanonski fajl`, h === sha, h.slice(0, 16));
}
const index = await readFile(join(KOREN, "index.html"), "utf8");
const css = await readFile(join(KOREN, "src/app.css"), "utf8");
const izvorni = [index, css, ...(await Promise.all((await readdir(join(KOREN, "src"))).map(f => readFile(join(KOREN, "src", f), "utf8"))))].join("\n");
zapisi("integritet", "logo nije ugrađen kao data:/base64 u HTML, CSS ili JS (servira se kao statički fajl)", !/data:image|base64,/.test(izvorni));
zapisi("integritet", "nema tehničkog vektora, favicon-a ni manifest-a u V2", !/Technical_(White|Black)_VECTOR|rel="(icon|manifest|apple-touch-icon)"/.test(izvorni));
const SRC = (index.match(/<a class="wordmark"[\s\S]*?<\/a>/) || [""])[0];
zapisi("integritet", "oznaka linka: dva <img alt=\"\"> sa odobrenim fajlovima i izvornim width/height",
  SRC.includes(`src="${LOGO.dark.fajl}" alt="" width="357" height="305"`) && SRC.includes(`src="${LOGO.light.fajl}" alt="" width="357" height="305"`) && (SRC.match(/<img/g) || []).length === 2);

// ── 2. Serveri: HEAD i foundation ───────────────────────────────────────
const refDir = await mkdtemp(join(tmpdir(), "vx-brand-ref-"));
let referenca = true;
try {
  await writeFile(join(refDir, "ref.tar"), execFileSync("git", ["archive", "--format=tar", FOUNDATION, "frontend-v2-ng"], { cwd: REPO, maxBuffer: 64 * 1024 * 1024 }));
  execFileSync("tar", ["-xf", "ref.tar"], { cwd: refDir });
} catch { referenca = false; }
zapisi("referenca", `foundation ${FOUNDATION} izvučen iz git-a`, referenca);
const server = (dir, port) => spawn(process.execPath, ["serve.mjs", String(port)], { cwd: dir, stdio: "ignore" });
async function spreman(port) {
  for (let i = 0; i < 100; i++) {
    if (await new Promise(r => http.get({ host: "127.0.0.1", port, path: "/" }, s => { s.resume(); r(true); }).on("error", () => r(false)))) return true;
    await new Promise(r => setTimeout(r, 50));
  }
  return false;
}
const P_REF = 4451, P_HEAD = 4452;
const sRef = server(join(refDir, "frontend-v2-ng"), P_REF), sHead = server(KOREN, P_HEAD);
zapisi("referenca", "oba servera se podižu", (await spreman(P_REF)) && (await spreman(P_HEAD)));

const browser = await chromium.launch();
const SAKRIJ_POZADINU = "#pozadina{visibility:hidden!important}";
const spolja = [];

/* Pikseli snimka (RGBA) u pregledaču, bez novih zavisnosti. */
const platno = await (await browser.newContext()).newPage();
/* Oblasti su u CSS px; razmera snimka se meri iz same slike (pri zumu
 * pregledača snimak nije nužno u DPR pikselima). Granice se zaokružuju KA
 * UNUTRA, da delimični piksel na ivici znaka ne uđe u proveru. */
async function pikseli(png, oblasti, cssSirina) {
  return platno.evaluate(async ([src, oblasti, cssSirina]) => {
    const i = new Image(); await new Promise((r, x) => { i.onload = r; i.onerror = x; i.src = src; });
    const c = document.createElement("canvas"); c.width = i.width; c.height = i.height;
    const g = c.getContext("2d"); g.drawImage(i, 0, 0);
    const k = i.width / cssSirina;
    return oblasti.map(o => {
      const x0 = Math.max(0, Math.ceil(o.x * k)), y0 = Math.max(0, Math.ceil(o.y * k)), x1 = Math.min(i.width, Math.floor((o.x + o.w) * k)), y1 = Math.min(i.height, Math.floor((o.y + o.h) * k));
      if (x1 <= x0 || y1 <= y0) return { n: 0, maks: 0 };
      const d = g.getImageData(x0, y0, x1 - x0, y1 - y0).data; let n = 0, maks = 0;
      for (let k = 0; k < d.length; k += 4) { n++; maks = Math.max(maks, Math.abs(d[k] - o.c[0]), Math.abs(d[k + 1] - o.c[1]), Math.abs(d[k + 2] - o.c[2])); }
      return { n, maks, prvi: Array.from(g.getImageData(x0, y0, 1, 1).data.slice(0, 3)) };
    });
  }, ["data:image/png;base64," + png.toString("base64"), oblasti, cssSirina]);
}
const boja = (s) => s.match(/\d+/g).slice(0, 3).map(Number);

/** Piksel-dokaz unutar nameravanog regiona; nikad ne baca — greška je FAIL. */
async function pikselDokaz(p, u, ime) {
  try { return await pikselDokaz0(p, u, ime); }
  catch (e) { return [[`piksel-dokaz za ${u.tema === "light" ? "svetlu" : "tamnu"} temu je izvodljiv (logo vidljiv na ekranu)`, false, String(e).split("\n")[0].slice(0, 120)]]; }
}
async function pikselDokaz0(p, u, ime) {
  // CDP snimak celog prikaza u stvarnim pikselima uređaja (radi i pri zumu pregledača).
  const cdp = await p.context().newCDPSession(p);
  const png = Buffer.from((await cdp.send("Page.captureScreenshot", { format: "png" })).data, "base64");
  await cdp.detach();
  await writeFile(join(OUT, `${ime}.png`), png);
  const L = u.slike.find(s => s.vidljiv).okvir, s = (o) => o;
  // Stvarna površina trake odmah desno od logoa (u stanju sa otvorenom fiokom
  // preko nje je zatamnjenje — poredi se sa onim što korisnik stvarno vidi).
  const [uz] = await pikseli(png, [s({ x: L.x + L.w + 4, y: L.y + L.h / 2, w: 2, h: 2, c: [0, 0, 0] })], u.viewport);
  if (!uz.n) throw new Error("površina pored logoa je van snimka");
  const c = uz.prvi;
  // Potpuno providne oblasti logoa (357×305, alfa = 0, izmereno u fajlu) moraju biti iste kao traka.
  const kx = L.w / 357, ky = L.h / 305, U = 1;
  const o = (x0, y0, x1, y1) => ({ x: L.x + x0 * kx + U, y: L.y + y0 * ky + U, w: (x1 - x0) * kx - 2 * U, h: (y1 - y0) * ky - 2 * U, c });
  const ivice = [o(0, 0, 70, 75), o(290, 0, 357, 75), o(0, 120, 60, 222), o(300, 120, 357, 222)];
  const r = await pikseli(png, ivice, u.viewport);
  const maks = Math.max(...r.map(x => x.maks));
  const okolo = await pikseli(png, [{ x: Math.max(0, L.x - 6), y: L.y, w: 4, h: L.h, c }, { x: L.x, y: Math.max(0, L.y - 3), w: L.w, h: 2, c }], u.viewport);
  const maksO = Math.max(...okolo.map(x => x.maks));
  return [[`${u.tema === "light" ? "svetla" : "tamna"}: providne oblasti logoa i traka oko njega = površina trake (±2) — nema kutije ni oreola`,
    maks <= 2 && maksO <= 2 && r.every(x => x.n > 0), `površina ${c.join(",")}, maks ${maks}/255, okolo ${maksO}/255, ${r.map(x => x.n).join("/")} px`]];
}

async function otvori(port, { w = 1440, h = 900, tema = "dark", nav = "puna", motion = "reduce", panel = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: motion, deviceScaleFactor: 1 });
  await ctx.route("**/*", (r) => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spolja.push(u.href); return r.abort(); });
  await ctx.addInitScript(([t, n]) => { localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", n); }, [tema, nav]);
  const p = await ctx.newPage();
  const greske = []; p.on("pageerror", e => greske.push(String(e)));
  await p.goto(`http://127.0.0.1:${port}/`);
  await p.addStyleTag({ content: SAKRIJ_POZADINU });
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(() => Promise.all([...document.images].map(i => i.decode().catch(() => {}))));
  if (panel) { await p.click("#panel-toggle"); await p.waitForTimeout(300); }
  await p.waitForTimeout(150);
  return { ctx, p, greske };
}

const STANJA = [
  ["1440", { w: 1440 }], ["1280", { w: 1280, h: 800 }], ["1279", { w: 1279, h: 800 }], ["720", { w: 720 }],
  ["1440-nav-skupljena", { nav: "skupljena" }], ["1279-panel-otvoren", { w: 1279, h: 800, panel: true }], ["720-panel-otvoren", { w: 720, panel: true }],
  ["1440-bez-reduced-motion", { motion: "no-preference" }],
];
for (const [ime, o] of STANJA) {
  for (const tema of ["dark", "light"]) {
    const g = `${ime}-${tema}`;
    const h = await otvori(P_HEAD, { ...o, tema }), r = await otvori(P_REF, { ...o, tema });
    const u = await brendUgovor(h.p), ref = await brendUgovor(r.p);
    if (o.panel) zapisi(g, "panel „Zahteva pažnju“ je otvoren (i na foundation-u)", await h.p.evaluate(() => document.getElementById("panel-toggle").getAttribute("aria-expanded") === "true") && await r.p.evaluate(() => document.getElementById("panel-toggle").getAttribute("aria-expanded") === "true"));
    for (const [n, ok, d] of [...proveriBrend(u, ref), ...proveriKontrast(u, ref), ...(await pikselDokaz(h.p, u, g))]) zapisi(g, n, ok, d);
    zapisi(g, "bez JS grešaka", h.greske.length === 0, h.greske.join(" | "));
    await h.ctx.close(); await r.ctx.close();
  }
}

// ── 3. Stvarni zoom pregledača 200% (chrome.tabs.setZoom), obe teme ─────
async function zoom(port, tema) {
  const ctx = await chromium.launchPersistentContext("", { channel: "chromium", headless: true, viewport: null, reducedMotion: "reduce",
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, "--window-size=1440,900"] });
  let [sw] = ctx.serviceWorkers(); if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
  await ctx.addInitScript((t) => { localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", "puna"); }, tema);
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${port}/`);
  await p.addStyleTag({ content: SAKRIJ_POZADINU });
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(() => Promise.all([...document.images].map(i => i.decode().catch(() => {}))));
  const z = await sw.evaluate(async () => { const t = (await chrome.tabs.query({})).find(x => x.url && x.url.startsWith("http://127.0.0.1")); await chrome.tabs.setZoom(t.id, 2); return chrome.tabs.getZoom(t.id); });
  await p.waitForTimeout(400);
  return { ctx, p, z };
}
for (const tema of ["dark", "light"]) {
  const g = `zoom-200-${tema}`;
  const h = await zoom(P_HEAD, tema), r = await zoom(P_REF, tema);
  const u = await brendUgovor(h.p), ref = await brendUgovor(r.p);
  zapisi(g, "stvarni zoom 200% i DPR 2", h.z === 2 && r.z === 2 && (await h.p.evaluate(() => devicePixelRatio)) === 2);
  for (const [n, ok, d] of [...proveriBrend(u, ref), ...proveriKontrast(u, ref), ...(await pikselDokaz(h.p, u, g))]) zapisi(g, n, ok, d);
  await h.ctx.close(); await r.ctx.close();
}

// ── 4. Prebacivanje teme menja samo logo (bez JS-a za logo) ─────────────
{
  const h = await otvori(P_HEAD, {}), r = await otvori(P_REF, {});
  const pre = await brendUgovor(h.p);
  for (const x of [h, r]) { await x.p.click("#theme-toggle"); await x.p.waitForTimeout(150); }
  const posle = await brendUgovor(h.p), ref = await brendUgovor(r.p);
  zapisi("tema-prekidac", "dugme teme: tamna → svetla menja vidljiv logo u svetlu verziju", pre.tema === "dark" && posle.tema === "light" &&
    posle.slike.find(s => s.vidljiv).src === LOGO.light.fajl && pre.slike.find(s => s.vidljiv).src === LOGO.dark.fajl);
  for (const [n, ok, d] of proveriBrend(posle, ref)) zapisi("tema-prekidac", "posle prebacivanja: " + n, ok, d);
  await r.ctx.close();
  zapisi("tema-prekidac", "izbor logoa radi samo CSS (app.js ne pominje logo)", !/wordmark__logo|brand\//.test(await readFile(join(KOREN, "src/app.js"), "utf8")));
  await h.ctx.close();
}

await platno.context().close();
await browser.close();
await Promise.all([sRef, sHead].map(d => new Promise(r => { d.once("exit", r); d.kill(); })));
await rm(refDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
zapisi("bezbednost", "nijedan zahtev van 127.0.0.1", spolja.length === 0, spolja.slice(0, 3).join(","));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
