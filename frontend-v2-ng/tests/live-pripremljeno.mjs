// Vindex V2 NG — NS007 Task 15–16: „Vindex je pripremio" (Danas, pregled rada, Pregled predmeta).
// Pokretanje: `node tests/live-pripremljeno.mjs`. Odgovori API-ja su STVARNI odgovori posle STVARNOG autonomnog
// ciklusa (tests/ns007_ui_fixture.py), ne ručno pisani JSON.

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-vp-A-NE-U-LOG-31", TB = "vx-vp-B-NE-U-LOG-32";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
function backend() {
  const r = spawnSync(process.env.VX_PYTHON || "python", ["tests/ns007_ui_fixture.py"],
    { cwd: REPO, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, maxBuffer: 64 * 1024 * 1024 });
  const red = (r.stdout || "").split("\n").find(l => l.startsWith("@@"));
  if (!red) { console.log((r.stderr || "").slice(-2000)); throw new Error("ns007_ui_fixture.py nije vratio rezultat"); }
  return JSON.parse(red.slice(2));
}
const S = backend();
const { PA, PB } = S;
const HP = S.radovi.HEARING_PREP, PI = S.radovi.PRECEDENT_IMPACT;
const O = (k) => S.odgovori[k];
zapisi("backend", "stvarni ciklus: 2 pripremljena rada, 0 upisa van pregleda pri odluci",
  S.sazetak.spremno === 2 && !!HP && !!PI && S.upisi_van_pregleda === 0, JSON.stringify(S.sazetak).slice(0, 120));

const ses = (id, t) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const browser = await chromium.launch();
const konzola = [];

function korisnici() {
  const A = napraviPredmete("kA", 1), B = napraviPredmete("kB", 1);
  A[0].id = PA; A[0].naziv = "Petrović protiv Gradnja Invest DOO";
  B[0].id = PB; B[0].naziv = "Jovanović protiv Opštine";
  return { [TA]: { id: "kA", predmeti: A }, [TB]: { id: "kB", predmeti: B } };
}

/** API rad: tačno telo koje je backend vratio za (korisnik, metod, putanja); kuke menjaju/kasne/obaraju. */
function radRuta(kuke = {}) {
  const tok = { [TA]: "A", [TB]: "B" };
  return async (req, url, res) => {
    const p = url.pathname;
    if (p === "/api/rokovi/kandidati") { json(res, 200, { rokovi: [] }); return true; }
    if (p === "/api/kalendar/pregled") { json(res, 200, { dogadjaji: [] }); return true; }
    if (!/^\/api\/(workspace|autonomy\/work-items(\/[^/]+(\/(accept|reject))?)?|predmeti\/[^/]+\/genome-v2\/promene|case-actions\/predmeti\/[^/]+)$/.test(p)) return false;
    const k = tok[(req.headers.authorization || "").slice(7)];
    if (!k) { json(res, 401, { detail: "Prijava je obavezna" }); return true; }
    const metod = req.method;
    let telo = "";
    if (metod === "POST") { for await (const c of req) telo += c; }
    if (kuke.pre) { const z = await kuke.pre({ p, k, metod, url, telo, zaglavlja: req.headers }); if (z) { json(res, z.status, z.telo); return true; } }
    if (res.destroyed) return true;
    let kljuc = `${k}|${metod}|${p}`;
    if (p === "/api/autonomy/work-items" && url.searchParams.get("matter_id")) kljuc += `?matter_id=${url.searchParams.get("matter_id")}`;
    const o = S.odgovori[kljuc] || (p.startsWith("/api/autonomy/work-items/") ? { status: 404, telo: { detail: "Radni proizvod nije pronađen." } } : { status: 404, telo: { detail: "Nije pronađeno." } });
    let t = JSON.parse(JSON.stringify(o.telo));
    if (kuke.izmeni) t = kuke.izmeni({ p, k, metod }, t) || t;
    json(res, o.status, t);
    return true;
  };
}

