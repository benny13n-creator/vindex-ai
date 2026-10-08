// Vindex V2 NG — NS005 Task 4: klijenti predmeta + provera sukoba interesa (CAP-030/031/032/188).
// Pokretanje: `node tests/live-klijenti.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend isti ugovor dokazuje nad STVARNIM rutama: tests/test_ns005_t4_klijenti_coi.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { klijentiRuta, coiRuta, vezaRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-kl-A-NE-U-LOG-13", TB = "vx-kl-B-NE-U-LOG-24";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const XSS = '<img src=x onerror="window.__xss=1">Mila';

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", w = 1440, h = 900 } = {}) {
  const A = napraviPredmete("kA", 3, { tuzilac: i => ["Ana Jović", "Marko Marković", "Nikola Nikolić"][i], tuzeni: i => ["Petar Petrović", "Omega doo", "Zatvoreni Zoran"][i],
                                       status: i => i === 2 ? "zatvoren" : "aktivan", naziv: i => i === 1 ? '<b onclick="window.__xss=2">Marković spor</b>' : `Predmet A ${i}` });
  const B = napraviPredmete("kB", 1, { naziv: () => "TAJNI B", tuzilac: () => "Ana Bjelić" });
  const KOR = {
    [TA]: { id: "kA", predmeti: A, klijenti: {}, kartoteka: [
      { id: "kl-A1", user_id: "kA", ime: "Ana", prezime: "Jović", firma: "", email: "ana@primer.rs", tip: "fizicko_lice", jmbg_encrypted: "ENC-A" },
      { id: "kl-A2", user_id: "kA", ime: "Marko", prezime: "Marković", firma: "", email: "", tip: "fizicko_lice" },
      { id: "kl-A3", user_id: "kA", ime: "Zatvoreni", prezime: "Zoran", firma: "", email: "", tip: "fizicko_lice" },
      { id: "kl-A4", user_id: "kA", ime: "Nova", prezime: "Stranka", firma: XSS, email: "", tip: "pravno_lice" } ] },
    [TB]: { id: "kB", predmeti: B, kartoteka: [{ id: "kl-B1", user_id: "kB", ime: "Ana", prezime: "Bjelić", firma: "TAJNA FIRMA B", email: "", tip: "fizicko_lice" }] },
  };
  const f = await pokreniFixture(kombinuj(klijentiRuta(KOR, kuke), coiRuta(KOR, kuke), vezaRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/predmeti/${A[0].id}`);
  await cekaj(p, () => !document.getElementById("predmet-klijenti-blok").hidden);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const t = (id) => document.getElementById(id).textContent;
  return { povezani: [...document.querySelectorAll("#predmet-klijenti .people__name")].map(x => x.textContent), prazno: vid("predmet-klijenti-prazno"),
    otvori: vid("kl-otvori"), panel: vid("kl-panel"), rezultati: [...document.querySelectorAll("#kl-rezultati .pick__name")].map(x => x.textContent),
    rezMeta: [...document.querySelectorAll("#kl-rezultati .pick__meta")].map(x => x.textContent),
    stanje: vid("kl-stanje") ? (document.getElementById("kl-stanje").dataset.stanje || "") + ":" + t("kl-stanje") : null,
    izabran: vid("kl-izabran") ? t("kl-izabran-ime") : null, coi: vid("kl-coi") ? document.getElementById("kl-coi").dataset.stanje : null,
    coiNaslov: t("kl-coi-naslov"), coiLista: [...document.querySelectorAll("#kl-coi-lista .coi__case")].map(x => x.textContent),
    potvrdaVidljiva: vid("kl-potvrda-red"), poveziOnemoguceno: document.getElementById("kl-povezi").disabled,
    poruka: vid("kl-poruka") ? document.getElementById("kl-poruka").dataset.stanje + ":" + t("kl-poruka") : null,
    uspeh: vid("kl-uspeh") ? t("kl-uspeh") : null, xss: window.__xss || null, tekst: document.body.innerText };
});
const zahtevi = (s, metod, re) => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));
async function trazi(p, q) { await p.fill("#kl-pretraga", q); await p.press("#kl-pretraga", "Enter"); await cekaj(p, () => { const s = document.getElementById("kl-stanje"); return document.querySelectorAll("#kl-rezultati li").length > 0 || (!s.hidden && s.dataset.stanje !== "ucitavanje"); }); }
async function izaberi(p, id) { await p.click(`#kl-rezultati button[data-klijent="${id}"]`); await cekaj(p, () => { const c = document.getElementById("kl-coi"); return !c.hidden && c.dataset.stanje !== "ucitavanje"; }); }

// ── A: pretraga samo sopstvenih, izbor, čisto, povezivanje ───────────────
{
  const veze = [];
  const s = await scenario({ upisano: (l, b) => veze.push(b) });
  let e = await ekran(s.p);
  zapisi("A.ulaz", "predmet bez klijenata: „Nijedan klijent nije povezan“ + „Poveži klijenta“", e.prazno && e.otvori && !e.povezani.length);
  await s.p.click("#kl-otvori");
  await trazi(s.p, "Ana");
  e = await ekran(s.p);
  zapisi("A.pretraga", "rezultati su SAMO klijenti korisnika A (bez B-ove Ane i firme)", e.rezultati.length === 1 && e.rezultati[0] === "Ana Jović" && !/TAJNA|Bjelić/.test(e.tekst), e.rezultati.join("|"));
  const zp = zahtevi(s, "GET", /^\/klijenti$/)[0] || {};
  zapisi("A.pretraga", "GET /klijenti sa tokenom A, bez user_id, sa pretraga=", zp.auth === "Bearer " + TA && zp.parametri.pretraga === "Ana" && !("user_id" in zp.parametri));
  zapisi("A.pretraga", "šifrovana polja nisu ni u odgovoru ni na ekranu", !/ENC-A|jmbg/i.test(e.tekst));
  await izaberi(s.p, "kl-A1");
  e = await ekran(s.p);
  const coiTelo = zahtevi(s, "POST", /conflict-check$/);
  zapisi("A.coi", "izbor pokreće proveru sukoba interesa (ime + e-pošta, bez user_id)", coiTelo.length === 1);
  zapisi("A.coi", "nalaz o ISTOM predmetu (Ana Jović je tužilac ovog predmeta) se izostavlja → čisto", e.coi === "cisto" && /Nije pronađen/.test(e.coiNaslov) && !e.poveziOnemoguceno, `${e.coi} ${e.coiNaslov}`);
  zapisi("A.coi", "serverska poruka sa emodžijem se ne prikazuje", !e.tekst.includes("🚨"));
  await s.p.click("#kl-povezi");
  await cekaj(s.p, () => !document.getElementById("kl-uspeh").hidden);
  e = await ekran(s.p);
  zapisi("A.veza", "confirm-links telo: {klijent_ids:[kl-A1], uloga:stranka}", veze.length === 1 && JSON.stringify(veze[0]) === JSON.stringify({ klijent_ids: ["kl-A1"], uloga: "stranka" }), JSON.stringify(veze[0]));
  zapisi("A.veza", "posle uspeha predmet je ponovo pročitan: klijent je na listi, potvrda prikazana, panel zatvoren", e.povezani.includes("Ana Jović") && /povezan/.test(e.uspeh || "") && !e.panel, e.povezani.join());
  await s.p.reload();
  await cekaj(s.p, () => document.querySelectorAll("#predmet-klijenti .people__name").length > 0);
  zapisi("A.veza", "osvežavanje stranice: veza je trajna", (await ekran(s.p)).povezani.includes("Ana Jović"));
  await s.zatvori();
}
// ── B: sukob u drugom aktivnom predmetu → blokirano ──────────────────────
{
  const s = await scenario();
  await s.p.click("#kl-otvori");
  await trazi(s.p, "Marko");
  await izaberi(s.p, "kl-A2");
  let e = await ekran(s.p);
  zapisi("B.sukob", "sukob u drugom aktivnom predmetu: „Sukob interesa…“, povezivanje onemogućeno, bez potvrde", e.coi === "sukob" && e.poveziOnemoguceno && !e.potvrdaVidljiva, `${e.coi} ${e.coiNaslov}`);
  zapisi("B.sukob", "nalaz navodi predmet (HTML u nazivu je tekst)", e.coiLista.some(x => x.includes("<b onclick") && x.includes("(aktivan)")) && e.xss === null, e.coiLista.join("|"));
  await s.p.evaluate(() => { const b = document.getElementById("kl-povezi"); b.disabled = false; b.click(); });
  await s.p.waitForTimeout(300);
  zapisi("B.sukob", "ni nasilno omogućeno dugme ne šalje vezu (provera i u kodu)", zahtevi(s, "POST", /confirm-links$/).length === 0);
  await s.zatvori();
}
// ── C: pregled (zatvoren predmet) → samo uz potvrdu ──────────────────────
{
  const s = await scenario();
  await s.p.click("#kl-otvori");
  await trazi(s.p, "Zatvoreni");
  await izaberi(s.p, "kl-A3");
  let e = await ekran(s.p);
  zapisi("C.pregled", "preklapanje u zatvorenom predmetu: „traži proveru“, potrebna potvrda, dugme onemogućeno", e.coi === "pregled" && e.potvrdaVidljiva && e.poveziOnemoguceno, e.coiNaslov);
  await s.p.check("#kl-potvrda");
  e = await ekran(s.p);
  zapisi("C.pregled", "posle izričite potvrde povezivanje je dozvoljeno", !e.poveziOnemoguceno);
  await s.p.click("#kl-povezi");
  await cekaj(s.p, () => !document.getElementById("kl-uspeh").hidden);
  zapisi("C.pregled", "veza je napravljena", (await ekran(s.p)).povezani.includes("Zatvoreni Zoran"));
  await s.zatvori();
}
// ── D: provera nije izvršena / nije potpuna → nikad „čisto“ ──────────────
for (const [naziv, coi, re] of [
  ["500", () => ({ status: 500 }), /nije izvršena/], ["prekid", () => ({ prekid: true }), /nije izvršena/],
  ["nepotpuna", () => ({ status: 200, telo: { status: "review", provera_potpuna: false, slojevi_greska: ["klijenti"], konflikti: [] } }), /nije potpuna/],
  ["clear ali nepotpuna", () => ({ status: 200, telo: { status: "clear", provera_potpuna: false, konflikti: [] } }), /nije potpuna/],
  ["clear bez polja provera_potpuna", () => ({ status: 200, telo: { status: "clear", konflikti: [] } }), /nije potpuna/],
]) {
  const s = await scenario({ coi });
  await s.p.click("#kl-otvori");
  await trazi(s.p, "Ana");
  await izaberi(s.p, "kl-A1");
  const e = await ekran(s.p);
  zapisi("D.istina", `COI ${naziv}: nije „čisto“, traži potvrdu, dugme onemogućeno`, e.coi === "nepotpuna" && re.test(e.coiNaslov) && e.potvrdaVidljiva && e.poveziOnemoguceno && !/Nije pronađen/.test(e.tekst), `${e.coi} ${e.coiNaslov}`);
  await s.zatvori();
}
// ── E: pretraga — greška nije prazan rezultat ────────────────────────────
{
  const s = await scenario({ pre: (put) => put === "/klijenti:GET" ? { status: 500 } : null });
  await s.p.click("#kl-otvori");
  await trazi(s.p, "Ana");
  const e = await ekran(s.p);
  zapisi("E.pretraga", "500 pri pretrazi: „nije uspela… nije prazan rezultat“", e.stanje && e.stanje.startsWith("greska:") && /nije prazan/.test(e.stanje) && !e.rezultati.length, e.stanje);
  await s.zatvori();
}
{
  const s = await scenario();
  await s.p.click("#kl-otvori");
  await trazi(s.p, "Nepostojeći");
  const e = await ekran(s.p);
  zapisi("E.pretraga", "uspešna prazna pretraga: „Nijedan klijent ne odgovara…“", e.stanje && e.stanje.startsWith("prazno:"), e.stanje);
  await s.p.fill("#kl-pretraga", "Ana, ili(1)%");
  await s.p.press("#kl-pretraga", "Enter");
  await s.p.waitForTimeout(400);
  const z = zahtevi(s, "GET", /^\/klijenti$/).pop();
  zapisi("E.pretraga", "zarezi/zagrade/% se uklanjaju iz termina (PostgREST or_ filter)", z && !/[,()%]/.test(z.parametri.pretraga), z && z.parametri.pretraga);
  await s.zatvori();
}
// ── F: nov klijent → izbor → provera; HTML kao tekst ─────────────────────
{
  const upisi = [];
  const s = await scenario({ upisano: (r, b) => { if (b && b.ime) upisi.push(b); } });
  await s.p.click("#kl-otvori");
  await s.p.click("#kl-nov-prekidac");
  await s.p.click("#kl-nov-sacuvaj");
  let e = await ekran(s.p);
  zapisi("F.nov", "prazno ime: lokalna greška, ništa poslato", zahtevi(s, "POST", /^\/klijenti$/).length === 0 && /dva znaka/.test(e.poruka || ""));
  await s.p.selectOption("#kl-tip", "pravno_lice");
  await s.p.fill("#kl-ime", XSS);
  await s.p.fill("#kl-email", "kontakt@mila.rs");
  await s.p.click("#kl-nov-sacuvaj");
  await cekaj(s.p, () => { const c = document.getElementById("kl-coi"); return !c.hidden && c.dataset.stanje !== "ucitavanje"; });
  e = await ekran(s.p);
  zapisi("F.nov", "POST /klijenti: tip, ime, email — bez user_id i bez osetljivih polja", upisi.length === 1 && upisi[0].tip === "pravno_lice" && !("user_id" in upisi[0]) && !("jmbg" in upisi[0]) && !("pib" in upisi[0]), JSON.stringify(upisi[0]));
  zapisi("F.nov", "nov klijent je izabran i provera je odmah pokrenuta; ime je tekst", e.izabran === XSS && !!e.coi && e.xss === null, `${e.izabran} ${e.coi}`);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (put) => put === "/klijenti:POST" ? { status: 500 } : null });
  await s.p.click("#kl-otvori"); await s.p.click("#kl-nov-prekidac");
  await s.p.fill("#kl-ime", "Pera"); await s.p.click("#kl-nov-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("kl-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("F.nov", "500 pri čuvanju klijenta: ishod nepoznat, uputstvo da se proveri pretragom", (e.poruka || "").startsWith("nepoznato:") && /možda sačuvan/.test(e.poruka), e.poruka);
  await s.zatvori();
}
// ── G: server nije povezao / nepoznat ishod veze ─────────────────────────
for (const [naziv, kuke, stanje, re] of [["server izostavio klijenta", { odbijKlijenta: true }, "greska", /nije povezao/],
  ["500", { pre: (put) => /confirm-links$/.test(put) ? { status: 500 } : null }, "nepoznato", /možda povezan/],
  ["prekid", { pre: (put) => /confirm-links$/.test(put) ? { prekid: true } : null }, "nepoznato", /možda povezan/]]) {
  const s = await scenario(kuke);
  await s.p.click("#kl-otvori"); await trazi(s.p, "Ana"); await izaberi(s.p, "kl-A1");
  await s.p.click("#kl-povezi");
  await cekaj(s.p, () => { const n = document.getElementById("kl-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("G.veza", `${naziv}: „${stanje}“, bez lažnog uspeha`, (e.poruka || "").startsWith(stanje + ":") && re.test(e.poruka) && e.uspeh === null && !e.povezani.includes("Ana Jović"), e.poruka);
  await s.zatvori();
}
// ── H: zastareli odgovori ────────────────────────────────────────────────
{
  // Brz drugi izbor: spora provera prvog klijenta ne sme da prepiše ishod drugog.
  const s = await scenario({ coi: (b) => /Marko/.test(b.ime_prezime || "") ? new Promise(r => setTimeout(() => r(null), 1200)) : null });
  await s.p.click("#kl-otvori"); await trazi(s.p, "ov");
  await s.p.click('#kl-rezultati button[data-klijent="kl-A2"]');
  await s.p.waitForTimeout(100);
  await s.p.click('#kl-rezultati button[data-klijent="kl-A1"]');
  await s.p.waitForTimeout(1700);
  const e = await ekran(s.p);
  zapisi("H.zastarelo", "spora provera prethodnog izbora ne prepisuje ishod trenutnog", e.izabran === "Ana Jović" && e.coi === "cisto", `${e.izabran} ${e.coi}`);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (put) => put === "/klijenti:GET" ? new Promise(r => setTimeout(r, 1200)) : null });
  await s.p.click("#kl-otvori");
  await s.p.fill("#kl-pretraga", "Ana"); await s.p.press("#kl-pretraga", "Enter");
  await s.p.waitForTimeout(150);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1600);
  const e = await ekran(s.p);
  zapisi("H.sesija", "A→B tokom pretrage: rezultati A se ne prikazuju, panel zatvoren", !e.rezultati.length && !e.panel && !/Ana Jović/.test(e.tekst), e.rezultati.join());
  await s.zatvori();
}
// ── I: raspored ──────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await s.p.click("#kl-otvori"); await trazi(s.p, "Marko"); await izaberi(s.p, "kl-A2");
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("I.raspored", `${w}px: bez horizontalnog skrola sa otvorenim nalazom`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
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
