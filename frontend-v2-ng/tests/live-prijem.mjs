// Vindex V2 NG — NS005 Task 14: prijem dokumenata u predmet (Smart Intake + OCR).
// Pokretanje: `node tests/live-prijem.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend (stvarne rute, STVARAN worker i STVARAN Tesseract OCR, izolacija A/B, dedupe po korisniku,
// pregled pre prikačivanja, prikačivanje ne menja predmet, V2 idempotencija) dokazuje:
// tests/test_ns005_t14_smart_intake.py; OCR matrica: tests/test_ns005_b_ocr.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { prijemRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-pr-A-NE-U-LOG-73", TB = "vx-pr-B-NE-U-LOG-26";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const RAZMAK_U_TESTU = 3300;   // malo duže od razmaka praćenja (3 s): sledeće čitanje je tada u letu
const PDF = { name: "sken <b>tužbe</b>.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 skenirana tuzba A") };
const ENTITETI = () => [
  { entity_id: "ent-1", entity_type: "case_number", value: "P 1234/2026", confidence: 0.95, needs_review: false, corrected: false },
  { entity_id: "ent-2", entity_type: "plaintiff", value: "Marko <img src=x onerror=window.__xss=1>", confidence: 0.6, needs_review: true, corrected: false },
  { entity_id: "ent-3", entity_type: "amount", value: null, confidence: 0.0, needs_review: true, corrected: false },
];
const DO_PREGLEDA = (posao, n) => {   // stvarna stanja baze, korak po korak (samo dok je posao u obradi)
  if (posao.status === "completed" || posao.status === "failed" || posao.predmet_id || posao.dokument) return;
  const niz = ["received", "preprocessing", "classifying", "extracting", "awaiting_review"];
  posao.status = niz[Math.min(n - 1, niz.length - 1)];
  if (posao.status === "awaiting_review" && !posao.dokument) {
    posao.dokument = { tip: "other", tip_pouzdanost: 0.5, ocr_koriscen: true, tip_moze_biti_zastareo: false };
    posao.entiteti = ENTITETI();
    posao.provera = { razlog: "classification_uncertain", polja: ["document_type", "plaintiff", "amount"] };
  }
};

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  const KOR = { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
  const f = await pokreniFixture(kombinuj(prijemRuta(KOR, { napreduj: DO_PREGLEDA, ...kuke }), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(() => { window.__prFetch = {}; const o = window.fetch.bind(window); window.fetch = (u, opt) => { const k = String(u).split("?")[0].replace(/[0-9a-f-]{36}|ent-[\w-]+/g, "{id}") + ":" + ((opt && opt.method) || "GET"); window.__prFetch[k] = (window.__prFetch[k] || 0) + 1; return o(u, opt).catch(e => { if (e && e.name === "AbortError") window.__prPrekinuto = (window.__prPrekinuto || 0) + 1; throw e; }); }; });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}/prijem`);
  await cekaj(p, () => document.getElementById("predmet-naslov").textContent.length > 0 && !document.getElementById("odeljak-prijem").hidden);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  return {
    poruka: st("pd-poruka"),
    poslovi: [...document.querySelectorAll("#pd-poslovi .intake")].map(li => ({
      ime: li.querySelector(".intake__name").textContent, stanje: li.querySelector(".intake__state").textContent,
      kod: li.querySelector(".intake__state").dataset.stanje, tekst: li.innerText,
      polja: [...li.querySelectorAll(".intake__value")].map(x => x.dataset.polje + "=" + x.textContent),
      dugmad: [...li.querySelectorAll("button")].map(b => b.textContent), msg: li.querySelector(".intake__msg") && !li.querySelector(".intake__msg").hidden ? li.querySelector(".intake__msg").dataset.stanje + ":" + li.querySelector(".intake__msg").textContent : null,
    })),
    tab: document.getElementById("tab-prijem").getAttribute("aria-current"), xss: window.__xss || null, ceo: document.body.innerText,
  };
});
const zahtevi = (s, re, metod = "POST") => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));
const fetchova = (p, k) => p.evaluate((k) => window.__prFetch[k] || 0, k);
async function otpremi(p, fajl = PDF) { await p.setInputFiles("#pd-fajlovi", Array.isArray(fajl) ? fajl : [fajl]); await p.click("#pd-otpremi"); }
const naStanju = (p, kod) => cekaj(p, (kod) => [...document.querySelectorAll("#pd-poslovi .intake__state")].some(x => x.dataset.stanje === kod), kod, 20000);

// ── A: tok do pregleda, stvarna stanja ───────────────────────────────────
{
  const tela = [], videna = [];
  const s = await scenario({ upisano: (p, b) => tela.push([p, b]), napreduj: (posao, n) => { DO_PREGLEDA(posao, n); videna.push(posao.status); } });
  zapisi("A.tab", "#/predmeti/<id>/prijem otvara odeljak, tab je aktivan", (await ekran(s.p)).tab === "page");
  await otpremi(s.p);
  await naStanju(s.p, "awaiting_review");
  const e = await ekran(s.p);
  const t = (tela.find(x => x[0] === "/api/smart-intake/documents") || [])[1] || {};
  zapisi("A.otpremanje", "multipart sa jednim fajlom; ključ zahteva poslat (server ga za otpremanje ne koristi)", t.fajlova === 1 && t.imena[0] === "sken <b>tužbe</b>.pdf" && /^[0-9a-f-]{36}$/.test(t.kljuc || ""), JSON.stringify(t));
  zapisi("A.stanja", "prikazana su STVARNA stanja servera redom, bez izmišljenih procenata", videna.join(",").startsWith("received,preprocessing,classifying,extracting,awaiting_review") && !/\d+ ?%(?! *$)/.test(e.poslovi[0].stanje), videna.join(","));
  zapisi("A.pregled", "„Čeka vaš pregled“; vrsta sa pouzdanošću; OCR naveden", e.poslovi[0].stanje === "Čeka vaš pregled" && /Ostalo \(pouzdanost 50%\) · tekst pročitan OCR-om/.test(e.poslovi[0].tekst), e.poslovi[0].tekst.slice(0, 160));
  zapisi("A.polja", "pouzdan podatak bez oznake; nesiguran „proverite“; odsutan „nije pronađeno“ (ne prazan)", e.poslovi[0].polja.some(x => /^case_number=P 1234\/2026 · pouzdanost 95%$/.test(x)) && e.poslovi[0].polja.some(x => /^plaintiff=.*pouzdanost 60% · proverite/.test(x)) && e.poslovi[0].polja.some(x => /^amount=nije pronađeno · proverite/.test(x)), e.poslovi[0].polja.join(" | "));
  zapisi("A.razlog", "razlog pregleda je rečima", /Vrsta dokumenta nije pouzdano prepoznata/.test(e.poslovi[0].tekst));
  zapisi("A.xss", "HTML u imenu fajla i u podatku je tekst", e.poslovi[0].ime.includes("<b>tužbe</b>") && e.ceo.includes("<img src=x") && e.xss === null);
  zapisi("A.prikacivanje", "pre pregleda nema dugmeta za prikačivanje", e.poslovi[0].dugmad.includes("Potvrđujem pregled") && !e.poslovi[0].dugmad.includes("Prikači ovom predmetu"), e.poslovi[0].dugmad.join(","));
  const g0 = zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length;
  await s.p.waitForTimeout(3500);
  zapisi("A.pracenje", "praćenje staje u završnom stanju (nema novih čitanja)", zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length === g0);
  // ispravka → pregled → prikačivanje
  await s.p.fill('#pd-poslovi .intake__value[data-polje="plaintiff"] input', "Marko Petrović");
  await s.p.click('#pd-poslovi .intake__value[data-polje="plaintiff"] button');
  await cekaj(s.p, () => /ispravljeno/.test(document.querySelector('#pd-poslovi .intake__value[data-polje="plaintiff"]').textContent));
  const ti = (tela.find(x => /entities\/ent-2\/correct$/.test(x[0])) || [])[1] || {};
  zapisi("B.ispravka", "telo ispravke je samo {corrected_value}; prikaz „ispravljeno“", JSON.stringify(ti) === '{"corrected_value":"Marko Petrović"}');
  await s.p.click("text=Potvrđujem pregled");
  await naStanju(s.p, "completed");
  await cekaj(s.p, () => [...document.querySelectorAll("#pd-poslovi button")].some(b => b.textContent === "Prikači ovom predmetu"));
  const detPre = zahtevi(s, new RegExp(`^/api/predmeti/${s.A[0].id}$`), "GET").length;
  await s.p.click("text=Prikači ovom predmetu");
  await cekaj(s.p, () => /Prikačeno ovom predmetu/.test(document.getElementById("pd-poslovi").innerText));
  const tf = (tela.find(x => /\/finalize$/.test(x[0])) || [])[1] || {};
  const e2 = await ekran(s.p);
  zapisi("B.prikacivanje", "telo je SAMO {predmet_id: ovaj predmet} — bez klijenta i bez user_id", JSON.stringify(tf) === JSON.stringify({ predmet_id: s.A[0].id }), JSON.stringify(tf));
  zapisi("B.prikacivanje", "poruka: prikačen, podaci predmeta nisu menjani", /^uspeh:Dokument je prikačen predmetu\. Podaci predmeta nisu menjani\./.test((e2.poslovi[0].msg) || "") || /Prikačeno ovom predmetu/.test(e2.poslovi[0].tekst), e2.poslovi[0].msg);
  await cekaj(s.p, (n) => true, null, 50);
  await s.p.waitForTimeout(400);
  zapisi("B.prikacivanje", "predmet je ponovo pročitan (lista dokumenata se osvežava)", zahtevi(s, new RegExp(`^/api/predmeti/${s.A[0].id}$`), "GET").length > detPre);
  zapisi("B.prikacivanje", "nema dugmadi za pregled/prikačivanje posle prikačivanja", e2.poslovi[0].dugmad.length === 0, e2.poslovi[0].dugmad.join(","));
  await s.zatvori();
}
// ── C: ostala stanja ────────────────────────────────────────────────────
for (const [naziv, napreduj, re] of [
  ["OCR nije uspeo", (p) => { p.status = "awaiting_review"; p.dokument = { tip: "other", tip_pouzdanost: 0.0, ocr_koriscen: true }; p.entiteti = []; p.provera = { razlog: "ocr_failed", polja: [] }; }, /Tekst dokumenta nije mogao da se pročita \(OCR nije uspeo\)\. Ništa nije izvučeno\./],
  ["trajni neuspeh", (p) => { p.status = "failed"; p.attempts = 3; }, /Obrada nije uspela posle više pokušaja\. Dokument nije prikačen/],
  ["ponovni pokušaj", (p, n) => { p.status = n < 3 ? "received" : "failed"; p.attempts = n < 3 ? 1 : 3; }, /Ponovni pokušaj zakazan|Obrada nije uspela/],
  ["prikačen drugom predmetu", (p) => { p.status = "completed"; p.predmet_id = "kA-00001"; }, /već prikačen drugom vašem predmetu/],
]) {
  const s = await scenario({ napreduj });
  await otpremi(s.p);
  await cekaj(s.p, (re) => new RegExp(re).test(document.getElementById("pd-poslovi").innerText), re.source, 15000);
  const e = await ekran(s.p);
  zapisi("C.stanja", `${naziv}: poštena poruka, bez lažnog uspeha`, re.test(e.poslovi[0].tekst) && !e.poslovi[0].dugmad.includes("Prikači ovom predmetu") || (naziv === "ponovni pokušaj" && re.test(e.poslovi[0].tekst)), e.poslovi[0].tekst.slice(0, 200));
  if (naziv === "OCR nije uspeo") zapisi("C.stanja", "OCR nije uspeo: ne tvrdi „tekst pročitan OCR-om“", !/tekst pročitan OCR-om/.test(e.poslovi[0].tekst));
  await s.zatvori();
}
{
  const s = await scenario();
  await otpremi(s.p);
  await naStanju(s.p, "awaiting_review");
  await otpremi(s.p, { ...PDF, name: "isti sadrzaj.pdf" });
  await s.p.waitForTimeout(600);
  const e = await ekran(s.p);
  zapisi("C.dedupe", "isti sadržaj: isti posao (bez duplikata u listi), uz objašnjenje", e.poslovi.length === 1, String(e.poslovi.length));
  await s.zatvori();
}
// ── D: greške i nepoznat ishod ──────────────────────────────────────────
for (const [naziv, kuka, stanje, re] of [
  ["429", { status: 429 }, "greska", /Previše otpremanja/], ["500", { status: 500 }, "nepoznato", /Ponovo otpremite iste fajlove/], ["prekid", { prekid: true }, "nepoznato", /Ishod otpremanja nije poznat/],
]) {
  const s = await scenario({ pre: (p) => p === "/api/smart-intake/documents:POST" ? kuka : null });
  await otpremi(s.p);
  await cekaj(s.p, () => { const n = document.getElementById("pd-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("D.otpremanje", `${naziv}: „${stanje}“, bez posla u listi, jedno slanje`, (e.poruka || "").startsWith(stanje + ":") && re.test(e.poruka) && e.poslovi.length === 0 && await fetchova(s.p, "/api/smart-intake/documents:POST") === 1, e.poruka);
  await s.zatvori();
}
{
  const s = await scenario({ napreduj: (p) => { p.status = "completed"; p.dokument = { tip: "lawsuit", tip_pouzdanost: 0.9, ocr_koriscen: false }; },
    pre: (p) => p === "/api/smart-intake/jobs/{id}/finalize:POST" ? { prekid: true } : null });
  await otpremi(s.p);
  await cekaj(s.p, () => [...document.querySelectorAll("#pd-poslovi button")].some(b => b.textContent === "Prikači ovom predmetu"));
  const g0 = zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length;
  await s.p.click("text=Prikači ovom predmetu");
  await cekaj(s.p, () => { const m = document.querySelector("#pd-poslovi .intake__msg"); return m && !m.hidden && m.dataset.stanje !== "ucitavanje"; });
  await s.p.waitForTimeout(500);
  const e = await ekran(s.p);
  zapisi("D.prikacivanje", "prekid pri prikačivanju: „ishod nepoznat“ + ponovno čitanje, nikad „nije prikačen“", /^nepoznato:Ishod nije poznat/.test(e.poslovi[0].msg || "") && zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length > g0 && !/nije prikačen/.test(e.poslovi[0].msg), e.poslovi[0].msg);
  zapisi("D.prikacivanje", "prikačivanje poslato jednom", await fetchova(s.p, "/api/smart-intake/jobs/{id}/finalize:POST") === 1);
  await s.zatvori();
}
{
  const s = await scenario();
  await s.p.click("#pd-otpremi");
  let e = await ekran(s.p);
  zapisi("E.validacija", "bez fajla: lokalna greška, ništa poslato", /Izaberite bar jedan fajl/.test(e.poruka || "") && zahtevi(s, /smart-intake\/documents/).length === 0);
  await otpremi(s.p, { name: "program.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  e = await ekran(s.p);
  zapisi("E.validacija", "nepodržan format: lokalna greška, ništa poslato", /Nije poslato: program\.exe/.test(e.poruka || "") && zahtevi(s, /smart-intake\/documents/).length === 0, e.poruka);
  await s.zatvori();
}
// ── F: sesija i promena predmeta ────────────────────────────────────────
{
  const s = await scenario({ napreduj: (p, n) => { p.status = n < 50 ? "extracting" : "awaiting_review"; } });
  await otpremi(s.p);
  await naStanju(s.p, "extracting");
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(800);
  const g0 = zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length;
  await s.p.waitForTimeout(3500);
  const e = await ekran(s.p);
  zapisi("F.sesija", "A→B: poslovi A nestaju i praćenje A staje", e.poslovi.length === 0 && !/sken/.test(e.ceo) && zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length === g0);
  await s.zatvori();
}
{
  // Čitanje stanja je U LETU (server kasni) kad se promeni korisnik: zahtev mora biti PREKINUT, ne samo ignorisan.
  let n = 0;
  const s = await scenario({ napreduj: (p) => { p.status = "extracting"; }, pre: (p) => p === "/api/smart-intake/jobs/{id}:GET" && ++n >= 2 ? new Promise(r => setTimeout(r, 2500)) : null });
  await otpremi(s.p);
  await naStanju(s.p, "extracting");
  await s.p.waitForTimeout(RAZMAK_U_TESTU);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(3000);
  const e = await ekran(s.p);
  zapisi("F.sesija", "A→B dok je čitanje stanja u letu: zahtev je prekinut (AbortError), ništa od A se ne prikazuje", (await s.p.evaluate(() => window.__prPrekinuto || 0)) >= 1 && e.poslovi.length === 0, String(await s.p.evaluate(() => window.__prPrekinuto || 0)));
  await s.zatvori();
}
{
  const s = await scenario({ napreduj: (p, n) => { p.status = n < 50 ? "extracting" : "awaiting_review"; } });
  await otpremi(s.p);
  await naStanju(s.p, "extracting");
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/prijem"; }, s.A[1].id);
  await s.p.waitForTimeout(800);
  const g0 = zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length;
  await s.p.waitForTimeout(3500);
  const e = await ekran(s.p);
  zapisi("F.predmet", "drugi predmet: poslovi prvog se ne prikazuju i praćenje staje", e.poslovi.length === 0 && zahtevi(s, /^\/api\/smart-intake\/jobs\/[^/]+$/, "GET").length === g0);
  await s.zatvori();
}
// ── G: raspored ─────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await otpremi(s.p);
  await naStanju(s.p, "awaiting_review");
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("G.raspored", `${w}px: bez horizontalnog skrola`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  if (process.env.NS005_SNIMCI) await s.p.screenshot({ path: `${process.env.NS005_SNIMCI}/ns005-prijem-${w}.png` });
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0, sviSpoljni.slice(0, 2).join());
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("izolacija", "nijedan DELETE", sviZahtevi.every(z => z.metod !== "DELETE"));
zapisi("token", "token nikad u adresi", sviZahtevi.every(z => ![TA, TB].some(t => z.upit.includes(t))));
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
