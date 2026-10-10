// Vindex V2 NG — NS006 Task 12: Danas povezan sa kanonskom radnom tablom (GET /api/workspace).
// Pokretanje: `node tests/live-radna-lista.mjs`. Odgovor table je STVARNI backend odgovor (tests/ns006_ui_fixture.py).

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-rl-A-NE-U-LOG-17", TB = "vx-rl-B-NE-U-LOG-29";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend() {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns006_ui_fixture.py"],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log(r.stderr.slice(-2000)); throw new Error("ns006_ui_fixture.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const STVARNO = backend();
const { PA, PB } = STVARNO;
const TABLA_A = STVARNO.odgovori["A|/api/workspace"].telo;
const TABLA_B = STVARNO.odgovori["B|/api/workspace"].telo;
const AKCIJE_A = ["danas", "kriticno", "predstojece", "za_pregled", "na_cekanju"].flatMap(k => TABLA_A[k]);
zapisi("backend", "stvarna tabla A ima radnje, tabla B je prazna i potpuna", AKCIJE_A.length > 0 && TABLA_A.provera_potpuna === true && TABLA_B.ukupno_aktivnih === 0,
  `${AKCIJE_A.length} stavki`);

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
/** Tabla: tačno telo koje je backend vratio za korisnika; rokovi/kalendar Danas su prazni (nisu predmet ovog testa). */
function tablaRuta(kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  return async (req, url, res) => {
    if (url.pathname === "/api/rokovi/kandidati") { json(res, 200, { rokovi: [] }); return true; }
    if (url.pathname === "/api/kalendar/pregled") { json(res, 200, { dogadjaji: [] }); return true; }
    if (url.pathname !== "/api/workspace") return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    if (kuke.pre) { const z = await kuke.pre(k); if (z) { json(res, z.status, z.telo); return true; } }
    if (res.destroyed) return true;
    let telo = JSON.parse(JSON.stringify(STVARNO.odgovori[`${k}|/api/workspace`].telo));
    if (kuke.izmeni) telo = kuke.izmeni(telo, k) || telo;
    json(res, 200, telo);
    return true;
  };
}

async function scenario({ kuke = {}, hash = "#/danas", w = 1440, h = 900, tema = "dark" } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(tablaRuta(kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses("kA", TA), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const gotovo = (p) => cekaj(p, () => document.getElementById("rl-stanje").dataset.stanje !== "ucitavanje"
  && (document.getElementById("rl-korpe").children.length > 0 || !document.getElementById("rl-stanje").hidden));
const ekran = (p) => p.evaluate(() => {
  const n = document.getElementById("rl-stanje");
  return {
    stanje: n.hidden ? null : [n.dataset.stanje, n.textContent],
    korpe: [...document.querySelectorAll("#rl-korpe > section")].map(s => [s.dataset.korpa, s.querySelector("h3").textContent, s.querySelectorAll("li").length]),
    stavke: [...document.querySelectorAll("#rl-korpe li")].map(li => ({ vrsta: li.dataset.vrsta, prioritet: li.dataset.prioritet, tekst: li.innerText.replace(/\s+/g, " ").trim(),
      veza: li.querySelector("a") ? li.querySelector("a").getAttribute("href") : null })),
    ceo: document.getElementById("rl-korpe").textContent + " " + n.textContent,
    redosled: [...document.querySelectorAll("#danas-pogled .matter__section > h2")].map(h => h.textContent),
    preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    xss: window.__xss || null,
  };
});
const zahtevi = (s, re) => s.f.zahtevi.filter(z => re.test(z.putanja));

const ZADATAK = { vrsta: "zadatak", id: "zad-1", predmet_id: PA, predmet_naziv: "Petrović protiv Gradnja Invest DOO", naslov: "Pozvati klijenta radi potpisa punomoćja",
  tip: "ZADATAK", prioritet: "medium", rok: "2026-10-20", izvor: { zadatak_status: "u_toku" } };
const PREGLED = { vrsta: "review", id: "job-1", predmet_id: PA, predmet_naziv: "Petrović protiv Gradnja Invest DOO", naslov: "Pregled potreban: Dostavnica.pdf",
  tip: "PREGLED_DOKUMENTA", prioritet: "high", rok: null, izvor: { job_id: "job-1", status: "needs_review" } };

// ── 1. Stvarna tabla ─────────────────────────────────────────────────────────
{
  const s = await scenario();
  zapisi("prikaz", "Danas prikazuje radnu listu iz table", await gotovo(s.p));
  const e = await ekran(s.p);
  zapisi("prikaz", "„Radna lista“ je iznad Obaveza (prvo šta traži rad)", e.redosled[0] === "Radna lista" && e.redosled[1] === "Obaveze", e.redosled.join(","));
  const ocekivane = ["danas", "kriticno", "predstojece", "za_pregled", "na_cekanju", "zavrseno_nedavno"].filter(k => TABLA_A[k].length);
  zapisi("korpe", "korpe i brojevi tačno kao u odgovoru table (prazne se ne prikazuju)",
    JSON.stringify(e.korpe.map(k => [k[0], k[2]])) === JSON.stringify(ocekivane.map(k => [k, TABLA_A[k].length])), JSON.stringify(e.korpe));
  zapisi("istina", "svaka stavka je radnja iz table, sa razlogom u „Zašto“", e.stavke.length === AKCIJE_A.length
    && e.stavke.every(x => AKCIJE_A.some(a => x.tekst.includes("Zašto: " + a.naslov))), e.stavke.map(x => x.tekst).join(" | ").slice(0, 220));
  zapisi("istina", "razlog se ne ponavlja u naslovu stavke", e.stavke.every(x => x.tekst.split(AKCIJE_A.find(a => x.tekst.includes(a.naslov)).naslov).length === 2));
  const kontr = e.stavke.find(x => /protivrečnost u spisima/.test(x.tekst));
  zapisi("poreklo", "radnja iz protivrečnosti navodi svoj izvor", !!kontr && /Razrešiti protivrečnost/.test(kontr.tekst), kontr && kontr.tekst);
  zapisi("navigacija", "radnja sistema vodi na Analizu svog predmeta", e.stavke.filter(x => x.vrsta === "case_action").every(x => x.veza === `#/predmeti/${PA}/analiza`));
  zapisi("cena", "Danas čita tablu tačno jednom; 0 upisa", zahtevi(s, /^\/api\/workspace$/).length === 1 && s.f.zahtevi.every(z => z.metod === "GET"),
    s.f.zahtevi.map(z => z.metod + " " + z.putanja).join(","));
  await s.p.click('.sidenav__item[href="#glavni"]');
  await s.p.waitForTimeout(300);
  const posle = await s.p.evaluate(() => document.getElementById("rl-korpe").children.length);
  zapisi("zivotni-ciklus", "izlazak sa Danas prazni radnu listu", posle === 0);
  zapisi("bezbednost", "0 spoljnih zahteva", s.spoljni.length === 0);
  await s.zatvori();
}

// ── 2. Tri vrste ostaju različite ────────────────────────────────────────────
{
  const s = await scenario({ kuke: { izmeni: (t) => ({ ...t, na_cekanju: [ZADATAK], za_pregled: [PREGLED] }) } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  const z = e.stavke.find(x => x.vrsta === "zadatak"), r = e.stavke.find(x => x.vrsta === "review"), a = e.stavke.find(x => x.vrsta === "case_action");
  zapisi("vrste", "zadatak, dokument za pregled i radnja sistema su označeni RAZLIČITO",
    !!z && /^rok 20\.10\.2026\. Zadatak · srednje Pozvati klijenta/.test(z.tekst) && !!r && /Dokument za pregled · visoko/.test(r.tekst) && !!a && /Radnja sistema/.test(a.tekst),
    JSON.stringify([z && z.tekst, r && r.tekst]).slice(0, 220));
  zapisi("vrste", "pregled dokumenta objašnjava zašto čeka (potvrda pre nego što postane podatak)", !!r && /čeka vašu potvrdu/.test(r.tekst));
  zapisi("navigacija", "zadatak i pregled vode na Pregled predmeta", z.veza === `#/predmeti/${PA}` && r.veza === `#/predmeti/${PA}`, z.veza + " " + r.veza);
  await s.zatvori();
}

// ── 3. Pad / nepotpuno / prazno ──────────────────────────────────────────────
{
  const s = await scenario({ kuke: { pre: () => ({ status: 500, telo: { detail: "x" } }) } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("greska", "pad table → GREŠKA „ne znači da nema obaveza“, nikad „nema radnji“",
    !!e.stanje && e.stanje[0] === "greska" && /ne znači da nema obaveza/.test(e.stanje[1]) && e.korpe.length === 0, JSON.stringify(e.stanje));
  await s.zatvori();
}
{
  const s = await scenario({ kuke: { izmeni: (t) => ({ ...t, danas: [], kriticno: [], predstojece: [], degradirani_izvori: ["zadaci"], provera_potpuna: false, ukupno_aktivnih: 0 }) } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("nepotpuno", "nepročitan izvor table: „NIJE potpuna“ sa imenom izvora, ne „sve je u redu“",
    !!e.stanje && e.stanje[0] === "nepotpuno" && /NIJE potpuna — nije pročitano: zadaci/.test(e.stanje[1]) && !/Nema otvorenih radnji/.test(e.ceo), JSON.stringify(e.stanje));
  await s.zatvori();
}
{
  const s = await scenario({ kuke: { izmeni: (t) => ({ ...t, danas: [], kriticno: [], predstojece: [], za_pregled: [], na_cekanju: [], zavrseno_nedavno: [], ukupno_aktivnih: 0 }) } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("prazno", "potpuna prazna tabla: pošteno „nema otvorenih radnji“", !!e.stanje && e.stanje[0] === "prazno" && /Nema otvorenih radnji/.test(e.stanje[1]), JSON.stringify(e.stanje));
  await s.zatvori();
}

// ── 4. Zastareo odgovor i promena korisnika ─────────────────────────────────
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ kuke: { pre: async (k) => { if (k === "A") await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("rl-stanje").dataset.stanje === "ucitavanje");
  await s.p.evaluate(([k, v]) => { localStorage.setItem(k, v); window.dispatchEvent(new StorageEvent("storage", { key: k, newValue: v })); }, [KLJUC, ses("kB", TB)]);
  const bGotov = await cekaj(s.p, () => document.getElementById("rl-stanje").dataset.stanje === "prazno");
  pusti();
  await s.p.waitForTimeout(700);
  const e = await ekran(s.p);
  zapisi("sesija", "posle prelaska A→B: tabla B (prazna), nijedna stavka A ni posle zakasnelog odgovora",
    bGotov && e.korpe.length === 0 && !AKCIJE_A.some(a => e.ceo.includes(a.naslov)) && !/Petrović/.test(e.ceo), JSON.stringify(e.stanje));
  zapisi("sesija", "tabla za B je pročitana B tokenom", s.f.zahtevi.some(z => z.putanja === "/api/workspace" && z.auth === "Bearer " + TB));
  await s.zatvori();
}

// ── 5. Tekst iz baze se ne izvršava; neispravan id predmeta nije veza ────────
{
  const s = await scenario({ kuke: { izmeni: (t) => ({ ...t, na_cekanju: [{ ...ZADATAK, naslov: "<img src=x onerror=window.__xss=1>", predmet_id: "javascript:alert(1)" }] }) } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  const z = e.stavke.find(x => x.vrsta === "zadatak");
  zapisi("bezbednost", "HTML u naslovu je tekst, ne izvršava se", e.xss === null && /<img src=x onerror=/.test(e.ceo));
  zapisi("bezbednost", "neispravan id predmeta ne postaje veza", !!z && z.veza === null, z && z.veza);
  await s.zatvori();
}

// ── 6. Raspored ──────────────────────────────────────────────────────────────
for (const [w, tema] of [[360, "light"], [1440, "dark"]]) {
  const s = await scenario({ w, h: 800, tema, kuke: { izmeni: (t) => ({ ...t, na_cekanju: [ZADATAK], za_pregled: [PREGLED] }) } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("raspored", `${w}px/${tema}: bez vodoravnog preliva`, !e.preliv && e.stavke.length > 0);
  await s.zatvori();
}

await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
zapisi("bezbednost", "nijedan token u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
