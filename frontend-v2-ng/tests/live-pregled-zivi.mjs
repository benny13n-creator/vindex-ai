// Vindex V2 NG — NS006 Task 11: Pregled svestan događaja („Stanje predmeta": šta se promenilo, šta traži pažnju, sledeći korak).
// Pokretanje: `node tests/live-pregled-zivi.mjs` (Python iz VX_PYTHON ili `python`; fixture na 127.0.0.1; ništa spolja).
//
// Odgovori API-ja su STVARNI backend odgovori (tests/ns006_ui_fixture.py nad realističnim predmetom), ne ručno pisani.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-zp-A-NE-U-LOG-52", TB = "vx-zp-B-NE-U-LOG-63";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend() {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns006_ui_fixture.py"],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log(r.stderr.slice(-2000)); throw new Error("ns006_ui_fixture.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const STVARNO = backend();
const { PA, PB, D1, D2, D3 } = STVARNO;
const AKCIJE_A = STVARNO.odgovori[`A|/api/case-actions/predmeti/${PA}`].telo.akcije;
const PROMENE_A = STVARNO.odgovori[`A|/api/predmeti/${PA}/genome-v2/promene`].telo;
zapisi("backend", "stvarni backend odgovori: radnje i promene predmeta A", AKCIJE_A.length > 0 && PROMENE_A.stanje === "OK" && PROMENE_A.promene.length > 0,
  `${AKCIJE_A.length} radnji, ${PROMENE_A.promene.length} promena`);

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  A[0].id = PA; A[0].naziv = "Petrović protiv Gradnja Invest DOO"; A[0].tip = "radno";
  B[0].id = PB; B[0].naziv = "Jovanović protiv Opštine";
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}
const DOKUMENTI = () => ({ [PA]: [D1, D2, D3].map((id, i) => ({ id, predmet_id: PA, user_id: "kA", naziv_fajla: ["Rešenje o otkazu.pdf", "Dostavnica.pdf", "Platni listići 2024.pdf"][i],
  status: "indeksirano", velicina_kb: 40, redni_broj: i + 1, tip_dokaza: "dopis", created_at: "2026-10-01T09:00:00Z", tekst_sadrzaj: "TEKST-" + i })) });

/** Tačno telo koje je backend vratio za (korisnik, putanja); sve ostalo = isti 404 kao tuđ predmet. */
function ziviRuta(izvor, kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  const nijeNadjen = izvor.odgovori[`B|/api/predmeti/${PA}/genome-v2`];
  return async (req, url, res) => {
    if (!/^\/api\/(predmeti\/[^/]+\/genome-v2(\/promene)?|case-actions\/predmeti\/[^/]+)$/.test(url.pathname)) return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    if (kuke.pre) { const z = await kuke.pre(url.pathname, k); if (z) { json(res, z.status, z.telo); return true; } }
    if (res.destroyed) return true;
    const o = izvor.odgovori[`${k}|${url.pathname}`] || nijeNadjen;
    let telo = JSON.parse(JSON.stringify(o.telo));
    if (kuke.izmeni) telo = kuke.izmeni(url.pathname, telo) || telo;
    json(res, o.status, telo);
    return true;
  };
}

async function scenario({ kuke = {}, hash = `#/predmeti/${PA}`, w = 1440, h = 900, tema = "dark" } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(ziviRuta(STVARNO, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, DOKUMENTI())));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses("kA", TA), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}

const gotovo = (p) => cekaj(p, () => !document.getElementById("zp-blok").hidden
  && ["zp-promene-stanje", "zp-paznja-stanje", "zp-sledece-stanje"].every(id => document.getElementById(id).dataset.stanje !== "ucitavanje")
  && (document.getElementById("zp-sledece").children.length > 0 || !document.getElementById("zp-sledece-stanje").hidden));
