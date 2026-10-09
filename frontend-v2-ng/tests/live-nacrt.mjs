// Vindex V2 NG — NS005 Task 8: nacrt podneska u predmetu + overa + DOCX (CAP-060/061/063).
// Pokretanje: `node tests/live-nacrt.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend (tip van spiska 422 i tuđ predmet 404 PRE modela, kritika navoda, naplata,
// overa samo sopstvenih) dokazuje STVARNA ruta: tests/test_ns005_t8_nacrti.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { nacrtRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-nc-A-NE-U-LOG-91", TB = "vx-nc-B-NE-U-LOG-02";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const OPIS = "Ana Jović traži naknadu štete od Petra Petrovića zbog nezgode od 1.3.2026.";

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  const KOR = { [TA]: { id: "kA", predmeti: A, staging: [{ id: "st-old", predmet_id: A[0].id, naziv: "Žalba (parnični postupak)", tip: "zalba_parnicna", status: "pending", created_at: "2026-10-01T09:00:00Z" }] },
                [TB]: { id: "kB", predmeti: B, staging: [{ id: "st-B", predmet_id: B[0].id, naziv: "TAJNI nacrt B", status: "pending", created_at: "2026-10-01" }] } };
  const f = await pokreniFixture(kombinuj(nacrtRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", acceptDownloads: true });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1" || u.protocol === "blob:") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(() => { window.__ncFetch = 0; const o = window.fetch.bind(window); window.fetch = (u, opt) => { if (String(u) === "/api/podnesak") window.__ncFetch++; return o(u, opt); }; });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}/nacrt`);
  await cekaj(p, () => document.getElementById("predmet-naslov").textContent.length > 0);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  return { tipovi: [...document.querySelectorAll("#nc-tip option")].map(o => o.value).filter(Boolean), sudovi: [...document.querySelectorAll("#nc-sud option")].map(o => o.textContent).slice(1),
    dugme: document.getElementById("nc-generisi").disabled, poruka: st("nc-poruka"), provera: st("nc-provera"), rezultat: vid("nc-rezultat"),
    tekst: document.getElementById("nc-tekst").value, naslov: document.getElementById("nc-naslov-nacrta").textContent, docx: st("nc-docx-poruka"),
    overa: [...document.querySelectorAll("#nc-overa-lista .review")].map(li => li.querySelector(".review__name").textContent + "|" + li.querySelector(".review__meta").textContent),
    overaStanje: st("nc-overa-stanje"), overaPoruka: st("nc-overa-poruka"), xss: window.__xss || null, ceo: document.body.innerText };
});
const zahtevi = (s, re, metod = "POST") => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));
async function izradi(p, { tip = "tuzba_naknada_stete", opis = OPIS, sud = "" } = {}) {
  await cekaj(p, () => !document.getElementById("nc-generisi").disabled);
  if (tip) await p.selectOption("#nc-tip", tip);
  if (sud) await p.selectOption("#nc-sud", { label: sud });
  await p.fill("#nc-opis", opis);
  await p.click("#nc-generisi");
  await cekaj(p, () => { const n = document.getElementById("nc-poruka"); return !document.getElementById("nc-rezultat").hidden || (!n.hidden && n.dataset.stanje !== "ucitavanje"); }, null, 10000);
}

// ── A: katalog, validacija, izrada, napomena ─────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (p, b) => tela.push([p, b]) });
  await cekaj(s.p, () => !document.getElementById("nc-generisi").disabled);
  let e = await ekran(s.p);
  zapisi("A.katalog", "vrste podneska SAMO sa servera; sudovi grupisani", JSON.stringify(e.tipovi) === '["tuzba_naknada_stete","zalba_parnicna"]' && e.sudovi.includes("Osnovni sud u Beogradu"), e.tipovi.join());
  await s.p.fill("#nc-opis", OPIS); await s.p.click("#nc-generisi");
  e = await ekran(s.p);
  zapisi("A.validacija", "bez vrste: lokalna greška, ništa poslato", zahtevi(s, /^\/api\/podnesak$/).length === 0 && /vrstu podneska/.test(e.poruka || ""));
  await s.p.selectOption("#nc-tip", "tuzba_naknada_stete"); await s.p.fill("#nc-opis", "kratko"); await s.p.click("#nc-generisi");
  e = await ekran(s.p);
  zapisi("A.validacija", "kratak opis: lokalna greška, ništa poslato", zahtevi(s, /^\/api\/podnesak$/).length === 0 && /20 znakova/.test(e.poruka || ""));
  await izradi(s.p, { sud: "Osnovni sud u Beogradu" });
  e = await ekran(s.p);
  const telo = (tela.find(t => t[0] === "/api/podnesak") || [])[1] || {};
  zapisi("A.izrada", "telo: tip, opis, predmet_id, sud_naziv, sud_adresa — bez user_id", telo.tip === "tuzba_naknada_stete" && telo.predmet_id === s.A[0].id && telo.sud_naziv === "Osnovni sud u Beogradu" && telo.sud_adresa === "Ustanička 29, 11000 Beograd" && !("user_id" in telo), JSON.stringify(telo).slice(0, 160));
  zapisi("A.izrada", "nacrt prikazan; nosi napomenu sistema da ga advokat mora pregledati", e.rezultat && /mora biti pregledan od strane ovlašćenog advokata/.test(e.tekst) && /mora pregledati advokat/.test(e.ceo));
  zapisi("A.izrada", "HTML u nacrtu je tekst (u polju za izmenu), ništa se ne izvršava", e.tekst.includes("<script>") && e.xss === null);
  zapisi("A.izrada", "provera navoda potvrđena i bez placeholder-a → nema upozorenja", e.provera === null, String(e.provera));
  await cekaj(s.p, () => document.querySelectorAll("#nc-overa-lista .review").length >= 2);
  e = await ekran(s.p);
  zapisi("A.overa", "posle izrade lista nacrta na overi je ponovo pročitana (nov nacrt čeka overu)", e.overa.length === 2 && e.overa.every(x => /čeka overu/.test(x)), e.overa.join(" / "));
  // DOCX sa izmenjenim tekstom
  await s.p.fill("#nc-tekst", "IZMENJEN NACRT od advokata");
  const [preuzeto] = await Promise.all([s.p.waitForEvent("download", { timeout: 8000 }).catch(() => null), s.p.click("#nc-docx")]);
  e = await ekran(s.p);
  const docxTelo = (tela.find(t => t[0] === "/api/nacrti/export/docx") || [])[1] || {};
  zapisi("A.docx", "preuzimanje .docx: fajl sa imenom sa servera", !!preuzeto && preuzeto.suggestedFilename() === "Tuzba_za_naknadu_stete.docx" && /je preuzet/.test(e.docx || ""), preuzeto && preuzeto.suggestedFilename());
  zapisi("A.docx", "u .docx ide tekst koji je advokat izmenio", docxTelo.tekst === "IZMENJEN NACRT od advokata" && docxTelo.tip === "tuzba_naknada_stete");
  await s.zatvori();
}
// ── B: signali provere navoda ────────────────────────────────────────────
for (const [naziv, opis, re] of [
  ["kritika nije potvrđena", OPIS + " kritika pala", /NIJE potvrđena/],
  ["keširan nacrt", OPIS + " keš", /pre nekoliko minuta/],
  ["placeholder-i", OPIS + " izmišljen član", /2 mesta označena/],
]) {
  const s = await scenario();
  await izradi(s.p, { opis });
  const e = await ekran(s.p);
  zapisi("B.provera", `${naziv}: izričito upozorenje uz nacrt`, re.test(e.provera || ""), e.provera);
  await s.zatvori();
}
// ── C: greške i nepoznat ishod ───────────────────────────────────────────
for (const [naziv, kuka, stanje, re] of [
  ["422", { status: 422 }, "greska", /nije prihvatio/], ["404", { status: 404 }, "greska", /nije dostupan/], ["429", { status: 429 }, "greska", /najviše 5/],
  ["403", { status: 403 }, "greska", /nije dostupna|krediti/], ["500", { status: 500 }, "nepoznato", /Možda je izrađen/], ["prekid", { prekid: true }, "nepoznato", /nije dobijen/],
]) {
  const s = await scenario({ pre: (p) => p === "/api/podnesak" ? kuka : null });
  await izradi(s.p);
  const e = await ekran(s.p);
  zapisi("C.ishod", `${naziv}: „${stanje}“, bez nacrta, unos ostaje`, (e.poruka || "").startsWith(stanje + ":") && re.test(e.poruka) && !e.rezultat && await s.p.inputValue("#nc-opis") === OPIS, e.poruka);
  zapisi("C.ishod", `${naziv}: aplikacija šalje jednom`, await s.p.evaluate(() => window.__ncFetch) === 1);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/podnesak/types" ? { status: 500 } : null });
  await cekaj(s.p, () => !document.getElementById("nc-poruka").hidden && document.getElementById("nc-poruka").dataset.stanje === "greska");
  const e = await ekran(s.p);
  zapisi("C.katalog", "spisak vrsta nije učitan: izrada onemogućena, bez izmišljenog spiska", e.dugme && !e.tipovi.length && /nije učitan/.test(e.poruka || ""));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/podnesak" ? new Promise(r => setTimeout(r, 900)) : null });
  await cekaj(s.p, () => !document.getElementById("nc-generisi").disabled);
  await s.p.selectOption("#nc-tip", "tuzba_naknada_stete"); await s.p.fill("#nc-opis", OPIS);
  await s.p.evaluate(() => { const b = document.getElementById("nc-generisi"); b.click(); b.click(); document.getElementById("nc-forma").requestSubmit(); });
  await cekaj(s.p, () => !document.getElementById("nc-rezultat").hidden);
  zapisi("C.dupli", "višestruki klik → tačno jedna izrada (jedan trošak)", await s.p.evaluate(() => window.__ncFetch) === 1 && zahtevi(s, /^\/api\/podnesak$/).length === 1);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/nacrti/export/docx" ? { status: 500 } : null });
  await izradi(s.p);
  await s.p.click("#nc-docx");
  await cekaj(s.p, () => { const n = document.getElementById("nc-docx-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("C.docx", "DOCX 500: poruka o neuspehu, nacrt ostaje na ekranu", /nije preuzet/.test(e.docx || "") && e.rezultat);
  await s.zatvori();
}
// ── D: overa ─────────────────────────────────────────────────────────────
{
  const s = await scenario();
  await cekaj(s.p, () => document.querySelectorAll("#nc-overa-lista .review").length > 0);
  let e = await ekran(s.p);
  zapisi("D.overa", "lista overe: samo sopstveni nacrti (ništa od B)", e.overa.length === 1 && !/TAJNI/.test(e.ceo), e.overa.join());
  await s.p.click("#nc-overa-lista .review button:first-child");
  await cekaj(s.p, () => !document.getElementById("nc-overa-poruka").hidden);
  e = await ekran(s.p);
  zapisi("D.overa", "odobravanje: poruka bez internih brojeva, status osvežen", /odobren/.test(e.overaPoruka || "") && /nije dovoljna/.test(e.overaPoruka) && !/confidence|0\.85/.test(e.ceo), e.overaPoruka);
  await cekaj(s.p, () => /odobren/.test(document.querySelector("#nc-overa-lista .review__meta").textContent));
  zapisi("D.overa", "posle odluke stavka više nema dugmad (nije na čekanju)", await s.p.evaluate(() => document.querySelectorAll("#nc-overa-lista .review button").length === 0));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => /^\/api\/staging\/predmet\//.test(p) ? { status: 500 } : null });
  await cekaj(s.p, () => !document.getElementById("nc-overa-stanje").hidden && document.getElementById("nc-overa-stanje").dataset.stanje === "greska");
  zapisi("D.istina", "lista overe 500 → „nije prazna lista“", /nije prazna/.test((await ekran(s.p)).overaStanje || ""));
  await s.zatvori();
}
// ── E: zastarelo i sesija ────────────────────────────────────────────────
{
  const s = await scenario({ pre: (p) => p === "/api/podnesak" ? new Promise(r => setTimeout(r, 1300)) : null });
  await cekaj(s.p, () => !document.getElementById("nc-generisi").disabled);
  await s.p.selectOption("#nc-tip", "tuzba_naknada_stete"); await s.p.fill("#nc-opis", OPIS); await s.p.click("#nc-generisi");
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/nacrt"; }, s.A[1].id);
  await s.p.waitForTimeout(1900);
  const e = await ekran(s.p);
  zapisi("E.zastarelo", "nacrt za predmet 0 se ne prikazuje na predmetu 1", !e.rezultat && e.tekst === "" && e.poruka === null, String(e.poruka));
  await s.zatvori();
}
{
  const s = await scenario();
  await izradi(s.p);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(500);
  const e = await ekran(s.p);
  zapisi("E.sesija", "A→B: nacrt i lista overe A nestaju odmah", !e.rezultat && e.tekst === "" && !e.overa.length && !/Tužilac traži naknadu/.test(e.ceo));
  await s.zatvori();
}
// ── F: raspored ──────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await izradi(s.p);
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("F.raspored", `${w}px: bez horizontalnog skrola sa nacrtom`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0, sviSpoljni.slice(0, 2).join());
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
