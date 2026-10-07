// Vindex V2 NG — Task 7: dokaz integracije u stvarnom Chromium-u.
// Pokretanje: `node tests/live-browser-matrix.mjs` (sam podiže servere; treba git).
//
// DEMO: piksel-po-piksel poređenje sa nepromenjenim foundation commit-om
// `1eb20976` (izvučen `git archive`-om), u istom pregledaču i istim uslovima.
// Animirana pozadina (#pozadina) se sakriva u OBA snimka (inače se dva snimka
// istog koda razlikuju). Preostaje šum rasterizacije: izmereno 3 piksela sa
// razlikom 1/255 između dva snimka ISTOG koda. Zato je kriterijum izričit i
// uzak: najviše SUM_PIKSELA različitih piksela I najveća razlika kanala
// ≤ SUM_KANALA. Stvarna izmena (tekst, red, boja, pomeraj) daje hiljade
// piksela sa velikom razlikom. Šum HEAD-protiv-HEAD se meri istim pragom.
//
// LIVE: ponašanje + snimci iz stvarnog pregledača nad fixture-om koji ponavlja
// ugovor api.py. Snimci: shots/matrix/ (nije u git-u).

import { chromium } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { ugovor, fokusBezPomeranja, fiokeRade, razlikeUgovora } from "./fixtures/zoom-contract.mjs";

const KOREN = fileURLToPath(new URL("..", import.meta.url));
const REPO = fileURLToPath(new URL("../..", import.meta.url));
const FOUNDATION = "1eb20976";
const EXT = fileURLToPath(new URL("./fixtures/zoom-ext", import.meta.url));
const OUT = fileURLToPath(new URL("../shots/matrix/", import.meta.url));
await mkdir(OUT, { recursive: true });
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TOKEN = "vx-matrix-token-NE-U-LOG-88bb";

let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

function server(dir, port) {
  const d = spawn(process.execPath, ["serve.mjs", String(port)], { cwd: dir, stdio: "ignore" });
  return d;
}
async function spreman(port) {
  for (let i = 0; i < 100; i++) {
    const ok = await new Promise(r => http.get({ host: "127.0.0.1", port, path: "/" }, s => { s.resume(); r(true); }).on("error", () => r(false)));
    if (ok) return true;
    await new Promise(r => setTimeout(r, 50));
  }
  return false;
}

// ── Referenca: foundation 1eb20976 ──────────────────────────────────────
const refDir = await mkdtemp(join(tmpdir(), "vx-ref-"));
let referenca = true;
try {
  const tar = execFileSync("git", ["archive", "--format=tar", FOUNDATION, "frontend-v2-ng"], { cwd: REPO, maxBuffer: 64 * 1024 * 1024 });
  await writeFile(join(refDir, "ref.tar"), tar);
  execFileSync("tar", ["-xf", "ref.tar"], { cwd: refDir });
} catch (e) { referenca = false; }
zapisi("referenca", `foundation ${FOUNDATION} izvučen iz git-a (bez njega DEMO poređenje nije moguće)`, referenca);

const P_REF = 4441, P_HEAD = 4442;
const sRef = server(join(refDir, "frontend-v2-ng"), P_REF);
const sHead = server(KOREN, P_HEAD);
zapisi("referenca", "oba servera se podižu", (await spreman(P_REF)) && (await spreman(P_HEAD)));

const browser = await chromium.launch();
const SAKRIJ_POZADINU = "#pozadina{visibility:hidden!important}";
const SUM_PIKSELA = 64, SUM_KANALA = 2;

