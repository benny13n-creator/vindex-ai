// Vindex V2 NG — NS008 Task 13–14: Law Brain u Znanju i u Analizi predmeta.
// Pokretanje: `node tests/live-law-brain.mjs`. Odgovori API-ja su STVARNI odgovori Law Brain ruta
// (tests/ns008_ui_fixture.py), ne ručno pisani JSON.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-lb-A-NE-U-LOG-41", TB = "vx-lb-B-NE-U-LOG-42";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend() {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns008_ui_fixture.py"],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log((r.stderr || "").slice(-2000)); throw new Error("ns008_ui_fixture.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const S = backend();
const { PA_CUR, PB_CUR } = S;
zapisi("backend", "čitanje bez modela; jedna sinteza = jedan poziv i jedan kredit",
  S.model_pozvan_pri_citanju === 0 && S.model_pozvan_ukupno === 1 && S.krediti.length === 1, JSON.stringify(S.krediti));

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 1), B = napraviPredmete("kB", 1);
  A[0].id = PA_CUR; A[0].naziv = "A tekući";
  B[0].id = PB_CUR; B[0].naziv = "B tekući";
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}

/** Tačno telo koje je backend vratio za (korisnik, metod, putanja); `oznaka` bira varijantu (npr. #degradirano). */
function lbRuta(kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  return async (req, url, res) => {
    const p = url.pathname;
    if (!p.startsWith("/api/law-brain/") && !/^\/api\/predmeti\/[^/]+\/genome-v2(\/promene)?$/.test(p) && !/^\/api\/autonomy\/work-items\/[^/]+$/.test(p)) return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    if (/genome-v2/.test(p)) { json(res, 404, { detail: "Predmet nije pronađen." }); return true; }
    if (kuke.pre) { const z = await kuke.pre({ p, k, metod: req.method }); if (z) { json(res, z.status, z.telo); return true; } }
    const o = S.odgovori[`${k}|${req.method}|${p}${kuke.oznaka || ""}`] || S.odgovori[`${k}|${req.method}|${p}`]
      || { status: 404, telo: { detail: "Predmet nije pronađen." } };
    json(res, o.status, o.telo);
    return true;
  };
}

