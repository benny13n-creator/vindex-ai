// Vindex V2 NG — NS005 Task 7: Znanje — sudska praksa (CAP-042) i interni stavovi (CAP-045).
// Pokretanje: `node tests/live-znanje.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend (prijava, validacija filtera, pad = 500, namespace stavova po korisniku) dokazuje
// STVARNA ruta: tests/test_ns005_t7_znanje.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { praksaRuta, stavoviRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-zn-A-NE-U-LOG-79", TB = "vx-zn-B-NE-U-LOG-80";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const ODLUKE = [
  { decision_number: "Rev 123/2024", decision_date: "2024-05-10", court: "Vrhovni sud", matter: "Građanska", izreka_preview: "Revizija tužioca se odbija kao neosnovana; otkaz je zakonit.", citat_format: "Vrhovni sud, Rev 123/2024, od 10.05.2024." },
  { decision_number: "Gž 45/2023", decision_date: "", court: "Apelacioni sud u Beogradu", matter: "Građanska", izreka_preview: "Žalba se usvaja; otkaz <img src=x onerror=\"window.__xss=9\"> poništen.", citat_format: "Apelacioni sud u Beogradu, Gž 45/2023, od ." },
  { decision_number: "", decision_date: "2022-01-01", court: "Osnovni sud", matter: "Građanska", izreka_preview: "Odluka o otkazu bez broja.", citat_format: "" },
];

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", put = "#/znanje", w = 1440, h = 900 } = {}) {
  const KOR = { [TA]: { id: "kA", predmeti: napraviPredmete("kA", 1) }, [TB]: { id: "kB", predmeti: napraviPredmete("kB", 1) } };
  const f = await pokreniFixture(kombinuj(praksaRuta(KOR, Object.assign({ odluke: ODLUKE }, kuke)), stavoviRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${put}`);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  const zn = document.querySelector('.sidenav__item[href="#/znanje"]');
  return { hash: location.hash, pogled: vid("znanje-pogled"), znLink: !!zn, znCurrent: zn && zn.getAttribute("aria-current"),
    prCurrent: document.querySelector('.sidenav__item[href="#glavni"]').getAttribute("aria-current"),
    praksaStanje: st("zn-praksa-stanje"), stavStanje: st("zn-stav-stanje"), dodajPoruka: st("zn-dodaj-poruka"),
    odluke: [...document.querySelectorAll("#zn-praksa-lista .decision")].map(li => ({ citat: li.querySelector(".decision__cite").textContent,
      flag: !!li.querySelector(".decision__flag"), tekst: (li.querySelector(".decision__text") || {}).textContent || "" })),
    stavovi: [...document.querySelectorAll("#zn-stav-lista .decision__cite")].map(x => x.textContent), xss: window.__xss || null, ceo: document.body.innerText };
});
const zahtevi = (s, re) => s.f.zahtevi.filter(z => z.metod === "POST" && re.test(z.putanja));
async function praksa(p, q, oblast = "") { await p.fill("#zn-praksa-upit", q); if (oblast) await p.selectOption("#zn-praksa-oblast", oblast);
  await p.click('#zn-praksa-forma button[type="submit"]'); await cekaj(p, () => { const n = document.getElementById("zn-praksa-stanje"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; }); }
async function stavovi(p, q) { await p.fill("#zn-stav-upit", q); await p.click('#zn-stav-forma button[type="submit"]');
  await cekaj(p, () => { const n = document.getElementById("zn-stav-stanje"); return document.querySelectorAll("#zn-stav-lista li").length > 0 || (!n.hidden && n.dataset.stanje !== "ucitavanje"); }); }

// ── A: navigacija ────────────────────────────────────────────────────────
{
  const s = await scenario({}, { put: "" });
  await cekaj(s.p, () => document.querySelectorAll("#rows tr").length > 0);
  let e = await ekran(s.p);
  zapisi("A.nav", "LIVE: „Znanje“ je stvaran link (#/znanje), ne prototip", e.znLink && await s.p.evaluate(() => !document.querySelector(".sidenav__item[data-modul=\"Znanje\"]")));
  await s.p.click('.sidenav__item[href="#/znanje"]');
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  e = await ekran(s.p);
  zapisi("A.nav", "klik otvara Znanje; aktivna stavka je „Znanje“, ne „Predmeti“", e.pogled && e.znCurrent === "page" && e.prCurrent === null);
  await s.p.click('.sidenav__item[href="#glavni"]');
  await cekaj(s.p, () => document.getElementById("znanje-pogled").hidden);
  e = await ekran(s.p);
  zapisi("A.nav", "povratak na Predmete vraća aktivnu stavku", e.prCurrent === "page" && e.znCurrent === null);
  await s.zatvori();
}
{
  const ctx = await browser.newContext(); const p = await ctx.newPage();
  const f = await pokreniFixture(async () => false);
  await p.goto(`http://127.0.0.1:${f.port}/`);
  zapisi("A.nav", "DEMO: „Znanje“ ostaje prototip (data-modul), bez živog modula", await p.evaluate(() => !!document.querySelector('.sidenav__item[data-modul="Znanje"]')));
  await ctx.close(); await f.zatvori();
}

// ── B: sudska praksa ─────────────────────────────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (b) => tela.push(b) });
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await s.p.click('#zn-praksa-forma button[type="submit"]');
  let e = await ekran(s.p);
  zapisi("B.praksa", "bez kriterijuma: lokalna poruka, ništa poslato", zahtevi(s, /praksa\/search/).length === 0 && /bar jedan filter/.test(e.praksaStanje || ""));
  await praksa(s.p, "otkaz", "Građanska");
  e = await ekran(s.p);
  zapisi("B.praksa", "telo: query, matter, limit, offset — bez user_id", JSON.stringify(tela[0]) === JSON.stringify({ limit: 10, offset: 0, query: "otkaz", matter: "Građanska" }), JSON.stringify(tela[0]));
  zapisi("B.praksa", "citat sa servera; nedovršen rep „, od .“ se odseca, ne dopunjuje", e.odluke[0].citat === "Vrhovni sud, Rev 123/2024, od 10.05.2024." && e.odluke[1].citat === "Apelacioni sud u Beogradu, Gž 45/2023", e.odluke.map(o => o.citat).join(" | "));
  zapisi("B.praksa", "odluka bez broja označena kao necitljiva; ostale nisu", !e.odluke[0].flag && !e.odluke[1].flag && e.odluke[2].flag);
  zapisi("B.praksa", "izreka sa HTML-om je tekst", e.odluke[1].tekst.includes("<img") && e.xss === null);
  zapisi("B.praksa", "broj prikazanih i ukupno; bez skora/procenta", /Prikazano 3 od 3/.test(e.praksaStanje || "") && !/score|%/.test(e.ceo), e.praksaStanje);
  await s.p.fill("#zn-praksa-od", "2025"); await s.p.fill("#zn-praksa-do", "2020");
  await s.p.click('#zn-praksa-forma button[type="submit"]');
  e = await ekran(s.p);
  zapisi("B.praksa", "godina od > do: lokalna poruka, ništa poslato", zahtevi(s, /praksa\/search/).length === 1 && /manja ili jednaka/.test(e.praksaStanje || ""));
  await s.zatvori();
}
for (const [naziv, kuke, q, re] of [
  ["500", { pre: (put) => put === "/api/praksa/search" ? { status: 500 } : null }, "otkaz", /nije uspela.*nije prazan/],
  ["400", { pre: (put) => put === "/api/praksa/search" ? { status: 400 } : null }, "otkaz", /Filter nije prihvaćen/],
  ["bez rezultata", {}, "nepostojeći pojam", /Nijedna odluka/],
]) {
  const s = await scenario(kuke);
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await praksa(s.p, q);
  const e = await ekran(s.p);
  zapisi("B.istina", `praksa ${naziv}: tačno stanje, nijedna odluka`, re.test(e.praksaStanje || "") && !e.odluke.length, e.praksaStanje);
  await s.zatvori();
}