const ekran = (p) => p.evaluate(() => {
  const li = (id) => [...document.querySelectorAll("#" + id + " > li")];
  const st = (id) => { const n = document.getElementById(id); return n.hidden ? null : [n.dataset.stanje, n.textContent]; };
  const a = document.querySelector("#zp-promene a");
  return {
    blok: !document.getElementById("zp-blok").hidden,
    promene: li("zp-promene").map(x => x.innerText.replace(/\s+/g, " ").trim()),
    link: a ? a.getAttribute("href") : null,
    paznja: li("zp-paznja").map(x => [x.dataset.prioritet, x.innerText.replace(/\s+/g, " ").trim()]),
    sledece: li("zp-sledece").map(x => [x.dataset.akcija, x.dataset.prioritet, x.innerText.replace(/\s+/g, " ").trim()]),
    sPromene: st("zp-promene-stanje"), sPaznja: st("zp-paznja-stanje"), sSledece: st("zp-sledece-stanje"),
    ceo: document.getElementById("zp-blok").textContent,
    preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    xss: window.__xss || null,
  };
});
const zahtevi = (s, re, metod) => s.f.zahtevi.filter(z => (!metod || z.metod === metod) && re.test(z.putanja));
const DOZVOLJENO = /^\/api\/predmeti(\/[^/]+(\/(dokumenti|genome-v2\/promene))?)?$|^\/api\/case-actions\/predmeti\/[^/]+$|^\/api\/autonomy\/work-items$/;   // NS007: + pripremljen rad predmeta

