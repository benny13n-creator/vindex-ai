// Vindex V2 NG — OCR001-STATUS-RECOVERY: ograničeno praćenje stanja Smart Intake posla.
// Pokretanje: `node tests/live-prijem-pracenje.mjs` (fixture na 127.0.0.1; ništa spolja).
// Vreme stranice je Playwright lažni sat (`page.clock`): minuti praćenja se odvijaju za sekunde, mrežni zahtevi su pravi.
// Meri: razmak 10 s (jedan i pet poslova), 429 bez i sa `Retry-After`, stalnu grešku servera, zahtev koji „visi“, 404,
// oporavak posle 429 — i da praćenje uvek STANE u roku od 5 minuta i nikad ništa ne prikači samo od sebe.
// Backend limit rute stanja tokom Redis ispada: tests/test_ocr001_status_rate_limit.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { prijemRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-prp-A-NE-U-LOG-41";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const GET_STANJA = "/api/smart-intake/jobs/{id}:GET";
const U_OBRADI = (p) => { if (!p.zavrsi) p.status = "extracting"; };
const fajl = (i) => ({ name: `dokument-${i}.pdf`, mimeType: "application/pdf", buffer: Buffer.from(`%PDF-1.4 sadrzaj ${i}`) });

const browser = await chromium.launch();
const konzola = [];

