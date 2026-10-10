// Vindex V2 NG — NS008 jutarnji demo „Kancelarija pamti" (Law Brain samostalno; Task 18 namerno preskočen).
// Pokretanje: `npm run demo:ns008` → shots/ns008-demo/{1-znanje,2-analiza,3-sinteza,4-posle-opoziva}.png (shots/ je van git-a).
// Odgovori su STVARNI odgovori Law Brain ruta posle istorije napravljene stvarnim rutama (tests/ns008_demo.py --json).

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-demo8-A-NE-U-LOG";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns008_demo.py", "--json"],
  { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
if (!red) { console.log((r.stderr || "").slice(-2000)); throw new Error("ns008_demo.py nije vratio rezultat"); }
const S = JSON.parse(red.slice(2));
zapisi("istorija", "ishodi, odobrenje i potvrda lekcije kroz stvarne rute", Object.values(S.istorija).every(x => x === 200), JSON.stringify(S.istorija));
zapisi("trošak", "pre klika 0 poziva modela", S.model_pre_klika === 0);

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, ms = 12000) => p.waitForFunction(fn, null, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];
const OUT = new URL("../shots/ns008-demo/", import.meta.url);
mkdirSync(OUT, { recursive: true });

function ruta(oznaka) {
  return async (req, url, res) => {
    const p = url.pathname;
    if (!p.startsWith("/api/law-brain/") && !/^\/api\/predmeti\/[^/]+\/genome-v2(\/promene)?$/.test(p)) return false;
    if (/genome-v2/.test(p)) { json(res, 404, { detail: "Predmet nije pronađen." }); return true; }
    const o = S.odgovori[`A|${req.method}|${p}${oznaka}`] || S.odgovori[`A|${req.method}|${p}`] || { status: 404, telo: { detail: "x" } };
    json(res, o.status, o.telo);
    return true;
  };
}
async function scenario(hash, oznaka = "", h = 1400) {
  const A = napraviPredmete("kA", 1);
  A[0].id = S.CUR; A[0].naziv = "Petrović protiv Tehnoprom DOO";
  const KOR = { [TA]: { id: "kA", predmeti: A } };
  const f = await pokreniFixture(kombinuj(ruta(oznaka), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: 1280, height: h }, reducedMotion: "reduce" });
  await ctx.route("**/*", rr => { const u = new URL(rr.request().url()); return u.hostname === "127.0.0.1" ? rr.continue() : rr.abort(); });
  await ctx.addInitScript(([kl, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(kl, v); } }, [KLJUC, ses("kA", TA)]);
  const p = await ctx.newPage();
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, p, zatvori: async () => { await ctx.close(); await f.zatvori(); } };
}
const snimi = (p, sel, ime) => p.locator(sel).screenshot({ path: fileURLToPath(new URL(ime, OUT)) });
const ANALIZA = `#/predmeti/${encodeURIComponent(S.CUR)}/analiza`;

{
  const s = await scenario("#/znanje");
  const ok = await cekaj(s.p, () => !document.getElementById("lb-sadrzaj").hidden);
  const t = await s.p.evaluate(() => document.getElementById("lb-znanje").innerText);
  zapisi("1 Znanje", "iskustvo kancelarije: vrste predmeta, overen rad, potvrđena lekcija, beleška kolege",
    ok && /radni — 1 završen predmet/.test(t) && /Tužba — poništaj rešenja o otkazu/.test(t) && /dostavnicu rešenja/.test(t) && /Beleška kolege/.test(t));
  await snimi(s.p, "#lb-znanje", "1-znanje.png");
  await s.zatvori();
}
{
  const s = await scenario(ANALIZA, "", 1800);
  const ok = await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  const t = await s.p.evaluate(() => document.getElementById("lbp-blok").innerText);
  zapisi("2 Analiza", "CURRENT: Marković (OLD-1) sa razlogom, ishod sa imeniocem, bez šanse",
    ok && /Marković protiv Tehnoprom DOO/.test(t) && /Sličan jer: isti tip predmeta/.test(t) && /Veličina uzorka: 1/.test(t) && !/šans|%/i.test(t.replace(/Nisu procena šanse za uspeh\./g, "")));
  await snimi(s.p, "#lbp-blok", "2-analiza.png");
  await s.p.click("#lbp-analiziraj");
  const sin = await cekaj(s.p, () => document.querySelectorAll("#lbp-sinteza > .an-item").length > 0);
  const st = await s.p.evaluate(() => ({ n: document.querySelectorAll("#lbp-sinteza > .an-item").length, t: document.getElementById("lbp-blok").innerText }));
  zapisi("3 Sinteza", "izričit klik → tvrdnje sa izvorima; „80%” odbačeno", sin && st.n === 4 && !/80%/.test(st.t) && /Odbačeno tvrdnji bez izvora: 1/.test(st.t));
  await snimi(s.p, "#lbp-blok", "3-sinteza.png");
  await s.zatvori();
}
{
  const s = await scenario(ANALIZA, "#posle-opoziva", 1600);
  const ok = await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  const t = await s.p.evaluate(() => document.getElementById("lbp-blok").innerText);
  zapisi("4 Opoziv", "posle opoziva: tužba i lekcija nestaju, istorija predmeta ostaje",
    ok && !/Tužba — poništaj rešenja o otkazu/.test(t) && !/dostavnicu rešenja/.test(t) && /Marković protiv Tehnoprom DOO/.test(t));
  await snimi(s.p, "#lbp-blok", "4-posle-opoziva.png");
  await s.zatvori();
}
await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.length, konzola.join(" | "));
console.log(`\n${ukupno - pada}/${ukupno} PASS   (snimci: shots/ns008-demo/)`);
process.exit(pada ? 1 : 0);
