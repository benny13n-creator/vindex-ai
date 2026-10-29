// Vindex V2 NG — CG001: advokat razlikuje sačuvanu vezu, najnovije AI opažanje i nepotvrđen kontinuitet
// (incident „TEST — Bojan E2E / Evidencija uplate“, 28.10.2026). Pokretanje: `node tests/live-cg001-kontinuitet.mjs`.
//
// Odgovori API-ja NISU ručno pisani: tests/cg001_ui_fixture.py nad zatečenim produkcionim stanjem (V2 {A,B}, Genome
// v1→v2 {A,C,D}) izvršava STVARNI backend (događaj → refresh → reconcile akcija → rute) i vraća tačna tela odgovora.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-cg-A-NE-U-LOG-41", TB = "vx-cg-B-NE-U-LOG-87";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/cg001_ui_fixture.py"],
  { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
if (!red) { console.log((r.stderr || "").slice(-2000)); throw new Error("cg001_ui_fixture.py nije vratio rezultat"); }
const STVARNO = JSON.parse(red.slice(2));
const { P, D1, D2 } = STVARNO;
zapisi("backend", "stvarni odgovori učitani; čitanje nije pozvalo model", STVARNO.model_pozvan_pri_citanju === 0
  && Object.keys(STVARNO.odgovori).length === 6, String(STVARNO.model_pozvan_pri_citanju));

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, ms = 12000) => p.waitForFunction(fn, null, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 1), B = napraviPredmete("kB", 1);
  A[0].id = P; A[0].naziv = "TEST — Bojan E2E / Evidencija uplate"; A[0].tip = "ostalo";
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}
const DOKUMENTI = () => ({ [P]: [D1, D2].map((id, i) => ({ id, predmet_id: P, user_id: "kA",
  naziv_fajla: ["Vindex_TEST_01_Beleska_klijenta.pdf", "Vindex_TEST_02_Interna_evidencija.pdf"][i], status: "indeksirano",
  velicina_kb: 20, redni_broj: i + 1, tip_dokaza: "dopis", created_at: "2026-10-28T21:58:00Z", tekst_sadrzaj: "TEKST-" + i })) });

function ziviRuta(odgovori = STVARNO.odgovori) {
  const tok = { [TA]: "A", [TB]: "B" };
  return async (req, url, res) => {
    if (!/^\/api\/(predmeti\/[^/]+\/genome-v2(\/promene)?|case-actions\/predmeti\/[^/]+|case-actions\/worklist|workspace)$/.test(url.pathname)) return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    const o = odgovori[`${k}|${url.pathname}`] || STVARNO.odgovori[`B|/api/predmeti/${P}/genome-v2`];
    json(res, o.status, o.telo);
    return true;
  };
}

async function scenario({ hash, tema = "dark", token = TA, korisnik = "kA", w = 1440, h = 900, odgovori }) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(ziviRuta(odgovori), predmetiRuta(KOR), predmetDetaljRuta(KOR, DOKUMENTI())));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", rr => { const u = new URL(rr.request().url()); if (u.hostname === "127.0.0.1") return rr.continue(); spoljni.push(u.href); return rr.abort(); });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, ses(korisnik, token), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

