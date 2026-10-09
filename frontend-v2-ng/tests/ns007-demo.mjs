// Vindex V2 NG — NS007 jutarnji demo, V2 ekrani posle autonomnog ciklusa kroz pravu rutu (tests/ns007_demo.py --json).
// Pokretanje: `npm run demo:ns007` → shots/ns007-demo/{1-danas,2-priprema,3-praksa,4-pregled}.png (shots/ je van git-a).

// Vindex V2 NG — NS007 Task 15–16: „Vindex je pripremio" (Danas, pregled rada, Pregled predmeta).
// Pokretanje: `node tests/live-pripremljeno.mjs`. Odgovori API-ja su STVARNI odgovori posle STVARNOG autonomnog
// ciklusa (tests/ns007_ui_fixture.py), ne ručno pisani JSON.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-vp-A-NE-U-LOG-31", TB = "vx-vp-B-NE-U-LOG-32";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend() {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns007_demo.py", "--json"],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log((r.stderr || "").slice(-2000)); throw new Error("ns007_demo.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const S = backend();
const { PA, PB } = S;
const HP = S.radovi.HEARING_PREP, PI = S.radovi.PRECEDENT_IMPACT;
const O = (k) => S.odgovori[k];


const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 1), B = napraviPredmete("kB", 1);
  A[0].id = PA; A[0].naziv = "Petrović protiv Gradnja Invest DOO";
  B[0].id = PB; B[0].naziv = "Jovanović protiv Opštine";
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}

/** API rad: tačno telo koje je backend vratio za (korisnik, metod, putanja); kuke menjaju/kasne/obaraju. */
function radRuta(kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  return async (req, url, res) => {
    const p = url.pathname;
    if (p === "/api/rokovi/kandidati") { json(res, 200, { rokovi: [] }); return true; }
    if (p === "/api/kalendar/pregled") { json(res, 200, { dogadjaji: [] }); return true; }
    if (!/^\/api\/(workspace|autonomy\/work-items(\/[^/]+(\/(accept|reject))?)?|predmeti\/[^/]+\/genome-v2\/promene|case-actions\/predmeti\/[^/]+)$/.test(p)) return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    const metod = req.method;
    let telo = "";
    if (metod === "POST") { for await (const c of req) telo += c; }
    if (kuke.pre) { const z = await kuke.pre({ p, k, metod, url, telo, zaglavlja: req.headers }); if (z) { json(res, z.status, z.telo); return true; } }
    if (res.destroyed) return true;
    let kljuc = `${k}|${metod}|${p}`;
    if (p === "/api/autonomy/work-items" && url.searchParams.get("matter_id")) kljuc += `?matter_id=${url.searchParams.get("matter_id")}`;
    const o = S.odgovori[kljuc] || (p.startsWith("/api/autonomy/work-items/") ? { status: 404, telo: { detail: "Radni proizvod nije pronađen." } } : { status: 404, telo: { detail: "Nije pronađeno." } });
    let t = JSON.parse(JSON.stringify(o.telo));
    if (kuke.izmeni) t = kuke.izmeni({ p, k, metod }, t) || t;
    json(res, o.status, t);
    return true;
  };
}

