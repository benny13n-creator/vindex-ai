// Vindex V2 NG — NS006 Task 10: kartica „Analiza" (profesionalni Genome, dokazi, protivrečnosti, rizici i spremnost).
// Pokretanje: `node tests/live-analiza.mjs` (Python iz VX_PYTHON ili `python`; fixture na 127.0.0.1; ništa spolja).
//
// Odgovori API-ja NISU ručno pisani: test na početku pokreće tests/ns006_ui_fixture.py, koji nad realističnim
// predmetom izvršava STVARNI backend (reconcile akcija + rute genome-v2, promene, case-actions, workspace) i vraća
// tačna tela odgovora. UI se tako proverava protiv ugovora koji backend zaista daje.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-an-A-NE-U-LOG-41", TB = "vx-an-B-NE-U-LOG-87";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend(pad) {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns006_ui_fixture.py", ...(pad ? ["--pad=" + pad] : [])],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log(r.stderr.slice(-2000)); throw new Error("ns006_ui_fixture.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const STVARNO = backend(null);
const SA_PADOM = backend("predmet_dokazi");
const { PA, PB, D1, D2, D3 } = STVARNO;
zapisi("backend", "stvarni backend odgovori učitani (A, B, tuđ, tabla) bez upisa van reconcile-a",
  Object.keys(STVARNO.odgovori).length === 11 && STVARNO.pisanja_van_reconcile === 0, String(Object.keys(STVARNO.odgovori).length));

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