// ── C: interni stavovi — dodavanje, pretraga, izolacija ─────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (put, b) => { if (put.endsWith("/dodaj")) tela.push(b); } });
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await s.p.click("#zn-dodaj-otvori");
  await s.p.fill("#zn-dodaj-naslov", "Zastarelost zarade");
  await s.p.fill("#zn-dodaj-tekst", "kratko");
  await s.p.click("#zn-dodaj-sacuvaj");
  let e = await ekran(s.p);
  zapisi("C.stav", "kratak tekst: lokalna greška, ništa poslato", zahtevi(s, /dodaj$/).length === 0 && /30 znakova/.test(e.dodajPoruka || ""));
  await s.p.fill("#zn-dodaj-tekst", "Kancelarija zastupa stav da zastarelost teče od dospeća svake zarade.");
  await s.p.click("#zn-dodaj-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("zn-dodaj-poruka"); return !n.hidden && n.dataset.stanje === "uspeh"; });
  zapisi("C.stav", "POST /interni-stavovi/dodaj {naslov, tekst} — bez user_id", tela.length === 1 && JSON.stringify(Object.keys(tela[0]).sort()) === '["naslov","tekst"]');
  await stavovi(s.p, "zastarelost");
  e = await ekran(s.p);
  zapisi("C.stav", "A pronalazi sopstveni stav", e.stavovi.includes("Zastarelost zarade"), e.stavovi.join());
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(400);
  e = await ekran(s.p);
  zapisi("C.sesija", "A→B: rezultati i unos A odmah nestaju", !e.stavovi.length && !/Zastarelost zarade/.test(e.ceo) && await s.p.inputValue("#zn-stav-upit") === "");
  await stavovi(s.p, "zastarelost");
  e = await ekran(s.p);
  zapisi("C.izolacija", "B ne vidi stav korisnika A („Nijedan stav…“)", !e.stavovi.length && /Nijedan stav kancelarije/.test(e.stavStanje || ""), e.stavStanje);
  await s.zatvori();
}
for (const [naziv, kuke, re] of [["pretraga_neuspesna", { stavoviPad: true }, /nije izvršena.*nije prazan/], ["500", { pre: (put) => put === "/interni-stavovi/pretraga" ? { status: 500 } : null }, /nije uspela.*nije prazan/],
  ["403", { pre: (put) => put === "/interni-stavovi/pretraga" ? { status: 403 } : null }, /nisu dostupni/]]) {
  const s = await scenario(kuke);
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await stavovi(s.p, "zastarelost");
  const e = await ekran(s.p);
  zapisi("C.istina", `stavovi ${naziv}: greška, ne „nema stavova“`, re.test(e.stavStanje || "") && !/Nijedan stav/.test(e.stavStanje || ""), e.stavStanje);
  await s.zatvori();
}
for (const [naziv, kuka, stanje] of [["500", { status: 500 }, "nepoznato"], ["prekid", { prekid: true }, "nepoznato"], ["403", { status: 403 }, "greska"]]) {
  const s = await scenario({ pre: (put) => put === "/interni-stavovi/dodaj" ? kuka : null });
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await s.p.click("#zn-dodaj-otvori");
  await s.p.fill("#zn-dodaj-naslov", "Stav " + naziv);
  await s.p.fill("#zn-dodaj-tekst", "Tekst stava koji je dovoljno dug da prođe proveru dužine.");
  await s.p.click("#zn-dodaj-sacuvaj");
  await cekaj(s.p, () => { const n = document.getElementById("zn-dodaj-poruka"); return !n.hidden && n.dataset.stanje !== "ucitavanje"; });
  const e = await ekran(s.p);
  zapisi("C.ishod", `dodavanje ${naziv}: „${stanje}“, unos ostaje`, (e.dodajPoruka || "").startsWith(stanje + ":") && await s.p.inputValue("#zn-dodaj-naslov") === "Stav " + naziv, e.dodajPoruka);
  await s.zatvori();
}

// ── D: zastareo odgovor posle promene korisnika ─────────────────────────
{
  const s = await scenario({ pre: (put) => put === "/api/praksa/search" ? new Promise(r => setTimeout(r, 1200)) : null });
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await s.p.fill("#zn-praksa-upit", "otkaz"); await s.p.click('#zn-praksa-forma button[type="submit"]');
  await s.p.waitForTimeout(150);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1600);
  const e = await ekran(s.p);
  zapisi("D.zastarelo", "spor odgovor pretrage A se ne prikazuje posle prelaska na B", !e.odluke.length && e.praksaStanje === null, e.praksaStanje);
  await s.zatvori();
}
// ── E: raspored ──────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await cekaj(s.p, () => !document.getElementById("znanje-pogled").hidden);
  await praksa(s.p, "otkaz");
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("E.raspored", `${w}px: bez horizontalnog skrola sa rezultatima`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
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
