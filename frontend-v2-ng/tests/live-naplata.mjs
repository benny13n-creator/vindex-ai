// Vindex V2 NG — NS005 Task 10: naplata predmeta bez spoljnog slanja (stavke, tarifa, tajmer, nacrt fakture).
// Pokretanje: `node tests/live-naplata.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend (tuđ predmet 404, iznos po tarifi računa server, stavka ne ide na dve fakture,
// tuđe stavke se ne fakturišu, tajmer samo na svom predmetu, pad baze nije prazna lista)
// dokazuje STVARNA ruta: tests/test_ns005_t10_naplata.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { naplataRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-np-A-NE-U-LOG-37", TB = "vx-np-B-NE-U-LOG-58";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const ZABRANJENO = /posalji-email|sef|\/status$|konvertuj|\/pdf$|\/timer\/reset/i;

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", w = 1440, h = 900, pripremi } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  const KOR = {
    [TA]: { id: "kA", predmeti: A, stavke: [
      { id: "e-old-1", user_id: "kA", predmet_id: A[0].id, opis: "Sastanak sa klijentom <img src=x onerror=window.__xss=1>", tip: "ostalo", tarifa_sifra: null, sati: 2, iznos_rsd: 12000, datum: "2026-10-01", obracunato: false },
      { id: "e-old-2", user_id: "kA", predmet_id: A[0].id, opis: "Ranije fakturisano", tip: "tarifa", tarifa_sifra: "T01", sati: null, iznos_rsd: 600, datum: "2026-09-20", obracunato: true },
      { id: "e-drugi", user_id: "kA", predmet_id: A[1].id, opis: "STAVKA DRUGOG PREDMETA", tip: "ostalo", iznos_rsd: 1, datum: "2026-10-02", obracunato: false },
    ], fakture: [{ id: "f-old", user_id: "kA", predmet_id: A[0].id, broj_fakture: "2026/0001", klijent_naziv: "Ana Jović", iznos_sa_pdv: 600, status: "izdata", is_proforma: false, datum_dospeca: "2026-10-20" },
                 { id: "f-drugi", user_id: "kA", predmet_id: A[1].id, broj_fakture: "2026/0002", klijent_naziv: "FAKTURA DRUGOG PREDMETA", iznos_sa_pdv: 5, status: "nacrt" }] },
    [TB]: { id: "kB", predmeti: B, stavke: [{ id: "e-B", user_id: "kB", predmet_id: B[0].id, opis: "TAJNA stavka B", iznos_rsd: 9999, datum: "2026-10-01", obracunato: false }],
            fakture: [{ id: "f-B", user_id: "kB", predmet_id: B[0].id, broj_fakture: "2026/0009", klijent_naziv: "TAJNI klijent B", iznos_sa_pdv: 1, status: "nacrt" }] },
  };
  if (pripremi) pripremi(KOR, A);
  const f = await pokreniFixture(kombinuj(naplataRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(() => { window.__npFetch = {}; const o = window.fetch.bind(window); window.fetch = (u, opt) => { const k = String(u).split("?")[0] + ":" + ((opt && opt.method) || "GET"); window.__npFetch[k] = (window.__npFetch[k] || 0) + 1; return o(u, opt); }; });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}/naplata`);
  await cekaj(p, () => document.getElementById("predmet-naslov").textContent.length > 0);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  return {
    tarife: [...document.querySelectorAll("#np-tarifa option")].map(o => o.value + "=" + o.textContent).slice(1),
    zbir: vid("np-zbir") ? [...document.querySelectorAll("#np-zbir dd")].map(x => x.textContent) : null,
    redovi: vid("np-tabela") ? [...document.querySelectorAll("#np-stavke tr")].map(tr => [...tr.cells].slice(1).map(c => c.textContent).join("|") + (tr.querySelector("input") ? "|☐" : "")) : [],
    stavkeStanje: st("np-stavke-stanje"), poruka: st("np-poruka"),
    tajmerStanje: st("np-tajmer-stanje"), tajmerPoruka: st("np-tajmer-poruka"),
    start: vid("np-tajmer-start") ? (document.getElementById("np-tajmer-start").disabled ? "off" : "on") : "skriven",
    stop: vid("np-tajmer-stop") ? (document.getElementById("np-tajmer-stop").disabled ? "off" : "on") : "skriven",
    drugi: vid("np-tajmer-drugi") ? document.getElementById("np-tajmer-drugi").getAttribute("href") : null,
    fakturaDugme: document.getElementById("np-faktura-dugme").disabled ? "off" : "on", fakturaPoruka: st("np-faktura-poruka"),
    fakture: [...document.querySelectorAll("#np-fakture .review")].map(li => li.textContent), faktureStanje: st("np-fakture-stanje"),
    tab: document.getElementById("tab-naplata").getAttribute("href"), tabTekuci: document.getElementById("tab-naplata").getAttribute("aria-current"),
    vidljivo: vid("odeljak-naplata"), xss: window.__xss || null, ceo: document.body.innerText,
  };
});
const zahtevi = (s, re, metod = "POST") => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));
const fetchova = (p, k) => p.evaluate((k) => window.__npFetch[k] || 0, k);
const ucitano = (p) => cekaj(p, () => !document.getElementById("np-tabela").hidden && !document.getElementById("np-tarifa").disabled && document.getElementById("np-tajmer-stanje").dataset.stanje !== "ucitavanje" && document.getElementById("np-fakture-stanje").dataset.stanje !== "ucitavanje");
const gotovo = (p, id) => cekaj(p, (id) => { const n = document.getElementById(id); return !n.hidden && n.dataset.stanje !== "ucitavanje"; }, id);
async function upisi(p, { opis = "Sastav tužbe", tarifa = "", iznos = "", sati = "", datum = "" } = {}) {
  await p.fill("#np-opis", opis);
  await p.selectOption("#np-tarifa", tarifa);
  await p.fill("#np-iznos", iznos); await p.fill("#np-sati", sati); await p.fill("#np-datum", datum);
  await p.click("#np-dodaj");
  await gotovo(p, "np-poruka");
}

// ── A: učitavanje, istina o podacima, tab ───────────────────────────────
{
  const s = await scenario();
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("A.tab", "#/predmeti/<id>/naplata otvara odeljak; tab „Naplata“ aktivan", e.vidljivo && e.tab === `#/predmeti/${s.A[0].id}/naplata` && e.tabTekuci === "page");
  zapisi("A.tarifa", "tarifa SAMO sa servera; HTML u nazivu je tekst", e.tarife.length === 2 && e.tarife[0].startsWith("T01=T01 — Tužba") && e.tarife[1].includes("<b>složeniji</b>"), e.tarife.join(" / "));
  zapisi("A.stavke", "samo stavke ovog predmeta (ne drugog predmeta, ne korisnika B)", e.redovi.length === 2 && !/DRUGOG PREDMETA|TAJNA/.test(e.ceo), e.redovi.join(" / "));
  zapisi("A.stavke", "zbir sa servera: ukupno / nije fakturisano / na fakturama / sati", JSON.stringify(e.zbir) === JSON.stringify(["12.600,00 RSD", "12.000,00 RSD", "600,00 RSD", "2"]), JSON.stringify(e.zbir));
  zapisi("A.stavke", "fakturisana stavka nema polje za izbor; nefakturisana ima", /nije fakturisano\|☐$/.test(e.redovi[0]) && /na fakturi$/.test(e.redovi[1]));
  zapisi("A.xss", "HTML u opisu stavke je tekst, ništa se ne izvršava", e.ceo.includes("<img src=x") && e.xss === null);
  zapisi("A.fakture", "samo fakture ovog predmeta; status i dospeće", e.fakture.length === 1 && /Faktura 2026\/0001 — Ana Jović/.test(e.fakture[0]) && /izdata/.test(e.fakture[0]) && /dospeva 20\.10\.2026\./.test(e.fakture[0]) && !/DRUGOG|TAJNI/.test(e.ceo), e.fakture.join());
  zapisi("A.tajmer", "tajmer nije pokrenut: dugme za pokretanje dostupno, zaustavljanje skriveno", /nije pokrenut/.test(e.tajmerStanje || "") && e.start === "on" && e.stop === "skriven");
  zapisi("A.faktura", "bez označene stavke dugme za fakturu je onemogućeno", e.fakturaDugme === "off");
  zapisi("A.slanje", "nema dugmeta za slanje mejlom, SEF, PDF ni brisanje", !/[Pp]ošalji|SEF prijav|PDF|Obriši/.test(e.ceo.replace("ne prijavljuje se u SEF", "").replace("nije prijavljena u SEF", "")));
  await s.zatvori();
}
// ── B: upis stavke ───────────────────────────────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (p, b) => tela.push([p, b]) });
  await ucitano(s.p);
  await upisi(s.p, { opis: "Sastav tužbe", tarifa: "T01" });
  let e = await ekran(s.p);
  const t = (tela.find(x => x[0] === "/billing/entries") || [])[1] || {};
  zapisi("B.tarifa", "telo: predmet_id, opis, tip=tarifa, tarifa_sifra — BEZ iznosa i bez user_id", t.predmet_id === s.A[0].id && t.opis === "Sastav tužbe" && t.tip === "tarifa" && t.tarifa_sifra === "T01" && !("iznos_rsd" in t) && !("user_id" in t), JSON.stringify(t));
  zapisi("B.tarifa", "poruka: iznos je izračunao server", (e.poruka || "") === "uspeh:Stavka je upisana: 600,00 RSD (iznos je izračunao server).", e.poruka);
  await cekaj(s.p, () => document.querySelectorAll("#np-stavke tr").length === 3);
  e = await ekran(s.p);
  zapisi("B.tarifa", "lista je ponovo pročitana sa servera; forma je prazna", e.redovi.length === 3 && e.redovi.some(r => /Sastav tužbe\|T01/.test(r)) && await s.p.inputValue("#np-opis") === "");
  await upisi(s.p, { opis: "Konsultacije", sati: "1,5" });
  const t2 = tela.filter(x => x[0] === "/billing/entries")[1][1];
  zapisi("B.sati", "samo sati (zarez prihvaćen): tip=satnica, sati=1.5, bez iznosa", t2.tip === "satnica" && t2.sati === 1.5 && !("iznos_rsd" in t2) && !("tarifa_sifra" in t2), JSON.stringify(t2));
  await upisi(s.p, { opis: "Paušal", iznos: "15000", datum: "2026-10-05" });
  const t3 = tela.filter(x => x[0] === "/billing/entries")[2][1];
  zapisi("B.iznos", "iznos + datum: tip=ostalo, iznos_rsd=15000, datum", t3.tip === "ostalo" && t3.iznos_rsd === 15000 && t3.datum === "2026-10-05", JSON.stringify(t3));
  e = await ekran(s.p);
  zapisi("B.iznos", "uz unet iznos poruka ne tvrdi da je server računao", e.poruka === "uspeh:Stavka je upisana: 15.000,00 RSD.", e.poruka);
  await s.zatvori();
}
// ── C: lokalna validacija (ništa poslato) ───────────────────────────────
{
  const s = await scenario();
  await ucitano(s.p);
  for (const [naziv, ulaz, re] of [
    ["bez opisa", { opis: "", iznos: "100" }, /opis radnje/], ["bez osnova za iznos", { opis: "Rad" }, /tarifu, unesite iznos ili unesite sate/],
    ["iznos nije broj", { opis: "Rad", iznos: "sto" }, /Iznos mora biti broj/], ["negativan iznos", { opis: "Rad", iznos: "-5" }, /Iznos mora biti broj/],
    ["nula sati", { opis: "Rad", sati: "0" }, /Sati moraju/], ["previše sati", { opis: "Rad", sati: "30" }, /Sati moraju/],
  ]) {
    await upisi(s.p, ulaz);
    const e = await ekran(s.p);
    zapisi("C.validacija", `${naziv}: lokalna greška`, (e.poruka || "").startsWith("greska:") && re.test(e.poruka), e.poruka);
  }
  zapisi("C.validacija", "nijedan od neispravnih unosa nije poslat", zahtevi(s, /^\/billing\/entries$/).length === 0);
  await s.zatvori();
}
// ── D: greške upisa i nepoznat ishod ────────────────────────────────────
for (const [naziv, kuka, stanje, re] of [
  ["400", { status: 400 }, "greska", /nije prihvatio zahtev/], ["404", { status: 404 }, "greska", /Predmet nije dostupan/], ["422", { status: 422 }, "greska", /unete podatke/],
  ["429", { status: 429 }, "greska", /Previše zahteva/], ["403", { status: 403 }, "greska", /nije dostupna/], ["500", { status: 500 }, "nepoznato", /Ishod nije poznat/],
  ["prekid", { prekid: true }, "nepoznato", /Ishod nije poznat/],
]) {
  const s = await scenario({ pre: (p) => p === "/billing/entries:POST" ? kuka : null });
  await ucitano(s.p);
  const getPre = zahtevi(s, /^\/billing\/entries$/, "GET").length;
  await upisi(s.p, { opis: "Rad X", iznos: "100" });
  const e = await ekran(s.p);
  zapisi("D.ishod", `${naziv}: „${stanje}“, unos ostaje`, (e.poruka || "").startsWith(stanje + ":") && re.test(e.poruka) && await s.p.inputValue("#np-opis") === "Rad X" && !/Stavka je upisana/.test(e.poruka), e.poruka);
  zapisi("D.ishod", `${naziv}: aplikacija šalje jednom (bez ponavljanja)`, await fetchova(s.p, "/billing/entries:POST") === 1);
  if (stanje === "nepoznato") {
    await s.p.waitForTimeout(300);
    zapisi("D.ishod", `${naziv}: lista se ponovo čita radi provere`, zahtevi(s, /^\/billing\/entries$/, "GET").length > getPre);
  }
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/billing/entries:POST" ? new Promise(r => setTimeout(r, 900)) : null });
  await ucitano(s.p);
  await s.p.fill("#np-opis", "Dupli"); await s.p.fill("#np-iznos", "100");
  await s.p.evaluate(() => { const b = document.getElementById("np-dodaj"); b.click(); b.click(); document.getElementById("np-forma").requestSubmit(); });
  await gotovo(s.p, "np-poruka");
  await s.p.waitForTimeout(200);
  zapisi("D.dupli", "višestruki klik → tačno jedan upis", await fetchova(s.p, "/billing/entries:POST") === 1 && zahtevi(s, /^\/billing\/entries$/).length === 1);
  await s.zatvori();
}
// ── E: istina o čitanju ─────────────────────────────────────────────────
{
  const s = await scenario({ pre: (p) => p === "/billing/entries:GET" ? { status: 500 } : null });
  await gotovo(s.p, "np-stavke-stanje");
  const e = await ekran(s.p);
  zapisi("E.istina", "stavke 500 → „nije prazna lista“; bez zbira i tabele; faktura onemogućena", /nije prazna lista/.test(e.stavkeStanje || "") && e.stavkeStanje.startsWith("greska:") && e.zbir === null && !e.redovi.length && e.fakturaDugme === "off", e.stavkeStanje);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/billing/faktura:GET" ? { status: 503 } : null });
  await gotovo(s.p, "np-fakture-stanje");
  const e = await ekran(s.p);
  zapisi("E.istina", "fakture 503 → „nije prazna lista“", (e.faktureStanje || "").startsWith("greska:") && /nije prazna/.test(e.faktureStanje) && !e.fakture.length, e.faktureStanje);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/billing/tarifa:GET" ? { status: 500 } : null });
  await gotovo(s.p, "np-poruka");
  const e = await ekran(s.p);
  zapisi("E.istina", "tarifa 500 → poruka; spisak tarifa prazan (ništa izmišljeno), upis sa iznosom i dalje moguć", e.tarife.length === 0 && /Tarifa nije učitana/.test(e.poruka || ""));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/billing/timer/aktivan:GET" ? { status: 500 } : null });
  await gotovo(s.p, "np-tajmer-stanje");
  const e = await ekran(s.p);
  zapisi("E.istina", "stanje tajmera 500 → greška; pokretanje onemogućeno (ne glumi „nije pokrenut“)", (e.tajmerStanje || "").startsWith("greska:") && e.start === "off" && e.stop === "skriven", e.tajmerStanje);
  await s.zatvori();
}
{
  const dodatne = Array.from({ length: 200 }, (_, i) => ({ id: "fx" + i, user_id: "kA", predmet_id: "kA-00001", broj_fakture: "X" + i, status: "nacrt" }));
  const s = await scenario({ dodatneFakture: dodatne });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("E.granica", "na granici od 200 faktura spisak izričito kaže da možda nije potpun", e.fakture.length === 1 && /poslednjih 200/.test(e.faktureStanje || ""), e.faktureStanje);
  zapisi("E.granica", "zahtev za fakture traži limit=200", zahtevi(s, /^\/billing\/faktura$/, "GET").every(z => z.parametri.limit === "200"));
  await s.zatvori();
}
// ── F: tajmer ────────────────────────────────────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (p, b) => tela.push([p, b]) });
  await ucitano(s.p);
  await s.p.fill("#np-tajmer-opis", "Priprema ročišta");
  await s.p.click("#np-tajmer-start");
  await cekaj(s.p, () => !document.getElementById("np-tajmer-stop").hidden);
  let e = await ekran(s.p);
  const ts = (tela.find(x => x[0] === "/billing/timer/start") || [])[1] || {};
  zapisi("F.start", "telo: predmet_id + opis, bez user_id", ts.predmet_id === s.A[0].id && ts.opis === "Priprema ročišta" && !("user_id" in ts), JSON.stringify(ts));
  zapisi("F.start", "tajmer radi za ovaj predmet; samo dugme za zaustavljanje", /radi za ovaj predmet/.test(e.tajmerStanje || "") && /Priprema ročišta/.test(e.tajmerStanje) && e.start === "skriven" && e.stop === "on", e.tajmerStanje);
  await s.p.click("#np-tajmer-stop");
  await cekaj(s.p, () => document.querySelectorAll("#np-stavke tr").length === 3);
  e = await ekran(s.p);
  const tz = (tela.find(x => x[0] === "/billing/timer/stop") || [])[1] || {};
  zapisi("F.stop", "zaustavljanje traži upis stavke (kreiraj_entry: true), bez predmet_id/user_id", tz.kreiraj_entry === true && !("user_id" in tz), JSON.stringify(tz));
  zapisi("F.stop", "poruka: sati i iznos sa servera; stavka u listi", /1,5 h, 9\.000,00 RSD/.test(e.tajmerPoruka || "") && e.redovi.some(r => /Priprema ročišta/.test(r)), e.tajmerPoruka);
  await cekaj(s.p, () => /nije pokrenut/.test(document.getElementById("np-tajmer-stanje").textContent));
  zapisi("F.stop", "posle zaustavljanja stanje je ponovo pročitano", /nije pokrenut/.test((await ekran(s.p)).tajmerStanje || ""));
  await s.zatvori();
}
{
  const s = await scenario({}, { pripremi: (KOR, A) => { KOR[TA].tajmer = { id: "tm-x", user_id: "kA", predmet_id: A[1].id, opis: "Drugi rad", start_at: "2026-10-09T07:00:00+00:00", aktivan: true }; } });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("F.drugi", "tajmer na drugom predmetu: pokretanje onemogućeno, zaustavljanje skriveno, link ka tom predmetu", /drugom vašem predmetu/.test(e.tajmerStanje || "") && e.start === "off" && e.stop === "skriven" && e.drugi === `#/predmeti/${s.A[1].id}/naplata`, `${e.start}/${e.stop}/${e.drugi}`);
  await s.zatvori();
}
for (const [naziv, kuka, re] of [["409", { status: 409 }, /već radi/], ["prekid", { prekid: true }, /Ishod nije poznat/], ["500", { status: 500 }, /Ishod nije poznat/]]) {
  const s = await scenario({ pre: (p) => p === "/billing/timer/start:POST" ? kuka : null });
  await ucitano(s.p);
  const pre = zahtevi(s, /^\/billing\/timer\/aktivan$/, "GET").length;
  await s.p.click("#np-tajmer-start");
  await gotovo(s.p, "np-tajmer-poruka");
  await s.p.waitForTimeout(300);
  const e = await ekran(s.p);
  zapisi("F.greska", `start ${naziv}: poruka, stanje tajmera ponovo pročitano, jedno slanje`, re.test(e.tajmerPoruka || "") && zahtevi(s, /^\/billing\/timer\/aktivan$/, "GET").length > pre && await fetchova(s.p, "/billing/timer/start:POST") === 1, e.tajmerPoruka);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/billing/timer/stop:POST" ? { prekid: true } : null }, { pripremi: (KOR, A) => { KOR[TA].tajmer = { id: "tm-y", user_id: "kA", predmet_id: A[0].id, start_at: "2026-10-09T07:00:00+00:00", aktivan: true }; } });
  await ucitano(s.p);
  await s.p.click("#np-tajmer-stop");
  await gotovo(s.p, "np-tajmer-poruka");
  const e = await ekran(s.p);
  zapisi("F.greska", "stop prekid: „ishod nepoznat“, nikad „nije zaustavljen“; jedno slanje", e.tajmerPoruka.startsWith("nepoznato:") && !/nije zaustavljen|nije upisan/.test(e.tajmerPoruka) && await fetchova(s.p, "/billing/timer/stop:POST") === 1, e.tajmerPoruka);
  await s.zatvori();
}
// ── G: nacrt fakture ─────────────────────────────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (p, b) => tela.push([p, b]) });
  await ucitano(s.p);
  await s.p.check('#np-stavke input[data-stavka="e-old-1"]');
  let e = await ekran(s.p);
  zapisi("G.izbor", "označena stavka omogućava dugme", e.fakturaDugme === "on");
  await s.p.click("#np-faktura-dugme");
  e = await ekran(s.p);
  zapisi("G.validacija", "bez klijenta: lokalna greška, ništa poslato", /naziv klijenta/.test(e.fakturaPoruka || "") && zahtevi(s, /^\/billing\/faktura$/).length === 0);
  await s.p.fill("#np-klijent", "Ana Jović"); await s.p.selectOption("#np-pdv", "20"); await s.p.fill("#np-napomena", "Avans nije uplaćen");
  await s.p.click("#np-faktura-dugme");
  await gotovo(s.p, "np-faktura-poruka");
  e = await ekran(s.p);
  const t = (tela.find(x => x[0] === "/billing/faktura") || [])[1] || {};
  zapisi("G.faktura", "telo: predmet_id, entry_ids, klijent, pdv, napomena — bez user_id i bez statusa", t.predmet_id === s.A[0].id && JSON.stringify(t.entry_ids) === '["e-old-1"]' && t.klijent_naziv === "Ana Jović" && t.pdv_stopa === 20 && t.napomena === "Avans nije uplaćen" && !("user_id" in t) && !("status" in t), JSON.stringify(t));
  zapisi("G.faktura", "poruka: NACRT; izričito nije izdata, nije poslata, nije u SEF", /nacrt fakture br\. 2026\/0003 na 14\.400,00 RSD/.test(e.fakturaPoruka || "") && /nije izdata, nije poslata klijentu i nije prijavljena u SEF/.test(e.fakturaPoruka), e.fakturaPoruka);
  await cekaj(s.p, () => document.querySelectorAll("#np-fakture .review").length === 2 && !document.querySelector('#np-stavke input[data-stavka="e-old-1"]'));
  e = await ekran(s.p);
  zapisi("G.faktura", "stavka je sada „na fakturi“ bez polja za izbor; nova faktura u spisku kao nacrt", e.redovi.every(r => !/☐$/.test(r)) && /2026\/0003.*nacrt/.test(e.fakture[0]), e.fakture[0]);
  zapisi("G.slanje", "nijedan zahtev ka slanju mejlom, SEF-u, statusu, PDF-u ni brisanju", s.f.zahtevi.every(z => !ZABRANJENO.test(z.putanja) && z.metod !== "DELETE"));
  await s.zatvori();
}
for (const [naziv, kuka, stanje, re] of [["409", { status: 409 }, "greska", /već na fakturi/], ["400", { status: 400 }, "greska", /ne pripadaju ovom predmetu/], ["prekid", { prekid: true }, "nepoznato", /Ishod nije poznat/], ["500", { status: 500 }, "nepoznato", /Ishod nije poznat/]]) {
  const s = await scenario({ pre: (p) => p === "/billing/faktura:POST" ? kuka : null });
  await ucitano(s.p);
  const pre = zahtevi(s, /^\/billing\/entries$/, "GET").length;
  await s.p.check('#np-stavke input[data-stavka="e-old-1"]'); await s.p.fill("#np-klijent", "Ana Jović");
  await s.p.click("#np-faktura-dugme");
  await gotovo(s.p, "np-faktura-poruka");
  await s.p.waitForTimeout(300);
  const e = await ekran(s.p);
  zapisi("G.greska", `faktura ${naziv}: „${stanje}“, bez tvrdnje o uspehu, jedno slanje`, (e.fakturaPoruka || "").startsWith(stanje + ":") && re.test(e.fakturaPoruka) && !/Napravljen je/.test(e.fakturaPoruka) && await fetchova(s.p, "/billing/faktura:POST") === 1, e.fakturaPoruka);
  if (naziv !== "400") zapisi("G.greska", `faktura ${naziv}: stavke ponovo pročitane`, zahtevi(s, /^\/billing\/entries$/, "GET").length > pre);
  await s.zatvori();
}
// ── H: zastarelo i sesija ────────────────────────────────────────────────
{
  // Samo PRVO čitanje (predmet 0) kasni: odgovor predmeta 1 stiže pre zakasnelog odgovora predmeta 0.
  let n = 0;
  const s = await scenario({ pre: (p) => p === "/billing/entries:GET" && n++ === 0 ? new Promise(r => setTimeout(r, 1500)) : null });
  await s.p.waitForTimeout(200);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/naplata"; }, s.A[1].id);
  await s.p.waitForTimeout(2800);
  const e = await ekran(s.p);
  zapisi("H.zastarelo", "stavke predmeta 0 ne stižu na predmet 1", e.redovi.length === 1 && /STAVKA DRUGOG PREDMETA/.test(e.redovi[0]) && !/Sastanak sa klijentom/.test(e.ceo), e.redovi.join(" / "));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p, k) => p === "/billing/entries:GET" && k === "kA" ? new Promise(r => setTimeout(r, 1200)) : null });
  await s.p.waitForTimeout(250);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(2200);
  const e = await ekran(s.p);
  zapisi("H.sesija", "A→B usred učitavanja: zakasneli odgovor A se ne prikazuje", !/Sastanak sa klijentom|Ana Jović|12\.600/.test(e.ceo) && !e.redovi.length, e.redovi.join());
  await s.zatvori();
}
{
  const s = await scenario();
  await ucitano(s.p);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(600);
  const e = await ekran(s.p);
  zapisi("H.sesija", "A→B: stavke, zbir, fakture, tarifa i tajmer A nestaju odmah", !e.redovi.length && e.zbir === null && !e.fakture.length && !e.tarife.length && !/Sastanak sa klijentom|Ana Jović/.test(e.ceo));
  await s.zatvori();
}
// ── I: raspored ──────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await ucitano(s.p);
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("I.raspored", `${w}px: bez horizontalnog skrola stranice`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  // Bez fokusa (fokus pomera i odsečen kontejner): ili staje na ekran, ili se traka korisnički pomera vodoravno.
  const t = await s.p.evaluate(() => {
    const tr = document.getElementById("predmet-odeljci"), r = document.getElementById("tab-dokumenti").getBoundingClientRect();
    return { staje: r.left >= 0 && r.right <= innerWidth, pomera: ["auto", "scroll"].includes(getComputedStyle(tr).overflowX) && tr.scrollWidth > tr.clientWidth, jedanRed: [...tr.children].every(a => a.getClientRects().length === 1) };
  });
  zapisi("I.raspored", `${w}px: poslednji odeljak („Dokumenti“) je dostižan (staje ili se traka pomera)`, (t.staje || t.pomera) && t.jedanRed, JSON.stringify(t));
  if (process.env.NS005_SNIMCI) await s.p.screenshot({ path: `${process.env.NS005_SNIMCI}/ns005-naplata-${w}.png`, fullPage: true });
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0, sviSpoljni.slice(0, 2).join());
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("izolacija", "nijedan zahtev ka slanju/SEF/statusu/PDF/brisanju u celom testu", sviZahtevi.every(z => !ZABRANJENO.test(z.putanja) && z.metod !== "DELETE"));
zapisi("token", "token nikad u adresi", sviZahtevi.every(z => ![TA, TB].some(t => z.upit.includes(t))));
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
