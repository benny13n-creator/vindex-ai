// Vindex V2 NG — Task 3: most ka postojećoj prijavi (src/session.js + src/live.js).
// Pokretanje: `node tests/live-session.mjs` (sam podiže fixture server).
//
// Sesija se postavlja u KANONSKI Supabase ključ, a promene stižu kao STVARAN
// `storage` događaj iz drugog taba istog konteksta — tačno kako V1 prijava ili
// odjava u drugom tabu utiču na V2. Izvor podataka je lažan učitavač kroz isti
// šav koji koristi pravi (`window.VxLiveIzvor`): beleži kojim tokenom je pozvan
// i šta je bilo na ekranu u trenutku poziva.
//
// Svi tokeni su izmišljeni. Nijedan zahtev ne ide van 127.0.0.1.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TOKEN_A = "vx-sess-A-token-NE-U-LOG-11aa";
const TOKEN_A2 = "vx-sess-A2-osvezen-NE-U-LOG-22bb";
const TOKEN_B = "vx-sess-B-token-NE-U-LOG-33cc";
const SVI_TOKENI = [TOKEN_A, TOKEN_A2, TOKEN_B];

let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}

const sad = () => Math.floor(Date.now() / 1000);
function sesija(korisnik, token, isticeZaSek = 3600, base64 = false) {
  const o = { access_token: token, refresh_token: "r-" + korisnik, expires_at: sad() + isticeZaSek, user: { id: korisnik, email: korisnik + "@primer.test" } };
  const s = JSON.stringify(o);
  return base64 ? "base64-" + Buffer.from(s, "utf8").toString("base64") : s;
}

const f = await pokreniFixture(async () => false);
const sveKonzole = [];
const BASE = `http://127.0.0.1:${f.port}/?rezim=live`;
const browser = await chromium.launch();

/* Lažan učitavač: po tokenu vraća predmete tog korisnika, sa podesivim
 * kašnjenjem; pri pozivu snima šta je na ekranu. */
const UCITAVAC = `
  window.__pozivi = [];
  window.__kasnjenje = window.__kasnjenje || {};
  window.VxLiveIzvor = {
    ucitaj: async function (token, signal) {
      var ko = token && token.indexOf("-B-") !== -1 ? "B" : "A";
      window.__pozivi.push({
        ko: ko,
        redova: document.querySelectorAll("#rows tr").length,
        tekstA: document.body.innerText.indexOf("Predmet korisnika A") !== -1,
        memorija: window.__vxPredmetaUMemoriji ? window.__vxPredmetaUMemoriji() : -1,
      });
      var ms = window.__kasnjenje[ko] || 0;
      if (ms) await new Promise(function (r) { setTimeout(r, ms); });
      if (signal.aborted) return { ok: false, greska: { kod: "ABORTED" } };
      var p = [1, 2, 3].map(function (i) {
        return { id: ko + i, naziv: "Predmet korisnika " + ko + " #" + i, klijent: "", broj: ko + "-" + i, sud: "", vrsta: "", stanje: "aktivan", izmenjeno: "2026-10-0" + i };
      });
      return { ok: true, predmeti: p, ukupno: p.length };
    }
  };`;

async function kontekst({ pocetna = null, kasnjenje = {} } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.addInitScript(([k, v, kas]) => {
    if (!sessionStorage.getItem("vx-init")) {
      sessionStorage.setItem("vx-init", "1");
      if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v);
    }
    window.__kasnjenje = kas;
  }, [KLJUC, pocetna, kasnjenje]);
  await ctx.addInitScript(UCITAVAC);
  const p = await ctx.newPage();
  const konzola = [], spoljni = [];
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + String(e)));
  p.on("request", q => { if (new URL(q.url()).hostname !== "127.0.0.1") spoljni.push(q.url()); });
  await p.goto(BASE);
  // Drugi tab na istom izvoru (bez učitavanja aplikacije) — odatle V1 menja sesiju.
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  sveKonzole.push(konzola);
  return { ctx, p, drugi, konzola, spoljni, pocetna };
}
const upisiIzDrugog = (drugi, v) => drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => ({
  redova: document.querySelectorAll("#rows tr").length,
  stanje: document.getElementById("empty").hidden ? "registar" : (document.getElementById("empty").dataset.stanje || ""),
  naslov: document.getElementById("empty-title").textContent,
  tekst: document.body.innerText,
  html: document.documentElement.outerHTML,
  url: location.href,
  memorija: window.__vxPredmetaUMemoriji(),
  pozivi: window.__pozivi.slice(),
  sesija: window.VxSesija.stanje(),
  pretraga: document.getElementById("pretraga").value,
  kljucevi: Object.keys(localStorage).sort(),
}));
const sacekaj = (p, fn, arg, ms = 4000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);

