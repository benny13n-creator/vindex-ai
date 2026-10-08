// Vindex V2 NG — NS004 Task 1+2: detalj predmeta i dokumenti (samo čitanje).
// Pokretanje: `node tests/live-matter.mjs` (sam podiže fixture; nijedan zahtev van 127.0.0.1).
//
// Fixture ponavlja UGOVOR postojećih ruta (vlasnik iz tokena, 404 za tuđe):
//   GET /api/predmeti/{id}, GET /api/predmeti/{id}/dokumenti/{dok}/preview.
// Svi tokeni i podaci su izmišljeni.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, napraviDokumente, kombinuj } from "./fixtures/predmeti-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-matter-A-NE-U-LOG-41", TB = "vx-matter-B-NE-U-LOG-52";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);

const XSS = '<img src=x onerror="window.__xss=1">Naziv<script>window.__xss=2</script>';
const A = napraviPredmete("kA", 4, { naziv: i => i === 3 ? XSS : `Predmet A ${i}` });
A.push(...napraviPredmete("kA-obrisan", 1).map(p => ({ ...p, user_id: "kA", brisanje_zapoceto: "2026-10-01T00:00:00Z" })));
const B = napraviPredmete("kB", 2, { naziv: i => `TAJNI predmet B ${i}` });
const KOR = { [TA]: { id: "kA", predmeti: A, klijenti: { [A[0].id]: [{ id: "c1", ime: "Ana", prezime: "Jović", firma: "", uloga: "tužilac" }] } }, [TB]: { id: "kB", predmeti: B } };
const DOK = {
  [A[0].id]: napraviDokumente(A[0].id, "kA", 3),
  [A[1].id]: napraviDokumente(A[1].id, "kA", 2, { tekst: i => i === 0 ? "" : "Drugi tekst" }),
  [A[3].id]: napraviDokumente(A[3].id, "kA", 1, { naziv: () => '<script>window.__xss=3</script>spis.pdf' }),
  [B[0].id]: napraviDokumente(B[0].id, "kB", 2, { tekst: () => "TAJNI tekst B" }),
};