// ── 1. Analiza: sačuvana veza ≠ najnovije opažanje (obe teme, i uzan ekran) ─────────────────────
for (const [tema, w] of [["dark", 1440], ["light", 1440], ["dark", 390]]) {
  const s = await scenario({ hash: `#/predmeti/${P}/analiza`, tema, w });
  const ok = await cekaj(s.p, () => !document.getElementById("an-sadrzaj").hidden);
  const e = await s.p.evaluate(() => {
    const li = (id) => [...document.querySelectorAll("#" + id + " > li")];
    const dim = document.querySelector("#an-spremnost dd[data-dim='kontradikcije'] .an-dim__value");
    return {
      akt: li("an-kontr-aktivne").map(x => ({ stanje: x.dataset.stanje, tekst: x.innerText.replace(/\s+/g, " "), n: x.querySelectorAll(".an-sub > li").length })),
      pr: li("an-kontr-pregled").map(x => ({ stanje: x.dataset.stanje, tekst: x.innerText.replace(/\s+/g, " "), n: x.querySelectorAll(".an-sub > li").length })),
      promene: li("an-promene").map(x => [x.dataset.oznaka, x.innerText.replace(/\s+/g, " ").trim()]),
      dim: dim ? dim.textContent : null,
      sekcija: document.getElementById("an-kontr-naslov").closest("section").innerText,
      sirina: document.documentElement.scrollWidth, prozor: window.innerWidth,
    };
  });
  const g = `analiza ${tema} ${w}`;
  zapisi(g, "sadržaj prikazan", ok);
  const a = e.akt[0] || { tekst: "" }, p = e.pr[0] || { tekst: "" };
  zapisi(g, "sačuvana veza ostaje aktivna sa svoja 2 učesnika i težinom „manja“", e.akt.length === 1 && a.n === 2 && a.stanje === "AKTIVNA"
    && /težina: manja/.test(a.tekst) && /40\.000/.test(a.tekst) && /80\.000/.test(a.tekst), a.tekst.slice(0, 160));
  zapisi(g, "sačuvana veza kaže da kontinuitet nije potvrđen i da je iz ranije analize", /kontinuitet nije potvrđen/.test(a.tekst)
    && /Sačuvana veza iz ranije analize/.test(a.tekst), a.tekst.slice(0, 260));
  zapisi(g, "najnovije opažanje je posebno, „traži vaš pregled“, 3 učesnika, oba dokumenta, „kritična“", e.pr.length === 1 && p.n === 3
    && /traži vaš pregled/.test(p.tekst) && /kritična/.test(p.tekst) && /30\.000/.test(p.tekst) && /Najnovija analiza/.test(p.tekst)
    && /Vindex_TEST_01/.test(p.tekst) && /Vindex_TEST_02/.test(p.tekst), p.tekst.slice(0, 260));
  zapisi(g, "istorija: nerazrešena promena, ne „više se ne opaža“", e.promene.some(([o, t]) => o === "!" && /kontinuitet sporne tačke nije potvrđen/.test(t))
    && !e.promene.some(([, t]) => /više ne opaža|Nova kontradikcija/.test(t)), JSON.stringify(e.promene));
  zapisi(g, "spremnost broji 1 za pregled", /1 traži pregled/.test(e.dim || ""), e.dim);
  zapisi(g, "advokat ne vidi UUID ni interna stanja", !UUID.test(e.sekcija) && !/NIJE_POTVRDJEN|REVIEW_REQUIRED|OPEN\b/.test(e.sekcija));
  zapisi(g, "bez horizontalnog skrola", e.sirina <= e.prozor, `${e.sirina}/${e.prozor}`);
  const pisanja = s.f.zahtevi.filter(z => z.metod !== "GET");
  zapisi(g, "čitanje analize ne šalje nijedan upis/AI poziv", pisanja.length === 0, JSON.stringify(pisanja.map(z => z.putanja)));
  zapisi(g, "ništa spolja", s.spoljni.length === 0, s.spoljni.join(","));
  await s.zatvori();
}