// ── 1. Bez sesije ────────────────────────────────────────────────────────
{
  const k = await kontekst({ pocetna: null });
  const e = await ekran(k.p);
  zapisi("bez-sesije", "stanje je „bez-prijave“", e.stanje === "bez-prijave", e.stanje);
  zapisi("bez-sesije", "učitavač NIJE pozvan (nema zahteva bez tokena)", e.pozivi.length === 0);
  zapisi("bez-sesije", "nijedan red, ne tvrdi „Nema aktivnih predmeta“", e.redova === 0 && !/Nema aktivnih/.test(e.naslov), e.naslov);
  await k.ctx.close();
}

// ── 2. Sesija A → token A ────────────────────────────────────────────────
{
  const k = await kontekst({ pocetna: sesija("korisnik-A", TOKEN_A) });
  await sacekaj(k.p, () => document.querySelectorAll("#rows tr").length === 3);
  const e = await ekran(k.p);
  const tokeniUPozivu = await k.p.evaluate(() => window.__pozivi.length);
  zapisi("sesija-A", "učitavač pozvan tačno jednom", tokeniUPozivu === 1, `${tokeniUPozivu}`);
  zapisi("sesija-A", "prikazani su predmeti korisnika A", e.redova === 3 && e.tekst.includes("Predmet korisnika A #1"));
  zapisi("sesija-A", "VxSesija.stanje() ne sadrži token", !JSON.stringify(e.sesija).includes(TOKEN_A) && e.sesija.stanje === "prijavljen", JSON.stringify(e.sesija));
  zapisi("sesija-A", "token nije u DOM-u ni u URL-u", !e.html.includes(TOKEN_A) && !e.url.includes(TOKEN_A));
  zapisi("sesija-A", "nijedan novi localStorage ključ (token se ne kopira)", e.kljucevi.every(x => [KLJUC, "vx-ng-tema", "vx-ng-nav"].includes(x)), e.kljucevi.join(","));

  // ── 3. Odjava u drugom tabu ────────────────────────────────────────────
  const pre = await k.p.evaluate((kl) => localStorage.getItem(kl), KLJUC);
  await upisiIzDrugog(k.drugi, null);
  const stiglo = await sacekaj(k.p, () => document.getElementById("empty").dataset.stanje === "bez-prijave" && !document.getElementById("empty").hidden);
  const o = await ekran(k.p);
  zapisi("odjava", "storage događaj → stanje „bez-prijave“", stiglo, o.stanje);
  zapisi("odjava", "nijedan red na ekranu", o.redova === 0);
  zapisi("odjava", "nijedan predmet A u tekstu strane", !o.tekst.includes("Predmet korisnika A"));
  zapisi("odjava", "nijedan predmet u memoriji ekrana", o.memorija === 0, `${o.memorija}`);
  zapisi("odjava", "VxSesija.token() je null", await k.p.evaluate(() => window.VxSesija.token() === null));
  zapisi("odjava", "posle odjave nema novog učitavanja", o.pozivi.length === 1, `${o.pozivi.length}`);
  zapisi("odjava", "V2 nije pisao u kanonski zapis dok je bio prijavljen", pre === k.pocetna);
  zapisi("bez-mreze", "nijedan zahtev van 127.0.0.1 (nema Supabase refresh-a)", k.spoljni.length === 0, k.spoljni.join(","));
  await k.ctx.close();
}

// ── 4. A → B: podaci A se brišu PRE učitavanja B ────────────────────────
{
  const k = await kontekst({ pocetna: sesija("korisnik-A", TOKEN_A), kasnjenje: { B: 800 } });
  await sacekaj(k.p, () => document.querySelectorAll("#rows tr").length === 3);
  await k.p.fill("#pretraga", "korisnika A #2");
  const prePromene = await ekran(k.p);
  zapisi("A→B", "pre promene: pretraga nad A daje 1 red", prePromene.redova === 1, `${prePromene.redova}`);
  await upisiIzDrugog(k.drugi, sesija("korisnik-B", TOKEN_B));
  await sacekaj(k.p, () => window.__pozivi.length === 2);
  const tokom = await ekran(k.p);
  const pozivB = tokom.pozivi[1];
  zapisi("A→B", "učitavač pozvan za B", pozivB && pozivB.ko === "B");
  zapisi("A→B", "u trenutku poziva za B: 0 redova na ekranu", pozivB && pozivB.redova === 0, JSON.stringify(pozivB));
  zapisi("A→B", "u trenutku poziva za B: nijedan predmet A u tekstu", pozivB && pozivB.tekstA === false);
  zapisi("A→B", "u trenutku poziva za B: 0 predmeta u memoriji", pozivB && pozivB.memorija === 0);
  zapisi("A→B", "dok B učitava: stanje „ucitavanje“, nema A", tokom.stanje === "ucitavanje" && !tokom.tekst.includes("Predmet korisnika A"), tokom.stanje);
  zapisi("A→B", "pretraga korisnika A je obrisana", tokom.pretraga === "", JSON.stringify(tokom.pretraga));
  await sacekaj(k.p, () => document.querySelectorAll("#rows tr").length === 3);
  const posle = await ekran(k.p);
  zapisi("A→B", "posle: samo predmeti B", posle.redova === 3 && posle.tekst.includes("Predmet korisnika B #1") && !posle.tekst.includes("Predmet korisnika A"));
  await k.ctx.close();
}

