// Vindex V2 NG — NS005 Task 9: Kancelarija — tim, portfolio, zdravlje (CAP-091/090/095).
// Pokretanje: `node tests/live-kancelarija.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend (tim samo svoje kancelarije, portfolio samo svoji predmeti, pad → 503 umesto
// lažnog „nema kancelarije"/„sve pod kontrolom"/ocene) dokazuje tests/test_ns005_t9_kancelarija.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { kancelarijaRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-ka-A-NE-U-LOG-13", TB = "vx-ka-B-NE-U-LOG-24", TD = "vx-ka-D-NE-U-LOG-35";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", put = "#/kancelarija", w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2, { naziv: i => i === 1 ? '<img src=x onerror="window.__xss=5">Spor' : "Predmet A" }), B = napraviPredmete("kB", 1, { naziv: () => "TAJNI B" });
  const KOR = {
    [TA]: { id: "kA", predmeti: A, rokovi: [{ predmet_id: A[0].id, predmet_naziv: "Predmet A", dogadjaj: "Rok za žalbu", datum_iso: "2026-10-12", vaznost: "kritičan" }],
            kancelarija: { status: "aktivan", moja_uloga: "admin", firma: { id: "k1", naziv: "Jović i partneri" }, clanovi: [{ id: "c1", email: "saradnik@jovic.rs", uloga: "saradnik", uloga_label: "Saradnik", status: "ACTIVE" }] } },
    [TB]: { id: "kB", predmeti: B, kancelarija: { status: "aktivan", moja_uloga: "admin", firma: { id: "k2", naziv: "TAJNA kancelarija" }, clanovi: [{ email: "tajni@b.rs", uloga_label: "Partner", status: "ACTIVE" }] } },
    [TD]: { id: "kD", predmeti: [] },
  };
  const f = await pokreniFixture(kombinuj(kancelarijaRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${put}`);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, ctx, p, drugi, spoljni, A, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  const ka = document.querySelector('.sidenav__item[href="#/kancelarija"]');
  return { firma: document.getElementById("ka-firma").textContent, uloga: document.getElementById("ka-uloga").textContent,
    clanovi: [...document.querySelectorAll("#ka-tim-lista .people__name")].map(x => x.textContent), tim: st("ka-tim-stanje"),
    portfolio: document.getElementById("ka-portfolio").innerText, portfolioStanje: st("ka-portfolio-stanje"),
    zdravlje: document.getElementById("ka-zdravlje").innerText, zdravljeStanje: st("ka-zdravlje-stanje"),
    navCurrent: ka && ka.getAttribute("aria-current"), navLink: !!ka, xss: window.__xss || null, ceo: document.body.innerText };
});
const zahtevi = (s, put) => s.f.zahtevi.filter(z => z.putanja === put);
const gotovo = (p) => cekaj(p, () => ["ka-tim-stanje", "ka-portfolio-stanje"].every(id => { const n = document.getElementById(id); return n.hidden || n.dataset.stanje !== "ucitavanje"; })
  && (document.getElementById("ka-portfolio").children.length > 0 || !document.getElementById("ka-portfolio-stanje").hidden)
  && (document.getElementById("ka-firma").textContent.length > 0 || !document.getElementById("ka-tim-stanje").hidden));

// ── A: tim, portfolio, indeks na zahtev ──────────────────────────────────
{
  const s = await scenario({}, { put: "" });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  zapisi("A.nav", "LIVE: „Kancelarija“ je stvaran link", (await ekran(s.p)).navLink);
  await s.p.click('.sidenav__item[href="#/kancelarija"]');
  await gotovo(s.p);
  let e = await ekran(s.p);
  zapisi("A.nav", "aktivna stavka navigacije je „Kancelarija“", e.navCurrent === "page");
  zapisi("A.tim", "naziv kancelarije, uloga i članovi iz odgovora", e.firma === "Jović i partneri" && /administrator/.test(e.uloga) && JSON.stringify(e.clanovi) === '["saradnik@jovic.rs"]', e.clanovi.join());
  zapisi("A.portfolio", "brojevi i rokovi 14 dana; naziv predmeta je tekst", /Predmeta ukupno\s*2/.test(e.portfolio) && /Rok za žalbu/.test(e.portfolio) && /Kritičnih rokova u 7 dana\s*1/.test(e.portfolio) && e.xss === null, e.portfolio.slice(0, 160));
  zapisi("A.portfolio", "serverski sažetak sa ikonicom se ne prikazuje", !/⚠|HITNIH/.test(e.ceo));
  zapisi("A.zdravlje", "indeks se NE računa automatski (troši kredit)", zahtevi(s, "/api/firm/health-index").length === 0 && e.zdravlje === "");
  await s.p.click("#ka-zdravlje-dugme");
  await cekaj(s.p, () => document.getElementById("ka-zdravlje").children.length > 0);
  e = await ekran(s.p);
  zapisi("A.zdravlje", "ocena, slovo i komponente; bez AI direktive i slabih signala", /72\s*\/ 100/.test(e.zdravlje) && /B\+/.test(e.zdravlje) && /Rokovi i ročišta\s*15 od 20/.test(e.zdravlje) && !/AI DIREKTIVA|SLAB SIGNAL/.test(e.ceo), e.zdravlje.slice(0, 120));
  await s.zatvori();
}
// ── B: druga kancelarija, bez kancelarije, greške ────────────────────────
{
  const s = await scenario({}, { token: TB, korisnik: "kB" });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("B.izolacija", "korisnik B vidi samo svoju kancelariju (ništa od A)", e.firma === "TAJNA kancelarija" && !/Jović i partneri|saradnik@jovic/.test(e.ceo));
  await s.zatvori();
}
{
  const s = await scenario({}, { token: TD, korisnik: "kD" });
  await gotovo(s.p);
  zapisi("B.prazno", "bez kancelarije: „Niste član nijedne kancelarije“ (uspešan odgovor)", /Niste član/.test((await ekran(s.p)).tim || ""));
  await s.zatvori();
}
for (const [naziv, put, polje] of [["tim 503", "/api/kancelarija/moja", "tim"], ["portfolio 503", "/portfolio/dashboard", "portfolioStanje"]]) {
  const s = await scenario({ pre: (p) => p === put ? { status: 503 } : null });
  await gotovo(s.p);
  const e = await ekran(s.p);
  const ok = /nije učitan.*nije prazan/.test(e[polje] || "") && (polje === "tim" ? !/Niste član/.test(e.ceo) : !/Predmeta ukupno/.test(e.portfolio));
  zapisi("B.istina", `${naziv}: greška, ne „nema kancelarije“ / prazan portfolio`, ok, e[polje]);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/firm/health-index" ? { status: 503 } : null });
  await gotovo(s.p);
  await s.p.click("#ka-zdravlje-dugme");
  await cekaj(s.p, () => { const n = document.getElementById("ka-zdravlje-stanje"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("B.istina", "indeks 503: greška, bez ocene", /nije učitan/.test(e.zdravljeStanje || "") && e.zdravlje === "");
  await s.zatvori();
}
// ── C: sesija i zastarelo ────────────────────────────────────────────────
{
  const s = await scenario({ pre: (p) => p === "/portfolio/dashboard" ? new Promise(r => setTimeout(r, 1200)) : null });
  await cekaj(s.p, () => document.getElementById("ka-firma").textContent.length > 0);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1600);
  const e = await ekran(s.p);
  zapisi("C.sesija", "A→B: tim i portfolio A nestaju; spor portfolio A se ne slika", e.firma === "" && !/Jović i partneri|Rok za žalbu|Predmeta ukupno/.test(e.ceo));
  await s.zatvori();
}
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await gotovo(s.p);
  await s.p.click("#ka-zdravlje-dugme");
  await cekaj(s.p, () => document.getElementById("ka-zdravlje").children.length > 0);
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("D.raspored", `${w}px: bez horizontalnog skrola`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0);
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("token", "token nije u konzoli", ![TA, TB, TD].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB, TD].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
