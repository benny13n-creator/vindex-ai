// Vindex V2 NG — Task 6: izolacija LIVE podataka i zakasneli odgovori.
// Pokretanje: `node tests/live-isolation.mjs` (sam podiže fixture).
//
// Dva korisnika (A, B) sa različitim tokenima i predmetima na fixture-u koji
// ponavlja ugovor api.py. Promena sesije stiže kao STVARAN `storage` događaj iz
// drugog taba. Svaki scenario proverava da prethodni pravni podaci NIKAD ne
// ostanu prikazani kao trenutni.
//
//  A. zakasneli A posle B          E. neispravan odgovor na 2. strani
//  B. odjava tokom učitavanja      F. HTML/script u nazivu
//  C. dva brza osvežavanja         G. 401 posle uspešnog učitavanja
//  D. prekid na 2. strani          H. promena sesije dok pretraga ima rezultat
//  + zaštita generacijom NEZAVISNO od abort-a (izvor koji ignoriše signal)
//  + ugovor zakupca: frontend nikad ne šalje user_id i ne filtrira po vlasniku

import { chromium } from "playwright";
import { readFile } from "node:fs/promises";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-iso-A-token-NE-U-LOG-66ff", TB = "vx-iso-B-token-NE-U-LOG-77aa";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id, email: id + "@primer.test" } });
const SES_A = ses("korisnik-A", TA), SES_B = ses("korisnik-B", TB);
const pauza = (ms) => new Promise(r => setTimeout(r, ms));

const browser = await chromium.launch();

function korisnici(nA = 12, nB = 12, opcA = {}) {
  return {
    [TA]: { id: "korisnik-A", predmeti: napraviPredmete("korisnik-A", nA, { naziv: i => `Predmet A ${i}`, ...opcA }) },
    [TB]: { id: "korisnik-B", predmeti: napraviPredmete("korisnik-B", nB, { naziv: i => `Predmet B ${i}` }) },
  };
}