// ── 2. Pregled: radnja nosi isti signal, isti prioritet ──────────────────────────────────────
{
  const s = await scenario({ hash: `#/predmeti/${P}` });
  await cekaj(s.p, () => !document.getElementById("zp-blok").hidden && document.getElementById("zp-sledece").children.length > 0);
  const e = await s.p.evaluate(() => ({
    sve: [...document.querySelectorAll("#zp-paznja > li, #zp-sledece > li")].map(x => [x.dataset.prioritet, x.innerText.replace(/\s+/g, " ")]),
    promene: [...document.querySelectorAll("#zp-promene > li")].map(x => x.innerText.replace(/\s+/g, " ")),
  }));
  // „Šta traži pažnju“ prikazuje samo kritične i visoke: nepotvrđen predlog modela („kritična“) NE sme podići radnju tamo.
  zapisi("pregled", "radnja nad sačuvanom vezom nije eskalirana među „traži pažnju“",
    !e.sve.some(([pr, t]) => /Razrešiti protivrečnost/.test(t) && (pr === "critical" || pr === "high")), JSON.stringify(e.sve));
  const akc = STVARNO.odgovori[`A|/api/case-actions/predmeti/${P}`].telo.akcije.filter(a => a.tip === "RAZRESITI_KONTRADIKCIJU" && a.status === "open");
  zapisi("radnje", "jedna otvorena radnja, prioritet srednji, razlog kaže da kontinuitet nije potvrđen", akc.length === 1
    && akc[0].prioritet === "medium" && /kontinuitet nije potvrđen/.test(akc[0].razlog), JSON.stringify(akc.map(a => [a.prioritet, a.razlog])));
  zapisi("pregled", "promene: nerazrešena, ne „nestala“", e.promene.some(t => /kontinuitet sporne tačke nije potvrđen/.test(t))
    && !e.promene.some(t => /više ne opaža/.test(t)), JSON.stringify(e.promene));
  await s.zatvori();
}

// ── 2b. Odmah posle deploy-a, BEZ događaja i reconcile-a: radnja upisana starim kodom (CG001 Task 1) ──────────────
{
  const BEZ = STVARNO.bez_dogadjaja;
  zapisi("posle deploy-a", "zatečen red nema oznaku; čitanje ništa ne upisuje i ne zove model",
    !/kontinuitet/.test(BEZ.upisan_razlog) && BEZ.citanje_upisalo === false && BEZ.model_pozvan === 0, BEZ.upisan_razlog);
  const PAT = /kontinuitet nije potvrđen/;
  {
    const s = await scenario({ hash: "#/danas", odgovori: BEZ.odgovori });
    await cekaj(s.p, () => document.querySelectorAll("#rl-korpe li[data-vrsta='case_action']").length > 0);
    const e = await s.p.evaluate(() => [...document.querySelectorAll("#rl-korpe li[data-vrsta='case_action']")]
      .map(x => [x.dataset.prioritet, x.innerText.replace(/\s+/g, " ")]));
    const r = e.filter(([, t]) => /Razlika u iznosu uplate/.test(t));
    zapisi("posle deploy-a", "Danas/radna lista: A/B radnja kaže da kontinuitet nije potvrđen, prioritet srednji",
      r.length === 1 && PAT.test(r[0][1]) && r[0][0] === "medium", JSON.stringify(e));
    await s.zatvori();
  }
  {
    const s = await scenario({ hash: `#/predmeti/${P}`, odgovori: BEZ.odgovori });
    await cekaj(s.p, () => !document.getElementById("zp-blok").hidden && document.getElementById("zp-sledece").children.length > 0);
    const e = await s.p.evaluate(() => [...document.querySelectorAll("#zp-paznja > li, #zp-sledece > li")]
      .map(x => [x.dataset.prioritet, x.innerText.replace(/\s+/g, " ")]));
    const r = e.filter(([, t]) => /Razlika u iznosu uplate/.test(t));
    zapisi("posle deploy-a", "detalj predmeta: radnja (ako je prikazana) nosi oznaku i nije eskalirana",
      r.every(([pr, t]) => PAT.test(t) && pr !== "critical" && pr !== "high"), JSON.stringify(e));
    await s.zatvori();
  }
  for (const ruta of [`/api/case-actions/predmeti/${P}`, "/api/case-actions/worklist", "/api/workspace"]) {
    const t = BEZ.odgovori[`A|${ruta}`].telo;
    const akc = ruta === "/api/workspace" ? ["danas", "kriticno", "predstojece"].flatMap(k => t[k]).filter(x => x.predmet_id === P).map(x => ({ prioritet: x.prioritet, razlog: x.naslov }))
      : ruta.endsWith("worklist") ? t.predmeti.filter(c => c.predmet_id === P).flatMap(c => c.akcije) : t.akcije;
    zapisi("posle deploy-a", `${ruta}: jedna radnja, medium, sa oznakom`, akc.length === 1 && akc[0].prioritet === "medium" && PAT.test(akc[0].razlog),
      JSON.stringify(akc.map(a => [a.prioritet, a.razlog])));
    const tb = BEZ.odgovori[`B|${ruta}`];
    zapisi("posle deploy-a", `${ruta}: korisnik B ne dobija predmet A`, ruta.includes("/predmeti/") ? tb.status === 404
      : !JSON.stringify(tb.telo).includes(P), String(tb.status));
  }
  const kon = BEZ.odgovori[`A|/api/predmeti/${P}/genome-v2`].telo.kontradikcije;
  zapisi("posle deploy-a", "analiza: A/B označena, A/C/D za pregled — isto što i radnja",
    kon.aktivne.length === 1 && kon.aktivne[0].kontinuitet === "NIJE_POTVRDJEN" && kon.za_pregled.length === 1);
}