async function scenario({ kuke = {}, hash = "#/danas", w = 1440, h = 900, tema = "dark", korisnik = "kA", token = TA } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(radRuta(kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([kl, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(kl, v); } }, [KLJUC, ses(korisnik, token), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const zahtevi = (s, re, metod) => s.f.zahtevi.filter(z => (!metod || z.metod === metod) && re.test(z.putanja));
const danasGotov = (p) => cekaj(p, () => document.getElementById("rl-stanje").dataset.stanje !== "ucitavanje"
  && (document.getElementById("dp-lista").children.length > 0 || !document.getElementById("dp-stanje").hidden || document.getElementById("dp-blok").hidden)
  && (document.getElementById("rl-korpe").children.length > 0 || !document.getElementById("rl-stanje").hidden));
const listaDanas = (p) => p.evaluate(() => ({
  vidljiv: !document.getElementById("dp-blok").hidden,
  stavke: [...document.querySelectorAll("#dp-lista > li")].map(li => ({ id: li.dataset.rad, tip: li.dataset.tip, tekst: li.innerText.replace(/\s+/g, " ").trim(),
    veza: li.querySelector(".vp-item__title").getAttribute("href"), predmet: li.querySelector("a.text-btn") ? li.querySelector("a.text-btn").getAttribute("href") : null })),
  stanje: document.getElementById("dp-stanje").hidden ? null : [document.getElementById("dp-stanje").dataset.stanje, document.getElementById("dp-stanje").textContent],
  redosled: [...document.querySelectorAll("#danas-pogled .matter__section > h2")].map(x => x.textContent),
  preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
}));
const detaljGotov = (p) => cekaj(p, () => document.getElementById("vpr-stanje").dataset.stanje !== "ucitavanje"
  && (!document.getElementById("vpr-sadrzaj").hidden || !document.getElementById("vpr-stanje").hidden));
const detalj = (p) => p.evaluate(() => ({
  sadrzaj: !document.getElementById("vpr-sadrzaj").hidden,
  stanje: document.getElementById("vpr-stanje").hidden ? null : document.getElementById("vpr-stanje").textContent,
  naslov: document.getElementById("vpr-naslov").textContent, meta: document.getElementById("vpr-meta").innerText,
  razlog: document.getElementById("vpr-razlog").textContent, telo: document.getElementById("vpr-delovi").innerText.replace(/\s+/g, " "),
  odluka: !document.getElementById("vpr-odluka-blok").hidden,
  poruka: document.getElementById("vpr-poruka").hidden ? null : document.getElementById("vpr-poruka").textContent,
  porekla: [...document.querySelectorAll("#vpr-delovi .prov")].map(x => x.textContent),
  preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  xss: window.__xss || null,
}));
const DOK = (s) => s.p.evaluate(() => document.getElementById("vpr-delovi").textContent);


import { mkdirSync } from "node:fs";
const OUT = new URL("../shots/ns007-demo/", import.meta.url);
mkdirSync(OUT, { recursive: true });
const snimi = (p, sel, ime) => p.locator(sel).screenshot({ path: fileURLToPath(new URL(ime, OUT)) });
{
  const s = await scenario({ w: 1280, h: 1400 });
  zapisi("5 Danas", "„Vindex je pripremio“: preostaje analiza prakse (priprema je već prihvaćena i nije više na pregledu)", await danasGotov(s.p) && JSON.stringify((await listaDanas(s.p)).stavke.map(x => x.id)) === JSON.stringify([PI]));
  await snimi(s.p, "#danas-pogled", "1-danas.png");
  await s.zatvori();
}
for (const [rad, ime, re] of [[HP, "2-priprema.png", /Iz evidencije ročišta/], [PI, "3-praksa.png", /Proverena u bazi sudskih odluka/]]) {
  const s = await scenario({ hash: `#/pripremljeno/${rad}`, w: 1280, h: 2600 });
  zapisi("6-7/14-15 pregled", `pregled rada sa izvorima (${ime})`, await detaljGotov(s.p) && re.test(await DOK(s)));
  await snimi(s.p, "#pripremljeno-pogled", ime);
  await s.zatvori();
}
{
  const s = await scenario({ hash: `#/predmeti/${PA}`, w: 1280, h: 1200 });
  zapisi("Pregled", "pripremljen rad u Pregledu predmeta", await cekaj(s.p, () => document.querySelectorAll("#zp-prip > li").length > 0));
  await snimi(s.p, "#zp-blok", "4-pregled.png");
  await s.zatvori();
}
await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.some(l => l.startsWith("PAGEERROR")));
console.log(`
${ukupno - pada}/${ukupno} PASS   (snimci: shots/ns007-demo/)`);
process.exit(pada ? 1 : 0);