/* Poređenje dva PNG-a u pregledaču (canvas) — bez novih zavisnosti. */
const poredjenje = await (await browser.newContext()).newPage();
async function razlika(a, b) {
  return poredjenje.evaluate(async ([a, b]) => {
    const ucitaj = (src) => new Promise((r, x) => { const i = new Image(); i.onload = () => r(i); i.onerror = x; i.src = src; });
    const [ia, ib] = await Promise.all([ucitaj(a), ucitaj(b)]);
    if (ia.width !== ib.width || ia.height !== ib.height) return { piksela: Infinity, kanal: 255, dim: `${ia.width}x${ia.height} vs ${ib.width}x${ib.height}` };
    const pod = (img) => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height; const g = c.getContext("2d"); g.drawImage(img, 0, 0); return g.getImageData(0, 0, c.width, c.height).data; };
    const da = pod(ia), db = pod(ib);
    let piksela = 0, kanal = 0;
    for (let i = 0; i < da.length; i += 4) {
      const m = Math.max(Math.abs(da[i] - db[i]), Math.abs(da[i + 1] - db[i + 1]), Math.abs(da[i + 2] - db[i + 2]));
      if (m) { piksela++; if (m > kanal) kanal = m; }
    }
    return { piksela, kanal, dim: `${ia.width}x${ia.height}` };
  }, ["data:image/png;base64," + a.toString("base64"), "data:image/png;base64," + b.toString("base64")]);
}
const uSumu = (d) => d.piksela <= SUM_PIKSELA && d.kanal <= SUM_KANALA;
const opis = (d) => `${d.piksela} piksela, maks. ${d.kanal}/255, ${d.dim}`;

async function snimakDemo(port, { w = 1440, h = 900, tema = "dark", nav = "puna", upit = "", motion = "reduce", ceo = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: motion, deviceScaleFactor: 1 });
  await ctx.addInitScript(([t, n]) => { localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", n); }, [tema, nav]);
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${port}/${upit}`);
  await p.addStyleTag({ content: SAKRIJ_POZADINU });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(250);
  const b = await p.screenshot({ fullPage: ceo });
  await ctx.close();
  return b;
}

const DEMO = [
  ["1440-dark", {}], ["1440-light", { tema: "light" }], ["1280-dark", { w: 1280, h: 800 }],
  ["1279-dark", { w: 1279, h: 800 }], ["720-dark", { w: 720, h: 900 }], ["1440-nav-skupljena", { nav: "skupljena" }],
  ["1440-240-predmeta", { upit: "?predmeti=veliko" }], ["1440-240-predmeta-cela-strana", { upit: "?predmeti=veliko", ceo: true }],
  ["1440-bez-reduced-motion", { motion: "no-preference" }], ["1440-prazno", { upit: "?predmeti=prazno&paznja=prazno" }],
];
for (const [ime, o] of DEMO) {
  const h1 = await snimakDemo(P_HEAD, o), h2 = await snimakDemo(P_HEAD, o);
  const r = await snimakDemo(P_REF, o);
  await writeFile(join(OUT, `demo-${ime}.png`), h1);
  const dh = await razlika(h1, h2), dr = await razlika(h1, r);
  zapisi("demo-piksel", `${ime}: HEAD protiv HEAD u granici šuma`, uSumu(dh), opis(dh));
  zapisi("demo-piksel", `${ime}: HEAD protiv foundation ${FOUNDATION} u granici šuma`, uSumu(dr), opis(dr));
}

// Stvarni zoom pregledača 200% (isto kao refinement.mjs: chrome.tabs.setZoom).
async function snimakZoom(port) {
  const ctx = await chromium.launchPersistentContext("", { channel: "chromium", headless: true, viewport: null, reducedMotion: "reduce",
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, "--window-size=1440,900"] });
  let [sw] = ctx.serviceWorkers(); if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
  await ctx.addInitScript(() => { localStorage.setItem("vx-ng-tema", "dark"); localStorage.setItem("vx-ng-nav", "puna"); });
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${port}/`);
  await p.addStyleTag({ content: SAKRIJ_POZADINU });
  await p.evaluate(() => document.fonts.ready);
  const z = await sw.evaluate(async () => { const t = (await chrome.tabs.query({})).find(x => x.url && x.url.startsWith("http://127.0.0.1")); await chrome.tabs.setZoom(t.id, 2); return chrome.tabs.getZoom(t.id); });
  await p.waitForTimeout(400);
  const dpr = await p.evaluate(() => devicePixelRatio);
  const s = await p.context().newCDPSession(p);
  const { data } = await s.send("Page.captureScreenshot", { format: "png" });
  const u = await ugovor(p);
  const fokus = await fokusBezPomeranja(p);
  const fioke = await fiokeRade(p);
  await ctx.close();
  return { b: Buffer.from(data, "base64"), z, dpr, u, fokus, fioke };
}
// 200%: BLOKIRA semantički ugovor; snimak je dokaz, ne kapija.
// NS002B (run 37668839314): na Linux-u snimak ISTOG builda nije bit-deterministički
// pri DPR 2 — piksel (31,616), CSS (15.5,308) na polu-pikselnoj ivici u #registry,
// skače između dve vrednosti (plavi kanal 23/32) i na HEAD-u i na foundation-u,
// dok su ugovor, DOM i stilovi identični. 100% piksel-poređenja ostaju blokirajuća.
{
  const a = await snimakZoom(P_HEAD), a2 = await snimakZoom(P_HEAD), r = await snimakZoom(P_REF);
  await writeFile(join(OUT, "demo-zoom-200.png"), a.b);
  const g = "demo-zoom-200";
  zapisi(g, "stvarni zoom pregledača je 200% i DPR 2 (HEAD i foundation)", a.z === 2 && a.dpr === 2 && a.u.dpr === 2 && r.z === 2 && r.dpr === 2, `zoom=${a.z} dpr=${a.dpr}`);
  zapisi(g, "bez horizontalnog preliva", !a.u.preliv, a.u.sirine.join("/"));
  zapisi(g, "očekivan režim: navigacija i „Zahteva pažnju“ su fioke", a.u.nav === "fioka" && a.u.panel === "fioka", `${a.u.nav}/${a.u.panel}`);
  zapisi(g, "fioke rade: panel i navigacija se otvaraju, fokus ulazi, Escape zatvara", a.fioke.panel && a.fioke.panelZatvoren && a.fioke.nav, JSON.stringify(a.fioke));
  zapisi(g, "nazivi predmeta najviše 2 reda", a.u.najviseRedovaNaziva <= 2, `${a.u.najviseRedovaNaziva}`);
  zapisi(g, "fokus tastature na nazivu ne menja visinu reda", a.fokus.naNazivu && a.fokus.isto && a.fokus.linijaFokusiranog <= 2, JSON.stringify(a.fokus));
  zapisi(g, "tipografski pod: nijedan vidljiv tekst ispod 13 CSS px", a.u.minFont[0] >= 13, a.u.minFont.join(" "));
  const prema = razlikeUgovora(a.u, r.u), izmedju = razlikeUgovora(a.u, a2.u);
  zapisi(g, `geometrija i izračunati stilovi identični foundation-u ${FOUNDATION}`, prema.length === 0 && JSON.stringify(a.fokus) === JSON.stringify(r.fokus) && JSON.stringify(a.fioke) === JSON.stringify(r.fioke), prema.slice(0, 3).join(" | "));
  zapisi(g, "ugovor stabilan između dve HEAD sesije", izmedju.length === 0, izmedju.slice(0, 3).join(" | "));
  const dh = await razlika(a.b, a2.b), dr = await razlika(a.b, r.b);
  console.log(`INFO  [${g}] snimak HEAD protiv HEAD: ${opis(dh)}; protiv foundation: ${opis(dr)} (dokaz, ne kapija)`);
}
await poredjenje.context().close();
await Promise.all([sRef, sHead].map(d => new Promise(r => { d.once("exit", r); d.kill(); })));
await rm(refDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });

// ── LIVE matrica ─────────────────────────────────────────────────────────
const sesija = () => JSON.stringify({ access_token: TOKEN, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "k1", email: "k1@primer.test" } });
const DUG = "Naknada nematerijalne štete zbog povrede prava ličnosti i duševnih bolova usled objavljivanja netačnih informacija u elektronskom mediju i na društvenim mrežama u periodu od više godina";

async function live(api, { w = 1440, h = 900, tema = "dark", nav = "puna", cekaj = true } = {}) {
  const f = await pokreniFixture(api);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  await ctx.addInitScript(([k, v, t, n]) => { localStorage.setItem(k, v); localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", n); }, [KLJUC, sesija(), tema, nav]);
  const p = await ctx.newPage();
  const greske = [];
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live`);
  await p.evaluate(() => document.fonts.ready);
  if (cekaj) await p.waitForFunction(() => { const e = document.getElementById("empty"); return !e.hidden ? e.dataset.stanje !== "ucitavanje" : document.querySelectorAll("#rows tr").length > 0; }, null, { timeout: 15000 }).catch(() => {});
  await p.waitForTimeout(150);
  return { f, ctx, p, greske, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const bezPreliva = (p) => p.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
const bezDemoa = (p) => p.evaluate(() => document.querySelectorAll("#attention li").length === 0 && !/Demonstracioni|Demo nalog|Referentni demo datum/.test(document.body.innerText));
const stanje = (p) => p.evaluate(() => document.getElementById("empty").hidden ? "registar" : document.getElementById("empty").dataset.stanje);
const ruta = (n, kuke = {}, opc = {}) => predmetiRuta({ [TOKEN]: { id: "k1", predmeti: napraviPredmete("k1", n, opc) } }, kuke);

for (const [ime, api, ocekivano] of [
  ["12", ruta(12), "registar"], ["240", ruta(240), "registar"], ["0", ruta(0), "prazno"],
  ["401", ruta(12, { preStrane: () => ({ status: 401 }) }), "greska-prijava"],
  ["403", ruta(12, { preStrane: () => ({ status: 403 }) }), "greska-pristup"],
  ["429", ruta(12, { preStrane: () => ({ status: 429 }) }), "greska-ogranicenje"],
  ["500", ruta(12, { preStrane: () => ({ status: 500 }) }), "greska-server"],
  ["mreza", async (req, url) => { if (url.pathname !== "/api/predmeti") return false; req.socket.destroy(); return true; }, "greska-mreza"],
]) {
  for (const [w, h] of [[1440, 900], [1279, 800], [720, 900]]) {
    const s = await live(api, { w, h });
    const st = await stanje(s.p);
    const g = `live-${ime}@${w}`;
    zapisi(g, `stanje „${ocekivano}“`, st === ocekivano, st);
    zapisi(g, "bez horizontalnog preliva", await bezPreliva(s.p));
    zapisi(g, "bez demo obaveza i demo oznaka", await bezDemoa(s.p));
    zapisi(g, "bez JS grešaka", s.greske.length === 0, s.greske.join(" | "));
    if (w === 1440) await s.p.screenshot({ path: join(OUT, `live-${ime}-1440-dark.png`) });
    await s.zatvori();
  }
}
// 240 u svetloj temi, cela strana.
{
  const s = await live(ruta(240), { tema: "light" });
  zapisi("live-240-light", "svih 240 prikazano, svetla tema aktivna", (await s.p.evaluate(() => document.querySelectorAll("#rows tr").length)) === 240 && (await s.p.evaluate(() => document.documentElement.dataset.theme)) === "light");
  const bojaD = await s.p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await s.p.screenshot({ path: join(OUT, "live-240-1440-light-cela.png"), fullPage: true });
  await s.zatvori();
  const d = await live(ruta(240), { tema: "dark" });
  const bojaT = await d.p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  zapisi("tema", "tamna i svetla tema daju različitu pozadinu i u LIVE", bojaD !== bojaT, `${bojaD} / ${bojaT}`);
  await d.zatvori();
}

// Spor odgovor: bez pomeranja rasporeda između „učitavanje“ i podataka.
{
  let pusti; const kapija = new Promise(r => { pusti = r; });
  const s = await live(ruta(12, { preStrane: () => kapija }), { cekaj: false });
  await s.p.waitForFunction(() => document.getElementById("empty").dataset.stanje === "ucitavanje", null, { timeout: 8000 }).catch(() => {});
  await s.p.evaluate(() => { window.__cls = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: false }); });
  const okviri = () => s.p.evaluate(() => [".topbar", "#nav", ".sheet__head", "#panel", ".sheet__title"].map(sel => { const r = document.querySelector(sel).getBoundingClientRect(); return [sel, Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)].join(":"); }));
  const pre = await okviri();
  await s.p.screenshot({ path: join(OUT, "live-sporo-ucitavanje-1440-dark.png") });
  pusti();
  await s.p.waitForFunction(() => document.querySelectorAll("#rows tr").length === 12, null, { timeout: 8000 }).catch(() => {});
  await s.p.waitForTimeout(200);
  const posle = await okviri();
  const cls = await s.p.evaluate(() => window.__cls);
  zapisi("sporo", "zaglavlje, navigacija, naslov, pretraga i panel se ne pomeraju posle učitavanja", JSON.stringify(pre) === JSON.stringify(posle), JSON.stringify(pre) === JSON.stringify(posle) ? "" : `${pre} → ${posle}`);
  zapisi("sporo", "layout-shift (CLS) posle učitavanja je 0", cls === 0, `CLS=${cls}`);
  await s.p.screenshot({ path: join(OUT, "live-sporo-posle-1440-dark.png") });
  await s.zatvori();
}

// Prelom panela na 1280, sužavanje naziva na 2 reda, fokus ne menja visinu reda, navigacija.
{
  const s = await live(ruta(12, {}, { naziv: i => (i === 0 ? DUG : `Predmet ${i}`) }), { w: 1280, h: 800 });
  zapisi("prelom", "1280: panel je kolona (nije fioka)", await s.p.evaluate(() => getComputedStyle(document.getElementById("panel")).position !== "fixed"));
  await s.zatvori();
  const u = await live(ruta(12, {}, { naziv: i => (i === 0 ? DUG : `Predmet ${i}`) }), { w: 1279, h: 800 });
  zapisi("prelom", "1279: panel je fioka", await u.p.evaluate(() => getComputedStyle(document.getElementById("panel")).position === "fixed"));
  await u.zatvori();

  const t = await live(ruta(12, {}, { naziv: i => (i === 0 ? DUG : `Predmet ${i}`) }));
  const redovi = () => t.p.evaluate(() => Array.from(document.querySelectorAll("#rows tr")).map(r => Math.round(r.getBoundingClientRect().height)));
  const linijeDugog = () => t.p.evaluate((d) => { const a = [...document.querySelectorAll(".case__name")].find(x => x.textContent === d); return Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight)); }, DUG);
  zapisi("naziv", "dugačak stvaran naziv: najviše 2 reda", (await linijeDugog()) === 2, `${await linijeDugog()} reda`);
  const pre = await redovi();
  await t.p.focus('th[data-kljuc="izmenjeno"] .sort'); await t.p.keyboard.press("Tab");
  const fokusiran = await t.p.evaluate((d) => document.activeElement && document.activeElement.textContent === d, DUG);
  const posle = await redovi();
  zapisi("naziv", "Tab dolazi na dugačak naziv", fokusiran);
  zapisi("naziv", "fokus ne menja visinu nijednog reda", JSON.stringify(pre) === JSON.stringify(posle), `${pre[0]} → ${posle[0]}`);
  zapisi("naziv", "fokusiran naziv ostaje na 2 reda", (await linijeDugog()) === 2);
  await t.p.screenshot({ path: join(OUT, "live-dugi-naziv-fokus-1440-dark.png") });
  await t.p.click("#nav-collapse");
  zapisi("navigacija", "skupljanje navigacije radi u LIVE", await t.p.evaluate(() => document.documentElement.dataset.nav === "skupljena"));
  zapisi("navigacija", "posle skupljanja nema horizontalnog preliva", await bezPreliva(t.p));
  await t.p.screenshot({ path: join(OUT, "live-nav-skupljena-1440-dark.png") });
  zapisi("navigacija", "registar zadržava 12 predmeta posle skupljanja", (await t.p.evaluate(() => document.querySelectorAll("#rows tr").length)) === 12);
  await t.zatvori();
}

// LIVE i stvarni zoom 200%: bez preliva, bez demo podataka.
{
  const f = await pokreniFixture(ruta(240));
  const ctx = await chromium.launchPersistentContext("", { channel: "chromium", headless: true, viewport: null, reducedMotion: "reduce",
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, "--window-size=1440,900"] });
  let [sw] = ctx.serviceWorkers(); if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
  await ctx.addInitScript(([k, v]) => localStorage.setItem(k, v), [KLJUC, sesija()]);
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live`);
  await p.waitForFunction(() => document.querySelectorAll("#rows tr").length === 240, null, { timeout: 15000 }).catch(() => {});
  const z = await sw.evaluate(async () => { const t = (await chrome.tabs.query({})).find(x => x.url && x.url.startsWith("http://127.0.0.1")); await chrome.tabs.setZoom(t.id, 2); return chrome.tabs.getZoom(t.id); });
  await p.waitForTimeout(400);
  zapisi("live-zoom-200", "stvarni zoom 200%, 240 predmeta, bez horizontalnog preliva", z === 2 && (await p.evaluate(() => devicePixelRatio)) === 2 && (await bezPreliva(p)) && (await p.evaluate(() => document.querySelectorAll("#rows tr").length)) === 240);
  zapisi("live-zoom-200", "bez demo obaveza i oznaka", await bezDemoa(p));
  const s = await p.context().newCDPSession(p);
  const { data } = await s.send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(OUT, "live-240-zoom-200.png"), Buffer.from(data, "base64"));
  await ctx.close(); await f.zatvori();
}

await browser.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS   (snimci: shots/matrix/)`);
process.exit(pada ? 1 : 0);
