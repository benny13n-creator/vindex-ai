// Vindex V2 NG — NS005 Task 2: nov predmet (CAP-004).
// Pokretanje: `node tests/live-nov-predmet.mjs` (fixture na 127.0.0.1; ništa spolja).
//
// Ugovor POST /api/predmeti emulira tests/fixtures/pisanje-api.mjs (vlasnik iz
// tokena, 400 bez naziva, 409 za isti naziv u 5 s). Backend isti ugovor dokazuje
// nad STVARNOM rutom: tests/test_ns005_t2_nov_predmet.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { novPredmetRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-nov-A-NE-U-LOG-61", TB = "vx-nov-B-NE-U-LOG-72";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const XSS = '<img src=x onerror="window.__xss=1">Jović<script>window.__xss=2</script>';

const browser = await chromium.launch();
const konzola = [], sviZahtevi = [], sviSpoljni = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", put = "/?rezim=live#/predmeti/nov", w = 1440, h = 900 } = {}) {
  const KOR = { [TA]: { id: "kA", predmeti: napraviPredmete("kA", 2) }, [TB]: { id: "kB", predmeti: napraviPredmete("kB", 1, { naziv: () => "TAJNI B" }) } };
  const f = await pokreniFixture(kombinuj(novPredmetRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
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
  return { f, KOR, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const n = document.getElementById("nov-poruka");
  return { hash: location.hash, pogled: document.documentElement.dataset.pogled || "registar", forma: vid("nov-forma"), link: vid("nov-predmet-link"),
    poruka: vid("nov-poruka") ? n.dataset.stanje : null, porukaTekst: n.textContent, naziv: document.getElementById("nov-naziv").value,
    opis: document.getElementById("nov-opis").value, dugme: document.getElementById("nov-posalji").disabled,
    naslovPredmeta: document.getElementById("predmet-naslov").textContent, xss: window.__xss || null, tekst: document.body.innerText };
});
const postovi = (s) => s.f.zahtevi.filter(z => z.putanja === "/api/predmeti" && z.metod === "POST");
async function popuni(p, { naziv = "Jović protiv Petrovića", tip = "", opis = "" } = {}) {
  await p.fill("#nov-naziv", naziv); await p.fill("#nov-tip", tip); await p.fill("#nov-opis", opis);
}

// ── A: ulaz je vidljiv samo u LIVE i samo prijavljenom ──────────────────
{
  const s = await scenario({}, { put: "/?rezim=live" });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  let e = await ekran(s.p);
  zapisi("A.ulaz", "LIVE + prijava: „Nov predmet“ je vidljiv u registru", e.link && e.pogled === "registar");
  await s.p.click("#nov-predmet-link");
  await cekaj(s.p, () => location.hash === "#/predmeti/nov" && !document.getElementById("nov-forma").closest("[hidden]") && document.activeElement && document.activeElement.id === "nov-naziv");
  e = await ekran(s.p);
  zapisi("A.ulaz", "klik vodi na #/predmeti/nov: forma vidljiva, registar sakriven", e.forma && e.pogled === "nov" && !e.link, e.hash);
  const fokus = await s.p.evaluate(() => document.activeElement && document.activeElement.id);
  zapisi("A.ulaz", "fokus je na nazivu", fokus === "nov-naziv", fokus);
  await s.zatvori();
}
{
  const s = await scenario({}, { put: "/" });
  const e = await ekran(s.p);
  zapisi("A.ulaz", "DEMO: „Nov predmet“ ne postoji na ekranu", !e.link);
  await s.zatvori();
}
{
  const s = await scenario({}, { token: null });
  await s.p.waitForTimeout(400);
  const e = await ekran(s.p);
  zapisi("A.ulaz", "bez prijave: link sakriven", !e.link);
  await popuni(s.p); await s.p.click("#nov-posalji");
  await cekaj(s.p, () => !document.getElementById("nov-poruka").hidden);
  const e2 = await ekran(s.p);
  zapisi("A.ulaz", "bez prijave: slanje ne šalje zahtev i kaže da niste prijavljeni", postovi(s).length === 0 && e2.poruka === "greska" && /prijavljen/i.test(e2.porukaTekst), e2.porukaTekst);
  await s.zatvori();
}

// ── B: uspeh → otvara stvarno kreiran predmet ───────────────────────────
{
  const upisi = [];
  const s = await scenario({ upisano: (p, telo) => upisi.push({ p, telo }) });
  await cekaj(s.p, () => !document.getElementById("nov-forma").closest("[hidden]"));
  await s.p.click("#nov-posalji");
  let e = await ekran(s.p);
  zapisi("B.forma", "prazan naziv: greška pri polju, ništa poslato", postovi(s).length === 0 && e.poruka === "greska" && /obavezan/.test(e.porukaTekst));
  zapisi("B.forma", "polje naziva označeno aria-invalid", await s.p.getAttribute("#nov-naziv", "aria-invalid") === "true");
  await popuni(s.p, { naziv: XSS, tip: "Radni spor", opis: "Otkaz ugovora o radu" });
  await s.p.click("#nov-posalji");
  await cekaj(s.p, () => /^#\/predmeti\/kA-nov1$/.test(location.hash) && document.getElementById("predmet-naslov").textContent.length > 0);
  e = await ekran(s.p);
  const z = postovi(s)[0] || {};
  zapisi("B.uspeh", "tačno jedan POST /api/predmeti sa tokenom A", postovi(s).length === 1 && z.auth === "Bearer " + TA);
  zapisi("B.uspeh", "telo: naziv, tip (ključ baze radni_spor), opis — bez user_id", upisi[0] && upisi[0].telo.naziv === XSS && upisi[0].telo.tip === "radni_spor" && upisi[0].telo.opis === "Otkaz ugovora o radu" && !("user_id" in upisi[0].telo), JSON.stringify(upisi[0] && upisi[0].telo).slice(0, 120));
  zapisi("B.uspeh", "posle uspeha otvara se detalj NOVOG predmeta (#/predmeti/<id iz odgovora>)", e.hash === "#/predmeti/kA-nov1" && e.pogled === "predmet", e.hash);
  zapisi("B.uspeh", "naziv sa HTML-om se prikazuje kao tekst, ništa se ne izvršava", e.naslovPredmeta === XSS && e.xss === null);
  await s.p.click("#predmet-nazad");
  await cekaj(s.p, () => document.querySelector('#rows tr[data-id="kA-nov1"]') !== null);
  zapisi("B.uspeh", "registar je osvežen i sadrži nov predmet", await s.p.evaluate(() => !!document.querySelector('#rows tr[data-id="kA-nov1"]')));
  await s.p.goto(s.p.url().replace(/#.*$/, "") + "#/predmeti/nov");
  await cekaj(s.p, () => !document.getElementById("nov-forma").closest("[hidden]"));
  e = await ekran(s.p);
  zapisi("B.uspeh", "ponovni ulaz u formu: prazna forma, bez stare poruke", e.naziv === "" && e.opis === "" && e.poruka === null);
  // B ne vidi predmet koji je A upravo otvorio
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => { location.hash = "#/predmeti/kA-nov1"; });
  await cekaj(s.p, () => document.getElementById("predmet-stanje-naslov").textContent === "Predmet nije dostupan");
  e = await ekran(s.p);
  zapisi("B.izolacija", "korisnik B ne vidi predmet koji je A otvorio (404 → „nije dostupan“)", /nije dostupan/.test(await s.p.textContent("#predmet-stanje-naslov")) && !e.tekst.includes("Jović"));
  await s.zatvori();
}

// ── C: dupli klik / nepoznat ishod / odbijanje ──────────────────────────
{
  const s = await scenario({ pre: () => new Promise(r => setTimeout(r, 900)) });
  await cekaj(s.p, () => !document.getElementById("nov-forma").closest("[hidden]"));
  await popuni(s.p, { naziv: "Dupli klik" });
  await s.p.evaluate(() => { const b = document.getElementById("nov-posalji"); b.click(); b.click(); document.getElementById("nov-forma").requestSubmit(); });
  await s.p.keyboard.press("Enter");
  const tokom = await ekran(s.p);
  zapisi("C.dupli", "tokom slanja dugme je zaključano („Otvaranje…“)", tokom.dugme === true);
  await cekaj(s.p, () => /^#\/predmeti\/kA-nov1$/.test(location.hash));
  zapisi("C.dupli", "višestruki klik/Enter → tačno jedan POST", postovi(s).length === 1, String(postovi(s).length));
  await s.zatvori();
}
for (const [naziv, kuke, stanje, provera] of [
  ["500 posle slanja", { pre: () => ({ status: 500 }) }, "nepoznato", t => /nije poznat/.test(t) && /možda otvoren/.test(t) && !/nije otvoren|nije sa[cč]uvan/i.test(t)],
  ["prekid veze posle slanja", { pre: () => ({ prekid: true }) }, "nepoznato", t => /nije poznat/.test(t) && !/nije otvoren|nije sa[cč]uvan/i.test(t)],
  ["2xx bez id-a (neispravan odgovor)", { izmeniOdgovor: () => "Created" }, "nepoznato", t => /otvoren/.test(t) && /ne šaljite ponovo/.test(t)],
  ["409 isti naziv", { pre: () => ({ status: 409 }) }, "greska", t => /upravo otvoren/.test(t)],
  ["400 odbijeno", { pre: () => ({ status: 400 }) }, "greska", t => /nije otvoren/.test(t)],
  ["401 prijava nevažeća", { pre: () => ({ status: 401 }) }, "greska", t => /Prijava/.test(t) && /nije otvoren/.test(t)],
  ["429", { pre: () => ({ status: 429 }) }, "greska", t => /Previše/.test(t)],
]) {
  const s = await scenario(kuke);
  await cekaj(s.p, () => !document.getElementById("nov-forma").closest("[hidden]"));
  await popuni(s.p, { naziv: "Ishod " + naziv, opis: "zadrži me" });
  await s.p.click("#nov-posalji");
  await cekaj(s.p, () => { const n = document.getElementById("nov-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("C.ishod", `${naziv}: stanje „${stanje}“, poruka tačna`, e.poruka === stanje && provera(e.porukaTekst), `${e.poruka}: ${e.porukaTekst.slice(0, 90)}`);
  zapisi("C.ishod", `${naziv}: ostaje na formi, unos sačuvan, dugme ponovo aktivno, bez ponavljanja`, e.hash === "#/predmeti/nov" && e.naziv === "Ishod " + naziv && e.opis === "zadrži me" && !e.dugme && postovi(s).length <= 2, `${postovi(s).length} POST`);
  await s.zatvori();
}

// ── D: promena sesije dok zahtev leti ───────────────────────────────────
{
  const s = await scenario({ pre: () => new Promise(r => setTimeout(r, 1200)) });
  await cekaj(s.p, () => !document.getElementById("nov-forma").closest("[hidden]"));
  await popuni(s.p, { naziv: "TAJNO-A-u-letu", opis: "TAJNI-OPIS-A" });
  await s.p.click("#nov-posalji");
  await s.p.waitForTimeout(150);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1800);
  const e = await ekran(s.p);
  zapisi("D.sesija", "A→B tokom slanja: forma očišćena (ništa od A na ekranu)", e.naziv === "" && e.opis === "" && !e.tekst.includes("TAJNO-A") && !e.tekst.includes("TAJNI-OPIS-A"), e.naziv);
  zapisi("D.sesija", "kasni odgovor za A ne navigira korisnika B u predmet A", e.hash === "#/predmeti/nov", e.hash);
  zapisi("D.sesija", "nijedna poruka o ishodu A ne ostaje kod B", e.poruka === null, String(e.poruka));
  await s.zatvori();
}

// ── E: uski ekran ───────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await cekaj(s.p, () => !document.getElementById("nov-forma").closest("[hidden]"));
  const m = await s.p.evaluate(() => ({ sirina: document.documentElement.scrollWidth, vp: innerWidth,
    dugme: (() => { const r = document.getElementById("nov-posalji").getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth; })() }));
  zapisi("E.raspored", `${w}px: bez horizontalnog skrola, dugme vidljivo`, m.sirina <= m.vp && m.dugme, `${m.sirina}/${m.vp}`);
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0, sviSpoljni.slice(0, 2).join(","));
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 160));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