async function scenario(kuke = {}, rute = null) {
  const A = napraviPredmete("kA", 1);
  const KOR = { [TA]: { id: "kA", predmeti: A } };
  const f = await pokreniFixture(kombinuj(prijemRuta(KOR, { napreduj: U_OBRADI, ...kuke }), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.route("**/*", r => new URL(r.request().url()).hostname === "127.0.0.1" ? (rute ? rute(r) : r.continue()) : r.abort());
  await ctx.addInitScript(() => {
    window.__citanja = [];               // [{put, t}] — t je vreme STRANICE (lažni sat)
    window.__prekinuto = 0;
    const o = window.fetch.bind(window);
    window.fetch = (u, opt) => {
      const put = String(u).split("?")[0];
      if (/\/api\/smart-intake\/jobs\/[^/]+$/.test(put) && !(opt && opt.method && opt.method !== "GET")) window.__citanja.push({ put, t: Date.now() });
      return o(u, opt).catch(e => { if (e && e.name === "AbortError") window.__prekinuto++; throw e; });
    };
  });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses("kA", TA)]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.clock.install();
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}/prijem`);
  await dok(p, () => !document.getElementById("odeljak-prijem").hidden && document.getElementById("predmet-naslov").textContent.length > 0);
  return { f, KOR, p, async zatvori() { await ctx.close(); await Promise.race([f.zatvori(), new Promise(r => setTimeout(r, 2000))]); } };
}

// Čekanje u STVARNOM vremenu (lažni sat teče sam od sebe), proverom iz Node-a — ne zavisi od rAF-a stranice.
async function dok(p, fn, ms = 15000, arg) {
  const kraj = Date.now() + ms;
  while (Date.now() < kraj) { if (await p.evaluate(fn, arg).catch(() => false)) return true; await new Promise(r => setTimeout(r, 50)); }
  return false;
}
// Pomera sat stranice za `ms`, u koracima, uz kratko stvarno čekanje da pravi mrežni odgovori stignu.
async function tece(p, ms, korak = 1000) {
  for (let t = 0; t < ms; t += korak) { await p.clock.runFor(Math.min(korak, ms - t)); await new Promise(r => setTimeout(r, 25)); }
}
async function otpremi(p, n = 1) {
  await p.setInputFiles("#pd-fajlovi", Array.from({ length: n }, (_, i) => fajl(i)));
  await p.click("#pd-otpremi");
  return dok(p, (n) => document.querySelectorAll("#pd-poslovi .intake").length === n, 15000, n);
}
const citanja = (p) => p.evaluate(() => window.__citanja.slice());
const poslovi = (p) => p.evaluate(() => [...document.querySelectorAll("#pd-poslovi .intake")].map(li => ({ stanje: li.querySelector(".intake__state").dataset.stanje, tekst: li.innerText })));
const razmaci = (niz) => niz.slice(1).map((x, i) => x.t - niz[i].t);
const poPutanji = (niz) => niz.reduce((m, x) => ((m[x.put] = m[x.put] || []).push(x), m), {});
const bezPrikacivanja = (s) => s.f.zahtevi.filter(z => z.metod === "POST" && /\/(finalize|review\/|correct)/.test(z.putanja)).length === 0;
const ZAUSTAVLJENO = /Praćenje je zaustavljeno posle 5 minuta/;

// ── 1. Jedan posao u obradi: razmak 10 s ──
{
  const s = await scenario();
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 60000);
  const c = await citanja(s.p);
  const r = razmaci(c);
  zapisi("razmak", "jedan posao: 6–8 čitanja u minutu (staro: ~20)", c.length >= 6 && c.length <= 8, String(c.length));
  zapisi("razmak", "svaki razmak je ≥ 9,5 s", r.every(x => x >= 9500), r.join(","));
  zapisi("razmak", "nijedno prikačivanje/pregled nije poslato praćenjem", bezPrikacivanja(s));
  await s.zatvori();
}

// ── 2. Pet istovremenih poslova ──
{
  const s = await scenario();
  zapisi("pet", "pet poslova otpremljeno", await otpremi(s.p, 5));
  await tece(s.p, 60000);
  const pp = poPutanji(await citanja(s.p));
  const brojevi = Object.values(pp).map(x => x.length);
  zapisi("pet", "svaki od 5 poslova se prati", Object.keys(pp).length === 5, String(Object.keys(pp).length));
  zapisi("pet", "svaki posao 6–8 čitanja u minutu (limit rute: 60/minute po poslu)", brojevi.every(n => n >= 6 && n <= 8), brojevi.join(","));
  zapisi("pet", "razmak svakog posla ≥ 9,5 s", Object.values(pp).every(x => razmaci(x).every(d => d >= 9500)));
  zapisi("pet", "ukupno ≤ 40 čitanja u minutu za 5 poslova (staro: ~100)", brojevi.reduce((a, b) => a + b, 0) <= 40);
  zapisi("pet", "nijedno prikačivanje/pregled nije poslato praćenjem", bezPrikacivanja(s));
  await s.zatvori();
}

// ── 3. Stalni 429 bez Retry-After (backend ga ne šalje) ──
{
  const s = await scenario({ pre: (put) => put === GET_STANJA ? { status: 429, telo: { greska: "Previše zahteva." } } : null });
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 30000);
  const ekr = await poslovi(s.p);
  zapisi("429", "posle 429 jasna poruka, bez tvrdnje da obrada nije uspela", /ograničio broj zahteva/.test(ekr[0].tekst) && /ne znači da obrada nije uspela/.test(ekr[0].tekst), ekr[0].tekst.replace(/\s+/g, " ").slice(0, 160));
  zapisi("429", "posle 429 nema ponovnog čitanja u roku od 30 s (staro: na 6 s)", (await citanja(s.p)).length === 1);
  await tece(s.p, 10 * 60000, 2000);
  const c = await citanja(s.p);
  const r = razmaci(c);
  zapisi("429", "razmak posle 429 je ≥ 60 s", r.every(x => x >= 59500), r.join(","));
  zapisi("429", "ukupno ≤ 6 čitanja za 10 minuta stalnog 429", c.length <= 6, String(c.length));
  zapisi("429", "praćenje STALO u roku od 5 min, uz poruku", ZAUSTAVLJENO.test((await poslovi(s.p))[0].tekst) && c.every(x => x.t - c[0].t <= 5 * 60000));
  const pre = c.length;
  await tece(s.p, 10 * 60000, 5000);
  zapisi("429", "posle zaustavljanja: 0 novih čitanja za još 10 minuta", (await citanja(s.p)).length === pre);
  zapisi("429", "nijedno prikačivanje/pregled nije poslato praćenjem", bezPrikacivanja(s));
  await s.zatvori();
}

// ── 4. 429 sa Retry-After: 120 ──
{
  const s = await scenario({}, (r) => /\/api\/smart-intake\/jobs\/[^/]+$/.test(new URL(r.request().url()).pathname) && r.request().method() === "GET"
    ? r.fulfill({ status: 429, headers: { "Retry-After": "120", "Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "Retry-After" }, contentType: "application/json", body: "{}" })
    : r.continue());
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 4 * 60000, 2000);
  const r = razmaci(await citanja(s.p));
  zapisi("429", "Retry-After: 120 se poštuje (razmak ≥ 120 s)", r.length >= 1 && r.every(x => x >= 119500), r.join(","));
  await s.zatvori();
}

// ── 5. Stalna greška servera (503) ──
{
  const s = await scenario({ pre: (put) => put === GET_STANJA ? { status: 503 } : null });
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 10 * 60000, 2000);
  const c = await citanja(s.p);
  const r = razmaci(c);
  zapisi("greska", "razmak raste: 10 · 20 · 40 · 60 s (ograničen na 60 s)", r.length >= 4 && r[0] >= 9500 && r[1] >= 19500 && r[2] >= 39500 && r.slice(3).every(x => x >= 59500 && x < 62000), r.join(","));
  zapisi("greska", "ukupno ≤ 8 čitanja za 10 minuta stalne greške (staro: ~100, bez kraja)", c.length <= 8, String(c.length));
  zapisi("greska", "praćenje STALO u roku od 5 min, uz poruku", ZAUSTAVLJENO.test((await poslovi(s.p))[0].tekst) && c.every(x => x.t - c[0].t <= 5 * 60000));
  const pre = c.length;
  await tece(s.p, 10 * 60000, 5000);
  zapisi("greska", "posle zaustavljanja: 0 novih čitanja za još 10 minuta", (await citanja(s.p)).length === pre);
  await s.zatvori();
}

// ── 6. Zahtev koji „visi“ (server nikad ne odgovori) ──
{
  const s = await scenario({ pre: (put) => put === GET_STANJA ? new Promise(() => {}) : null });
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 25000);
  zapisi("visi", "zahtev koji visi prekida se posle 20 s", (await s.p.evaluate(() => window.__prekinuto)) >= 1);
  await tece(s.p, 10 * 60000, 2000);
  const c = await citanja(s.p);
  zapisi("visi", "praćenje se nastavlja posle prekida i STAJE u roku od 5 min (staro: zauvek zaglavljeno bez poruke)",
    c.length >= 2 && c.length <= 8 && ZAUSTAVLJENO.test((await poslovi(s.p))[0].tekst), String(c.length));
  const pre = c.length;
  await tece(s.p, 5 * 60000, 5000);
  zapisi("visi", "posle zaustavljanja: 0 novih čitanja", (await citanja(s.p)).length === pre);
  await s.zatvori();
}

// ── 7. 404: posao nije dostupan — praćenje staje odmah ──
{
  const s = await scenario({ pre: (put) => put === GET_STANJA ? { status: 404 } : null });
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 3 * 60000, 2000);
  const ekr = await poslovi(s.p);
  zapisi("404", "404: jedno čitanje, poruka „Posao nije dostupan.“ (staro: ponavljanje na 6 s)", (await citanja(s.p)).length === 1 && /Posao nije dostupan\./.test(ekr[0].tekst));
  await s.zatvori();
}

// ── 8. Oporavak: tri puta 429, zatim server odgovara; praćenje se nastavlja i staje u završnom stanju ──
{
  let n = 0;
  const s = await scenario({ pre: (put) => put === GET_STANJA && ++n <= 3 ? { status: 429 } : null,
    napreduj: (posao, k) => { posao.status = k >= 3 ? "awaiting_review" : "extracting"; if (posao.status === "awaiting_review") { posao.dokument = { tip: "other", tip_pouzdanost: 0.5, ocr_koriscen: false }; posao.provera = { razlog: "classification_uncertain", polja: [] }; } } });
  await otpremi(s.p);
  await dok(s.p, () => window.__citanja.length >= 1);
  await tece(s.p, 4 * 60000, 2000);
  const ekr = await poslovi(s.p);
  const c = await citanja(s.p);
  zapisi("oporavak", "posle 429 stanje je ponovo učitano, poruka o ograničenju nestaje", ekr[0].stanje === "awaiting_review" && !/ograničio/.test(ekr[0].tekst), ekr[0].stanje);
  const pre = c.length;
  await tece(s.p, 3 * 60000, 5000);
  zapisi("oporavak", "u završnom stanju praćenje staje", (await citanja(s.p)).length === pre, String(pre));
  zapisi("oporavak", "nijedno prikačivanje/pregled nije poslato praćenjem", bezPrikacivanja(s));
  await s.zatvori();
}

zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | "));
await browser.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