const browser = await chromium.launch();
const konzola = [], sviZahtevi = [], sviSpoljni = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", put = "/?rezim=live", w = 1440, h = 900 } = {}) {
  const f = await pokreniFixture(kombinuj(predmetiRuta(KOR), predmetDetaljRuta(KOR, DOK, kuke)));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}${put}`);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  return {
    hash: location.hash, pogled: document.documentElement.dataset.pogled || "registar",
    naslov: document.getElementById("predmet-naslov").textContent,
    stanje: vid("predmet-stanje") ? document.getElementById("predmet-stanje").dataset.stanje : null,
    stanjeNaslov: document.getElementById("predmet-stanje-naslov").textContent,
    cinjenice: [...document.querySelectorAll("#predmet-cinjenice dt")].map((dt) => dt.textContent + "=" + dt.nextElementSibling.textContent),
    dokumenti: [...document.querySelectorAll("#dok-lista .docs__item")].map(b => b.dataset.dok),
    dokPrazno: vid("dok-prazno"), dokStanje: vid("dok-stanje") ? document.getElementById("dok-stanje").dataset.stanje : null,
    dokStanjeTekst: document.getElementById("dok-stanje").textContent,
    dokTekst: vid("dok-tekst") ? document.getElementById("dok-tekst").textContent : null,
    odeljci: vid("predmet-odeljci"), pregled: vid("odeljak-pregled"), dokOdeljak: vid("odeljak-dokumenti"),
    registar: vid("registry"), redovi: document.querySelectorAll("#rows tr").length,
    tekst: document.body.innerText, html: document.body.innerHTML, mem: window.__vxDetaljUMemoriji(),
  };
});
const zahteviDetalja = (s, id) => s.f.zahtevi.filter(z => z.putanja === "/api/predmeti/" + id);
const zahteviTeksta = (s) => s.f.zahtevi.filter(z => /\/preview$/.test(z.putanja));
const nijedanDetalj = (e) => e.mem.predmet === null && e.cinjenice.length === 0 && e.dokumenti.length === 0 && e.mem.tekst === 0;

// ── Task 1 A: sopstveni predmet ─────────────────────────────────────────
{
  const s = await scenario();
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  const reg = await s.p.evaluate(() => ({ ids: [...document.querySelectorAll("#rows tr")].map(t => t.dataset.id), tekst: document.body.innerText }));
  const live = reg.ids.length === 4 && reg.ids.every(id => id.startsWith("kA-")) && !/Demonstracioni/.test(reg.tekst);
  zapisi("1A.svoj", "?rezim=live: registar su stvarni predmeti korisnika A (nikad DEMO)", live, reg.ids.slice(0, 2).join(","));
  if (live) await s.p.click(`#rows tr[data-id="${A[0].id}"] .case__name`);
  await cekaj(s.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  const e = await ekran(s.p);
  zapisi("1A.svoj", "klik na naziv otvara #/predmeti/<id> (pregled)", e.hash === "#/predmeti/" + A[0].id && e.pogled === "predmet" && e.pregled && !e.registar, e.hash);
  zapisi("1A.svoj", "naslov i činjenice su iz stvarnog odgovora", e.naslov === "Predmet A 0" && e.cinjenice.includes("Tužilac=Tužilac 0") && e.cinjenice.includes("Broj predmeta=P 1000/2026") && e.cinjenice.includes("Vrednost spora=100.000 RSD"), e.cinjenice.join("|"));
  zapisi("1A.svoj", "nema izmišljenih polja (sud, rok)", !e.cinjenice.some(c => /^(Sud|Rok)/.test(c)) && !/TAJNI-OPIS/.test(e.tekst));
  zapisi("1A.svoj", "klijenti iz klijenti_linked", /Ana Jović/.test(e.tekst));
  const z = zahteviDetalja(s, A[0].id);
  zapisi("1A.svoj", "jedan GET detalja, sa tokenom, bez user_id", z.length === 1 && z[0].metod === "GET" && z[0].auth === "Bearer " + TA && !/user_id/.test(z[0].upit));
  zapisi("2.ulaz", "otvaranje predmeta ne poziva tekst dokumenta", zahteviTeksta(s).length === 0);
  await s.zatvori();
}
// ── Task 1 B: tuđ / nepostojeći / obrisan / neispravan ID ───────────────
for (const [naziv, id, ocekujeZahtev] of [["tuđ predmet (B) sa tokenom A", B[0].id, true], ["nepostojeći", "kA-99999", true],
  ["predmet u brisanju", "kA-obrisan-00000", true], ["neispravan ID (putanja)", "..%2F..%2Fapi", false], ["neispravan ID (HTML)", "%3Cimg%3E", false]]) {
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + id });
  await cekaj(s.p, () => !!document.getElementById("predmet-stanje").dataset.stanje && document.getElementById("predmet-stanje").dataset.stanje !== "ucitavanje");
  const e = await ekran(s.p);
  zapisi("1B.tudj", `${naziv}: „Predmet nije dostupan“, nijedan podatak`, e.stanjeNaslov === "Predmet nije dostupan" && nijedanDetalj(e) && !/TAJNI/.test(e.tekst) && !e.odeljci, `${e.stanje} „${e.stanjeNaslov}“`);
  const poslat = s.f.zahtevi.some(z => z.putanja.startsWith("/api/predmeti/") && z.putanja !== "/api/predmeti");
  zapisi("1B.tudj", `${naziv}: ${ocekujeZahtev ? "server odlučuje (zahtev poslat)" : "zahtev se ni ne šalje"}`, poslat === ocekujeZahtev);
  await s.zatvori();
}
// Odgovor za DRUGI predmet (server bi vratio tuđ zapis) se odbacuje.
{
  const s = await scenario({ izmeniDetalj: (t) => ({ ...t, predmet: { ...B[0] } }) }, { put: "/?rezim=live#/predmeti/" + A[0].id });
  await cekaj(s.p, () => document.getElementById("predmet-stanje").dataset.stanje === "greska-invalid_response");
  const e = await ekran(s.p);
  zapisi("1B.tudj", "odgovor sa drugim predmet.id se odbacuje kao neispravan (ništa od B)", e.stanje === "greska-invalid_response" && nijedanDetalj(e) && !/TAJNI/.test(e.tekst), e.stanje);
  await s.zatvori();
}
// ── Task 1 C: sesija uklonjena dok je detalj na ekranu ──────────────────
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:first-child button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  await postavi(s, null);
  await cekaj(s.p, () => document.getElementById("predmet-stanje").dataset.stanje === "bez-prijave");
  const e = await ekran(s.p);
  zapisi("1C.odjava", "odjava: detalj, lista dokumenata i tekst nestaju (ekran i memorija)", e.stanje === "bez-prijave" && nijedanDetalj(e) && !/Predmet A 0|TEKST-kA/.test(e.tekst), e.stanje);
  await s.zatvori();
}
// ── Task 1 D: zakasneli odgovor prethodne sesije ────────────────────────
{
  let pusti; const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ preDetalja: (id, k) => (k === "kA" ? kapija : null) }, { put: "/?rezim=live#/predmeti/" + A[0].id });
  await cekaj(s.p, () => document.getElementById("predmet-stanje").dataset.stanje === "ucitavanje");
  await postavi(s, ses("kB", TB));
  await cekaj(s.p, () => document.getElementById("predmet-stanje").dataset.stanje === "greska-not_found");
  pusti();
  await new Promise(r => setTimeout(r, 800));
  const e = await ekran(s.p);
  zapisi("1D.zakasneli", "odgovor za A stigao posle prelaska na B: ne iscrtava se", e.stanje === "greska-not_found" && nijedanDetalj(e) && !/Predmet A 0/.test(e.tekst), e.stanje);
  zapisi("1D.zakasneli", "B je zatražio isti ID sopstvenim tokenom (server odbija)", zahteviDetalja(s, A[0].id).some(z => z.auth === "Bearer " + TB));
  await s.zatvori();
}
// ── Task 1 E: neispravni odgovori i greške ──────────────────────────────
for (const [naziv, kuke, oznaka, naslov] of [
  ["predmet bez niza dokumenata", { izmeniDetalj: (t) => ({ ...t, dokumenti: null }) }, "greska-invalid_response", "Odgovor servera nije ispravan"],
  ["dokument tuđeg predmeta u odgovoru", { izmeniDetalj: (t) => ({ ...t, dokumenti: [...t.dokumenti, DOK[B[0].id][0]] }) }, "greska-invalid_response", "Odgovor servera nije ispravan"],
  ["odgovor nije JSON", { preDetalja: () => ({ status: 200, telo: "<html>" }) }, "greska-invalid_response", "Odgovor servera nije ispravan"],
  ["500", { preDetalja: () => ({ status: 500 }) }, "greska-server_error", "Predmet nije učitan"],
  ["403", { preDetalja: () => ({ status: 403 }) }, "greska-forbidden", "Predmet nije dostupan"],
  ["401", { preDetalja: () => ({ status: 401 }) }, "greska-auth_required", "Prijava više nije važeća"],
]) {
  const s = await scenario(kuke, { put: "/?rezim=live#/predmeti/" + A[0].id });
  await cekaj(s.p, (o) => document.getElementById("predmet-stanje").dataset.stanje === o, oznaka);
  const e = await ekran(s.p);
  zapisi("1E.greske", `${naziv} → „${naslov}“, ništa od podataka, nije „prazan predmet“`, e.stanje === oznaka && e.stanjeNaslov === naslov && nijedanDetalj(e) && !/TAJNI|nema dokumenata/i.test(e.tekst), `${e.stanje}`);
  await s.zatvori();
}
{
  const s = await scenario({ preDetalja: () => new Promise(() => {}) }, { put: "/?rezim=live" });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  // mreža: server prekida vezu
  await s.zatvori();
  const s2 = await scenario({}, { put: "/?rezim=live" });
  await cekaj(s2.p, () => document.querySelectorAll("#rows tr").length > 0);
  await s2.p.route("**/api/predmeti/" + A[0].id, r => r.abort("connectionreset"));
  await s2.p.evaluate((id) => { location.hash = "#/predmeti/" + id; }, A[0].id);
  await cekaj(s2.p, () => document.getElementById("predmet-stanje").dataset.stanje === "greska-network_error");
  const e = await ekran(s2.p);
  zapisi("1E.greske", "mreža prekinuta → „Server nije dostupan“, ništa od podataka", e.stanje === "greska-network_error" && nijedanDetalj(e), e.stanje);
  await s2.zatvori();
}
// ── Task 1 F/G: osvežavanje, Back/Forward ───────────────────────────────
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.reload();
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  const e = await ekran(s.p);
  zapisi("1F.refresh", "osvežavanje na #/…/dokumenti vraća isti predmet i odeljak dokumenata (LIVE)", e.dokOdeljak && e.dokumenti.length === 3 && e.naslov === "Predmet A 0" && !/Demonstracioni/.test(e.tekst));
  await s.zatvori();
}
{
  const s = await scenario();
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  await s.p.click(`#rows tr[data-id="${A[1].id}"] .case__name`);
  await cekaj(s.p, () => document.getElementById("predmet-naslov").textContent === "Predmet A 1");
  await s.p.click("#tab-dokumenti");
  await cekaj(s.p, () => !document.getElementById("odeljak-dokumenti").hidden);
  await s.p.goBack();
  await cekaj(s.p, () => !document.getElementById("odeljak-pregled").hidden);
  const naPregled = await ekran(s.p);
  await s.p.goBack();
  await cekaj(s.p, () => document.documentElement.dataset.pogled !== "predmet");
  const naRegistar = await ekran(s.p);
  zapisi("1G.back", "Back: dokumenti → pregled → registar; registar ponovo prikazuje predmete", naPregled.pregled && !naPregled.dokOdeljak && naRegistar.registar && naRegistar.redovi === 4 && nijedanDetalj(naRegistar), `${naRegistar.redovi}`);
  await s.p.goForward();
  await cekaj(s.p, () => document.getElementById("predmet-naslov").textContent === "Predmet A 1");
  zapisi("1G.back", "Forward vraća predmet (nov zahtev, ista pravila)", (await ekran(s.p)).naslov === "Predmet A 1");
  await s.p.click("#predmet-nazad");
  await cekaj(s.p, () => document.documentElement.dataset.pogled !== "predmet");
  zapisi("1G.back", "link „Predmeti“ vraća registar", (await ekran(s.p)).registar);
  await s.zatvori();
}
// ── Task 2: dokumenti ───────────────────────────────────────────────────
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[0].id });
  await cekaj(s.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  await s.p.click("#tab-dokumenti");
  await cekaj(s.p, () => !document.getElementById("odeljak-dokumenti").hidden);
  const e = await ekran(s.p);
  zapisi("2A.svoji", "lista stvarnih dokumenata predmeta, broj na kartici", e.dokumenti.join() === DOK[A[0].id].map(d => d.id).join() && /Dokumenti\s*3/.test(e.tekst));
  zapisi("2F.bez-upisa", "ulazak u Dokumente ne šalje zahtev za tekst (bez audit upisa)", zahteviTeksta(s).length === 0);
  await s.p.click("#dok-lista li:nth-child(2) button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  const d = await ekran(s.p);
  zapisi("2A.svoji", "izabran dokument: stvaran tekst sa preview rute", d.dokTekst === DOK[A[0].id][1].tekst_sadrzaj && zahteviTeksta(s).length === 1, d.dokTekst);
  await s.zatvori();
}
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[1].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:first-child button");
  await cekaj(s.p, () => document.getElementById("dok-stanje").dataset.stanje === "bez-teksta");
  const e = await ekran(s.p);
  zapisi("2.istina", "dokument bez izdvojenog teksta: pošteno stanje, bez lažnog prikazivača", e.dokStanje === "bez-teksta" && e.dokTekst === null && /nije izdvojen/.test(e.dokStanjeTekst));
  await s.zatvori();
}
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[2].id + "/dokumenti" });
  await cekaj(s.p, () => !document.getElementById("dok-prazno").closest("[hidden]") && !document.getElementById("dok-prazno").hidden);
  const e = await ekran(s.p);
  zapisi("2.prazno", "predmet bez dokumenata: „Predmet nema dokumenata“ (samo posle uspešnog čitanja)", e.dokPrazno && e.dokumenti.length === 0);
  await s.zatvori();
  const s2 = await scenario({ preDetalja: () => ({ status: 500 }) }, { put: "/?rezim=live#/predmeti/" + A[2].id + "/dokumenti" });
  await cekaj(s2.p, () => document.getElementById("predmet-stanje").dataset.stanje === "greska-server_error");
  const g = await ekran(s2.p);
  zapisi("2.prazno", "greška čitanja NIKAD ne kaže „nema dokumenata“", !g.dokPrazno && !/nema dokumenata/i.test(g.tekst));
  await s2.zatvori();
}
for (const [naziv, kuke, ocek] of [["500", { preTeksta: () => ({ status: 500 }) }, /greške na serveru/], ["404", { preTeksta: () => ({ status: 404 }) }, /nije dostupan/]]) {
  const s = await scenario(kuke, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:first-child button");
  await cekaj(s.p, () => document.getElementById("dok-stanje").dataset.stanje === "greska");
  const e = await ekran(s.p);
  zapisi("2E.greska", `tekst ${naziv}: greška, bez teksta`, e.dokStanje === "greska" && e.dokTekst === null && ocek.test(e.dokStanjeTekst), e.dokStanjeTekst);
  await s.zatvori();
}
// 2E: neuspeh posle uspeha ne ostavlja stari tekst
{
  let n = 0;
  const s = await scenario({ preTeksta: () => (++n === 2 ? { status: 500 } : null) }, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:nth-child(1) button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  await s.p.click("#dok-lista li:nth-child(2) button");
  await cekaj(s.p, () => document.getElementById("dok-stanje").dataset.stanje === "greska");
  const e = await ekran(s.p);
  zapisi("2E.greska", "uspešan pa neuspešan dokument: tekst prethodnog nije ostao na ekranu", e.dokTekst === null && !/TEKST-kA-00000-d0/.test(e.tekst));
  await s.zatvori();
}
// 2C: promena dokumenta i predmeta dok tekst kasni
{
  let pusti; const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ preTeksta: (dok) => (dok.endsWith("-d0") ? kapija : null) }, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:nth-child(1) button");
  await s.p.click("#dok-lista li:nth-child(2) button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  pusti(); await new Promise(r => setTimeout(r, 600));
  const e = await ekran(s.p);
  zapisi("2C.promena", "zakasneli tekst dokumenta 1 ne prepisuje izabrani dokument 2", e.dokTekst === DOK[A[0].id][1].tekst_sadrzaj, e.dokTekst);
  await s.zatvori();
}
{
  let pusti; const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ preDetalja: (id) => (id === A[1].id ? kapija : null) }, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:nth-child(1) button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/dokumenti"; }, A[1].id);
  await cekaj(s.p, () => document.getElementById("predmet-stanje").dataset.stanje === "ucitavanje");
  const tokom = await ekran(s.p);
  zapisi("2C.promena", "prelazak na drugi predmet: lista i tekst prethodnog nestaju PRE novih podataka", nijedanDetalj(tokom) && !/TEKST-kA-00000|Spis 1 predmeta kA-00000/.test(tokom.tekst), JSON.stringify(tokom.mem));
  pusti();
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length === 2);
  const posle = await ekran(s.p);
  zapisi("2C.promena", "posle: samo dokumenti novog predmeta", posle.dokumenti.every(id => id.startsWith(A[1].id)));
  await s.zatvori();
}
// 2B: tuđ dokument preko izvora (direktan poziv) — server/fixture odbija
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[0].id });
  await cekaj(s.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  const r = await s.p.evaluate(async ([pid, did]) => {
    const t = window.VxSesija.token();
    const a = await window.VxPredmetIzvor.ucitajTekst(pid, did, t);
    const b = await window.VxPredmetIzvor.ucitajPredmet(pid, t);
    return [a.ok ? "OK" : a.greska.kod, b.ok ? "OK" : b.greska.kod];
  }, [B[0].id, DOK[B[0].id][0].id]);
  zapisi("2B.tudji", "tuđ dokument i tuđ predmet sa tokenom A: NOT_FOUND (bez sadržaja)", r[0] === "NOT_FOUND" && r[1] === "NOT_FOUND", r.join(","));
  await s.zatvori();
}
// 2D: promena sesije briše dokumente
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[0].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:first-child button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  await postavi(s, ses("kB", TB));
  await cekaj(s.p, () => document.getElementById("predmet-stanje").dataset.stanje === "greska-not_found");
  const e = await ekran(s.p);
  zapisi("2D.sesija", "A → B: dokumenti i tekst A nestaju; B ne dobija A-ov predmet", nijedanDetalj(e) && !/TEKST-kA|Spis 1 predmeta kA/.test(e.tekst));
  await s.zatvori();
}
// XSS
{
  const s = await scenario({}, { put: "/?rezim=live#/predmeti/" + A[3].id + "/dokumenti" });
  await cekaj(s.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await s.p.click("#dok-lista li:first-child button");
  await cekaj(s.p, () => !document.getElementById("dok-tekst").hidden);
  const r = await s.p.evaluate(() => ({ el: document.querySelectorAll("#predmet img, #predmet script").length, xss: window.__xss,
    naslov: document.getElementById("predmet-naslov").textContent, dok: document.getElementById("dok-naslov").textContent }));
  zapisi("xss", "HTML u nazivu predmeta i dokumenta je tekst; ništa se ne izvršava", r.el === 0 && r.xss === undefined && r.naslov.includes("<img") && r.dok.includes("<script>"), JSON.stringify({ el: r.el, xss: r.xss }));
  await s.zatvori();
}
// Bez prijave / istekla sesija na direktnom linku
for (const [naziv, token, za, oznaka] of [["bez prijave", null, 0, "bez-prijave"], ["istekla sesija", TA, -60, "istekla"]]) {
  const f = await pokreniFixture(kombinuj(predmetiRuta(KOR), predmetDetaljRuta(KOR, DOK)));
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, token ? ses("kA", token, za) : null]);
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}`);
  await cekaj(p, (o) => document.getElementById("predmet-stanje").dataset.stanje === o, oznaka);
  const e = await ekran(p);
  zapisi("stanja", `${naziv}: stanje „${oznaka}“, nijedan zahtev detalja`, e.stanje === oznaka && nijedanDetalj(e) && f.zahtevi.every(z => z.putanja === "/api/predmeti" || false) && !f.zahtevi.some(z => z.putanja.startsWith("/api/predmeti/")));
  await ctx.close(); await f.zatvori();
}
// DEMO: nema detalja, nema zahteva
{
  const f = await pokreniFixture(kombinuj(predmetiRuta(KOR), predmetDetaljRuta(KOR, DOK)));
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${f.port}/#/predmeti/${A[0].id}`);
  await p.waitForTimeout(400);
  const e = await ekran(p);
  zapisi("demo", "DEMO ignoriše rutu predmeta: registar, nijedan /api zahtev", e.pogled === "registar" && e.registar && f.zahtevi.length === 0);
  await p.click("#rows tr:first-child .case__name");
  await p.waitForTimeout(200);
  zapisi("demo", "DEMO: klik na naziv ne otvara izmišljen detalj", (await ekran(p)).pogled === "registar" && f.zahtevi.length === 0);
  await ctx.close(); await f.zatvori();
}

await browser.close();
const sve = [konzola.join("\n"), izlaz.join("\n")].join("\n");
zapisi("bezbednost", "svi zahtevi ka API-ju su GET (nijedan upis iz V2)", sviZahtevi.length > 0 && sviZahtevi.every(z => z.metod === "GET"), `${sviZahtevi.length} zahteva`);
zapisi("bezbednost", "token nikad u URL-u ili upitu; user_id se ne šalje", sviZahtevi.every(z => ![TA, TB].some(t => (z.putanja + z.upit).includes(t)) && !/user_id/.test(z.upit)));
zapisi("bezbednost", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0, sviSpoljni.slice(0, 2).join(","));
zapisi("bezbednost", "nijedan token u konzoli ni izlazu", ![TA, TB].some(t => sve.includes(t)));
zapisi("bezbednost", "nijedna JS greška stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
