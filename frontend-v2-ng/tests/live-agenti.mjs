// Vindex V2 NG — VCR001 T06: savetnik (agent) na zahtev u predmetu, kroz čuvar citata.
// Pokretanje: `node tests/live-agenti.mjs` (fixture na 127.0.0.1; ništa spolja).
// Čuvar citata, granicu poverenja i kontekst predmeta dokazuje STVARNA ruta: tests/test_vcr001_t06_agenti.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { agentRuta, pitanjeRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-ag-A-NE-U-LOG-71", TB = "vx-ag-B-NE-U-LOG-82";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [];
async function scenario(kuke = {}, { w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  const KOR = { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
  const f = await pokreniFixture(kombinuj(agentRuta(KOR, kuke), pitanjeRuta(KOR, {}), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses("kA", TA)]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}/pitanje`);
  await cekaj(p, () => document.getElementById("predmet-naslov").textContent.length > 0);
  await cekaj(p, () => !document.getElementById("ag-posalji").disabled);
  return { f, A, p, async zatvori() { sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  return { opcije: [...document.querySelectorAll("#ag-agent option")].map(o => o.textContent), pomoc: document.getElementById("ag-agent-pomoc").textContent,
    odgovor: vid("ag-odgovor"), naslov: document.getElementById("ag-odgovor-naslov").textContent,
    citati: [...document.querySelectorAll("#ag-citati > .warn")].map(x => x.dataset.kljuc + ":" + x.textContent),
    kontekst: vid("ag-kontekst") ? document.getElementById("ag-kontekst").textContent : null,
    naslovi: [...document.querySelectorAll("#ag-tekst h4")].map(x => x.textContent), tekst: document.getElementById("ag-tekst").innerText,
    stanje: vid("ag-stanje") ? document.getElementById("ag-stanje").dataset.stanje + ":" + document.getElementById("ag-stanje").textContent : null,
    xss: window.__xss || null, dugme: document.getElementById("ag-posalji").disabled };
});
async function pokreni(p, agent = "research", zadatak = "Analiziraj osnov odgovornosti za štetu.") {
  await p.selectOption("#ag-agent", agent); await p.fill("#ag-zadatak", zadatak); await p.click("#ag-posalji");
  await cekaj(p, () => { const n = document.getElementById("ag-stanje"); return !document.getElementById("ag-odgovor").hidden || (!n.hidden && n.dataset.stanje !== "ucitavanje"); });
}
const EMODZI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

// ── A: spisak i odgovor sa neproverenim citatom ─────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b) });
  let e = await ekran(s.p);
  zapisi("A.spisak", "6 savetnika sa srpskim nazivima iz zatvorenog spiska", e.opcije.length === 6 && e.opcije.includes("Pravno istraživanje") && e.opcije.includes("Rokovi"), e.opcije.join());
  zapisi("A.spisak", "bez ikonica (emodži) u spisku i opisu", !e.opcije.some(o => EMODZI.test(o)) && !EMODZI.test(e.pomoc), e.pomoc);
  await pokreni(s.p);
  e = await ekran(s.p);
  zapisi("A.odgovor", "odgovor prikazan sa naslovom savetnika i naslovima odeljaka", e.odgovor && /Pravno istraživanje/.test(e.naslov) && e.naslovi.join("|") === "1. OSNOV ODGOVORNOSTI|2. DOKAZI", e.naslovi.join("|"));
  zapisi("A.citati", "neproveren član je izričito naveden (Član 999)", e.citati.length === 1 && /^citati-neprovereni:/.test(e.citati[0]) && /Član 999 \(zoo\)/.test(e.citati[0]) && /nije potvrđen/.test(e.citati[0]), e.citati.join());
  // QA-08: ranije „savet je dat uz podatke i dokumente ovog predmeta“ — tvrdnja koju server nije mogao da dokaže.
  zapisi("A.kontekst", "kaže TAČNO koje je dokumente savetnik dobio i koje nije", /Savetnik je dobio tekst 5 od 7 dokumenata: DOK-07, DOK-06, DOK-05, DOK-04, DOK-03\./.test(e.kontekst || "")
    && /Ostali \(2\) nisu pročitani/.test(e.kontekst || "") && !/uz podatke i dokumente ovog predmeta/.test(e.kontekst || ""), e.kontekst);
  zapisi("A.bezbednost", "tekst odgovora bez izvršavanja HTML-a, bez emodžija i bez **", e.xss === null && !EMODZI.test(e.tekst + e.naslovi.join()) && !/\*\*/.test(e.tekst), e.tekst.slice(0, 80));
  zapisi("A.ugovor", "zahtev nosi agent, zadatak i predmet (bez user_id)", tela.length === 1 && tela[0].agent === "research" && tela[0].predmet_id === s.A[0].id && !("user_id" in tela[0]), JSON.stringify(tela[0]));
  await s.zatvori();
}
// ── B: svi ishodi provere citata ─────────────────────────────────────────
for (const [naziv, provera, kljuc, re] of [
  ["provereni", { status: "PROVERENI", ukupno: 3, neprovereni: [], izvori_dostavljeni: true }, "citati-provereni", /Svi citirani članovi \(3\) potvrđeni/],
  ["bez citata", { status: "BEZ_CITATA", ukupno: 0, neprovereni: [], izvori_dostavljeni: false }, "bez-citata", /ne citira članove/],
  ["nepoznato", { status: "NEPOZNATO", ukupno: null, neprovereni: [], izvori_dostavljeni: true }, "citati-nepoznato", /nije izvršena/],
  ["polje nedostaje", null, "citati-nepoznato", /nije izvršena/],
]) {
  const s = await scenario({ provera });
  await pokreni(s.p);
  const e = await ekran(s.p);
  zapisi("B.citati", `${naziv}: tačna poruka, nikad „provereno“ bez potvrde`, e.citati.length === 1 && e.citati[0].startsWith(kljuc + ":") && re.test(e.citati[0]), e.citati.join());
  await s.zatvori();
}
// ── C: greške, nepoznat ishod, dupli klik, zastarelo ─────────────────────
for (const [naziv, kuka, re] of [
  ["403", { status: 403 }, /profesionalni paket/], ["503", { status: 503 }, /AI servis trenutno nije dostupan/],
  ["429", { status: 429 }, /Previše/], ["prekid", { prekid: true }, /Ne ponavljajte odmah/],
]) {
  const s = await scenario({ pre: (p) => p === "/api/agents/run" ? kuka : null });
  await pokreni(s.p);
  const e = await ekran(s.p);
  zapisi("C.greske", `${naziv}: poruka bez odgovora`, !e.odgovor && re.test(e.stanje || ""), e.stanje);
  await s.zatvori();
}
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b), pre: (p) => p === "/api/agents/run" ? new Promise(r => setTimeout(r, 600)) : null });
  await s.p.selectOption("#ag-agent", "research"); await s.p.fill("#ag-zadatak", "Analiziraj osnov odgovornosti za štetu.");
  await s.p.click("#ag-posalji"); await s.p.click("#ag-posalji", { force: true, timeout: 1000 }).catch(() => {});
  await cekaj(s.p, () => !document.getElementById("ag-odgovor").hidden);
  zapisi("C.dupli", "dupli klik: tačno jedan zahtev (trošak)", tela.length === 1, String(tela.length));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/agents/run" ? new Promise(r => setTimeout(r, 1200)) : null });
  await s.p.selectOption("#ag-agent", "research"); await s.p.fill("#ag-zadatak", "Analiziraj osnov odgovornosti za štetu.");
  await s.p.click("#ag-posalji");
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/pitanje"; }, s.A[1].id);
  await s.p.waitForTimeout(1800);
  const e = await ekran(s.p);
  zapisi("C.zastarelo", "odgovor iz prethodnog predmeta se ne prikazuje u novom", !e.odgovor && !e.stanje, JSON.stringify([e.odgovor, e.stanje]));
  await s.zatvori();
}
{
  const s = await scenario();
  await s.p.fill("#ag-zadatak", "kratko"); await s.p.click("#ag-posalji");
  const e = await ekran(s.p);
  zapisi("C.validacija", "prekratak zadatak se ne šalje", /bar 10 znakova/.test(e.stanje || "") && s.f.zahtevi.filter(z => z.putanja === "/api/agents/run").length === 0);
  await s.zatvori();
}
for (const [w, h] of [[390, 844], [1440, 900]]) {
  const s = await scenario({}, { w, h });
  await pokreni(s.p);
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("D.raspored", `${w}px: bez horizontalnog skrola sa odgovorom savetnika`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  await s.zatvori();
}

// ── E/F (VCR002 T07): tri pogleda istovremeno; niz je isključen (RC FIX 2) ─────────────
const ekranKomb = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  return { odgovor: vid("ag-odgovor"), naslov: document.getElementById("ag-odgovor-naslov").textContent,
    vrh: [...document.querySelectorAll("#ag-citati > li")].map(x => x.dataset.kljuc + ":" + x.textContent),
    blokovi: [...document.querySelectorAll("#ag-tekst .ag-rez")].map(s => ({ agent: s.dataset.agent, stanje: s.dataset.stanje,
      naslov: s.querySelector(".ag-rez__naslov").textContent, citati: [...s.querySelectorAll(".warns > .warn")].map(w => w.dataset.kljuc + ":" + w.textContent),
      tekst: s.innerText })),
    kontekst: vid("ag-kontekst") ? document.getElementById("ag-kontekst").textContent : null,
    agentPolje: vid("ag-agent-polje"), pomoc: document.getElementById("ag-nacin-pomoc").textContent,
    stanje: vid("ag-stanje") ? document.getElementById("ag-stanje").dataset.stanje + ":" + document.getElementById("ag-stanje").textContent : null,
    xss: window.__xss || null };
});
async function pokreniKomb(p, nacin, zadatak = "Pripremi tužbu za naknadu štete iz ugovora.") {
  await p.selectOption("#ag-nacin", nacin); await p.fill("#ag-zadatak", zadatak); await p.click("#ag-posalji");
  await cekaj(p, () => { const n = document.getElementById("ag-stanje"); return !document.getElementById("ag-odgovor").hidden || (!n.hidden && n.dataset.stanje !== "ucitavanje"); });
}
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b) });
  await s.p.selectOption("#ag-nacin", "paralelno");
  let e = await ekranKomb(s.p);
  zapisi("E.izbor", "kombinovan način sakriva izbor savetnika i kaže kako se naplaćuje", !e.agentPolje && /neuspeli se ne naplaćuju/.test(e.pomoc), e.pomoc);
  await pokreniKomb(s.p, "paralelno");
  e = await ekranKomb(s.p);
  zapisi("E.paralelno", "tri odeljka, svaki sa SOPSTVENOM proverom citata", e.odgovor && e.blokovi.length === 3
    && e.blokovi[0].citati[0].startsWith("citati-provereni:") && e.blokovi[1].citati[0].startsWith("citati-neprovereni:") && /Član 999/.test(e.blokovi[1].citati[0])
    && e.blokovi[2].citati[0].startsWith("bez-citata:"), JSON.stringify(e.blokovi.map(b => [b.agent, b.citati.map(c => c.split(":")[0])])));
  zapisi("E.paralelno", "radni materijal za pregled advokata; kontekst predmeta naveden", e.vrh.some(v => v.startsWith("pregled:")) && /Savetnik je dobio tekst 5 od 7 dokumenata/.test(e.kontekst || ""), e.kontekst);
  zapisi("E.ugovor", "jedan zahtev sa tačno tri proverena savetnika, predmetom i ključem idempotencije, bez user_id",
    tela.length === 1 && tela[0]._putanja === "/api/agents/run-parallel" && tela[0].agenti.join() === "research,litigation,intake"
    && tela[0].predmet_id === s.A[0].id && !!tela[0]._kljuc && !("user_id" in tela[0]), JSON.stringify(tela[0]));
  zapisi("E.bezbednost", "bez izvršavanja HTML-a i bez emodžija u odeljcima", e.xss === null && !e.blokovi.some(b => EMODZI.test(b.tekst)));
  await s.zatvori();
}
{
  const s = await scenario({ padaju: ["litigation"] });
  await pokreniKomb(s.p, "paralelno");
  const e = await ekranKomb(s.p);
  const neusp = e.blokovi.find(b => b.agent === "litigation");
  zapisi("E.delimicno", "jedan savetnik pao: vidljivo, nije naplaćen, ostali prikazani", e.vrh.some(v => /^delimicno:.*2 od 3.*nisu naplaćeni/.test(v))
    && neusp && neusp.stanje === "NEUSPEH" && /nije uspeo/.test(neusp.naslov) && neusp.citati.length === 0
    && e.blokovi.filter(b => b.stanje === "USPEH").length === 2, JSON.stringify(e.vrh));
  await s.zatvori();
}
{
  const s = await scenario({ padaju: ["research", "litigation", "intake"] });
  await pokreniKomb(s.p, "paralelno");
  const e = await ekranKomb(s.p);
  zapisi("E.svi_pali", "svi pali: bez lažnog odgovora, „ništa nije naplaćeno“", !e.odgovor && /Nijedan savetnik nije odgovorio.*Ništa nije naplaćeno/.test(e.stanje || ""), e.stanje);
  await s.zatvori();
}
// F (VCR002 RC FIX 2): niz je ISKLJUČEN dok oporavak plaćenog niza posle pada radnika nije bezbedan.
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b) });
  const o = await s.p.evaluate(() => [...document.querySelectorAll("#ag-nacin option")].map(x => [x.value, x.disabled, x.textContent]));
  const niz = o.find(x => x[0] === "niz");
  zapisi("F.iskljucen", "niz se ne nudi posle učitanog kataloga i jasno piše da je privremeno isključen",
    !!niz && niz[1] === true && /privremeno isključeno/.test(niz[2]), JSON.stringify(o));
  zapisi("F.ostali", "jedan savetnik i tri pogleda ostaju dostupni", o.filter(x => x[0] !== "niz").every(x => x[1] === false), JSON.stringify(o));
  await s.p.evaluate(() => { const n = document.getElementById("ag-nacin"); n.value = "niz"; n.dispatchEvent(new Event("change")); });
  await s.p.fill("#ag-zadatak", "Pripremi tužbu za naknadu štete iz ugovora."); await s.p.click("#ag-posalji");
  await cekaj(s.p, () => { const n = document.getElementById("ag-stanje"); return !n.hidden; });
  const e = await ekranKomb(s.p);
  zapisi("F.bez_zahteva", "nasilno izabran niz: nijedan zahtev, nijedna naplata, iskrena poruka",
    tela.length === 0 && !e.odgovor && /trenutno nije dostupan/.test(e.stanje || ""), JSON.stringify([tela.length, e.stanje]));
  await s.zatvori();
}
for (const [nacin, putanja] of [["paralelno", "/api/agents/run-parallel"]]) {
  for (const [naziv, kuka, re] of [["402", { status: 402 }, /dovoljno kredita.*Ništa nije pokrenuto/], ["prekid", { prekid: true }, /Ne ponavljajte odmah/], ["403", { status: 403 }, /profesionalni paket/]]) {
    const s = await scenario({ pre: (p) => p === putanja ? kuka : null });
    await pokreniKomb(s.p, nacin);
    const e = await ekranKomb(s.p);
    zapisi("G.greske", `${nacin} ${naziv}: poruka bez odgovora`, !e.odgovor && re.test(e.stanje || ""), e.stanje);
    await s.zatvori();
  }
}
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b), pre: (p) => p === "/api/agents/run-parallel" ? new Promise(r => setTimeout(r, 700)) : null });
  await s.p.selectOption("#ag-nacin", "paralelno"); await s.p.fill("#ag-zadatak", "Pripremi tužbu za naknadu štete iz ugovora.");
  await s.p.click("#ag-posalji"); await s.p.click("#ag-posalji", { force: true, timeout: 1000 }).catch(() => {});
  const zakljucano = await s.p.evaluate(() => document.getElementById("ag-nacin").disabled && document.getElementById("ag-posalji").disabled);
  await cekaj(s.p, () => !document.getElementById("ag-odgovor").hidden);
  zapisi("G.dupli", "tri pogleda: dupli klik = tačno jedan zahtev; način rada zaključan dok traje", tela.length === 1 && zakljucano, String(tela.length));
  await s.zatvori();
}
for (const [w, h] of [[390, 844]]) {
  const s = await scenario({}, { w, h });
  await pokreniKomb(s.p, "paralelno");
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("G.raspored", `${w}px: bez horizontalnog skrola sa tri pogleda`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  await s.zatvori();
}

// ── Q (QA-08): ekran kaže koje je dokumente savetnik STVARNO dobio; nikad „uz dokumente“ bez evidencije servera ─────
{
  const { izvoriPredmeta } = await import("./fixtures/pisanje-api.mjs");
  const DOK = (n, potpun = true) => ({ oznaka: "DOK-" + String(n).padStart(2, "0"), naziv: n + ".pdf", trazen: false, potpun, znakova_dostavljeno: potpun ? 900 : 5000, znakova_ukupno: potpun ? 900 : 30000 });
  const stanjeKonteksta = (p) => p.evaluate(() => { const n = document.getElementById("ag-kontekst"); return n.hidden ? null : n.dataset.stanje; });
  for (const [naziv, izvori, re, ocekivanoStanje] of [
    ["traženi ne postoji", izvoriPredmeta({ trazeni_nisu_dostavljeni: [{ oznaka: "DOK-09", razlog: "NE_POSTOJI", razlog_tekst: "ne postoji u ovom predmetu" }] }),
      /Traženo, a NIJE pročitano: DOK-09 ne postoji u ovom predmetu\./, "nepoznato"],
    ["traženi iznad ograničenja", izvoriPredmeta({ trazeni_nisu_dostavljeni: [{ oznaka: "DOK-06", razlog: "OGRANICENJE", razlog_tekst: "" }] }),
      /DOK-06 nije dostavljen \(ograničenje broja dokumenata\)/, "nepoznato"],
    ["traženi bez teksta", izvoriPredmeta({ bez_teksta: [{ oznaka: "DOK-04", naziv: "4.pdf" }], trazeni_nisu_dostavljeni: [{ oznaka: "DOK-04", razlog: "BEZ_TEKSTA", razlog_tekst: "" }] }),
      /DOK-04 nema izdvojen tekst/, "nepoznato"],
    ["traženi uz grešku čitanja", izvoriPredmeta({ greska_citanja: true, trazenih_nedostavljenih_ukupno: 34,
        trazeni_nisu_dostavljeni: Array.from({ length: 30 }, (_, i) => ({ oznaka: "DOK-" + (i + 1), razlog: "NEPOZNATO", razlog_tekst: "" })) }),
      /DOK-1 nije pročitan \(nije utvrđeno zašto\);.* i još 4\./, "nepoznato"],
    ["delimičan dokument", izvoriPredmeta({ ukljuceni: [DOK(1, false), DOK(7)], izostavljenih_ukupno: 5 }),
      /dobio tekst 2 od 7 dokumenata: DOK-01, DOK-07\. Delimično \(samo početak\): DOK-01\./, "nepoznato"],
    ["svi u celini", izvoriPredmeta({ dokumenata_u_predmetu: 3, ukljuceni: [DOK(3), DOK(2), DOK(1)], izostavljeni: [], izostavljenih_ukupno: 0, svi_dokumenti_u_celini: true }),
      /^Savetnik je dobio tekst 3 od 3 dokumenata: DOK-03, DOK-02, DOK-01\.$/, "uspeh"],
    ["predmet bez dokumenata", izvoriPredmeta({ dokumenata_u_predmetu: 0, ukljuceni: [], izostavljeni: [], izostavljenih_ukupno: 0 }),
      /nema dokumenata; savet nije zasnovan na dokumentima/, "nepoznato"],
    ["greška čitanja", izvoriPredmeta({ dokumenata_u_predmetu: null, greska_citanja: true, ukljuceni: [], izostavljeni: [], izostavljenih_ukupno: 0 }),
      /nisu \(potpuno\) pročitani zbog greške/, "nepoznato"],
    ["server bez evidencije", null, /nije utvrđeno koje je dokumente savetnik dobio/, "nepoznato"],
  ]) {
    const s = await scenario({ izvori });
    await pokreni(s.p);
    const e = await ekran(s.p);
    const st = await stanjeKonteksta(s.p);
    zapisi("Q.izvori", naziv, re.test(e.kontekst || "") && st === ocekivanoStanje && !/uz podatke i dokumente/.test(e.kontekst || ""), `${st} | ${e.kontekst}`);
    await s.zatvori();
  }
  {
    const s = await scenario({ izvori: izvoriPredmeta({ odgovor_pominje_nedostavljene: ["DOK-02", "DOK-01"] }) });
    await pokreni(s.p);
    const e = await ekran(s.p);
    zapisi("Q.pominje", "odgovor pominje nepročitane dokumente: izričito upozorenje", e.citati.some(c => /^nedostavljeni:.*odgovor pominje DOK-02, DOK-01, čiji tekst savetnik nije dobio/.test(c)), e.citati.join(" | "));
    await s.zatvori();
  }
  {
    const s = await scenario({ pominje: { litigation: ["DOK-01"] } });
    await pokreniKomb(s.p, "paralelno");
    const e = await ekranKomb(s.p);
    zapisi("Q.pominje", "tri pogleda: upozorenje samo za savetnika koji pominje nepročitan dokument",
      e.vrh.filter(v => v.startsWith("nedostavljeni:")).length === 1 && e.vrh.some(v => /^nedostavljeni:Parnična strategija: odgovor pominje DOK-01/.test(v)), e.vrh.join(" | "));
    await s.zatvori();
  }
  {
    // QA-06: server prepoznaje i tačan naziv fajla — upozorenje nosi oznaku i naziv, naziv (koji je uneo korisnik) kao tekst.
    const s = await scenario({ izvori: izvoriPredmeta({ odgovor_pominje_nedostavljene: ["DOK-02 (zapisnik_rociste.pdf)", "DOK-01 (<img src=x onerror=window.__xss=98>.pdf)"] }) });
    await pokreni(s.p);
    const e = await ekran(s.p);
    zapisi("Q.pominje", "naziv fajla nepročitanog dokumenta: upozorenje sa oznakom i nazivom, naziv kao tekst",
      e.citati.some(c => /^nedostavljeni:.*odgovor pominje DOK-02 \(zapisnik_rociste\.pdf\), DOK-01 \(<img src=x onerror=window\.__xss=98>\.pdf\), čiji tekst savetnik nije dobio/.test(c))
        && e.xss !== 98, e.citati.join(" | ") + " | xss=" + e.xss);
    await s.zatvori();
  }
  {
    // Nesaglasnost: server je DOK-01 dostavio, a model tvrdi da ga nije pročitao. Ekran ne skriva ni jedno ni drugo —
    // evidencija servera i tekst odgovora su oba vidljivi; sistem NE pokušava da tumači rečenicu modela.
    const s = await scenario({ izvori: izvoriPredmeta({ ukljuceni: [{ ...DOK(1), trazen: true }, DOK(7)], izostavljenih_ukupno: 5 }),
                               odgovor: "Nisam pročitao DOK-01, pa ne mogu da potvrdim rok isporuke." });
    await pokreni(s.p, "research", "Šta piše u DOK-01?");
    const e = await ekran(s.p);
    zapisi("Q.nesaglasnost", "server: DOK-01 dostavljen; model: nije pročitan — oba vidljiva, bez lažnog upozorenja",
      /dobio tekst 2 od 7 dokumenata: DOK-01, DOK-07/.test(e.kontekst || "") && /Nisam pročitao DOK-01/.test(e.tekst)
        && !e.citati.some(c => c.startsWith("nedostavljeni:")), `${e.kontekst} | ${e.tekst.slice(0, 80)} | ${e.citati.join(" | ")}`);
    await s.zatvori();
  }
  {
    const s = await scenario({ izvori: izvoriPredmeta({ ukljuceni: [{ ...DOK(1), oznaka: "<img src=x onerror=window.__xss=99>" }] }) });
    await pokreni(s.p);
    const e = await ekran(s.p);
    zapisi("Q.bezbednost", "oznaka iz odgovora servera se prikazuje kao tekst", e.xss === null, String(e.xss));
    await s.zatvori();
  }
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0);
zapisi("token", "token nije u konzoli ni u izlazu", ![TA, TB].some(t => konzola.join("\n").includes(t) || izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