async function scenario({ kuke = {}, hash = "#/danas", w = 1440, h = 900, tema = "dark", korisnik = "kA", token = TA } = {}) {
  const KOR = korisnici();
  const f = await pokreniFixture(kombinuj(radRuta(kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce", colorScheme: tema });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(([kl, v, t]) => { localStorage.setItem("vx-ng-tema", t); if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(kl, v); } }, [KLJUC, ses(korisnik, token), tema]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live${hash}`);
  return { f, ctx, p, spoljni, async zatvori() { await ctx.close(); await f.zatvori(); } };
}
const zahtevi = (s, re, metod) => s.f.zahtevi.filter(z => (!metod || z.metod === metod) && re.test(z.putanja));
const danasGotov = (p) => cekaj(p, () => document.getElementById("rl-stanje").dataset.stanje !== "ucitavanje"
  && (document.getElementById("dp-lista").children.length > 0 || !document.getElementById("dp-stanje").hidden || document.getElementById("dp-blok").hidden)
  && (document.getElementById("rl-korpe").children.length > 0 || !document.getElementById("rl-stanje").hidden));
const listaDanas = (p) => p.evaluate(() => ({
  vidljiv: !document.getElementById("dp-blok").hidden,
  stavke: [...document.querySelectorAll("#dp-lista > li")].map(li => ({ id: li.dataset.rad, tip: li.dataset.tip, tekst: li.innerText.replace(/\s+/g, " ").trim(),
    veza: li.querySelector(".vp-item__title").getAttribute("href"), predmet: li.querySelector("a.text-btn") ? li.querySelector("a.text-btn").getAttribute("href") : null })),
  stanje: document.getElementById("dp-stanje").hidden ? null : [document.getElementById("dp-stanje").dataset.stanje, document.getElementById("dp-stanje").textContent],
  redosled: [...document.querySelectorAll("#danas-pogled .matter__section > h2")].map(x => x.textContent),
  preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
}));
const detaljGotov = (p) => cekaj(p, () => document.getElementById("vpr-stanje").dataset.stanje !== "ucitavanje"
  && (!document.getElementById("vpr-sadrzaj").hidden || !document.getElementById("vpr-stanje").hidden));
const detalj = (p) => p.evaluate(() => ({
  sadrzaj: !document.getElementById("vpr-sadrzaj").hidden,
  stanje: document.getElementById("vpr-stanje").hidden ? null : document.getElementById("vpr-stanje").textContent,
  naslov: document.getElementById("vpr-naslov").textContent, meta: document.getElementById("vpr-meta").innerText,
  razlog: document.getElementById("vpr-razlog").textContent, telo: document.getElementById("vpr-delovi").innerText.replace(/\s+/g, " "),
  odluka: !document.getElementById("vpr-odluka-blok").hidden,
  poruka: document.getElementById("vpr-poruka").hidden ? null : document.getElementById("vpr-poruka").textContent,
  porekla: [...document.querySelectorAll("#vpr-delovi .prov")].map(x => x.textContent),
  preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  xss: window.__xss || null,
}));
const DOK = (s) => s.p.evaluate(() => document.getElementById("vpr-delovi").textContent);

// ── 1. Danas: „Vindex je pripremio" na vrhu, iz ISTOG odgovora table ─────────
{
  const s = await scenario();
  zapisi("danas", "Danas učitan", await danasGotov(s.p));
  const e = await listaDanas(s.p);
  zapisi("danas", "„Vindex je pripremio“ je PRVA sekcija Danas, pre radne liste", e.redosled[0] === "Vindex je pripremio" && e.redosled[1] === "Radna lista", e.redosled.join(","));
  zapisi("danas", "2 pripremljena rada iz stvarnog ciklusa", e.stavke.length === 2 && new Set(e.stavke.map(x => x.id)).size === 2, e.stavke.map(x => x.tip).join(","));
  const hp = e.stavke.find(x => x.id === HP), pi = e.stavke.find(x => x.id === PI);
  zapisi("danas", "stavka: vrsta rada, predmet, ZAŠTO, kada, stanje poverenja, sažetak",
    !!hp && /Priprema za ročište · Petrović protiv Gradnja Invest DOO · pripremljeno \d\d\.\d\d\.\d{4}\. u \d\d:\d\d/.test(hp.tekst)
      && /Zašto: Ročište sutra/.test(hp.tekst) && /Sadrži analizu \(AI\)/.test(hp.tekst) && /Iz spisa: \d+ ključnih činjenica/.test(hp.tekst), hp && hp.tekst.slice(0, 220));
  zapisi("danas", "nova praksa: izvor i razlog vidljivi u listi", !!pi && /Nova praksa — analiza uticaja/.test(pi.tekst) && /Rev 1234\/2023/.test(pi.tekst), pi && pi.tekst.slice(0, 160));
  zapisi("danas", "veze: pregled rada i predmet", hp.veza === `#/pripremljeno/${HP}` && hp.predmet === `#/predmeti/${PA}`);
  zapisi("cena", "Danas = jedan GET table, bez posebnog zahteva za pripremljen rad, 0 upisa",
    zahtevi(s, /^\/api\/workspace$/).length === 1 && zahtevi(s, /^\/api\/autonomy/).length === 0 && s.f.zahtevi.every(z => z.metod === "GET"));
  await s.p.click(`#dp-lista li[data-rad="${HP}"] .vp-item__title`);
  zapisi("navigacija", "klik otvara pregled rada", await cekaj(s.p, (id) => location.hash === `#/pripremljeno/${id}` && !document.getElementById("pripremljeno-pogled").hidden, HP));
  const dupli = await s.p.evaluate(() => { const v = {}; document.querySelectorAll("[id]").forEach(e => { v[e.id] = (v[e.id] || 0) + 1; }); return Object.keys(v).filter(k => v[k] > 1); });
  zapisi("integritet", "nijedan id se ne ponavlja na stranici (sudar sa drugim modulom bi preusmerio njegov getElementById)", dupli.length === 0, dupli.join(","));
  zapisi("bezbednost", "0 spoljnih zahteva", s.spoljni.length === 0);
  await s.zatvori();
}

// ── 2. Pregled pripreme za ročište + prihvatanje (samo odluka) ────────────────
{
  const s = await scenario({ hash: `#/pripremljeno/${HP}` });
  zapisi("pregled", "pregled pripreme učitan", await detaljGotov(s.p));
  const e = await detalj(s.p);
  const t = await DOK(s);
  zapisi("pregled", "naslov, predmet, ZAŠTO", /^Priprema za ročište \d\d\.\d\d\.\d{4}\. — Petrović protiv Gradnja Invest DOO$/.test(e.naslov)
    && /Čeka vaš pregled/.test(e.meta) && /^Zašto je pripremljeno: Ročište sutra/.test(e.razlog), e.naslov + " | " + e.razlog.slice(0, 80));
  zapisi("pregled", "ročište iz evidencije (10:00, Osnovni sud u Beogradu, sudnica 12), ne iz analize",
    /u 10:00 · Osnovni sud u Beogradu · sudnica 12/.test(t) && /Iz evidencije ročišta predmeta \(ne iz analize\)/.test(t));
  zapisi("pregled", "ključne činjenice sa poreklom i izvorom po NAZIVU dokumenta", /Izvor: Rešenje o otkazu\.pdf · približno str\. 1/.test(t) && e.porekla.includes("Iz dokumenta"));
  zapisi("pregled", "protivrečnost sa oba izvora", /datum uručenja rešenja o otkazu/.test(t) && /Izvor: Dostavnica\.pdf/.test(t));
  zapisi("pregled", "AI predlozi su označeni kao analiza, sa napomenom", e.porekla.includes("Analiza (AI)") && /nije utvrđena činjenica/.test(t) && /Proveriti koji je datum uručenja tačan/.test(t));
  zapisi("istina", "nijedan id umesto naziva u prikazu", !/[0-9a-f]{8}-[0-9a-f]{4}-/.test(e.telo));
  zapisi("odluka", "odluka objašnjava da se ništa ne šalje", e.odluka && /ništa se ne šalje, ne podnosi i ne menja u predmetu/.test(await s.p.evaluate(() => document.getElementById("vpr-odluka-blok").innerText)));
  await s.p.click("#vpr-prihvati");
  const gotovo = await cekaj(s.p, () => document.getElementById("vpr-poruka").dataset.stanje === "ok");
  const e2 = await detalj(s.p);
  const post = zahtevi(s, /\/api\/autonomy\/work-items\/.+\/(accept|reject)$/, "POST");
  zapisi("odluka", "prihvatanje: jedan POST sa Idempotency-Key, poruka bez spoljnog efekta",
    gotovo && post.length === 1 && post[0].putanja.endsWith(`${HP}/accept`) && !e2.odluka && /Prihvaćeno\. Ništa nije poslato niti promenjeno u predmetu\./.test(e2.poruka || ""), e2.poruka);
  zapisi("odluka", "nijedan drugi upis (POST) osim odluke", s.f.zahtevi.filter(z => z.metod !== "GET").length === 1);
  await s.zatvori();
}

// ── 3. Nova praksa: proveren izvor, izvod, odbijanje sa razlogom ──────────────
{
  let telo = null;
  const s = await scenario({ hash: `#/pripremljeno/${PI}`, kuke: { pre: ({ metod, telo: t, zaglavlja }) => { if (metod === "POST") telo = { t, kljuc: zaglavlja["idempotency-key"] }; return null; } } });
  await detaljGotov(s.p);
  const t = await DOK(s);
  zapisi("praksa", "odluka iz baze odluka: broj, sud, datum, provereno", /Rev 1234\/2023 · Vrhovni sud · 10\.05\.2023\./.test(t) && /Proverena u bazi sudskih odluka/.test(t));
  zapisi("praksa", "uticaj se prikazuje SA doslovnim izvodom iz odluke", /Izvod iz odluke: „dan uručenja utvrđen u dostavnici ima prednost/.test(t));
  zapisi("praksa", "odnos je procena analize (AI), ne činjenica", /Procena odnosa prema predmetu: u prilog predmeta/.test(t) && /Zašto je pronađena/.test(t));
  await s.p.fill("#vpr-razlog-odbijanja", "Nije relevantno za ovaj spor.");
  await s.p.click("#vpr-odbaci");
  await cekaj(s.p, () => document.getElementById("vpr-poruka").dataset.stanje === "ok");
  zapisi("odluka", "odbijanje šalje razlog i ključ idempotentnosti", !!telo && JSON.parse(telo.t).razlog === "Nije relevantno za ovaj spor." && /^[0-9a-f-]{36}$/.test(telo.kljuc || ""), JSON.stringify(telo));
  zapisi("odluka", "posle odbijanja: „Odbačeno.“", /Odbačeno\./.test((await detalj(s.p)).poruka || ""));
  await s.zatvori();
}

// ── 4. Tuđ rad i greška servera ───────────────────────────────────────────────
{
  const s = await scenario({ hash: `#/pripremljeno/${HP}`, korisnik: "kB", token: TB });
  await detaljGotov(s.p);
  const e = await detalj(s.p);
  zapisi("tenant", "korisnik B na radu A: „nije pronađen“, bez sadržaja", !e.sadrzaj && e.stanje === "Pripremljeni rad nije pronađen." && !/Petrović/.test(await s.p.evaluate(() => document.body.innerText)));
  await s.zatvori();
}
{
  const s = await scenario({ hash: `#/pripremljeno/${HP}`, kuke: { pre: ({ metod, p }) => metod === "GET" && /work-items\/.+/.test(p) ? { status: 500, telo: { detail: "x" } } : null } });
  await detaljGotov(s.p);
  const e = await detalj(s.p);
  zapisi("greska", "500 → „nije učitan … ne znači da ga nema“ (ne „nije pronađen“)", !e.sadrzaj && /nije učitan zbog greške\. Ovo ne znači da ga nema/.test(e.stanje || ""), e.stanje);
  await s.zatvori();
}

// ── 5. Ishod odluke nepoznat / već rešeno ─────────────────────────────────────
for (const [opis, odg, ocek] of [["ishod nepoznat (500)", { status: 500, telo: { detail: "x" } }, /Ishod prethodne odluke nije bio poznat/],
                                  ["već rešeno (409)", { status: 409, telo: { detail: "Ovaj rad više nije na pregledu." } }, /više nije na pregledu/]]) {
  const s = await scenario({ hash: `#/pripremljeno/${HP}`, kuke: { pre: ({ metod }) => metod === "POST" ? odg : null } });
  await detaljGotov(s.p);
  await s.p.click("#vpr-prihvati");
  await s.p.waitForTimeout(900);
  const e = await detalj(s.p);
  zapisi("odluka", `${opis}: poštena poruka, stanje ponovo pročitano`, ocek.test(e.poruka || "") && zahtevi(s, /work-items\/[^/]+$/, "GET").length === 2, e.poruka);
  await s.zatvori();
}

// ── 6. Danas: pad / isključeno / prazno ───────────────────────────────────────
{
  const s = await scenario({ kuke: { izmeni: ({ p }, t) => p === "/api/workspace" ? { ...t, vindex_je_pripremio: [], vindex_je_pripremio_stanje: "NIJE_PROCITANO" } : null } });
  await danasGotov(s.p);
  const e = await listaDanas(s.p);
  zapisi("danas", "izvor nije pročitan → greška „ne znači da ga nema“", !!e.stanje && e.stanje[0] === "greska" && /ne znači da ga nema/.test(e.stanje[1]), JSON.stringify(e.stanje));
  await s.zatvori();
}
{
  const s = await scenario({ kuke: { izmeni: ({ p }, t) => p === "/api/workspace" ? { ...t, vindex_je_pripremio: [], vindex_je_pripremio_stanje: "OK" } : null } });
  await danasGotov(s.p);
  const e = await listaDanas(s.p);
  zapisi("danas", "ništa pripremljeno → normalno prazno stanje, bez izmišljanja", !!e.stanje && e.stanje[0] === "prazno" && /nema pripremljenog rada/.test(e.stanje[1]) && e.stavke.length === 0);
  await s.zatvori();
}
{
  const s = await scenario({ kuke: { izmeni: ({ p }, t) => { if (p !== "/api/workspace") return null; const x = { ...t }; delete x.vindex_je_pripremio; delete x.vindex_je_pripremio_stanje; return x; } } });
  await danasGotov(s.p);
  zapisi("danas", "server bez ove mogućnosti (pre migracije) → sekcija skrivena", !(await listaDanas(s.p)).vidljiv);
  await s.zatvori();
}

// ── 7. Pregled predmeta: pripremljen rad tog predmeta ─────────────────────────
{
  const s = await scenario({ hash: `#/predmeti/${PA}` });
  const ok = await cekaj(s.p, () => !document.getElementById("zp-prip-blok").hidden && document.querySelectorAll("#zp-prip > li").length > 0);
  const n = await s.p.evaluate(() => [...document.querySelectorAll("#zp-prip > li")].map(li => li.dataset.rad));
  zapisi("pregled-predmeta", "Pregled prikazuje pripremljen rad OVOG predmeta", ok && n.length === 2 && n.includes(HP) && n.includes(PI), n.join(","));
  zapisi("cena", "Pregled = promene + radnje + pripremljen rad (3 GET), bez modela i upisa",
    zahtevi(s, /genome-v2\/promene$/).length === 1 && zahtevi(s, /case-actions/).length === 1 && zahtevi(s, /^\/api\/autonomy\/work-items$/).length === 1 && s.f.zahtevi.every(z => z.metod === "GET"));
  await s.zatvori();
}

// ── 8. Zastareo odgovor: rad A → rad B; korisnik A → B ────────────────────────
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ hash: `#/pripremljeno/${HP}`, kuke: { pre: async ({ metod, p }) => { if (metod === "GET" && p.endsWith(HP)) await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("vpr-stanje").dataset.stanje === "ucitavanje");
  await s.p.evaluate((h) => { location.hash = h; }, `#/pripremljeno/${PI}`);
  await detaljGotov(s.p);
  pusti();
  await s.p.waitForTimeout(700);
  const e = await detalj(s.p);
  zapisi("sesija", "zakasneli odgovor rada A se ne iscrtava preko rada B", /Rev 1234\/2023/.test(e.telo) && !/Iz evidencije ročišta/.test(e.telo), e.naslov);
  await s.zatvori();
}
{
  let pusti;
  const kapija = new Promise(r => { pusti = r; });
  const s = await scenario({ hash: `#/pripremljeno/${HP}`, kuke: { pre: async ({ k, metod }) => { if (k === "A" && metod === "GET") await kapija; return null; } } });
  await cekaj(s.p, () => document.getElementById("vpr-stanje").dataset.stanje === "ucitavanje");
  await s.p.evaluate(([kl, v]) => { localStorage.setItem(kl, v); window.dispatchEvent(new StorageEvent("storage", { key: kl, newValue: v })); }, [KLJUC, ses("kB", TB)]);
  await s.p.waitForTimeout(400);
  pusti();
  await s.p.waitForTimeout(700);
  const sve = await s.p.evaluate(() => document.getElementById("pripremljeno-pogled").textContent);
  zapisi("sesija", "posle prelaska A→B ništa od rada A nije na ekranu", !/Petrović|Rešenje o otkazu|Osnovni sud u Beogradu/.test(sve), sve.replace(/\s+/g, " ").slice(0, 100));
  await s.zatvori();
}

{
  const s = await scenario({ hash: `#/pripremljeno/${HP}` });
  await detaljGotov(s.p);
  await s.p.evaluate(([kl, v]) => { localStorage.setItem(kl, v); window.dispatchEvent(new StorageEvent("storage", { key: kl, newValue: v })); }, [KLJUC, ses("kB", TB)]);
  await s.p.waitForTimeout(500);
  const sve = await s.p.evaluate(() => document.getElementById("pripremljeno-pogled").textContent);
  zapisi("sesija", "već prikazan rad A nestaje kad se prijavi B", !/Petrović|Rešenje o otkazu|Osnovni sud u Beogradu/.test(sve), sve.replace(/\s+/g, " ").slice(0, 100));
  await s.zatvori();
}

// ── 9. XSS i raspored ─────────────────────────────────────────────────────────
{
  const s = await scenario({ kuke: { izmeni: ({ p }, t) => p === "/api/workspace" ? { ...t, vindex_je_pripremio: t.vindex_je_pripremio.map((x, i) => i ? x : { ...x, naslov: "<img src=x onerror=window.__xss=1>", razlog: "<b>r</b>" }) } : null } });
  await danasGotov(s.p);
  const e = await listaDanas(s.p);
  zapisi("bezbednost", "HTML u naslovu/razlogu se prikazuje kao tekst", (await s.p.evaluate(() => window.__xss || null)) === null && e.stavke.some(x => /<img src=x onerror=/.test(x.tekst)));
  await s.zatvori();
}
for (const [w, tema, hash] of [[360, "light", "#/danas"], [360, "dark", `#/pripremljeno/${HP}`], [1440, "light", `#/pripremljeno/${PI}`]]) {
  const s = await scenario({ w, h: 800, tema, hash });
  if (hash === "#/danas") await danasGotov(s.p); else await detaljGotov(s.p);
  const pr = await s.p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  zapisi("raspored", `${w}px/${tema} ${hash.slice(0, 16)}: bez vodoravnog preliva`, !pr);
  await s.zatvori();
}
{
  const s = await scenario();
  await danasGotov(s.p);
  const nav = await s.p.evaluate(() => [...document.querySelectorAll(".sidenav__item")].filter(a => a.getClientRects().length).map(a => a.textContent.trim()));
  zapisi("navigacija", "bočni meni bez novog modula (nema „Agenti“ / „Pripremljeno“)", !nav.some(x => /Agent|Pripremljen|Autonom/i.test(x)) && nav.includes("Danas"), nav.join(","));
  await s.zatvori();
}

await browser.close();
zapisi("bezbednost", "nijedna JS greška na stranici", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
zapisi("bezbednost", "nijedan token u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