// ── 5. Osvežen token ISTOG korisnika ne briše podatke ───────────────────
{
  const k = await kontekst({ pocetna: sesija("korisnik-A", TOKEN_A) });
  await sacekaj(k.p, () => document.querySelectorAll("#rows tr").length === 3);
  await upisiIzDrugog(k.drugi, sesija("korisnik-A", TOKEN_A2));
  await k.p.waitForTimeout(400);
  const e = await ekran(k.p);
  zapisi("osvezen-token", "isti korisnik: podaci ostaju, bez novog učitavanja", e.redova === 3 && e.pozivi.length === 1, `redova=${e.redova} poziva=${e.pozivi.length}`);
  zapisi("osvezen-token", "novi token se koristi (VxSesija.token)", await k.p.evaluate((t) => window.VxSesija.token() === t, TOKEN_A2));
  await k.ctx.close();
}

// ── 6. Istekla sesija ────────────────────────────────────────────────────
{
  const k = await kontekst({ pocetna: sesija("korisnik-A", TOKEN_A, -60) });
  const e = await ekran(k.p);
  zapisi("istekla", "istekla sesija → stanje „istekla“", e.stanje === "istekla", e.stanje);
  zapisi("istekla", "nije prazna lista („Nema aktivnih predmeta“)", !/Nema aktivnih/.test(e.naslov), e.naslov);
  zapisi("istekla", "učitavač nije pozvan, nema mreže", e.pozivi.length === 0 && k.spoljni.length === 0);
  await k.ctx.close();
}

// ── 7. Sesija istekne DOK je ekran otvoren ──────────────────────────────
{
  const k = await kontekst({ pocetna: sesija("korisnik-A", TOKEN_A, 31) });
  await sacekaj(k.p, () => document.querySelectorAll("#rows tr").length === 3);
  const istekla = await sacekaj(k.p, () => document.getElementById("empty").dataset.stanje === "istekla" && !document.getElementById("empty").hidden, null, 6000);
  const e = await ekran(k.p);
  zapisi("istek-tokom", "posle isteka stanje „istekla“", istekla, e.stanje);
  zapisi("istek-tokom", "predmeti A uklonjeni sa ekrana i iz memorije", e.redova === 0 && e.memorija === 0 && !e.tekst.includes("Predmet korisnika A"));
  await k.ctx.close();
}

// ── 8. Neispravni zapisi sesije ─────────────────────────────────────────
for (const [naziv, vrednost, ocekivano] of [
  ["base64- zapis (supabase-js format)", sesija("korisnik-A", TOKEN_A, 3600, true), "registar"],
  ["pokvaren JSON", "{nije json", "greska-sesije"],
  ["bez access_token", JSON.stringify({ user: { id: "x" }, expires_at: sad() + 3600 }), "greska-sesije"],
  ["bez user.id", JSON.stringify({ access_token: TOKEN_A, expires_at: sad() + 3600 }), "greska-sesije"],
]) {
  const k = await kontekst({ pocetna: vrednost });
  await k.p.waitForTimeout(300);
  const e = await ekran(k.p);
  const ok = ocekivano === "registar" ? (e.stanje === "registar" && e.redova === 3) : (e.stanje === ocekivano && e.pozivi.length === 0 && e.redova === 0);
  zapisi("zapis", `${naziv} → ${ocekivano}`, ok, `${e.stanje} poziva=${e.pozivi.length}`);
  await k.ctx.close();
}

await browser.close();
await f.zatvori();

// ── Token nigde u izlazu ────────────────────────────────────────────────
const konzolaTekst = sveKonzole.flat().join("\n");
zapisi("token", "nijedan token u konzoli nijedne stranice", !SVI_TOKENI.some(t => konzolaTekst.includes(t)));
zapisi("greske", "nijedna JS greška stranice", !/PAGEERROR/.test(konzolaTekst), konzolaTekst.split("\n").filter(l => /PAGEERROR/.test(l)).slice(0, 2).join(" | "));
zapisi("token", "nijedan token u izlazu testa", !SVI_TOKENI.some(t => izlaz.join("\n").includes(t)));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