// ── 2c. Čitanje usred osvežavanja (CG001 Task 3): kontinuitet NIJE PROVEREN, ne „potvrđen“ i ne iz ustajalog opažanja ──
{
  const US = STVARNO.usred_osvezavanja;
  const s = await scenario({ hash: `#/predmeti/${P}/analiza`, odgovori: US.odgovori });
  await cekaj(s.p, () => !document.getElementById("an-sadrzaj").hidden);
  const e = await s.p.evaluate(() => ({
    akt: [...document.querySelectorAll("#an-kontr-aktivne > li")].map(x => x.innerText.replace(/\s+/g, " ")),
    pr: [...document.querySelectorAll("#an-kontr-pregled > li")].length,
    sekcija: document.getElementById("an-kontr-naslov").closest("section").innerText,
  }));
  zapisi("usred osvežavanja", "aktivna veza: „kontinuitet nije proveren“, bez „traži pregled“ iz starog opažanja",
    e.akt.length === 1 && /kontinuitet nije proveren/.test(e.akt[0]) && !/kontinuitet nije potvrđen/.test(e.akt[0]) && e.pr === 0, JSON.stringify(e.akt));
  zapisi("usred osvežavanja", "bez internih stanja na ekranu", !/NEPOZNAT|NIJE_POTVRDJEN/.test(e.sekcija));
  await s.zatvori();
  const akc = US.odgovori[`A|/api/case-actions/predmeti/${P}`].telo.akcije;
  zapisi("usred osvežavanja", "radnja: ista, medium, „kontinuitet nije proveren“", akc.length === 1 && akc[0].prioritet === "medium"
    && /kontinuitet nije proveren/.test(akc[0].razlog), JSON.stringify(akc.map(a => a.razlog)));
  zapisi("usred osvežavanja", "čitanje ništa ne upisuje", US.citanje_upisalo === false && US.model_pozvan === 0);
}

// ── 3. Drugi korisnik ────────────────────────────────────────────────────────────────────────
{
  const s = await scenario({ hash: `#/predmeti/${P}/analiza`, token: TB, korisnik: "kB" });
  await s.p.waitForTimeout(1500);
  const e = await s.p.evaluate(() => document.body.innerText);
  zapisi("izolacija", "tuđ korisnik ne vidi iznose, tvrdnje ni sporne tačke", !/40\.000|30\.000|Razlika u iznosu uplate/.test(e));
  await s.zatvori();
}

await browser.close();
const greske = konzola.filter(x => /PAGEERROR|TypeError|ReferenceError/.test(x));
zapisi("konzola", "bez JS grešaka", greske.length === 0, greske.slice(0, 3).join(" | "));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
