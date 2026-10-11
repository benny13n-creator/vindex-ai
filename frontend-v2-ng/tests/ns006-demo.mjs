// Vindex V2 NG — NS006 jutarnji demo, koraci 12–15: V2 ekrani posle promene predmeta, bez ručnog osvežavanja.
// Pokretanje: `node tests/ns006-demo.mjs` (prvo izvršava tests/ns006_demo.py --json: stvarni tok nad lažnom bazom).
// Snimci: shots/ns006-demo/13-analiza.png, 14-pregled.png, 15-danas.png (shots/ je van git-a).

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { mkdirSync } from "node:fs";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-demo-A-NE-U-LOG-71", TB = "vx-demo-B-NE-U-LOG-72";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend() {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns006_demo.py", "--json"],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log(r.stderr.slice(-2000)); throw new Error("ns006_demo.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const STVARNO = backend();
const { PA, PB, D1, D2, D3 } = STVARNO;

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  A[0].id = PA; A[0].naziv = "Petrović protiv Gradnja Invest DOO"; A[0].tip = "radno";
  B[0].id = PB; B[0].naziv = "Jovanović protiv Opštine";
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}
const DOKUMENTI = () => ({ [PA]: [D1, D2, D3].map((id, i) => ({ id, predmet_id: PA, user_id: "kA", naziv_fajla: ["Rešenje o otkazu.pdf", "Dostavnica.pdf", "Platni listići 2024.pdf"][i],
  status: "indeksirano", velicina_kb: 40, redni_broj: i + 1, tip_dokaza: "dopis", created_at: "2026-10-01T09:00:00Z", tekst_sadrzaj: "TEKST-" + i })) });

/** Tačno telo koje je backend vratio za (korisnik, putanja); sve ostalo = isti 404 kao tuđ predmet. */
function ziviRuta(izvor, kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  const nijeNadjen = izvor.odgovori[`B|/api/predmeti/${PA}/genome-v2`];
  return async (req, url, res) => {
    if (url.pathname === "/api/rokovi/kandidati") { json(res, 200, { rokovi: [] }); return true; }
    if (url.pathname === "/api/kalendar/pregled") { json(res, 200, { dogadjaji: [] }); return true; }
    if (!/^\/api\/(predmeti\/[^/]+\/genome-v2(\/promene)?|case-actions\/predmeti\/[^/]+|workspace)$/.test(url.pathname)) return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    if (kuke.pre) { const z = await kuke.pre(url.pathname, k); if (z) { json(res, z.status, z.telo); return true; } }
    if (res.destroyed) return true;
    const o = izvor.odgovori[`${k}|${url.pathname}`] || nijeNadjen;
    let telo = JSON.parse(JSON.stringify(o.telo));
    if (kuke.izmeni) telo = kuke.izmeni(url.pathname, telo) || telo;
    json(res, o.status, telo);
    return true;
  };
}

async function scenario({ kuke = {}, hash = `#/predmeti/${PA}`, w = 1440, h = 900, tema = "dark" } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(ziviRuta(STVARNO, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, DOKUMENTI())));
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


const OUT = new URL("../shots/ns006-demo/", import.meta.url);
mkdirSync(OUT, { recursive: true });
const snimi = (p, sel, ime) => p.locator(sel).screenshot({ path: fileURLToPath(new URL(ime, OUT)) });

{
  const s = await scenario({ hash: `#/predmeti/${PA}/analiza`, h: 2400 });
  zapisi("12-13 Analiza", "otvorena posle promene: v2 i nova protivrečnost, bez klika na osvežavanje",
    await cekaj(s.p, () => /Analiza v2/.test(document.getElementById("an-verzija").textContent) && document.querySelectorAll("#an-kontr-aktivne > li").length === 1));
  await snimi(s.p, "#odeljak-analiza", "13-analiza.png");
  await s.p.click("#tab-pregled");
  zapisi("14 Pregled", "„Sledeći korak“ = razrešiti protivrečnost",
    await cekaj(s.p, () => /Razrešiti protivrečnost/.test(document.getElementById("zp-sledece").textContent)));
  await snimi(s.p, "#zp-blok", "14-pregled.png");
  await s.zatvori();
}
{
  const s = await scenario({ hash: "#/danas", h: 1400 });
  zapisi("15 Danas", "kritična radnja na vrhu radne liste, sa razlogom i vezom na predmet",
    await cekaj(s.p, () => { const k = document.querySelector('#rl-korpe [data-korpa="kriticno"]'); return !!k && /datum uručenja rešenja o otkazu/.test(k.textContent) && !!k.querySelector("a"); }));
  await snimi(s.p, "#danas-pogled .matter__section--first", "15-danas.png");
  await s.zatvori();
}

await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.some(l => l.startsWith("PAGEERROR")));
console.log(`
${ukupno - pada}/${ukupno} PASS   (snimci: shots/ns006-demo/)`);
process.exit(pada ? 1 : 0);
