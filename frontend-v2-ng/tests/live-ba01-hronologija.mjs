// Vindex V2 NG — BA-01 Task 7 (BA-04): advokat u „Rad na predmetu → Hronologija“ vidi procesne događaje iz dokumenata
// sa datumom, izvornim dokumentom i oznakom da je to analiza (AI), odvojeno od zapisa sistema („Dokument prihvaćen“).
// Pokretanje: `node tests/live-ba01-hronologija.mjs`.
//
// Odgovori NISU ručno pisani: tests/ba01_ui_fixture.py izvršava STVARNI backend tok (prijem dva dokumenta → finalize →
// DOCUMENT_ACCEPTED → genome_refresh → GET /api/predmeti/{id}); zamenjen je samo izlaz Genome modela.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-ba01-A-NE-U-LOG-17", TB = "vx-ba01-B-NE-U-LOG-29";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ba01_ui_fixture.py"],
  { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
if (!red) { console.log((r.stderr || "").slice(-2000)); throw new Error("ba01_ui_fixture.py nije vratio rezultat"); }
const STVARNO = JSON.parse(red.slice(2));
const P = STVARNO.P, ODG = STVARNO.odgovori;
zapisi("backend", "stvarni odgovori: A 200 sa 4 procesna događaja, B 404, čitanje ne zove model",
  ODG.A.status === 200 && ODG.A.telo.procesni_dogadjaji.stavke.length === 4 && ODG.B.status === 404 && STVARNO.model_pozvan_pri_citanju === 0);

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, ms = 12000) => p.waitForFunction(fn, null, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 1), B = napraviPredmete("kB", 1);
  A[0].id = P; A[0].naziv = ODG.A.telo.predmet.naziv;
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}
// detalj predmeta = STVARNI odgovor backend-a za tog korisnika
const kuke = { preDetalja: (id, k) => (id === P ? (k === "kA" ? ODG.A : ODG.B) : null) };

async function scenario({ hash, tema = "dark", token = TA, korisnik = "kA", w = 1440, h = 900 }) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(predmetiRuta(KOR), predmetDetaljRuta(KOR, {}, kuke)));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", rr => { const u = new URL(rr.request().url()); if (u.hostname === "127.0.0.1") return rr.continue(); spoljni.push(u.href); return rr.abort(); });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses(korisnik, token), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

