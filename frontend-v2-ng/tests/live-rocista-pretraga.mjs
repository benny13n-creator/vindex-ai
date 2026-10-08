// Vindex V2 NG — NS005 Task 5: ročišta predmeta (CAP-074) i globalna pretraga (CAP-160).
// Pokretanje: `node tests/live-rocista-pretraga.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend isti ugovor dokazuje nad STVARNIM rutama: tests/test_ns005_t5_rocista_pretraga.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { rocistaRuta, pretragaRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-rp-A-NE-U-LOG-35", TB = "vx-rp-B-NE-U-LOG-46";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const XSS = '<img src=x onerror="window.__xss=1">';

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", put = null, w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2, { naziv: i => ["Jović protiv Petrovića", "Radni spor Jović" + XSS][i] });
  const B = napraviPredmete("kB", 1, { naziv: () => "TAJNI Jović B" });
  const KOR = {
    [TA]: { id: "kA", predmeti: A, rocista: [
      { id: "r1", predmet_id: A[0].id, user_id: "kA", sud: "Osnovni sud u Beogradu", datum: "2026-11-12", vreme: "10:30", sudnica: "12", status: "zakazano", napomena: XSS + "ponesti dokaze" },
      { id: "r0", predmet_id: A[0].id, user_id: "kA", sud: "Viši sud", datum: "2026-10-20", vreme: null, status: "odrzano" } ],
      dokumentiPretraga: [{ id: "d1", predmet_id: A[0].id, naziv_fajla: "Jović tužba.pdf" }],
      beleske: { [A[0].id]: [{ id: "b1", sadrzaj: "Jović — pozvati svedoka" }] } },
    [TB]: { id: "kB", predmeti: B, rocista: [{ id: "rB", predmet_id: B[0].id, user_id: "kB", sud: "TAJNI sud B", datum: "2026-11-01", status: "zakazano" }] },
  };
  const f = await pokreniFixture(kombinuj(rocistaRuta(KOR, kuke), pretragaRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${put === null ? "#/predmeti/" + A[0].id + "/rad" : put}`);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, B, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? (document.getElementById(id).dataset.stanje || "") + ":" + document.getElementById(id).textContent : null;
  return { hash: location.hash, rocista: [...document.querySelectorAll("#roc-lista .hearing")].map(x => x.innerText.replace(/\s+/g, " ")),
    rocStanje: st("roc-stanje"), rocPoruka: st("roc-poruka"), forma: vid("roc-forma"), rocDugme: vid("roc-otvori"),
    prStanje: st("pr-stanje"), prNepotpuno: vid("pr-nepotpuno") ? document.getElementById("pr-nepotpuno").textContent : null,
    rezultati: [...document.querySelectorAll("#pr-rezultati .results__item")].map(a => ({ href: a.getAttribute("href"), t: a.querySelector(".results__name").textContent })),
    grupe: [...document.querySelectorAll("#pr-rezultati .results__title")].map(x => x.textContent), prLink: vid("pretraga-link"),
    xss: window.__xss || null, tekst: document.body.innerText };
});
const zahtevi = (s, metod, re) => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));

// ── A: ročišta predmeta ─────────────────────────────────────────────────
{
  const upisi = [];
  const s = await scenario({ upisano: (r, b) => upisi.push(b) });
  await cekaj(s.p, () => document.querySelectorAll("#roc-lista .hearing").length > 0);
  let e = await ekran(s.p);
  const z = zahtevi(s, "GET", /^\/api\/rocista$/)[0] || {};
  zapisi("A.lista", "GET /api/rocista?predmet_id=<id> sa tokenom A, bez user_id", z.auth === "Bearer " + TA && z.parametri.predmet_id === s.A[0].id && !("user_id" in z.parametri));
  zapisi("A.lista", "ročišta po datumu: datum, vreme, sud, sudnica, status (održano)", e.rocista.length === 2 && /20\.10\.2026\./.test(e.rocista[0]) && /održano/.test(e.rocista[0]) && /12\.11\.2026\. u 10:30/.test(e.rocista[1]) && /sudnica 12/.test(e.rocista[1]), e.rocista.join(" | "));
  zapisi("A.lista", "napomena sa HTML-om je tekst; nema ničega od B", e.rocista[1].includes("<img") && e.xss === null && !/TAJNI/.test(e.tekst));
  await s.p.click("#roc-otvori");
  await s.p.click("#roc-sacuvaj");
  e = await ekran(s.p);
  zapisi("A.zakazi", "bez suda: lokalna greška, ništa poslato", zahtevi(s, "POST", /rocista$/).length === 0 && /sud/i.test(e.rocPoruka || ""));
  await s.p.fill("#roc-sud", "Privredni sud");
  await s.p.click("#roc-sacuvaj");
  e = await ekran(s.p);
  zapisi("A.zakazi", "bez datuma: lokalna greška, ništa poslato", zahtevi(s, "POST", /rocista$/).length === 0 && /datum/i.test(e.rocPoruka || ""));
  await s.p.fill("#roc-datum", "2026-12-03");
  await s.p.fill("#roc-vreme", "09:15");
  await s.p.fill("#roc-sudnica", "3");
  await s.p.click("#roc-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("roc-poruka"); return !n.hidden && n.dataset.stanje === "uspeh"; });
  e = await ekran(s.p);
  zapisi("A.zakazi", "POST telo: predmet_id, sud, datum, vreme, sudnica — bez user_id", upisi.length === 1 && upisi[0].predmet_id === s.A[0].id && upisi[0].datum === "2026-12-03" && upisi[0].vreme === "09:15" && !("user_id" in upisi[0]), JSON.stringify(upisi[0]));
  zapisi("A.zakazi", "posle uspeha lista je PONOVO pročitana i sadrži novo ročište", e.rocista.some(x => /03\.12\.2026\. u 09:15/.test(x) && /Privredni sud/.test(x)) && zahtevi(s, "GET", /^\/api\/rocista$/).length === 2 && !e.forma, e.rocista.join(" | "));
  await s.zatvori();
}
for (const [naziv, kuka, stanje, re] of [["500", { status: 500 }, "nepoznato", /možda zakazano/], ["prekid", { prekid: true }, "nepoznato", /nije poznat/],
  ["404", { status: 404 }, "greska", /nije dostupan/], ["422", { status: 422 }, "greska", /nije prihvatio/]]) {
  const s = await scenario({ pre: (put) => put === "/api/rocista:POST" ? kuka : null });
  await cekaj(s.p, () => !document.getElementById("roc-otvori").hidden);
  await s.p.click("#roc-otvori");
  await s.p.fill("#roc-sud", "Sud " + naziv); await s.p.fill("#roc-datum", "2026-12-01");
  await s.p.click("#roc-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("roc-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("A.ishod", `zakazivanje ${naziv}: „${stanje}“, forma ostaje sa unosom, bez lažnog uspeha`, (e.rocPoruka || "").startsWith(stanje + ":") && re.test(e.rocPoruka) && e.forma && !e.rocista.some(x => x.includes("Sud " + naziv)), e.rocPoruka);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (put) => put === "/api/rocista:GET" ? { status: 500 } : null });
  await cekaj(s.p, () => { const n = document.getElementById("roc-stanje"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("A.istina", "lista 500 → „nisu učitana… nije prazna lista“", (e.rocStanje || "").startsWith("greska:") && /nije prazna/.test(e.rocStanje), e.rocStanje);
  await s.zatvori();
}
{
  const s = await scenario({ izmeniListu: (r) => r.concat([{ id: "x", predmet_id: "kB-00000", user_id: "kA", sud: "TAJNI tuđi", datum: "2026-01-01" }]) });
  await cekaj(s.p, () => { const n = document.getElementById("roc-stanje"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("A.istina", "red drugog predmeta u odgovoru → ceo odgovor odbijen, ništa se ne prikazuje", (e.rocStanje || "").startsWith("greska:") && !e.rocista.length && !/TAJNI/.test(e.tekst), e.rocStanje);
  await s.zatvori();
}
{
  const s = await scenario();
  await cekaj(s.p, () => document.querySelectorAll("#roc-lista .hearing").length > 0);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(500);
  const e = await ekran(s.p);
  zapisi("A.sesija", "A→B: ročišta A nestaju odmah", !e.rocista.length && !/Osnovni sud u Beogradu/.test(e.tekst));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (put) => put === "/api/rocista:GET" ? new Promise(r => setTimeout(r, 1200)) : null });
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/rad"; }, s.A[1].id);
  await s.p.waitForTimeout(2800);
  const e = await ekran(s.p);
  zapisi("A.zastarelo", "spor odgovor za predmet 0 posle prelaska na predmet 1 se ne slika", e.hash.includes(s.A[1].id) && !e.rocista.some(x => /Osnovni sud u Beogradu/.test(x)), e.rocista.join("|"));
  await s.zatvori();
}

{
  // Ročišta se čitaju tek na odeljku „Rad na predmetu": pregled i dokumenti ostaju kao u NS004.
  const s = await scenario({}, { put: "#/predmeti/kA-00000" });
  await cekaj(s.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  await s.p.evaluate(() => { location.hash = "#/predmeti/kA-00000/dokumenti"; });
  await s.p.waitForTimeout(400);
  zapisi("A.lenjo", "pregled i dokumenti ne šalju GET /api/rocista", zahtevi(s, "GET", /^\/api\/rocista$/).length === 0);
  await s.p.click("#tab-rad");
  await cekaj(s.p, () => document.querySelectorAll("#roc-lista .hearing").length > 0);
  zapisi("A.lenjo", "otvaranje „Rad na predmetu“ učitava ročišta tačno jednom", zahtevi(s, "GET", /^\/api\/rocista$/).length === 1);
  await s.p.click("#tab-pregled"); await s.p.click("#tab-rad"); await s.p.waitForTimeout(300);
  zapisi("A.lenjo", "povratak na odeljak ne ponavlja zahtev", zahtevi(s, "GET", /^\/api\/rocista$/).length === 1);
  await s.zatvori();
}

// ── B: globalna pretraga ─────────────────────────────────────────────────
{
  const s = await scenario({}, { put: "" });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  let e = await ekran(s.p);
  zapisi("B.ulaz", "„Pretraga“ je u gornjoj traci (LIVE, prijavljen)", e.prLink);
  await s.p.click("#pretraga-link");
  await cekaj(s.p, () => location.hash === "#/pretraga" && document.activeElement && document.activeElement.id === "pr-upit");
  await s.p.fill("#pr-upit", "Jović");
  await s.p.press("#pr-upit", "Enter");
  await cekaj(s.p, () => { const n = document.getElementById("pr-stanje"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  e = await ekran(s.p);
  const z = zahtevi(s, "GET", /^\/api\/search$/).pop() || {};
  zapisi("B.pretraga", "GET /api/search sa q, vrste bez klijenata, tokenom A, bez user_id", z.auth === "Bearer " + TA && z.parametri.q === "Jović" && z.parametri.vrste === "predmeti,dokumenti,beleske,hronologija" && !("user_id" in z.parametri), JSON.stringify(z.parametri));
  zapisi("B.pretraga", "rezultati samo A: predmeti, dokument, beleška — ništa od B", e.grupe.join() === "Predmeti,Dokumenti,Beleške" && !/TAJNI/.test(e.tekst), e.grupe.join());
  zapisi("B.pretraga", "linkovi vode u odgovarajući odeljak predmeta", e.rezultati.some(r => r.href === "#/predmeti/kA-00000/dokumenti" && r.t === "Jović tužba.pdf") && e.rezultati.some(r => r.href === "#/predmeti/kA-00000/rad") && e.rezultati.some(r => r.href === "#/predmeti/kA-00000"), JSON.stringify(e.rezultati).slice(0, 200));
  zapisi("B.pretraga", "naziv sa HTML-om je tekst", e.rezultati.some(r => r.t.includes("<img")) && e.xss === null);
  await s.p.click('#pr-rezultati a[href="#/predmeti/kA-00000/dokumenti"]');
  await cekaj(s.p, () => !document.getElementById("odeljak-dokumenti").hidden);
  zapisi("B.pretraga", "klik otvara predmet na dokumentima", (await ekran(s.p)).hash === "#/predmeti/kA-00000/dokumenti");
  await s.zatvori();
}
for (const [naziv, kuke, provera] of [
  ["500", { pre: (put) => put === "/api/search" ? { status: 500 } : null }, e => (e.prStanje || "").startsWith("greska:") && /nije prazan/.test(e.prStanje) && !e.rezultati.length],
  ["nepotpuno (dokumenti)", { nepotpuno: ["dokumenti"] }, e => /nije potpuna/.test(e.prNepotpuno || "") && /dokumenti/.test(e.prNepotpuno) && e.rezultati.length > 0],
  ["bez rezultata", {}, e => (e.prStanje || "").startsWith("prazno:") && /Nema rezultata/.test(e.prStanje)],
]) {
  const s = await scenario(kuke, { put: "#/pretraga" });
  await cekaj(s.p, () => !document.getElementById("pretraga-pogled").hidden);
  await s.p.fill("#pr-upit", naziv === "bez rezultata" ? "Nepostojeće" : "Jović");
  await s.p.press("#pr-upit", "Enter");
  await cekaj(s.p, () => { const n = document.getElementById("pr-stanje"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("B.istina", `pretraga ${naziv}: tačno stanje`, provera(e), `${e.prStanje} / ${e.prNepotpuno}`);
  await s.zatvori();
}
{
  const s = await scenario({}, { put: "#/pretraga" });
  await cekaj(s.p, () => !document.getElementById("pretraga-pogled").hidden);
  await s.p.fill("#pr-upit", "J"); await s.p.press("#pr-upit", "Enter");
  await s.p.waitForTimeout(300);
  zapisi("B.istina", "jedan znak: lokalna poruka, zahtev se ne šalje", zahtevi(s, "GET", /^\/api\/search$/).length === 0 && /dva znaka/.test((await ekran(s.p)).prStanje || ""));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (put) => put === "/api/search" ? new Promise(r => setTimeout(r, 1200)) : null }, { put: "#/pretraga" });
  await cekaj(s.p, () => !document.getElementById("pretraga-pogled").hidden);
  await s.p.fill("#pr-upit", "Jović"); await s.p.press("#pr-upit", "Enter");
  await s.p.waitForTimeout(150);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1600);
  const e = await ekran(s.p);
  zapisi("B.sesija", "A→B tokom pretrage: rezultati A se ne prikazuju, upit obrisan", !e.rezultati.length && !/Jović tužba/.test(e.tekst) && await s.p.inputValue("#pr-upit") === "");
  await s.zatvori();
}
{
  const s = await scenario({}, { put: "", token: null });
  await s.p.waitForTimeout(400);
  zapisi("B.ulaz", "bez prijave „Pretraga“ nije ponuđena", !(await ekran(s.p)).prLink);
  await s.zatvori();
}
// ── C: raspored ─────────────────────────────────────────────────────────
for (const [w, h, put] of [[390, 844, null], [390, 844, "#/pretraga"], [1024, 768, null]]) {
  const s = await scenario({}, { w, h, put });
  await s.p.waitForTimeout(500);
  if (put === null) { await s.p.click("#roc-otvori"); }
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("C.raspored", `${w}px ${put || "ročišta"}: bez horizontalnog skrola`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
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