/** Ruta živog predmeta: tačno telo koje je backend vratio za (korisnik, putanja); sve ostalo = isti 404 kao tuđ predmet. */
function ziviRuta(izvor, kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  const nijeNadjen = izvor.odgovori[`B|/api/predmeti/${PA}/genome-v2`];
  return async (req, url, res) => {
    if (!/^\/api\/(predmeti\/[^/]+\/genome-v2(\/promene)?|case-actions\/predmeti\/[^/]+)$/.test(url.pathname)) return false;
    const a = req.headers.authorization || "";
    const k = tok[a.slice(7)];
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

async function scenario({ izvor = STVARNO, kuke = {}, token = TA, korisnik = "kA", hash = `#/predmeti/${PA}/analiza`, w = 1440, h = 900, tema = "dark" } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(ziviRuta(izvor, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, DOKUMENTI())));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses(korisnik, token), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const gotovo = (p) => cekaj(p, () => !document.getElementById("an-sadrzaj").hidden || !document.getElementById("an-stanje").hidden && document.getElementById("an-stanje").dataset.stanje !== "ucitavanje");
const ekran = (p) => p.evaluate(() => {
  const t = (id) => document.getElementById(id) ? document.getElementById(id).innerText : "";
  const li = (id) => [...document.querySelectorAll("#" + id + " > li")];
  return {
    sadrzaj: !document.getElementById("an-sadrzaj").hidden, stanje: document.getElementById("an-stanje").hidden ? null : document.getElementById("an-stanje").textContent,
    verzija: t("an-verzija"), promene: li("an-promene").map(x => x.innerText.replace(/\s+/g, " ").trim()),
    oznake: li("an-promene").map(x => x.dataset.oznaka), analiticke: li("an-analiticke").map(x => x.textContent),
    poreklaDokaza: li("an-dokazi").map(x => x.querySelector(".prov") && x.querySelector(".prov").dataset.poreklo),
    oznakePorekla: [...document.querySelectorAll("#an-dokazi .prov")].map(x => x.textContent),
    dokazi: t("an-dokazi"), sazetak: t("an-dokazi-sazetak"), dokumenti: li("an-dokumenti").map(x => [x.dataset.klasifikacija, x.innerText]),
    kontr: li("an-kontr-aktivne").map(x => ({ id: x.dataset.kontradikcija, stanje: x.dataset.stanje, tekst: x.innerText, ucesnika: x.querySelectorAll(".an-sub > li").length })),
    osnovi: t("an-osnovi"), spremnost: [...document.querySelectorAll("#an-spremnost dd")].map(x => [x.dataset.dim, x.dataset.stanje, x.querySelector(".an-dim__value").textContent]),
    metrike: !document.getElementById("an-metrike-blok").hidden ? t("an-metrike-blok") : null,
    dokazStanje: document.getElementById("an-dokazi-stanje").hidden ? null : document.getElementById("an-dokazi-stanje").textContent,
    dokazStanjeVrsta: document.getElementById("an-dokazi-stanje").dataset.stanje || null,
    metrikeStavke: li("an-metrike").map(x => x.textContent),
    sav: document.getElementById("odeljak-analiza").textContent,
    cinjenice: t("an-cinjenice"), ceo: document.body.innerText,
    tabovi: [...document.querySelectorAll(".tabs__item")].filter(a => a.getClientRects().length).map(a => a.childNodes[0].textContent.trim()),
    aktivni: document.querySelector(".tabs__item[aria-current='page']") ? document.querySelector(".tabs__item[aria-current='page']").id : null,
    xss: window.__xss || null,
  };
});
const zahtevi = (s, re, metod) => s.f.zahtevi.filter(z => (!metod || z.metod === metod) && re.test(z.putanja));
const ZABRANJENO = /verovatnoća uspeha|šans[ae]|predviđanje (ishoda|presude)|chance|probability/i;

// ── 1. Sadržaj, poreklo, promene ─────────────────────────────────────────────
{
  const s = await scenario();
  zapisi("prikaz", "Analiza se učitava za predmet A", await gotovo(s.p));
  const e = await ekran(s.p);
  zapisi("prikaz", "kartica „Analiza“ je druga i aktivna; ukupno 8 kartica",
    e.tabovi[1] === "Analiza" && e.tabovi.length === 8 && e.aktivni === "tab-analiza", e.tabovi.join(","));
  zapisi("promene", "verzija i kompletnost iz ugovora", /Analiza v4/.test(e.verzija) && /kompletnost: kompletna/.test(e.verzija), e.verzija);
  zapisi("promene", "„Šta se promenilo“ = 4 strukturne promene iz stvarnog ugovora",
    e.promene.length === 4 && e.promene.some(x => /Nova kontradikcija: datum uručenja rešenja o otkazu/.test(x)) && e.promene.some(x => /Dokumenata u analizi: 2 → 3/.test(x)),
    e.promene.join(" | "));
  zapisi("promene", "oznake promena (+ za nove)", e.oznake.filter(x => x === "+").length === 4, e.oznake.join(""));
  zapisi("promene", "procena modela je ODVOJENA i označena kao analiza", e.analiticke.length >= 1 && e.analiticke.every(x => /Analiza \(AI\)/.test(x)), e.analiticke.join("|"));
  zapisi("poreklo", "dokazi nose 4 različite klase porekla (iz dokumenta, advokat, AI, nepoznato)",
    ["SOURCE_FACT", "HUMAN_CONFIRMED", "AI_ANALYSIS", "UNKNOWN"].every(k => e.poreklaDokaza.includes(k)), e.poreklaDokaza.join(","));
  zapisi("poreklo", "poreklo je i REČ, ne samo boja", ["Iz dokumenta", "Uneo advokat", "Analiza (AI)", "Poreklo nepoznato"].every(x => e.oznakePorekla.includes(x)), e.oznakePorekla.join(","));
  const stil = await s.p.evaluate(() => {
    const st = (k) => { const e = document.querySelector(`#an-dokazi .prov[data-poreklo="${k}"]`); const c = getComputedStyle(e); return c.borderLeftStyle + "/" + c.borderLeftColor + "/" + c.color; };
    return { izvor: st("SOURCE_FACT"), ai: st("AI_ANALYSIS"), nepoznato: st("UNKNOWN") };
  });
  zapisi("poreklo", "analiza (AI) vizuelno NIJE ista kao činjenica iz dokumenta", stil.izvor !== stil.ai && stil.ai.startsWith("dashed") && stil.izvor !== stil.nepoznato, JSON.stringify(stil));
  zapisi("dokazi", "sažetak dokaza iz grafa (5 tvrdnji, 2 u protivrečnosti)", /5 tvrdnji/.test(e.sazetak) && /2 u protivrečnosti/.test(e.sazetak), e.sazetak);
  const d3 = e.dokumenti.find(x => /Platni listići/.test(x[1]));
  zapisi("dokazi", "pala klasifikacija se prikazuje kao neuspeh, ne kao „ostalo“", d3 && d3[0] === "NEUSPESNA" && /klasifikacija nije uspela/.test(d3[1]) && !/ostalo/.test(d3[1]), d3 && d3[1]);
  zapisi("genome", "ključne činjenice = samo iz dokumenta i od advokata", /Rešenje je uručeno/.test(e.cinjenice) && /nije primio lično/.test(e.cinjenice) && !/480\.000/.test(e.cinjenice), e.cinjenice.slice(0, 120));
  zapisi("genome", "pravni osnovi su „predlog analize — nije potvrđeno“ + signal za nemoguć član",
    /nije potvrđeno u izvorima prava/.test(e.osnovi) && /broj člana je van uobičajenog opsega/.test(e.osnovi), e.osnovi.slice(0, 160));
  const k1 = e.kontr[0];
  zapisi("protivrečnosti", "jedna sporna tačka sa 2 učesnika, relacija, težina, stanje",
    e.kontr.length === 1 && k1.ucesnika === 2 && /datum uručenja rešenja o otkazu/.test(k1.tekst) && /činjenica — činjenica/.test(k1.tekst) && /kritična/.test(k1.tekst) && k1.stanje === "AKTIVNA", k1 && k1.tekst.replace(/\s+/g, " ").slice(0, 200));
  zapisi("protivrečnosti", "svaki učesnik ima dugme izvora (dokument + procenjena strana)", /Izvor: Rešenje o otkazu\.pdf · približno str\. 1/.test(k1.tekst) && /Izvor: Dostavnica\.pdf/.test(k1.tekst));
  const sp = Object.fromEntries(e.spremnost.map(x => [x[0], x[2]]));
  zapisi("spremnost", "operativna spremnost i pokrivenost bez pseudo-predviđanja",
    sp.operativna_spremnost === "Kritičan nedostatak" && /2 od 5 tvrdnji ima procenu dokaza/.test(sp.pokrivenost_procene) && /pravilo, nije procena ishoda/.test(sp.procesni_rizik), JSON.stringify(sp));
  zapisi("spremnost", "ocene modela su u zasebnom bloku sa „nije verovatnoća ishoda“", e.metrike && /nisu verovatnoća ishoda/.test(e.metrike));
  zapisi("spremnost", "SVAKA ocena modela nosi sopstvenu napomenu „NIJE verovatnoća ishoda“",
    e.metrikeStavke.length > 0 && e.metrikeStavke.every(x => /NIJE verovatnoća ishoda/.test(x) && !/verovatnoća uspeha|šans/i.test(x)) && e.metrikeStavke.some(x => /^Snaga predmeta \(analitička ocena, 0–100\): \d+/.test(x)) && !e.metrikeStavke.some(x => /[a-z]_[a-z]+:/.test(x)), e.metrikeStavke.join(" | ").slice(0, 200));
  const _bez = (e.ceo + " " + e.sav).replace(/(nisu|nije|ni jedan nije|nijedan pokazatelj nije) (verovatnoća|predviđanje) ishoda/gi, "");
  zapisi("istina", "nigde reči o šansi/verovatnoći uspeha", !ZABRANJENO.test(_bez), (_bez.match(ZABRANJENO) || [""])[0]);
  const DOZVOLJENO = [/^\/api\/predmeti$/, /^\/api\/predmeti\/[^/]+$/, /^\/api\/predmeti\/[^/]+\/dokumenti$/, /^\/api\/predmeti\/[^/]+\/genome-v2(\/promene)?$/];
  const visak = s.f.zahtevi.filter(z => z.putanja.startsWith("/api/") && !DOZVOLJENO.some(re => re.test(z.putanja)));
  zapisi("cena", "otvaranje Analize ne poziva ništa van ugovora (nema refresh-a, analize ni modela)", visak.length === 0, visak.map(z => z.metod + " " + z.putanja).join(","));
  zapisi("cena", "otvaranje Analize = tačno 2 GET (genome-v2 + promene), 0 upisa",
    zahtevi(s, /genome-v2$/, "GET").length === 1 && zahtevi(s, /genome-v2\/promene$/, "GET").length === 1 && s.f.zahtevi.every(z => z.metod === "GET"),
    s.f.zahtevi.map(z => z.metod + " " + z.putanja).join(","));
  // povratak na Pregled i nazad: bez novog čitanja
  await s.p.click("#tab-pregled"); await cekaj(s.p, () => !document.getElementById("odeljak-pregled").hidden);
  await s.p.click("#tab-analiza"); await cekaj(s.p, () => !document.getElementById("odeljak-analiza").hidden);
  zapisi("cena", "povratak na Analizu ne čita ponovo", zahtevi(s, /genome-v2$/).length === 1);
  // izvor → Dokumenti sa izabranim dokumentom
  await s.p.click("#an-kontr-aktivne button.an-src >> text=/Dostavnica/");
  const otvoren = await cekaj(s.p, (id) => location.hash.endsWith("/dokumenti") && document.querySelector(`#dok-lista [data-dok="${id}"]`)?.getAttribute("aria-current") === "true", D2);
  zapisi("izvor", "„Izvor: Dostavnica“ otvara Dokumente sa izabranim dokumentom (bez mrtvog linka)", otvoren && zahtevi(s, new RegExp(`/dokumenti/${D2}/preview$`)).length === 1);
  zapisi("bezbednost", "0 spoljnih zahteva", s.spoljni.length === 0, s.spoljni.slice(0, 2).join(","));
  await s.zatvori();
}

// ── 2. Lenjo: Pregled ne čita Analizu ────────────────────────────────────────
{
  const s = await scenario({ hash: `#/predmeti/${PA}` });
  await cekaj(s.p, () => !document.getElementById("odeljak-pregled").hidden);
  await s.p.waitForTimeout(300);
  zapisi("cena", "Pregled ne čita pun Genome (samo promene, Task 11)", zahtevi(s, /genome-v2$/).length === 0 && zahtevi(s, /genome-v2\/promene$/).length === 1);
  await s.zatvori();
}

// ── 3. Izvor nije pročitan → DEGRADED, nikad „0" ─────────────────────────────
{
  const s = await scenario({ izvor: SA_PADOM });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("degradirano", "dokazi: „Nije dostupno“ umesto prazne liste ili 0", /Nije dostupno — izvor podataka trenutno nije pročitan/.test(e.dokazStanje || "") && !/0 tvrdnji/.test(e.ceo), e.dokazStanje);
  zapisi("degradirano", "stanje sekcije je GREŠKA, ne PRAZNO (FAILED ≠ EMPTY)", e.dokazStanjeVrsta === "greska", e.dokazStanjeVrsta);
  const sp = Object.fromEntries(e.spremnost.map(x => [x[0], [x[1], x[2]]]));
  zapisi("degradirano", "pokazatelji iz palog izvora su „Nije dostupno“, ostali važe",
    sp.pokrivenost_procene[0] === "DEGRADED" && /Nije dostupno/.test(sp.pokrivenost_procene[1]) && sp.operativna_spremnost[0] === "OK", JSON.stringify(sp));
  await s.zatvori();
}

// ── 3b. Skraćen odgovor (granica 500) se kaže, ne predstavlja se kao ceo predmet ──
{
  const s = await scenario({ kuke: { izmeni: (put, t) => /genome-v2$/.test(put) ? { ...t, metapodaci: { ...t.metapodaci, skraceno: { dokazi: true, dokumenti: false } } } : null } });
  await gotovo(s.p);
  const sk = await s.p.evaluate(() => { const n = document.getElementById("an-skraceno"); return n.hidden ? null : [n.dataset.stanje, n.textContent]; });
  zapisi("granica", "skraćena lista tvrdnji: vidljivo „brojevi NISU potpuni“", !!sk && sk[0] === "nepotpuno" && /tvrdnji je skraćena na prvih 500/.test(sk[1]) && /NISU potpuni/.test(sk[1]), JSON.stringify(sk));
  await s.zatvori();
  const s2 = await scenario();
  await gotovo(s2.p);
  zapisi("granica", "potpun odgovor: bez upozorenja o skraćivanju", await s2.p.evaluate(() => document.getElementById("an-skraceno").hidden));
  await s2.zatvori();
}

// ── 4. Greške ────────────────────────────────────────────────────────────────
for (const [status, ocekivano] of [[500, /Analiza nije učitana zbog greške na serveru/], [404, /Predmet nije dostupan/]]) {
  const s = await scenario({ kuke: { pre: (put) => /genome-v2$/.test(put) ? { status, telo: { detail: "x" } } : null } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("greska", `${status} → jasna poruka, bez sadržaja`, !e.sadrzaj && ocekivano.test(e.stanje || ""), e.stanje);
  await s.zatvori();
}

// ── 5. Zastarela sesija: odgovor za A ne sme da se iscrta posle prelaska na B ──
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ kuke: { pre: async (put, k) => { if (k === "A" && /genome-v2/.test(put)) await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("an-stanje").dataset.stanje === "ucitavanje");
  await s.p.evaluate(([k, v]) => { localStorage.setItem(k, v); window.dispatchEvent(new StorageEvent("storage", { key: k, newValue: v })); }, [KLJUC, ses("kB", TB)]);
  await s.p.waitForTimeout(400);
  pusti();
  await s.p.waitForTimeout(600);
  const e = await ekran(s.p);
  zapisi("sesija", "posle prelaska A→B nijedan podatak predmeta A nije na ekranu",
    !e.sadrzaj && !/Rešenje je uručeno|datum uručenja rešenja|Gradnja Invest|480\.000/.test(e.ceo), (e.stanje || "") + " | " + e.ceo.slice(0, 80));
  await s.zatvori();
}

// ── 5b. Isti korisnik prelazi na DRUGI predmet: genome-v2 za A je STIGAO, promene za A kasne ──
// (abort tada pogađa samo promene; iscrtavanje A sprečava jedino provera generacije)
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const DRUGI = "kA-00001";
  const s = await scenario({ kuke: { pre: async (put) => { if (put.includes(PA) && /genome-v2\/promene$/.test(put)) await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("an-stanje").dataset.stanje === "ucitavanje");
  await s.p.evaluate((h) => { location.hash = h; }, `#/predmeti/${DRUGI}/analiza`);
  const drugiGotov = await cekaj(s.p, () => document.getElementById("an-stanje").dataset.stanje === "greska");
  pusti();
  await s.p.waitForTimeout(700);
  const e = await ekran(s.p);
  zapisi("sesija", "zakasneli odgovor predmeta A se NE iscrtava na drugom predmetu istog korisnika",
    drugiGotov && !e.sadrzaj && /Predmet nije dostupan/.test(e.stanje || "") && !/Rešenje je uručeno|datum uručenja rešenja/.test(e.ceo + e.sav),
    (e.stanje || "") + " | sadrzaj=" + e.sadrzaj);
  await s.zatvori();
}

// ── 6. Tekst iz baze se ne izvršava ──────────────────────────────────────────
{
  const s = await scenario({ kuke: { izmeni: (put, t) => { if (/genome-v2$/.test(put) && t.dokazi) { t.dokazi.tvrdnje[0].vrednost = "<img src=x onerror=window.__xss=1>"; } return t; } } });
  await gotovo(s.p);
  const e = await ekran(s.p);
  zapisi("bezbednost", "HTML u tvrdnji se prikazuje kao tekst, ne izvršava", e.xss === null && /<img src=x onerror=/.test(e.dokazi));
  await s.zatvori();
}

// ── 7. Responzivno i teme ────────────────────────────────────────────────────
for (const [w, tema] of [[390, "dark"], [390, "light"], [1440, "light"], [1280, "dark"]]) {
  const s = await scenario({ w, h: 860, tema });
  await gotovo(s.p);
  const m = await s.p.evaluate(() => ({ preliv: document.documentElement.scrollWidth - window.innerWidth,
    tabovi: (() => { const t = document.querySelector(".tabs"); return getComputedStyle(t).overflowX; })(),
    analizaVidljiva: (() => { const a = document.getElementById("tab-analiza"); const r = a.getBoundingClientRect(); return r.width > 0; })(),
    pozadina: getComputedStyle(document.body).backgroundColor, tekst: getComputedStyle(document.querySelector("#an-dokazi .an-item__text")).color }));
  zapisi("raspored", `${w}px/${tema}: bez vodoravnog preliva stranice; kartice se pomeraju unutar trake`,
    m.preliv <= 0 && m.tabovi === "auto" && m.analizaVidljiva && m.pozadina !== m.tekst, JSON.stringify(m));
  await s.zatvori();
}

// ── 8. Bočni meni nepromenjen (bez novog modula) ──────────────────────────────
{
  const s = await scenario();
  await gotovo(s.p);
  const nav = await s.p.evaluate(() => [...document.querySelectorAll(".sidenav__item")].filter(a => a.getClientRects().length).map(a => a.textContent.trim()));
  // Uklanjanje nedovršenih modula je ugovor PRIMARNOG /app (e2e:primary P3/P9); ovde: Analiza NIJE modul bočnog menija.
  zapisi("navigacija", "Analiza nije nov modul bočnog menija (samo kartica predmeta)", !nav.some(x => /Analiza/.test(x)) && nav.includes("Predmeti"), nav.join(","));
  await s.zatvori();
}

await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
zapisi("bezbednost", "nijedan token u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