async function scenario({ k = korisnici(), kuke = {}, pocetna = SES_A, initSkripta = null } = {}) {
  const f = await pokreniFixture(predmetiRuta(k, kuke));
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.addInitScript(([kl, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(kl); else localStorage.setItem(kl, v); }
  }, [KLJUC, pocetna]);
  if (initSkripta) await ctx.addInitScript(initSkripta);
  const p = await ctx.newPage();
  const greske = [];
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live`);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, ctx, p, drugi, greske };
}
const postavi = (s, v) => s.drugi.evaluate(([kl, v]) => { if (v === null) localStorage.removeItem(kl); else localStorage.setItem(kl, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => ({
  ids: Array.from(document.querySelectorAll("#rows tr")).map(t => t.dataset.id),
  stanje: document.getElementById("empty").hidden ? "registar" : (document.getElementById("empty").dataset.stanje || ""),
  tekst: document.body.innerText,
  memorija: window.__vxPredmetaUMemoriji(),
  pretraga: document.getElementById("pretraga").value,
}));
const imaA = (e) => e.ids.some(id => id.startsWith("korisnik-A")) || /Predmet A \d/.test(e.tekst);
const imaB = (e) => e.ids.some(id => id.startsWith("korisnik-B")) || /Predmet B \d/.test(e.tekst);
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
async function zatvori(s) { await s.ctx.close(); await s.f.zatvori(); }

// ── A. Zakasneli A posle B ───────────────────────────────────────────────
{
  const s = await scenario({ kuke: { preStrane: (off, ko) => (ko === "korisnik-A" ? pauza(1500) : null) } });
  await cekaj(s.p, () => window.__vxPredmetaUMemoriji && document.getElementById("empty").dataset.stanje === "ucitavanje");
  await postavi(s, SES_B);
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 12);
  const posleB = await ekran(s.p);
  zapisi("A.zakasneli", "B je prikazan", imaB(posleB) && !imaA(posleB));
  await pauza(2000); // A je sada odgovorio (ili je otkazan)
  const kasnije = await ekran(s.p);
  zapisi("A.zakasneli", "ekran OSTAJE B posle zakasnelog A", imaB(kasnije) && !imaA(kasnije) && kasnije.ids.length === 12, `${kasnije.ids.slice(0, 2).join(",")}`);
  zapisi("A.zakasneli", "u memoriji nema A", kasnije.memorija === 12 && !imaA(kasnije));
  await zatvori(s);
}

// ── Zaštita generacijom NEZAVISNO od abort-a ────────────────────────────
// Izvor namerno ignoriše signal i vraća A kasno, posle B. Bez provere
// generacije/identiteta A bi pregazio B.
{
  const IZVOR = `
    window.VxLiveIzvor = { ucitaj: async function (token) {
      var ko = token.indexOf("-A-") !== -1 ? "A" : "B";
      await new Promise(function (r) { setTimeout(r, ko === "A" ? 1500 : 100); });
      var p = [0,1,2].map(function (i) { return { id: "korisnik-" + ko + "-" + i, naziv: "Predmet " + ko + " " + i, broj: "", stranke: [], klijent: "", sud: "", vrsta: "", stanje: "aktivan", izmenjeno: "" }; });
      return { ok: true, predmeti: p, ukupno: p.length };
    } };`;
  const s = await scenario({ initSkripta: IZVOR });
  await pauza(200);
  await postavi(s, SES_B);
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 3);
  await pauza(1800);
  const e = await ekran(s.p);
  zapisi("generacija", "izvor koji ignoriše abort: zakasneli A ne pregazi B", imaB(e) && !imaA(e), e.ids.join(","));
  await zatvori(s);
}

// ── Promena sesije BEZ `storage` događaja (isti tab) tokom učitavanja ───
// Rezultat A stiže kada je zapis već B, a događaj nije stigao: sesija se mora
// ponovo pročitati pre primene rezultata.
{
  const s = await scenario({ kuke: { preStrane: (off, ko) => (ko === "korisnik-A" ? pauza(900) : null) } });
  await cekaj(s.p, () => document.getElementById("empty").dataset.stanje === "ucitavanje");
  await s.p.evaluate(([kl, v]) => localStorage.setItem(kl, v), [KLJUC, SES_B]); // isti tab: nema storage događaja
  await pauza(1500);
  const e = await ekran(s.p);
  zapisi("bez-dogadjaja", "A (učitan pod starom sesijom) NIJE prikazan", !imaA(e), e.ids.slice(0, 2).join(","));
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 12);
  const posle = await ekran(s.p);
  zapisi("bez-dogadjaja", "umesto toga učitan je B", imaB(posle) && !imaA(posle) && posle.ids.length === 12, `${posle.ids.length}`);
  await zatvori(s);
}

// ── B. Odjava tokom učitavanja ───────────────────────────────────────────
{
  const s = await scenario({ kuke: { preStrane: () => pauza(1200) } });
  await cekaj(s.p, () => document.getElementById("empty").dataset.stanje === "ucitavanje");
  await postavi(s, null);
  await pauza(1800);
  const e = await ekran(s.p);
  zapisi("B.odjava-tokom", "stanje „bez-prijave“ i posle zakasnelog odgovora", e.stanje === "bez-prijave", e.stanje);
  zapisi("B.odjava-tokom", "nijedan predmet na ekranu ni u memoriji", e.ids.length === 0 && e.memorija === 0 && !imaA(e));
  await zatvori(s);
}

// ── C. Dva brza osvežavanja ──────────────────────────────────────────────
{
  let n = 0;
  const s = await scenario({ kuke: { preStrane: () => { n++; return pauza(n === 1 ? 50 : 900); } } });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 12);
  n = 0;
  const pre = s.f.zahtevi.length;
  await s.p.evaluate(() => { window.__vxLiveOsvezi(); window.__vxLiveOsvezi(); });
  await cekaj(s.p, () => document.getElementById("empty").dataset.stanje === "ucitavanje" || document.querySelectorAll("#rows tr").length === 12);
  await pauza(1500);
  const e = await ekran(s.p);
  zapisi("C.brzo-osvezavanje", "konačno: tačno 12 predmeta A, bez duplikata", e.ids.length === 12 && new Set(e.ids).size === 12 && imaA(e), `${e.ids.length}`);
  zapisi("C.brzo-osvezavanje", "najviše dva nova zahteva (prvi otkazan, drugi važeći)", s.f.zahtevi.length - pre <= 2, `${s.f.zahtevi.length - pre}`);
  await zatvori(s);
}

// ── D. Prekid na 2. strani ───────────────────────────────────────────────
{
  const s = await scenario({ k: korisnici(1037, 12), kuke: { preStrane: (off) => (off === 500 ? pauza(1500) : null) } });
  await cekaj(s.p, () => true);
  await pauza(500); // strana 0 je stigla, strana 500 čeka
  const pre = s.f.zahtevi.map(z => z.parametri.offset);
  await postavi(s, null);
  await pauza(2200);
  const e = await ekran(s.p);
  const offseti = s.f.zahtevi.map(z => z.parametri.offset);
  zapisi("D.prekid-strane", "pre odjave: tražene strane 0 i 500", pre.join(",") === "0,500", pre.join(","));
  zapisi("D.prekid-strane", "strana 1000 NIKAD nije tražena", !offseti.includes("1000"), offseti.join(","));
  zapisi("D.prekid-strane", "nijedna delimična lista (strana 0) nije prikazana", e.ids.length === 0 && e.memorija === 0 && e.stanje === "bez-prijave", `${e.stanje} ${e.ids.length}`);
  await zatvori(s);
}

// ── E. Neispravan odgovor na 2. strani ───────────────────────────────────
{
  const s = await scenario({ k: korisnici(1037, 12), kuke: { izmeniOdgovor: (t, off) => (off === 500 ? { predmeti: "nije niz" } : t) } });
  await cekaj(s.p, () => /^greska/.test(document.getElementById("empty").dataset.stanje || ""));
  const e = await ekran(s.p);
  zapisi("E.neispravno", "greška, a prva strana NIJE prikazana kao lista", /^greska/.test(e.stanje) && e.ids.length === 0 && e.memorija === 0, `${e.stanje} ${e.ids.length}`);
  await zatvori(s);
}

// ── F. HTML/script u nazivu ──────────────────────────────────────────────
{
  const N = '<script>window.__xss=1</script><img src=x onerror="window.__xss=2">';
  const s = await scenario({ k: korisnici(2, 2, { naziv: i => (i ? "Obican" : N) }) });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 2);
  const r = await s.p.evaluate(() => ({ el: document.querySelectorAll("#rows script, #rows img").length, xss: window.__xss }));
  zapisi("F.html", "naziv sa HTML-om je tekst, ništa se ne izvršava", r.el === 0 && r.xss === undefined, JSON.stringify(r));
  await zatvori(s);
}

// ── G. 401 posle uspešnog učitavanja ─────────────────────────────────────
{
  const k = korisnici();
  const s = await scenario({ k });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 12);
  delete k[TA]; // server opozvao token
  await s.p.evaluate(() => window.__vxLiveOsvezi());
  await cekaj(s.p, () => document.getElementById("empty").dataset.stanje === "greska-prijava");
  const e = await ekran(s.p);
  zapisi("G.401-posle-uspeha", "stanje „greska-prijava“", e.stanje === "greska-prijava", e.stanje);
  zapisi("G.401-posle-uspeha", "prethodni predmeti NISU prikazani ni u memoriji", e.ids.length === 0 && e.memorija === 0 && !imaA(e));
  await zatvori(s);
}

// ── H. Promena sesije dok pretraga ima rezultat ─────────────────────────
{
  const s = await scenario({ kuke: { preStrane: (off, ko) => (ko === "korisnik-B" ? pauza(700) : null) } });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 12);
  await s.p.fill("#pretraga", "Predmet A 3");
  const pre = await ekran(s.p);
  zapisi("H.pretraga", "pre: pretraga nad A daje 1 red", pre.ids.length === 1, `${pre.ids.length}`);
  await postavi(s, SES_B);
  await cekaj(s.p, () => document.getElementById("empty").dataset.stanje === "ucitavanje");
  const tokom = await ekran(s.p);
  zapisi("H.pretraga", "tokom učitavanja B: nema A, pretraga obrisana", !imaA(tokom) && tokom.pretraga === "" && tokom.memorija === 0, `${tokom.pretraga}`);
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length === 12);
  const posle = await ekran(s.p);
  zapisi("H.pretraga", "posle: svih 12 predmeta B, bez filtera iz sesije A", posle.ids.length === 12 && imaB(posle) && !imaA(posle));
  await zatvori(s);
}

// ── Ugovor zakupca ───────────────────────────────────────────────────────
{
  const s = await scenario({ k: korisnici(1037, 12) });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 1000, null, 15000);
  const z = s.f.zahtevi;
  const zabranjeni = ["user_id", "userid", "uid", "owner_id", "korisnik", "vlasnik"];
  zapisi("zakupac", "nijedan GET /api/predmeti ne šalje identitet vlasnika kao parametar", z.length > 0 && z.every(x => Object.keys(x.parametri).every(p => !zabranjeni.includes(p.toLowerCase()))), JSON.stringify(z.map(x => x.parametri)).slice(0, 120));
  zapisi("zakupac", "identitet ide samo kroz Authorization: Bearer", z.every(x => x.auth === `Bearer ${TA}`));
  await zatvori(s);
}
{
  // Server je granica: ako bi server vratio red drugog vlasnika, frontend ga NE
  // filtrira „za svaki slučaj“ — ne odlučuje o pripadnosti. (Server to ne radi;
  // ovo dokazuje samo da frontend nema sopstvenu, lažnu granicu.)
  const k = korisnici(3, 0);
  const s = await scenario({ k, kuke: { izmeniOdgovor: (t) => ({ ...t, predmeti: t.predmeti.map((p, i) => (i === 0 ? { ...p, user_id: "neko-drugi" } : p)) }) } });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  const e = await ekran(s.p);
  zapisi("zakupac", "frontend ne filtrira po `user_id` (ne glumi bezbednosnu granicu)", e.ids.length === 3, `${e.ids.length}`);
  await zatvori(s);
}
{
  const izvori = await Promise.all(["src/predmeti.js", "src/app.js", "src/live.js"].map(f => readFile(new URL("../" + f, import.meta.url), "utf8")));
  const kod = izvori.map(t => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "")).join("\n");
  zapisi("zakupac", "LIVE kod ne čita `user_id` iz podataka niti ga gradi u zahtevu", !/user_id/.test(kod));
  zapisi("zakupac", "predmeti.js gradi parametre samo od view/status/limit/offset", /parametri:\s*\{\s*view:\s*"summary",\s*status:\s*"aktivan",\s*limit:\s*STRANA,\s*offset:\s*offset\s*\}/.test(izvori[0]));
}

await browser.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