async function scenario({ kuke = {}, hash = "#/znanje", w = 1440, h = 900, tema = "dark", korisnik = "kA", token = TA } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(lbRuta(kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([kl, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(kl, v); } }, [KLJUC, ses(korisnik, token), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, zatvori: async () => { await ctx.close(); await f.zatvori(); } };
}
const lb = (s) => s.f.zahtevi.filter(z => z.putanja.startsWith("/api/law-brain/") && !z.putanja.startsWith("/api/law-brain/rad/"));
const lbSve = (s) => s.f.zahtevi.filter(z => z.putanja.startsWith("/api/law-brain/"));
const tekstStranice = (p) => p.evaluate(() => document.body.innerText);

// ── Znanje: A ──
{
  const s = await scenario();
  const ok = await cekaj(s.p, () => !document.getElementById("lb-sadrzaj").hidden);
  zapisi("znanje", "otvaranje Znanja učitava iskustvo kancelarije", ok);
  const r = await s.p.evaluate(() => {
    const lista = (id) => [...document.querySelectorAll("#" + id + " > .an-item")].map(li => ({ t: li.innerText, trust: li.dataset.trust }));
    return { isk: lista("lb-iskustvo"), rad: lista("lb-radovi"), lek: lista("lb-lekcije"), mem: lista("lb-memorija"),
      kand: (document.querySelector("#lb-lekcije .lb-kandidati") || {}).textContent || "",
      slojevi: document.getElementById("lb-slojevi").innerText,
      ids: [...document.querySelectorAll("[id]")].map(e => e.id) };
  });
  zapisi("znanje", "raniji predmeti po vrsti: opis sa imeniocem, bez procenata",
    r.isk.length === 1 && /radni — 1 završen predmet/.test(r.isk[0].t) && /1 nagodba/.test(r.isk[0].t) && /Veličina uzorka: 1/.test(r.isk[0].t)
      && /Mali uzorak/.test(r.isk[0].t) && !/%/.test(r.isk[0].t), r.isk[0] && r.isk[0].t.replace(/\n/g, " | "));
  zapisi("znanje", "verifikovani rad nosi oznaku „Overio advokat” i predmet",
    r.rad.length === 1 && r.rad[0].trust === "LAWYER_VERIFIED_ARTIFACT" && /Overio advokat/.test(r.rad[0].t) && /Petrović protiv Gradnja Invest DOO/.test(r.rad[0].t));
  zapisi("važenje", "overen rad koji se poziva na propis traži proveru izmena (bez tvrdnje da je aktuelan)",
    /proverite da li su u međuvremenu izmenjeni/.test(r.rad[0].t) && !/aktuelan|važeći/.test(r.rad[0].t), r.rad[0].t.replace(/\n/g, " | "));
  zapisi("znanje", "samo potvrđena lekcija; predlog AI samo kao broj koji čeka potvrdu",
    r.lek.length === 1 && /Pribaviti pisane dokaze rano/.test(r.lek[0].t) && !/AI predlog/.test(r.lek.map(x => x.t).join()) && /1 predlog lekcije čeka/.test(r.kand));
  const sudija = r.mem.find(x => /Traži tabelu rokova/.test(x.t));
  zapisi("znanje", "beleška kolege je beleška, ne činjenica",
    !!sudija && sudija.trust === "HUMAN_MEMORY_NOTE" && /nije proverena činjenica/.test(sudija.t) && /Beleška kolege/.test(sudija.t));
  const xss = await s.p.evaluate(() => ({ img: document.querySelectorAll("#lb-memorija img, #lb-memorija script, #lb-memorija b").length,
    flag: window.__xss || null, tekst: [...document.querySelectorAll("#lb-memorija > .an-item")].map(x => x.innerText).join(" ") }));
  zapisi("trovanje", "HTML/script u belešci se crta kao tekst (nema elementa, nema izvršavanja)",
    xss.img === 0 && xss.flag === null && /<img src=x onerror=/.test(xss.tekst) && /<script>/.test(xss.tekst), JSON.stringify({ img: xss.img, flag: xss.flag }));
  zapisi("znanje", "objašnjenje tri vrste znanja (zakon / kancelarija / AI)",
    /Zakon i sudska praksa/.test(r.slojevi) && /Znanje kancelarije/.test(r.slojevi) && /AI analiza/.test(r.slojevi) && /ne pravni izvor/.test(r.slojevi));
  zapisi("znanje", "nema duplih ID-eva", new Set(r.ids).size === r.ids.length, String(r.ids.length - new Set(r.ids).size));
  const z = lb(s);
  zapisi("trošak", "otvaranje: tačno 1 GET Law Brain, 0 POST (nema modela ni kredita)",
    z.length === 1 && z[0].metod === "GET" && z[0].putanja === "/api/law-brain/znanje", JSON.stringify(z.map(x => x.metod + " " + x.putanja)));
  await s.p.fill("#lb-filter", "pribaviti");
  const filt = await s.p.evaluate(() => ["lb-iskustvo", "lb-radovi", "lb-lekcije", "lb-memorija"].map(id => [...document.querySelectorAll("#" + id + " > .an-item")].filter(li => !li.hidden).length));
  zapisi("znanje", "filter je lokalan (bez zahteva) i sužava prikaz", filt.join() === "0,0,1,0" && lb(s).length === 1, filt.join());
  zapisi("izolacija", "nijedan spoljni zahtev", s.spoljni.length === 0, s.spoljni.join());
  await s.zatvori();
}

// ── Znanje: B (ista kancelarija) ne vidi A ──
{
  const s = await scenario({ korisnik: "kB", token: TB });
  await cekaj(s.p, () => !document.getElementById("lb-sadrzaj").hidden);
  const t = await tekstStranice(s.p);
  zapisi("poverljivost", "B ne vidi A-ov predmet, rad, lekciju ni ishod",
    !/Petrović protiv/.test(t) && !/Tekst tužbe/.test(t) && !/Pribaviti/.test(t) && !/nagodba/.test(t));
  zapisi("poverljivost", "B vidi opštu belešku o sudiji (deljena u kancelariji)", /Traži tabelu rokova/.test(t));
  zapisi("poverljivost", "B: iskreno prazno iskustvo", /Još nema završenih predmeta/.test(t));
  await s.zatvori();
}

// ── Znanje: izvor pao → nedostupno, ne prazno ──
{
  const s = await scenario({ kuke: { oznaka: "#degradirano" } });
  await cekaj(s.p, () => !document.getElementById("lb-sadrzaj").hidden);
  const st = await s.p.evaluate(() => { const n = document.getElementById("lb-mem-stanje"); return n.hidden ? null : n.dataset.stanje + ":" + n.textContent; });
  zapisi("stanja", "memorija pala → „Nije dostupno — izvor nije pročitan”, nikad „Nema beleški”",
    !!st && st.startsWith("greska:") && /Nije dostupno/.test(st) && !/Nema beleški/.test(st), st);
  await s.zatvori();
}

// ── Znanje: ceo zahtev pao → greška, ne prazno ──
{
  const s = await scenario({ kuke: { pre: () => ({ status: 503, telo: { detail: "x" } }) } });
  const ok = await cekaj(s.p, () => { const n = document.getElementById("lb-stanje"); return !n.hidden && n.dataset.stanje === "greska"; });
  const t = await s.p.evaluate(() => document.getElementById("lb-stanje").textContent);
  zapisi("stanja", "503 → greška sa „ne znači da ga nema”", ok && /ne znači da ga nema/.test(t) && await s.p.evaluate(() => document.getElementById("lb-sadrzaj").hidden), t);
  await s.zatvori();
}

// ── Predmet → Analiza → Iskustvo kancelarije (Task 14) ──
const ANALIZA = (pid) => `#/predmeti/${encodeURIComponent(pid)}/analiza`;
{
  const s = await scenario({ hash: ANALIZA(PA_CUR) });
  const ok = await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  zapisi("predmet", "Analiza učitava iskustvo kancelarije kao sekundarnu sekciju", ok);
  const r = await s.p.evaluate(() => {
    const li = (id) => [...document.querySelectorAll("#" + id + " > .an-item")].map(x => x.innerText);
    return { sl: li("lbp-slicni"), rad: li("lbp-radovi"), lek: li("lbp-lekcije"), is: li("lbp-ishodi"), mem: li("lbp-memorija"),
      prazno: !document.getElementById("lbp-prazno").hidden, tabovi: [...document.querySelectorAll(".matter__tabs a, [role=tab]")].map(a => a.textContent.trim()),
      ids: [...document.querySelectorAll("[id]")].map(e => e.id) };
  });
  zapisi("predmet", "sličan raniji predmet sa razlogom i ljudskim ishodom",
    r.sl.length === 1 && /Petrović protiv Gradnja Invest DOO/.test(r.sl[0]) && /Sličan jer:/.test(r.sl[0]) && /Ishod \(uneo advokat\): nagodba/.test(r.sl[0]), r.sl[0]);
  zapisi("predmet", "overen rad, potvrđena lekcija, opis ishoda sa imeniocem",
    r.rad.length === 1 && /Overio advokat/.test(r.rad[0]) && r.lek.length === 1 && r.is.some(x => /Veličina uzorka: 1/.test(x)) && !r.is.join().includes("%"));
  zapisi("predmet", "nema „nema iskustva” kada iskustvo postoji", r.prazno === false);
  zapisi("predmet", "nema duplih ID-eva", new Set(r.ids).size === r.ids.length);
  zapisi("trošak", "otvaranje Analize: 1 GET konteksta, 0 sinteza",
    lb(s).length === 1 && lb(s)[0].metod === "GET" && lb(s)[0].putanja === `/api/law-brain/predmeti/${PA_CUR}`, JSON.stringify(lb(s).map(z => z.metod + " " + z.putanja)));

  await s.p.click("#lbp-analiziraj");
  const gotovo = await cekaj(s.p, () => document.querySelectorAll("#lbp-sinteza > .an-item").length > 0);
  const sin = await s.p.evaluate(() => ({ t: [...document.querySelectorAll("#lbp-sinteza > .an-item")].map(x => ({ t: x.innerText, v: x.dataset.vrsta })),
    st: document.getElementById("lbp-sinteza-stanje").textContent }));
  zapisi("sinteza", "izričit klik → tvrdnje sa izvorima i vrstom; odbačene nisu prikazane",
    gotovo && sin.t.length === 3 && sin.t.every(x => /izvori: R\d/.test(x.t)) && !sin.t.some(x => /80%|Šansa|Izmišljen/.test(x.t))
      && /Odbačeno tvrdnji bez izvora: 2/.test(sin.st) && /nije pravni savet/i.test(sin.st), JSON.stringify(sin).slice(0, 300));
  const posle = lb(s).filter(z => z.metod === "POST");
  zapisi("sinteza", "tačno 1 POST sinteze sa Idempotency-Key",
    posle.length === 1 && posle[0].putanja === `/api/law-brain/predmeti/${PA_CUR}/sinteza`);
  await s.zatvori();
}
{
  const s = await scenario({ hash: ANALIZA(PB_CUR), korisnik: "kB", token: TB });
  await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  const t = await tekstStranice(s.p);
  zapisi("predmet", "B: iskreno „nema proverenog iskustva”, bez A-ovih podataka",
    /kancelarija još nema proverenog iskustva/.test(t) && !/Petrović protiv/.test(t) && !/nagodba/.test(t) && !/Pribaviti/.test(t));
  await s.p.click("#lbp-analiziraj");
  const ok = await cekaj(s.p, () => { const n = document.getElementById("lbp-sinteza-stanje"); return !n.hidden && n.dataset.stanje === "prazno"; });
  const st = await s.p.evaluate(() => document.getElementById("lbp-sinteza-stanje").textContent);
  zapisi("sinteza", "bez osnova → poruka, bez tvrdnji (model nije pozvan)", ok && /nema proverenog iskustva/i.test(st), st);
  await s.zatvori();
}
{
  const s = await scenario({ hash: ANALIZA(PA_CUR), kuke: { oznaka: "#degradirano" } });
  await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  const st = await s.p.evaluate(() => { const n = document.getElementById("lbp-mem-stanje"); return n.hidden ? null : n.dataset.stanje + ":" + n.textContent; });
  zapisi("stanja", "beleške pale u predmetu → nedostupno, ne prazno", !!st && st.startsWith("greska:") && /Nije dostupno/.test(st), st);
  await s.zatvori();
}
{
  const s = await scenario({ hash: ANALIZA(PA_CUR), kuke: { pre: ({ metod }) => metod === "POST" ? { status: 503, telo: { detail: "x" } } : null } });
  await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  await s.p.click("#lbp-analiziraj");
  const ok = await cekaj(s.p, () => { const n = document.getElementById("lbp-sinteza-stanje"); return !n.hidden && n.dataset.stanje === "greska"; });
  const st = await s.p.evaluate(() => document.getElementById("lbp-sinteza-stanje").textContent);
  zapisi("sinteza", "503 → „Analiza nije izvršena. Kredit nije potrošen.”", ok && /Kredit nije potrošen/.test(st), st);
  await s.zatvori();
}
{
  const s = await scenario({ hash: ANALIZA(PA_CUR), kuke: { pre: ({ metod }) => metod === "POST" ? { status: 500, telo: { detail: "x" } } : null } });
  await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  await s.p.click("#lbp-analiziraj");
  const ok = await cekaj(s.p, () => { const n = document.getElementById("lbp-sinteza-stanje"); return !n.hidden && n.dataset.stanje === "greska"; });
  const st = await s.p.evaluate(() => document.getElementById("lbp-sinteza-stanje").textContent);
  zapisi("sinteza", "500 → „ishod nije poznat” (ne obećava da kredit nije potrošen)", ok && /Ishod analize nije poznat/.test(st) && !/Kredit nije/.test(st), st);
  await s.zatvori();
}
{
  const s = await scenario({ hash: ANALIZA(PA_CUR), w: 390, h: 844, tema: "light" });
  await cekaj(s.p, () => !document.getElementById("lbp-sadrzaj").hidden);
  const preliv = await s.p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  zapisi("raspored", "Analiza 390px light: bez horizontalnog prelivanja", preliv <= 0, String(preliv));
  await s.zatvori();
}

// ── Task 15: prihvaćen rad → izričit predlog znanja (staging) ──
{
  const s = await scenario({ hash: `#/pripremljeno/${S.W_ACC}` });
  const vid = await cekaj(s.p, () => !document.getElementById("vpr-sadrzaj").hidden);
  const blok = await s.p.evaluate(() => !document.getElementById("vpr-znanje-blok").hidden);
  zapisi("promocija", "prihvaćen rad nudi „Predloži kao znanje kancelarije”, bez automatskog upisa",
    vid && blok && lbSve(s).filter(z => z.metod === "POST").length === 0);
  await s.p.click("#vpr-predlozi-znanje");
  const ok = await cekaj(s.p, () => { const n = document.getElementById("vpr-znanje-poruka"); return !n.hidden && n.dataset.stanje === "ok"; });
  const t = await s.p.evaluate(() => document.getElementById("vpr-znanje-poruka").textContent);
  zapisi("promocija", "predlog → „čeka advokatsku overu” (staging pending, ne verifikovano)",
    ok && /čeka advokatsku overu/.test(t) && S.staging_posle_predloga.length === 1 && S.staging_posle_predloga[0].status === "pending"
      && S.staging_posle_predloga[0].is_lawyer_approved === false && S.staging_posle_predloga[0].pinecone_indexed === false, t);
  await s.zatvori();
}
{
  const s = await scenario({ hash: `#/pripremljeno/${S.W_READY}` });
  await cekaj(s.p, () => !document.getElementById("vpr-sadrzaj").hidden);
  const blok = await s.p.evaluate(() => !document.getElementById("vpr-znanje-blok").hidden);
  zapisi("promocija", "rad na pregledu (READY) nema opciju predloga znanja", blok === false);
  await s.zatvori();
}
zapisi("promocija", "ponovljen predlog vraća isti staging (bez duplikata)",
  S.odgovori[`A|POST|/api/law-brain/rad/${S.W_ACC}/predlozi-znanje#ponovo`].telo.staging_id === S.odgovori[`A|POST|/api/law-brain/rad/${S.W_ACC}/predlozi-znanje`].telo.staging_id
    && S.odgovori[`A|POST|/api/law-brain/rad/${S.W_ACC}/predlozi-znanje#ponovo`].telo.novo === false);

// ── Task 19: promena sesije usred spornog odgovora — A-ovi podaci nikad ne iscrtavaju za B ──
{
  let pusti = null;
  const zadrzan = new Promise(r => { pusti = r; });
  const s = await scenario({ kuke: { pre: async ({ k, p }) => { if (k === "A" && p === "/api/law-brain/znanje") await zadrzan; return null; } } });
  await cekaj(s.p, () => !document.getElementById("lb-stanje").hidden);
  const drugi = await s.ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${s.f.port}/src/tokens.css`);
  await drugi.evaluate(([kl, v]) => localStorage.setItem(kl, v), [KLJUC, ses("kB", TB)]);
  await cekaj(s.p, () => !document.getElementById("lb-sadrzaj").hidden && /Još nema završenih predmeta/.test(document.body.innerText));
  pusti();
  await s.p.waitForTimeout(600);
  const t = await tekstStranice(s.p);
  zapisi("sesija", "zakasneli A-ov odgovor posle prelaska na B se ne iscrtava",
    !/Petrović protiv/.test(t) && !/Pribaviti/.test(t) && !/nagodba/.test(t) && /Traži tabelu rokova/.test(t),
    JSON.stringify({ curenje: /Petrović protiv|Pribaviti|nagodba/.test(t), bVidi: /Traži tabelu rokova/.test(t), lb: lbSve(s).map(z => z.auth && z.auth.slice(-6)) }));
  await drugi.evaluate((kl) => localStorage.removeItem(kl), KLJUC);
  const prazno = await cekaj(s.p, () => document.getElementById("lb-sadrzaj").hidden && !document.querySelector("#lb-iskustvo > .an-item, #lb-memorija > .an-item"));
  zapisi("sesija", "odjava briše prikaz iskustva kancelarije", prazno);
  await s.zatvori();
}

// ── Znanje: svetla tema + mobilni ──
for (const [w, h, tema] of [[390, 844, "light"], [1440, 900, "light"]]) {
  const s = await scenario({ w, h, tema });
  await cekaj(s.p, () => !document.getElementById("lb-sadrzaj").hidden);
  const preliv = await s.p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  zapisi("raspored", `${w}px ${tema}: bez horizontalnog prelivanja`, preliv <= 0, String(preliv));
  await s.zatvori();
}

const greske = konzola.filter(x => /PAGEERROR|Uncaught/.test(x));
zapisi("konzola", "bez grešaka u stranici", greske.length === 0, greske.slice(0, 3).join(" | "));
await browser.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
