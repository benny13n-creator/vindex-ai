// Vindex V2 NG — NS005 Task 6: pravno pitanje u kontekstu predmeta (CAP-040).
// Pokretanje: `node tests/live-pitanje.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend ishode (bez izvora → model se ne poziva; izmišljen član; pad korpusa; tuđ
// predmet bez konteksta) dokazuje STVARNA ruta: tests/test_ns005_t6_pravno_pitanje.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { pitanjeRuta, beleskaRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-pp-A-NE-U-LOG-57", TB = "vx-pp-B-NE-U-LOG-68";
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
async function scenario(kuke = {}, { token = TA, korisnik = "kA", put = null, w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  const KOR = { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
  const f = await pokreniFixture(kombinuj(pitanjeRuta(KOR, kuke), beleskaRuta(KOR), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  // Broji POZIVE IZ APLIKACIJE (fetch) ka /api/pitanje — odvojeno od zahteva koje server primi.
  await ctx.addInitScript(() => {
    window.__ppFetch = 0;
    const o = window.fetch.bind(window);
    window.fetch = (u, opt) => { if (String(u).indexOf("/api/pitanje") === 0 && opt && opt.method === "POST") window.__ppFetch++; return o(u, opt); };
  });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${put === null ? "#/predmeti/" + A[0].id + "/pitanje" : put}`);
  await cekaj(p, () => document.getElementById("predmet-naslov").textContent.length > 0);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  return { hash: location.hash, odgovor: vid("pp-odgovor"), tabAktivan: document.getElementById("tab-pitanje").getAttribute("aria-current"),
    stanje: vid("pp-stanje") ? document.getElementById("pp-stanje").dataset.stanje + ":" + document.getElementById("pp-stanje").textContent : null,
    upozorenja: [...document.querySelectorAll("#pp-upozorenja .warn")].map(x => x.dataset.kljuc),
    izvori: [...document.querySelectorAll("#pp-izvori .source")].map(x => x.textContent),
    izvoriVidljivi: vid("pp-izvori-blok"), sigurnost: vid("pp-sigurnost") ? document.getElementById("pp-sigurnost").textContent : null,
    kontekst: vid("pp-kontekst") ? document.getElementById("pp-kontekst").textContent : null,
    naslovi: [...document.querySelectorAll("#pp-tekst .answer__h")].map(x => x.textContent),
    tekst: document.getElementById("pp-tekst").textContent, cinjenice: [...document.querySelectorAll("#pp-cinjenice .source")].map(x => x.textContent),
    dugme: document.getElementById("pp-posalji").disabled, unos: document.getElementById("pp-pitanje").value,
    xss: window.__xss || null, ceo: document.body.innerText };
});
const posti = (s) => s.f.zahtevi.filter(z => z.metod === "POST" && z.putanja === "/api/pitanje");
async function pitaj(p, q) { await p.fill("#pp-pitanje", q); await p.click("#pp-posalji");
  await cekaj(p, () => { const n = document.getElementById("pp-stanje"); return !document.getElementById("pp-odgovor").hidden || (!n.hidden && n.dataset.stanje !== "ucitavanje"); }); }

// ── A: odgovor sa izvorima ───────────────────────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b) });
  let e = await ekran(s.p);
  zapisi("A.ulaz", "#/predmeti/<id>/pitanje: tab „Pravno pitanje“ aktivan, nema odgovora pre pitanja", e.tabAktivan === "page" && !e.odgovor);
  await s.p.click("#pp-posalji");
  e = await ekran(s.p);
  zapisi("A.ulaz", "prazno pitanje: lokalna greška, ništa poslato", posti(s).length === 0 && /tri znaka/.test(e.stanje || ""));
  await pitaj(s.p, "Kako dokazati štetu?");
  e = await ekran(s.p);
  zapisi("A.zahtev", "tačno jedan POST sa {pitanje, predmet_id} — bez user_id i bez istorije", posti(s).length === 1 && JSON.stringify(Object.keys(tela[0]).sort()) === '["pitanje","predmet_id"]' && tela[0].predmet_id === s.A[0].id && posti(s)[0].auth === "Bearer " + TA, JSON.stringify(tela[0]));
  zapisi("A.izvori", "izvori SAMO iz odgovora: „Zakon o…, Član 154“ i „…, član 200“; red bez zakona ispušten", JSON.stringify(e.izvori) === JSON.stringify(["Zakon o obligacionim odnosima, Član 154", "Zakon o obligacionim odnosima, član 200"]), e.izvori.join(" | "));
  zapisi("A.izvori", "sigurnost kao reč (ne procenat)", e.sigurnost === "Jako poklapanje sa propisom" && !/%/.test(e.sigurnost));
  zapisi("A.izvori", "bez upozorenja kada ima izvora i ništa nije palo", e.upozorenja.length === 0, e.upozorenja.join());
  zapisi("A.tekst", "odeljci odgovora („--- NASLOV“) postaju naslovi; ** i ikonice uklonjeni", JSON.stringify(e.naslovi) === '["BRZA PROCENA","PRAVNI ZAKLJUČAK",""]'.replace(',""', '') || e.naslovi.slice(0, 2).join() === "BRZA PROCENA,PRAVNI ZAKLJUČAK", e.naslovi.join("|"));
  zapisi("A.tekst", "tekst bez ** i bez ⚠️/📊; pravna napomena backend-a zadržana (jednom)", !/\*\*/.test(e.tekst) && !/⚠|📊/.test(e.tekst) && (e.tekst.match(/Pravna napomena/g) || []).length === 1);
  zapisi("A.tekst", "HTML u odgovoru je tekst (ništa se ne izvršava)", e.tekst.includes("<img src=x") && e.xss === null);
  zapisi("A.kontekst", "kontekst predmeta potvrđen", /uz beleške i utvrđene činjenice/.test(e.kontekst || ""));
  zapisi("A.cinjenice", "činjenice iz dokumenta odvojeno, označene kao „nije utvrđena činjenica“", e.cinjenice.length === 1 && /nije utvrđena činjenica/.test(e.ceo));
  // Osvežavanje istog predmeta (npr. posle beleške) ne briše odgovor.
  await s.p.click("#tab-rad");
  await s.p.fill("#bel-tekst", "Nova beleška");
  await s.p.click("#bel-dodaj");
  await cekaj(s.p, () => { const n = document.getElementById("bel-poruka"); return !n.hidden && n.dataset.stanje === "uspeh"; });
  await s.p.click("#tab-pitanje");
  await cekaj(s.p, () => !document.getElementById("odeljak-pitanje").hidden);
  e = await ekran(s.p);
  zapisi("A.trajnost", "posle osvežavanja istog predmeta odgovor ostaje", e.odgovor && e.izvori.length === 2);
  await s.zatvori();
}
// ── B: bez izvora / izmišljen član / pad korpusa / delimično ─────────────
for (const [naziv, q, provera] of [
  ["bez pouzdanog izvora", "Pitanje bez izvora o avio prevozu", e => e.upozorenja.join() === "bez-pogotka" && !e.izvoriVidljivi && /Nemam pouzdan odgovor/.test(e.tekst) && /nije izvor prava/.test(e.ceo) && e.sigurnost === "Slabo poklapanje sa propisom"],
  ["izmišljen član", "Šta kaže član 9999 ZOO?", e => e.upozorenja.join() === "bez-pogotka" && !e.izvoriVidljivi && /nije pronađen/.test(e.tekst)],
  ["pad korpusa", "Pitanje kad je pad korpusa", e => e.upozorenja.join() === "korpus-pao" && !e.izvoriVidljivi && /NE počiva na pretrazi propisa/.test(e.ceo) && !/Nijedan propis nije pronađen/.test(e.ceo)],
  ["delimično provereno", "Delimično pitanje o otkazu", e => e.upozorenja.join() === "izvor-nije-proveren" && /dokumenti predmeta/.test(e.ceo) && e.izvori.length === 1],
]) {
  const s = await scenario();
  await pitaj(s.p, q);
  const e = await ekran(s.p);
  zapisi("B.istina", `${naziv}: tačno upozorenje, nikakav izmišljen izvor`, provera(e), `${e.upozorenja.join()} | izvori=${e.izvori.length} | ${e.sigurnost}`);
  await s.zatvori();
}
{
  const s = await scenario({}, { put: "#/predmeti/kB-00000/pitanje", token: TA });
  await s.p.waitForTimeout(400);
  zapisi("B.tudj", "tuđ predmet: detalj „nije dostupan“, kartica pitanja nije ponuđena", /nije dostupan/.test(await s.p.textContent("#predmet-stanje-naslov")) && await s.p.evaluate(() => document.getElementById("odeljak-pitanje").hidden));
  await s.zatvori();
}
{
  // Backend je kontekst preskočio (fail-closed: predmet nije mogao da se pročita).
  const s = await scenario({ kontekst: false });
  await pitaj(s.p, "Kako dokazati štetu?");
  const e = await ekran(s.p);
  zapisi("B.kontekst", "`kontekst_predmeta:false` se izričito saopštava („NISU uključeni“)", /NISU uključeni/.test(e.kontekst || ""), e.kontekst);
  await s.zatvori();
}

// ── C: greške i nepoznat ishod ───────────────────────────────────────────
for (const [naziv, kuka, stanje, re] of [
  ["500", { status: 500 }, "nepoznato", /nije dobijen/], ["prekid", { prekid: true }, "nepoznato", /možda obrađeno/],
  ["400 guard", { status: 400 }, "greska", /nije prihvaćen/], ["403", { status: 403 }, "greska", /nije dostupna|krediti/],
  ["429", { status: 429 }, "greska", /Previše/], ["401", { status: 401 }, "greska", /Prijava/],
]) {
  const s = await scenario({ pre: () => kuka });
  await pitaj(s.p, "Kako dokazati štetu?");
  const e = await ekran(s.p);
  zapisi("C.ishod", `${naziv}: „${stanje}“, bez odgovora i bez izvora, pitanje ostaje u polju`, (e.stanje || "").startsWith(stanje + ":") && re.test(e.stanje) && !e.odgovor && !e.izvori.length && e.unos === "Kako dokazati štetu?", e.stanje);
  const fetchova = await s.p.evaluate(() => window.__ppFetch);
  zapisi("C.ishod", `${naziv}: aplikacija šalje pitanje tačno jednom (bez automatskog ponavljanja)`, fetchova === 1, `fetch=${fetchova}, server=${posti(s).length}`);
  if (posti(s).length > 1) console.log(`INFO  [ogranicenje] ${naziv}: server je primio ${posti(s).length} pitanja za 1 fetch (Chromium ponovo šalje na ponovo korišćenoj vezi)`);
  await s.zatvori();
}
{
  const s = await scenario({ pre: () => new Promise(r => setTimeout(r, 900)) });
  await s.p.fill("#pp-pitanje", "Kako dokazati štetu?");
  await s.p.evaluate(() => { const b = document.getElementById("pp-posalji"); b.click(); b.click(); document.getElementById("pp-forma").requestSubmit(); });
  zapisi("C.dupli", "tokom pretrage dugme zaključano", (await ekran(s.p)).dugme === true);
  await cekaj(s.p, () => !document.getElementById("pp-odgovor").hidden);
  zapisi("C.dupli", "višestruki klik → tačno jedno pitanje (jedan trošak)", posti(s).length === 1);
  await s.zatvori();
}
// ── D: zastareli odgovor ─────────────────────────────────────────────────
{
  const s = await scenario({ pre: () => new Promise(r => setTimeout(r, 1300)) });
  await s.p.fill("#pp-pitanje", "Kako dokazati štetu?"); await s.p.click("#pp-posalji");
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/pitanje"; }, s.A[1].id);
  await s.p.waitForTimeout(1800);
  const e = await ekran(s.p);
  zapisi("D.zastarelo", "odgovor za predmet 0 se ne prikazuje na predmetu 1", e.hash.includes(s.A[1].id) && !e.odgovor && !e.izvori.length && e.stanje === null && e.unos === "", `${e.stanje}`);
  await s.zatvori();
}
{
  const s = await scenario({ pre: () => new Promise(r => setTimeout(r, 1300)) });
  await s.p.fill("#pp-pitanje", "Kako dokazati štetu?"); await s.p.click("#pp-posalji");
  await s.p.waitForTimeout(150);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1800);
  const e = await ekran(s.p);
  zapisi("D.sesija", "A→B dok pitanje leti: ni pitanje ni odgovor A nisu vidljivi", !e.odgovor && e.unos === "" && !/Kako dokazati štetu|Član 154/.test(e.ceo));
  await s.zatvori();
}
{
  const s = await scenario();
  await pitaj(s.p, "Kako dokazati štetu?");
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/pitanje"; }, s.A[1].id);
  await cekaj(s.p, () => document.getElementById("predmet-naslov").textContent === "Predmet kA broj 1");
  const e = await ekran(s.p);
  zapisi("D.predmet", "prelazak na drugi predmet briše prethodni odgovor", !e.odgovor && !e.izvori.length && e.unos === "");
  await s.zatvori();
}
// ── E: raspored ──────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await pitaj(s.p, "Kako dokazati štetu?");
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("E.raspored", `${w}px: bez horizontalnog skrola sa odgovorom`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0);
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