// ── 1. Stvarno stanje predmeta ───────────────────────────────────────────────
{
  const s = await scenario();
  zapisi("prikaz", "Pregled prikazuje „Stanje predmeta“", await gotovo(s.p));
  const e = await ekran(s.p);
  zapisi("promene", "„Šta se promenilo“ = promene iz ugovora (najviše 4) + veza na Analizu",
    e.promene.length === Math.min(PROMENE_A.promene.length, 4) + 1 && e.promene[0].includes(PROMENE_A.promene[0].opis), e.promene.join(" | ").slice(0, 220));
  zapisi("promene", "veza vodi na karticu Analiza istog predmeta", e.link === `#/predmeti/${PA}/analiza`, e.link);
  const vazne = AKCIJE_A.filter(a => a.prioritet === "critical" || a.prioritet === "high");
  zapisi("paznja", "„Šta traži pažnju“ = samo kritične i visoke kanonske radnje, kritične prve",
    e.paznja.length === Math.min(vazne.length, 3) && e.paznja.every(x => x[0] === "critical" || x[0] === "high") && e.paznja[0][0] === "critical", JSON.stringify(e.paznja).slice(0, 220));
  zapisi("paznja", "svaka radnja kaže ZAŠTO (razlog iz backend-a) i rok", e.paznja.every(x => /Zašto: .+ · (rok \d{2}\.\d{2}\.\d{4}\.|bez roka)/.test(x[1])),
    e.paznja.map(x => x[1]).join(" | ").slice(0, 220));
  const prva = AKCIJE_A.find(a => a.prioritet === "critical");
  zapisi("sledece", "„Sledeći korak“ = prva radnja po kanonskom redosledu (prioritet, pa rok)", e.sledece.length === 1 && e.sledece[0][0] === prva.id, JSON.stringify(e.sledece));
  zapisi("istina", "ništa izmišljeno: svaka prikazana radnja postoji u odgovoru backend-a",
    [...e.paznja.map(x => x[1]), ...e.sledece.map(x => x[2])].every(t => AKCIJE_A.some(a => t.includes(a.razlog))));
  zapisi("cena", "Pregled čita tačno promene + radnje + pripremljen rad (3 GET, NS007), ne pun Genome i ništa van ugovora",
    zahtevi(s, /genome-v2\/promene$/, "GET").length === 1 && zahtevi(s, /case-actions\/predmeti\//, "GET").length === 1 && zahtevi(s, /genome-v2$/).length === 0
      && zahtevi(s, /^\/api\/autonomy\/work-items$/, "GET").length === 1
      && s.f.zahtevi.every(z => z.metod === "GET") && s.f.zahtevi.filter(z => z.putanja.startsWith("/api/")).every(z => DOZVOLJENO.test(z.putanja)),
    s.f.zahtevi.map(z => z.metod + " " + z.putanja).join(","));
  await s.p.click("#tab-analiza"); await cekaj(s.p, () => !document.getElementById("odeljak-analiza").hidden);
  await s.p.click("#tab-pregled"); await cekaj(s.p, () => !document.getElementById("odeljak-pregled").hidden);
  await s.p.waitForTimeout(200);
  zapisi("cena", "povratak na Pregled ne čita ponovo", zahtevi(s, /case-actions\/predmeti\//).length === 1);
  await s.p.click("#zp-promene a");
  zapisi("navigacija", "„Detalji u Analizi“ otvara Analizu", await cekaj(s.p, () => !document.getElementById("odeljak-analiza").hidden && location.hash.endsWith("/analiza")));
  zapisi("bezbednost", "0 spoljnih zahteva", s.spoljni.length === 0, s.spoljni.slice(0, 2).join(","));
  await s.zatvori();
}

// ── 1b. Srednji i nizak prioritet NE ulaze u „pažnju“, ali ostaju u redosledu ──────
{
  const NISKA = { id: "niska-0001", predmet_id: PA, tip: "PLANIRATI_ROKOVE", razlog: "Planirati rokove za dopunu spisa", prioritet: "low", rok: "2026-10-10", status: "open" };
  const SREDNJA = { id: "srednja-0001", predmet_id: PA, tip: "OJACATI_DOKAZE", razlog: "Ojačati dokaze o radnom stažu", prioritet: "medium", rok: null, status: "open" };
  const s = await scenario({ kuke: { izmeni: (put, t) => /case-actions/.test(put) ? { ...t, akcije: [NISKA, SREDNJA, ...t.akcije] } : null } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("paznja", "radnje srednjeg i niskog prioriteta nisu u „pažnji“ čak ni kad su prve u odgovoru",
    !e.paznja.some(x => /dopunu spisa|radnom stažu/.test(x[1])) && e.paznja.length === 3, JSON.stringify(e.paznja.map(x => x[0])));
  zapisi("sledece", "„sledeći korak“ i dalje kritična radnja (ne prva u odgovoru)", e.sledece.length === 1 && e.sledece[0][1] === "critical", JSON.stringify(e.sledece));
  // bez kritičnih/visokih: „pažnja“ pošteno prazna, a sledeći korak = srednja pre niske
  await s.zatvori();
  const s2 = await scenario({ kuke: { izmeni: (put, t) => /case-actions/.test(put) ? { ...t, akcije: [NISKA, SREDNJA] } : null } });
  await gotovo(s2.p);
  const e2 = await ekran(s2.p);
  zapisi("sledece", "bez kritičnih: pažnja prazna, sledeći korak = srednji prioritet pre niskog",
    !!e2.sPaznja && e2.sPaznja[0] === "prazno" && e2.sledece.length === 1 && e2.sledece[0][0] === "srednja-0001", JSON.stringify([e2.sPaznja, e2.sledece]));
  await s2.zatvori();
}

// ── 1c. Prelazak na nedostupan predmet: ništa od A ne ostaje ni u skrivenom delu stranice ──
{
  const s = await scenario();
  await gotovo(s.p);
  await s.p.evaluate((h) => { location.hash = h; }, "#/predmeti/kB-00000");
  await s.p.waitForTimeout(900);
  const ostatak = await s.p.evaluate(() => document.getElementById("zp-blok").textContent);
  zapisi("sesija", "posle prelaska na tuđ/nepostojeći predmet blok je ispražnjen (ni skriveno)",
    !AKCIJE_A.some(a => ostatak.includes(a.razlog)) && !PROMENE_A.promene.some(x => ostatak.includes(x.opis)), ostatak.replace(/\s+/g, " ").slice(0, 120));
  await s.zatvori();
}

// ── 2. Lenjo: druga kartica ne čita stanje Pregleda ──────────────────────────
{
  const s = await scenario({ hash: `#/predmeti/${PA}/dokumenti` });
  await cekaj(s.p, () => !document.getElementById("odeljak-dokumenti").hidden);
  await s.p.waitForTimeout(300);
  zapisi("cena", "otvaranje Dokumenata ne čita radnje ni promene", zahtevi(s, /case-actions|genome-v2/).length === 0);
  await s.zatvori();
}

// ── 3. Pad izvora: nikad „sve je u redu" ─────────────────────────────────────
for (const [ime, re] of [["promene", /genome-v2\/promene$/], ["radnje", /case-actions\/predmeti\//]]) {
  const s = await scenario({ kuke: { pre: (put) => re.test(put) ? { status: 500, telo: { detail: "x" } } : null } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  if (ime === "promene") zapisi("greska", "pad promena → GREŠKA „ne znači da promena nema“, radnje i dalje vidljive",
    !!e.sPromene && e.sPromene[0] === "greska" && /ne znači da promena nema/.test(e.sPromene[1]) && e.paznja.length > 0, JSON.stringify(e.sPromene));
  else zapisi("greska", "pad radnji → GREŠKA i u „pažnji“ i u „sledećem“, NE „nema radnji“",
    !!e.sPaznja && e.sPaznja[0] === "greska" && !!e.sSledece && e.sSledece[0] === "greska" && !/Nema otvorenih|Nijedna otvorena/.test(e.ceo), JSON.stringify([e.sPaznja, e.sSledece]));
  await s.zatvori();
}

// ── 4. Prazno je prazno (pošteno); prva verzija je prva verzija ──────────────
{
  const s = await scenario({ kuke: { izmeni: (put, t) => /case-actions/.test(put) ? { ...t, akcije: [], broj_akcija: 0 } : /promene$/.test(put) ? { ...t, promene: [] } : null } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("prazno", "bez promena: „Nema nove materijalne promene od prethodne verzije“, ništa dopisano",
    !!e.sPromene && e.sPromene[0] === "prazno" && /Nema nove materijalne promene/.test(e.sPromene[1]) && e.promene.length === 0, JSON.stringify(e.sPromene));
  zapisi("prazno", "bez radnji: pošteno „nema otvorenih radnji“", !!e.sSledece && e.sSledece[0] === "prazno" && !!e.sPaznja && e.sPaznja[0] === "prazno" && e.sledece.length === 0);
  await s.zatvori();
}
{
  const s = await scenario({ kuke: { izmeni: (put) => /promene$/.test(put) ? { stanje: "PRVA_VERZIJA", trenutna_verzija: 1, prethodna_verzija: null, promene: [] } : null } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("prazno", "prva verzija analize: kaže da nema sa čim da se uporedi", !!e.sPromene && /samo jednu verziju/.test(e.sPromene[1]), JSON.stringify(e.sPromene));
  await s.zatvori();
}

// ── 5. Zastareo odgovor: radnje A su STIGLE, promene A kasne; prelazak na drugi predmet, pa na drugog korisnika ──
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ kuke: { pre: async (put) => { if (put.includes(PA) && /promene$/.test(put)) await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("zp-promene-stanje").dataset.stanje === "ucitavanje");
  await s.p.waitForTimeout(200);
  await s.p.evaluate((h) => { location.hash = h; }, "#/predmeti/kA-00001");
  const drugi = await cekaj(s.p, () => document.getElementById("zp-sledece-stanje").dataset.stanje === "greska");
  pusti();
  await s.p.waitForTimeout(700);
  const e = await ekran(s.p);
  zapisi("sesija", "radnje predmeta A se NE pojavljuju na drugom predmetu istog korisnika", drugi && !AKCIJE_A.some(a => e.ceo.includes(a.razlog)), e.ceo.slice(0, 120));
  await s.zatvori();
}
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ kuke: { pre: async (put, k) => { if (k === "A" && /promene$/.test(put)) await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("zp-promene-stanje").dataset.stanje === "ucitavanje");
  await s.p.waitForTimeout(200);
  await s.p.evaluate(([k, v]) => { localStorage.setItem(k, v); window.dispatchEvent(new StorageEvent("storage", { key: k, newValue: v })); }, [KLJUC, ses("kB", TB)]);
  await s.p.waitForTimeout(400);
  pusti();
  await s.p.waitForTimeout(600);
  const e = await ekran(s.p);
  zapisi("sesija", "posle prelaska A→B nijedna radnja ni promena A nije na ekranu",
    !AKCIJE_A.some(a => e.ceo.includes(a.razlog)) && !PROMENE_A.promene.some(x => e.ceo.includes(x.opis)), e.ceo.slice(0, 120));
  await s.zatvori();
}

// ── 6. Tekst iz baze se ne izvršava ──────────────────────────────────────────
{
  const s = await scenario({ kuke: { izmeni: (put, t) => /case-actions/.test(put) ? { ...t, akcije: t.akcije.map((a, i) => i ? a : { ...a, razlog: "<img src=x onerror=window.__xss=1>" }) } : null } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("bezbednost", "HTML u razlogu se prikazuje kao tekst, ne izvršava", e.xss === null && /<img src=x onerror=/.test(e.ceo));
  await s.zatvori();
}

// ── 7. Raspored ──────────────────────────────────────────────────────────────
for (const [w, tema] of [[360, "light"], [768, "dark"], [1440, "light"]]) {
  const s = await scenario({ w, h: 800, tema });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("raspored", `${w}px/${tema}: blok vidljiv, bez vodoravnog preliva`, e.blok && !e.preliv);
  await s.zatvori();
}

await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
zapisi("bezbednost", "nijedan token u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