for (const [tema, w] of [["dark", 1440], ["light", 1440], ["dark", 390]]) {
  const s = await scenario({ hash: `#/predmeti/${P}/rad`, tema, w });
  const ok = await cekaj(s.p, () => document.querySelectorAll("#hron-procesni > li").length > 0);
  const e = await s.p.evaluate(() => ({
    proc: [...document.querySelectorAll("#hron-procesni > li")].map(li => ({
      datum: li.querySelector(".chrono__date").textContent, dt: li.querySelector("time").dateTime,
      tekst: li.querySelector(".chrono__text").textContent, meta: (li.querySelector(".chrono__meta") || {}).textContent || "" })),
    zapisi: [...document.querySelectorAll("#hron-lista > li")].map(li => li.innerText.replace(/\s+/g, " ")),
    vidljivo: !!document.getElementById("hron-procesni").offsetParent,
    naslov: document.getElementById("hron-procesni-naslov").textContent,
    sekcija: document.getElementById("hron-naslov").closest("section").innerText,
    sirina: document.documentElement.scrollWidth, prozor: window.innerWidth,
  }));
  const g = `hronologija ${tema} ${w}`;
  if (process.env.VX_SNIMAK) await s.p.locator("#hron-naslov").locator("xpath=..").screenshot({ path: `${process.env.VX_SNIMAK}/ba01-hronologija-${tema}-${w}.png` });
  zapisi(g, "procesni događaji vidljivi u „Rad na predmetu → Hronologija“", ok && e.vidljivo && /Procesni događaji/.test(e.naslov));
  zapisi(g, "hronološki redosled sa datumima", JSON.stringify(e.proc.map(x => x.datum)) === JSON.stringify(["20.10.2026.", "23.10.2026.", "25.10.2026.", "26.10.2026."])
    && e.proc[0].dt === "2026-10-20", JSON.stringify(e.proc.map(x => x.datum)));
  zapisi(g, "izvor je stvarno ime dokumenta", /Izvor: 01 Presuda digitalna\.pdf/.test(e.proc[0].meta) && /Izvor: 02 Dostava\.pdf/.test(e.proc[1].meta),
    e.proc.slice(0, 2).map(x => x.meta).join(" | "));
  zapisi(g, "svaka stavka je označena kao analiza (AI), nije potvrđeno", e.proc.every(x => /analiza \(AI\) — nije potvrđeno/.test(x.meta)));
  zapisi(g, "događaj koji izvor ne navodi je označen", /datum nije pronađen u navedenom dokumentu/.test(e.proc[2].meta)
    && !/nije pronađen/.test(e.proc[0].meta) && !/nije pronađen/.test(e.proc[1].meta), e.proc[2].meta);
  zapisi(g, "nerazrešen izvor se kaže, ne pogađa", /izvor nije razrešen/.test(e.proc[3].meta) && !/Izvor:/.test(e.proc[3].meta), e.proc[3].meta);
  zapisi(g, "zapisi sistema su odvojeni od procesnih događaja", e.zapisi.length === 2 && e.zapisi.every(t => /Dokument prihvaćen/.test(t))
    && !e.proc.some(x => /Dokument prihvaćen/.test(x.tekst)), JSON.stringify(e.zapisi));
  zapisi(g, "advokat ne vidi UUID", !UUID.test(e.sekcija));
  zapisi(g, "bez horizontalnog skrola", e.sirina <= e.prozor, `${e.sirina}/${e.prozor}`);
  const pisanja = s.f.zahtevi.filter(z => z.metod !== "GET");
  zapisi(g, "čitanje hronologije ne šalje nijedan upis", pisanja.length === 0, JSON.stringify(pisanja.map(z => z.putanja)));
  zapisi(g, "ništa spolja", s.spoljni.length === 0, s.spoljni.join(","));
  await s.zatvori();
}

// ── korisnik B: tuđi predmet nije dostupan i ništa od A se ne prikazuje ─────────────────────────────────────────
{
  const s = await scenario({ hash: `#/predmeti/${P}/rad`, token: TB, korisnik: "kB" });
  await cekaj(s.p, () => !document.getElementById("predmet-stanje").hidden);
  const e = await s.p.evaluate(() => ({ stanje: document.getElementById("predmet-stanje").innerText,
    proc: document.querySelectorAll("#hron-procesni > li").length, telo: document.body.innerText }));
  zapisi("izolacija", "B dobija stanje „nije dostupan“ i nijedan događaj A", e.proc === 0 && !/Presuda doneta|01 Presuda digitalna/.test(e.telo), e.stanje.slice(0, 120));
  await s.zatvori();
}

// ── nije učitano ≠ prazno ─────────────────────────────────────────────────────────────────────────────────────
{
  const bez = JSON.parse(JSON.stringify(ODG.A)); bez.telo.procesni_dogadjaji = null;
  kuke.preDetalja = (id, k) => (id === P && k === "kA" ? bez : null);
  const s = await scenario({ hash: `#/predmeti/${P}/rad` });
  const ok = await cekaj(s.p, () => !document.getElementById("hron-procesni-stanje").hidden);
  const t = await s.p.evaluate(() => document.getElementById("hron-procesni-stanje").textContent);
  zapisi("istina", "pad projekcije → „nisu učitani“, nikad „nema događaja“", ok && /nisu učitani/.test(t), t);
  await s.zatvori();
}

await browser.close();
const greske = konzola.filter(x => /PAGEERROR|Uncaught/.test(x));
zapisi("konzola", "bez grešaka u stranici", greske.length === 0, greske.slice(0, 3).join(" | "));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
