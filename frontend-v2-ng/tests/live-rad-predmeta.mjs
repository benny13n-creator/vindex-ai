// Vindex V2 NG — NS005 Task 3: izmena predmeta, beleške, hronologija (CAP-005/006/007).
// Pokretanje: `node tests/live-rad-predmeta.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend isti ugovor dokazuje nad STVARNIM rutama: tests/test_ns005_t3_izmena_beleske.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { izmenaPredmetaRuta, beleskaRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-rad-A-NE-U-LOG-81", TB = "vx-rad-B-NE-U-LOG-92";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const XSS = '<img src=x onerror="window.__xss=1">beleška<script>window.__xss=2</script>';

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", odeljak = "", w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1, { naziv: () => "TAJNI B" });
  const KOR = {
    [TA]: { id: "kA", predmeti: A, beleske: { [A[0].id]: [{ id: "b0", predmet_id: A[0].id, user_id: "kA", sadrzaj: "Prva beleška A", created_at: "2026-10-05T09:00:00Z" }] },
            hronologija: { [A[0].id]: [{ id: "h0", predmet_id: A[0].id, dogadjaj: "Tužba podneta", datum_iso: "2026-09-01", vaznost: "visoka" },
                                       { id: "h1", predmet_id: A[0].id, dogadjaj: '<b onmouseover="window.__xss=3">Ročište</b>', datum_iso: "2026-10-15", vaznost: "" }] } },
    [TB]: { id: "kB", predmeti: B, beleske: { [B[0].id]: [{ id: "bB", predmet_id: B[0].id, user_id: "kB", sadrzaj: "TAJNA beleška B", created_at: "2026-10-05T09:00:00Z" }] } },
  };
  const f = await pokreniFixture(kombinuj(izmenaPredmetaRuta(KOR, kuke), beleskaRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {}, kuke.detalj || {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}${odeljak}`);
  await cekaj(p, () => document.getElementById("predmet-naslov").textContent.length > 0);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, B, ctx, p, drugi, spoljni, async zatvori() { sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const por = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  return { hash: location.hash, cinjenice: [...document.querySelectorAll("#predmet-cinjenice dt")].map(dt => dt.textContent + "=" + dt.nextElementSibling.textContent),
    naslov: document.getElementById("predmet-naslov").textContent, forma: vid("izmena-forma"), dugmeIzmena: vid("izmena-otvori"),
    izmPoruka: por("izm-poruka"), pregledPoruka: por("pregled-poruka"), belPoruka: por("bel-poruka"),
    beleske: [...document.querySelectorAll("#bel-lista .note__text")].map(x => x.textContent),
    hron: [...document.querySelectorAll("#hron-lista .chrono__item")].map(x => x.querySelector(".chrono__date").textContent + " " + x.querySelector(".chrono__text").textContent),
    belStanje: vid("bel-stanje") ? document.getElementById("bel-stanje").textContent : null, hronStanje: vid("hron-stanje") ? document.getElementById("hron-stanje").textContent : null,
    rad: vid("odeljak-rad"), tabRad: document.getElementById("tab-rad").getAttribute("aria-current"),
    vrednostPolja: document.getElementById("izm-tuzilac").value, belTekst: document.getElementById("bel-tekst").value,
    xss: window.__xss || null, tekst: document.body.innerText };
});
const zahtevi = (s, metod, re) => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));

// ── A: izmena jednog polja → ponovno čitanje → tačna sačuvana vrednost ──
{
  const upisi = [];
  const s = await scenario({ upisano: (p, b) => upisi.push(b) });
  let e = await ekran(s.p);
  zapisi("A.izmena", "„Izmeni podatke“ je vidljivo na pregledu sopstvenog predmeta", e.dugmeIzmena);
  await s.p.click("#izmena-otvori");
  e = await ekran(s.p);
  zapisi("A.izmena", "forma je popunjena trenutnim vrednostima", e.forma && e.vrednostPolja === "Tužilac 0", e.vrednostPolja);
  await s.p.fill("#izm-tuzilac", "Ana Jović");
  await s.p.fill("#izm-vrednost", "850.000");
  const detaljaPre = zahtevi(s, "GET", /^\/api\/predmeti\/kA-00000$/).length;
  await s.p.click("#izm-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("pregled-poruka"); return !n.hidden && n.dataset.stanje === "uspeh"; });
  e = await ekran(s.p);
  const z = zahtevi(s, "PATCH", /^\/api\/predmeti\/kA-00000$/);
  zapisi("A.izmena", "jedan PATCH sa tokenom A", z.length === 1 && z[0].auth === "Bearer " + TA);
  zapisi("A.izmena", "telo nosi SAMO izmenjena polja + if_updated_at (bez user_id, bez broja)", upisi.length === 1 && JSON.stringify(Object.keys(upisi[0]).sort()) === JSON.stringify(["if_updated_at", "tuzilac", "vrednost_spora"]) && upisi[0].vrednost_spora === 850000, JSON.stringify(upisi[0]));
  zapisi("A.izmena", "posle uspeha predmet je PONOVO pročitan sa servera", zahtevi(s, "GET", /^\/api\/predmeti\/kA-00000$/).length === detaljaPre + 1);
  zapisi("A.izmena", "prikazana je sačuvana vrednost i potvrda", e.cinjenice.includes("Tužilac=Ana Jović") && e.cinjenice.includes("Vrednost spora=850.000 RSD") && /sačuvane/.test(e.pregledPoruka || ""), e.cinjenice.join("|"));
  await s.p.reload();
  await cekaj(s.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  e = await ekran(s.p);
  zapisi("A.izmena", "osvežavanje stranice: ista sačuvana vrednost", e.cinjenice.includes("Tužilac=Ana Jović"));
  // Bez izmena → ništa se ne šalje
  await s.p.click("#izmena-otvori"); await s.p.click("#izm-sacuvaj");
  e = await ekran(s.p);
  zapisi("A.izmena", "bez izmena: ništa se ne šalje", zahtevi(s, "PATCH", /./).length === 1 && /Nema izmena/.test(e.izmPoruka || ""));
  await s.p.fill("#izm-naziv", "  ");
  await s.p.click("#izm-sacuvaj");
  e = await ekran(s.p);
  zapisi("A.izmena", "prazan naziv: lokalna greška, ništa poslato", zahtevi(s, "PATCH", /./).length === 1 && /prazan/.test(e.izmPoruka || ""));
  await s.p.fill("#izm-naziv", "Predmet kA broj 0"); await s.p.fill("#izm-vrednost", "dvesta");
  await s.p.click("#izm-sacuvaj");
  e = await ekran(s.p);
  zapisi("A.izmena", "neispravna vrednost spora: lokalna greška, ništa poslato", zahtevi(s, "PATCH", /./).length === 1 && /broj/.test(e.izmPoruka || ""));
  await s.zatvori();
}
// ── A2: istovremena izmena (409), nepoznat ishod, odbijanje ─────────────
{
  const s = await scenario();
  await s.p.click("#izmena-otvori");
  s.KOR[TA].predmeti[0].updated_at = "2026-10-07T00:00:00.000Z";   // izmenjeno na drugom mestu
  await s.p.fill("#izm-tuzeni", "Moja verzija");
  await s.p.click("#izm-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("izm-poruka"); return !n.hidden && n.dataset.stanje === "greska"; });
  const e = await ekran(s.p);
  zapisi("A2.konflikt", "409: „izmenjen na drugom mestu… NIJE sačuvana“, forma ostaje sa unosom", /drugom mestu/.test(e.izmPoruka) && /NIJE sačuvana/.test(e.izmPoruka) && e.forma && s.KOR[TA].predmeti[0].tuzeni === "Tuženi 0", e.izmPoruka);
  await s.zatvori();
}
for (const [naziv, kuka, stanje, re] of [
  ["500", { status: 500 }, "nepoznato", /nije poznat/], ["prekid veze", { prekid: true }, "nepoznato", /možda sačuvane/],
  ["404", { status: 404 }, "greska", /nije dostupan/], ["422", { status: 422 }, "greska", /nije prihvatio/],
]) {
  const s = await scenario({ pre: (put) => /^\/api\/predmeti\/[^/]+$/.test(put) ? kuka : null });
  await s.p.click("#izmena-otvori");
  await s.p.fill("#izm-tuzeni", "Novi tuženi");
  await s.p.click("#izm-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("izm-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("A2.ishod", `izmena ${naziv}: stanje „${stanje}“, bez lažnog uspeha, unos ostaje`, (e.izmPoruka || "").startsWith(stanje + ":") && re.test(e.izmPoruka) && e.forma && !e.cinjenice.includes("Tuženi=Novi tuženi"), e.izmPoruka);
  zapisi("A2.ishod", `izmena ${naziv}: ${stanje === "nepoznato" ? "ne tvrdi „nije sačuvano“" : "jasno: ništa nije sačuvano"}`, stanje === "nepoznato" ? !/nije sa[cč]uvan|NIJE/.test(e.izmPoruka) : /Ništa nije sačuvano|nije dostupan/.test(e.izmPoruka));
  await s.zatvori();
}

// ── B: beleška → ponovno čitanje → beleška je tu; hronologija ───────────
{
  const upisi = [];
  const s = await scenario({ upisano: (r, b) => upisi.push(b) }, { odeljak: "/rad" });
  await cekaj(s.p, () => document.querySelectorAll("#bel-lista .note").length > 0);
  let e = await ekran(s.p);
  zapisi("B.beleske", "#/predmeti/<id>/rad: tab „Beleške i tok“ aktivan, postojeća beleška prikazana", e.rad && e.tabRad === "page" && e.beleske.includes("Prva beleška A"));
  zapisi("B.hronologija", "hronologija iz odgovora: datum + događaj, redom", e.hron[0] === "01.09.2026. Tužba podneta" && e.hron.length === 2, e.hron.join("|"));
  zapisi("B.hronologija", "HTML u događaju je tekst (ništa se ne izvršava)", e.hron[1].includes("<b onmouseover") && e.xss === null);
  await s.p.click("#bel-dodaj");
  e = await ekran(s.p);
  zapisi("B.beleske", "prazna beleška: lokalna greška, ništa poslato", zahtevi(s, "POST", /beleske$/).length === 0 && /prazna/.test(e.belPoruka || ""));
  await s.p.fill("#bel-tekst", XSS);
  await s.p.click("#bel-dodaj");
  await cekaj(s.p, () => { const n = document.getElementById("bel-poruka"); return !n.hidden && n.dataset.stanje === "uspeh"; });
  e = await ekran(s.p);
  zapisi("B.beleske", "jedan POST sa {sadrzaj} — bez user_id", zahtevi(s, "POST", /beleske$/).length === 1 && upisi[0] && Object.keys(upisi[0]).join() === "sadrzaj");
  zapisi("B.beleske", "posle uspeha beleška je u listi (iz ponovo pročitanog predmeta), kao tekst", e.beleske[0] === XSS && e.xss === null && /dodata/.test(e.belPoruka), e.beleske.join("|").slice(0, 80));
  zapisi("B.beleske", "polje za belešku je prazno posle uspeha", e.belTekst === "");
  await s.p.reload();
  await cekaj(s.p, () => document.querySelectorAll("#bel-lista .note").length > 1);
  e = await ekran(s.p);
  zapisi("B.beleske", "osvežavanje stranice: beleška je i dalje tu", e.beleske.includes(XSS));
  await s.zatvori();
}
for (const [naziv, kuka, stanje] of [["500", { status: 500 }, "nepoznato"], ["prekid", { prekid: true }, "nepoznato"], ["400", { status: 400 }, "greska"]]) {
  const s = await scenario({ pre: (put) => /beleske$/.test(put) ? kuka : null }, { odeljak: "/rad" });
  await cekaj(s.p, () => !document.getElementById("odeljak-rad").hidden);
  await s.p.fill("#bel-tekst", "Ishod " + naziv);
  await s.p.click("#bel-dodaj");
  await cekaj(s.p, () => { const n = document.getElementById("bel-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("B.ishod", `beleška ${naziv}: „${stanje}“, tekst ostaje u polju, ne pojavljuje se u listi`, (e.belPoruka || "").startsWith(stanje + ":") && e.belTekst === "Ishod " + naziv && !e.beleske.includes("Ishod " + naziv), e.belPoruka);
  await s.zatvori();
}
{
  const s = await scenario({ detalj: { izmeniDetalj: (t) => { const x = { ...t }; delete x.beleske; delete x.hronologija; return x; } } }, { odeljak: "/rad" });
  await cekaj(s.p, () => !document.getElementById("odeljak-rad").hidden);
  const e = await ekran(s.p);
  zapisi("B.istina", "odgovor bez beleški/hronologije → „nisu učitane“, nikad „nema beleški“", /nisu učitane/.test(e.belStanje || "") && /nije učitana/.test(e.hronStanje || "") && !/nema beleški|prazna/i.test(e.tekst), `${e.belStanje} / ${e.hronStanje}`);
  await s.zatvori();
}

// ── C: promena predmeta dok upis leti → kasni odgovor se ne slika ───────
{
  const s = await scenario({ pre: (put) => /beleske$/.test(put) ? new Promise(r => setTimeout(r, 1200)) : null }, { odeljak: "/rad" });
  await cekaj(s.p, () => !document.getElementById("odeljak-rad").hidden);
  await s.p.fill("#bel-tekst", "Beleška za predmet 0");
  await s.p.click("#bel-dodaj");
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/rad"; }, s.A[1].id);
  await s.p.waitForTimeout(1700);
  const e = await ekran(s.p);
  zapisi("C.zastarelo", "na drugom predmetu nema poruke ni beleške iz prethodnog upisa", e.hash.endsWith(s.A[1].id + "/rad") && e.belPoruka === null && !e.beleske.includes("Beleška za predmet 0") && e.belTekst === "", `${e.belPoruka} ${e.beleske.join()}`);
  zapisi("C.zastarelo", "dugme za belešku nije ostalo zaključano", await s.p.evaluate(() => !document.getElementById("bel-dodaj").disabled));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (put) => /^\/api\/predmeti\/[^/]+$/.test(put) ? new Promise(r => setTimeout(r, 1200)) : null });
  await s.p.click("#izmena-otvori");
  await s.p.fill("#izm-tuzilac", "Izmena u letu");
  await s.p.click("#izm-sacuvaj");
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id; }, s.A[1].id);
  await s.p.waitForTimeout(1700);
  const e = await ekran(s.p);
  zapisi("C.zastarelo", "izmena u letu + prelazak na drugi predmet: drugi predmet nema poruku ni otvorenu formu", e.naslov === "Predmet kA broj 1" && e.izmPoruka === null && e.pregledPoruka === null && !e.forma, `${e.naslov} ${e.pregledPoruka}`);
  await s.zatvori();
}

{
  // Spor NEUSPEH (500) stiže posle prelaska na drugi predmet: poruka o ishodu ne sme
  // da se pojavi na drugom predmetu.
  const s = await scenario({ pre: (put) => /beleske$/.test(put) ? new Promise(r => setTimeout(() => r({ status: 500 }), 1500)) : null }, { odeljak: "/rad" });
  await cekaj(s.p, () => !document.getElementById("odeljak-rad").hidden);
  await s.p.fill("#bel-tekst", "Spor neuspeh");
  await s.p.click("#bel-dodaj");
  await s.p.waitForTimeout(150);
  await s.p.evaluate((id) => { location.hash = "#/predmeti/" + id + "/rad"; }, s.A[1].id);
  await s.p.waitForTimeout(2000);
  const e = await ekran(s.p);
  zapisi("C.zastarelo", "spor 500 za predmet 0 posle prelaska: drugi predmet nema poruku o ishodu", e.hash.endsWith(s.A[1].id + "/rad") && e.belPoruka === null, String(e.belPoruka));
  await s.zatvori();
}

// ── D: A → B: sve od A nestaje odmah ────────────────────────────────────
{
  const s = await scenario({}, { odeljak: "/rad" });
  await cekaj(s.p, () => document.querySelectorAll("#bel-lista .note").length > 0);
  await s.p.fill("#bel-tekst", "NEPOSLATO-A");
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(500);
  const e = await ekran(s.p);
  zapisi("D.sesija", "A→B: beleške, hronologija i nacrt beleške A nestaju", !e.beleske.length && !e.hron.length && e.belTekst === "" && !/Prva beleška A|Tužba podneta|NEPOSLATO-A/.test(e.tekst), e.beleske.join());
  zapisi("D.sesija", "B na predmetu A vidi „nije dostupan“ (server 404)", /nije dostupan/.test(await s.p.textContent("#predmet-stanje-naslov")));
  await s.zatvori();
}

// ── E: raspored ─────────────────────────────────────────────────────────
for (const [w, h, odeljak] of [[390, 844, "/rad"], [390, 844, ""], [1024, 768, "/rad"]]) {
  const s = await scenario({}, { w, h, odeljak });
  if (!odeljak) await s.p.click("#izmena-otvori");
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("E.raspored", `${w}px ${odeljak || "izmena"}: bez horizontalnog skrola`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0);
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
