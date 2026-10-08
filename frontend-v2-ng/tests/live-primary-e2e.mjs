// Vindex V2 NG — NS004 Task 3/5: V2 kao PRIMARNI /app (stvaran api.py + Chromium).
// Pokretanje: `node tests/live-primary-e2e.mjs` (Python iz VX_PYTHON ili `python`).
//
// Harness: VINDEX_V2_NG_PRIMARY_ENABLED=1, preview ISKLJUČEN — dokaz da primarni
// /app ne zavisi od /v2/preview. Svi tokeni i podaci su izmišljeni; ništa ne
// izlazi van 127.0.0.1 (pregledač: route čuvar; Python: čuvar soketa).

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}

const dir = await mkdtemp(join(tmpdir(), "vx-primary-"));
const LOG = join(dir, "harness.jsonl");
const PORT = 4493;
const SISTEM = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "pythonLocation", "LD_LIBRARY_PATH"];
const env = Object.fromEntries(SISTEM.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
Object.assign(env, {
  SUPABASE_URL: "https://fake.supabase.co", SUPABASE_ANON_KEY: "fake-anon-key", SUPABASE_SERVICE_KEY: "fake-service-key",
  SUPABASE_JWT_SECRET: "fake-jwt-secret-longer-than-32-chars-ok", OPENAI_API_KEY: "sk-fake", PINECONE_API_KEY: "fake-pinecone",
  PINECONE_HOST: "https://fake.pinecone.io", FIELD_ENCRYPTION_KEY: "f".repeat(64),
  FOUNDER_EMAILS: "ci@example.com", PYTHONUTF8: "1", PYTHONUNBUFFERED: "1",
  VINDEX_V2_NG_PRIMARY_ENABLED: "1", VX_E2E_LOG: LOG, VX_E2E_PORT: String(PORT),
});
const py = spawn(process.env.VX_PYTHON || "python", ["tests/v2_ng_e2e_harness.py"], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let pyIzlaz = "";
py.stdout.on("data", d => pyIzlaz += d); py.stderr.on("data", d => pyIzlaz += d);
let gotov = false;
for (let i = 0; i < 600 && !gotov; i++) {
  gotov = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/app" }, s => { s.resume(); r(s.statusCode === 200); }).on("error", () => r(false)));
  if (!gotov) await new Promise(r => setTimeout(r, 200));
}
zapisi("harness", "stvaran api.py sa primarnim prekidačem servira /app", gotov, gotov ? "" : pyIzlaz.slice(-800));
if (!gotov) { py.kill(); process.exit(1); }
const BASE = `http://127.0.0.1:${PORT}`;
const dnevnik = async () => (await readFile(LOG, "utf8")).split("\n").filter(Boolean).map(l => JSON.parse(l));

const browser = await chromium.launch();
const spoljniV2 = [], metodiV2 = [], konzola = [];
const ses = (id, token) => JSON.stringify({ access_token: token, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);

/** V2 stranica na /app. `legacyStub`: zamena za /static/vindex.js na legacy stranici. */
async function otvori(pocetna, adresa = "/app", { legacyStub = null } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") { if (!r.request().frame().url().includes("/app-legacy")) spoljniV2.push(u.href); return r.abort(); }
    if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: legacyStub || "/* legacy blokiran u testu */" });
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, pocetna]);
  const p = await ctx.newPage();
  p.on("request", q => { const u = new URL(q.url()); if (u.pathname.startsWith("/api/") && !(q.frame().url() || "").includes("/app-legacy")) metodiV2.push(q.method() + " " + u.pathname); });
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => { if (!p.url().includes("/app-legacy")) konzola.push("PAGEERROR " + e); });
  await p.goto(BASE + adresa);
  return { ctx, p };
}
const ekran = (p) => p.evaluate(() => {
  const vid = (e) => !!e && !e.closest("[hidden]") && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
  return {
    put: location.pathname + location.search + location.hash, prikaz: document.documentElement.dataset.prikaz || "",
    stanje: document.getElementById("empty").hidden ? "registar" : document.getElementById("empty").dataset.stanje,
    redovi: document.querySelectorAll("#rows tr").length,
    moduli: [...document.querySelectorAll(".sidenav__item")].filter(vid).map(a => a.textContent.trim()),
    panel: vid(document.getElementById("panel")), panelDugme: vid(document.getElementById("panel-toggle")),
    znacka: vid(document.querySelector(".demo-badge")), nalog: vid(document.querySelector(".account")),
    prijava: vid(document.getElementById("empty-prijava")) ? document.getElementById("empty-prijava").getAttribute("href") : null,
    odjava: vid(document.getElementById("odjava")) ? document.getElementById("odjava").getAttribute("href") : null,
    tekst: document.body.innerText, toast: document.getElementById("status").classList.contains("is-on"),
  };
});
const DEMO = /Demonstracioni|Demo nalog|Referentni demo datum|nije deo ovog prototipa/;

// P1/P2: bez prijave — LIVE, poziv na postojeću prijavu, nikad DEMO
for (const adresa of ["/app", "/app?rezim=demo", "/app?rezim=nesto"]) {
  const preApi = metodiV2.length;
  const o = await otvori(null, adresa);
  await cekaj(o.p, () => document.getElementById("empty").dataset.stanje === "bez-prijave");
  const e = await ekran(o.p);
  zapisi("P1.bez-prijave", `${adresa}: primarni V2, „Niste prijavljeni“, bez demo sadržaja`, e.prikaz === "primarni" && e.stanje === "bez-prijave" && e.redovi === 0 && !DEMO.test(e.tekst), `${e.prikaz} ${e.stanje}`);
  zapisi("P1.bez-prijave", `${adresa}: „Prijavite se“ vodi na postojeću prijavu (/app-legacy?posle=app)`, e.prijava === "/app-legacy?posle=app", String(e.prijava));
  zapisi("P1.bez-prijave", `${adresa}: bez poziva /api/predmeti i bez odjave`, metodiV2.length === preApi && e.odjava === null);
  await o.ctx.close();
}
// P3: prijavljen — stvarni predmeti, samo stvarne funkcije
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"));
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  const e = await ekran(o.p);
  zapisi("P3.primarni", "stvarni predmeti korisnika A (12), LIVE", e.redovi === 12 && e.stanje === "registar" && !DEMO.test(e.tekst), `${e.redovi}`);
  zapisi("P3.primarni", "navigacija: samo „Predmeti“ (moduli koji ne rade su uklonjeni)", JSON.stringify(e.moduli) === JSON.stringify(["Predmeti"]), e.moduli.join(","));
  zapisi("P3.primarni", "bez panela „Zahteva pažnju“, demo značke i „Demo nalog“", !e.panel && !e.panelDugme && !e.znacka && !e.nalog);
  zapisi("P3.primarni", "odjava vodi kroz postojeću odjavu (/app-legacy?odjava=1)", e.odjava === "/app-legacy?odjava=1", String(e.odjava));
  for (const sel of [".sidenav__item", "#nav-collapse", ".wordmark"]) await o.p.click(sel).catch(() => {});
  await o.p.waitForTimeout(150);
  zapisi("P3.primarni", "nijedan klik ne prikazuje „prototip“ poruku", !(await ekran(o.p)).toast && !DEMO.test((await ekran(o.p)).tekst));
  await o.p.click('#rows tr[data-id="korisnik-A-00000"] .case__name');
  await cekaj(o.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  zapisi("P3.primarni", "klik na predmet: /app#/predmeti/<id>, stvaran detalj", (await ekran(o.p)).put === "/app#/predmeti/korisnik-A-00000");
  await o.p.click("#tab-dokumenti");
  await cekaj(o.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await o.p.reload();
  await cekaj(o.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  const r = await ekran(o.p);
  zapisi("P3.primarni", "osvežavanje /app#/predmeti/<id>/dokumenti: isti predmet, LIVE, primarni", r.prikaz === "primarni" && r.put === "/app#/predmeti/korisnik-A-00000/dokumenti" && !DEMO.test(r.tekst));
  await o.p.goBack();
  await cekaj(o.p, () => !document.getElementById("odeljak-pregled").hidden);
  await o.p.goBack();
  await cekaj(o.p, () => document.documentElement.dataset.pogled !== "predmet" && document.querySelectorAll("#rows tr").length === 12);
  zapisi("P3.primarni", "Back vraća registar sa stvarnim predmetima", (await ekran(o.p)).redovi === 12);
  const assets = await o.p.evaluate(() => performance.getEntriesByType("resource").map(e => new URL(e.name).pathname).filter(x => /\.(js|css|svg|png|woff2)$/.test(x)));
  zapisi("P3.primarni", "svi V2 asseti sa /v2/app/ (ne zavise od /v2/preview)", assets.length > 5 && assets.every(a => a.startsWith("/v2/app/")), assets.filter(a => !a.startsWith("/v2/app/")).slice(0, 3).join(","));
  await o.ctx.close();
}
// P4: linkovi postojeće prijave (reset lozinke, #login) idu u legacy sa istim hash-om
for (const hash of ["#access_token=vx-lazni-oporavak&type=recovery", "#login", "#error=access_denied&error_description=x"]) {
  const preApi = metodiV2.length;
  const o = await otvori(null, "/app" + hash);
  await cekaj(o.p, () => location.pathname === "/app-legacy");
  const put = await o.p.evaluate(() => location.pathname + location.hash);
  zapisi("P4.prijava-linkovi", `/app${hash.slice(0, 22)}… → /app-legacy sa istim hash-om; V2 ga ne čita`, put === "/app-legacy" + hash && metodiV2.length === preApi, put.replace(/access_token=[^&]+/, "access_token=<skriveno>"));
  await o.ctx.close();
}
// P5: /app-legacy?posle=app vraća na /app čim postoji važeća sesija
{
  const o = await otvori(null, "/app-legacy?posle=app");
  await o.p.waitForTimeout(600);
  zapisi("P5.povratak", "bez sesije: ostaje na klasičnoj prijavi", (await o.p.evaluate(() => location.pathname)) === "/app-legacy");
  await o.p.evaluate(([k, v]) => localStorage.setItem(k, v), [KLJUC, ses("korisnik-A", "vx-e2e-A")]);
  await cekaj(o.p, () => location.pathname === "/app");
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  zapisi("P5.povratak", "posle prijave (sesija upisana): /app, primarni V2 sa stvarnim predmetima", (await ekran(o.p)).redovi === 12);
  await o.ctx.close();
}
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"), "/app-legacy");
  await o.p.waitForTimeout(800);
  zapisi("P5.povratak", "/app-legacy bez parametra ostaje klasičan (rezerva), i sa sesijom", (await o.p.evaluate(() => location.pathname)) === "/app-legacy");
  await o.ctx.close();
}
// P6: odjava poziva POSTOJEĆU legacy doLogout jednom; adresa se menja da reload ne ponovi odjavu
{
  const stub = "window.doLogout = function () { window.__odjava = (window.__odjava || 0) + 1; };";
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"), "/app-legacy?odjava=1", { legacyStub: stub });
  await cekaj(o.p, () => window.__odjava === 1);
  const r = await o.p.evaluate(() => ({ put: location.pathname + location.search, n: window.__odjava }));
  zapisi("P6.odjava", "odjava: legacy doLogout() pozvan tačno jednom, adresa → /app-legacy?posle=app", r.n === 1 && r.put === "/app-legacy?posle=app", JSON.stringify(r));
  await o.ctx.close();
}

// P7 (Task 6): ceo tok — javni sajt → /app → postojeća prijava → predmeti →
// predmet → dokumenti → nazad → odjava → bez ostataka. Prijava/odjava u legacy
// delu su zamenjene minimalnim stubom (upis/brisanje kanonskog zapisa), jer je
// legacy prijava van obima; V2 strana toka je stvarna.
{
  const stub = "window.doLogout = function () { localStorage.removeItem(" + JSON.stringify(KLJUC) + "); location.reload(); };";
  const o = await otvori(null, "/", { legacyStub: stub });
  zapisi("P7.tok", "javni sajt: „Uđi u aplikaciju“ vodi na /app", (await o.p.evaluate(() => [...document.querySelectorAll("a.dugme")].every(a => a.getAttribute("href") === "/app"))));
  await o.p.click("header a.dugme");
  await cekaj(o.p, () => location.pathname === "/app" && document.getElementById("empty").dataset.stanje === "bez-prijave");
  zapisi("P7.tok", "/app bez prijave: V2 primarni, poziv na postojeću prijavu", (await ekran(o.p)).prijava === "/app-legacy?posle=app");
  await o.p.click("#empty-prijava");
  await cekaj(o.p, () => location.pathname === "/app-legacy");
  await o.p.evaluate(([k, v]) => localStorage.setItem(k, v), [KLJUC, ses("korisnik-A", "vx-e2e-A")]);   // postojeća prijava upisuje sesiju
  await cekaj(o.p, () => location.pathname === "/app" && document.querySelectorAll("#rows tr").length === 12);
  zapisi("P7.tok", "posle prijave: nazad na /app, stvarni predmeti", (await ekran(o.p)).redovi === 12);
  await o.p.click('#rows tr[data-id="korisnik-A-00000"] .case__name');
  await cekaj(o.p, () => document.querySelectorAll("#predmet-cinjenice dt").length > 0);
  await o.p.click("#tab-dokumenti");
  await cekaj(o.p, () => document.querySelectorAll("#dok-lista button").length > 0);
  await o.p.click("#dok-lista li:first-child button");
  await cekaj(o.p, () => !document.getElementById("dok-tekst").hidden);
  zapisi("P7.tok", "predmet → Dokumenti → stvaran tekst dokumenta", (await o.p.evaluate(() => document.getElementById("dok-tekst").textContent)) === "TEKST-A0-d0 sadržaj spisa.");
  await o.p.click("#predmet-nazad");
  await cekaj(o.p, () => document.documentElement.dataset.pogled !== "predmet");
  zapisi("P7.tok", "„Predmeti“ vraća registar", (await ekran(o.p)).redovi === 12);
  await o.p.click("#odjava");
  await cekaj(o.p, () => location.pathname === "/app-legacy" && location.search === "?posle=app");
  await o.p.waitForTimeout(500);
  await o.p.goto(BASE + "/app#/predmeti/korisnik-A-00000/dokumenti");
  await cekaj(o.p, () => document.getElementById("predmet-stanje").dataset.stanje === "bez-prijave");
  const e = await o.p.evaluate(() => ({ tekst: document.body.innerText, mem: window.__vxDetaljUMemoriji(), redovi: document.querySelectorAll("#rows tr").length }));
  zapisi("P7.tok", "posle odjave: direktan link na predmet ne prikazuje ništa (bez ostataka)", e.mem.predmet === null && e.mem.tekst === 0 && e.redovi === 0 && !/TEKST-A0|Predmet korisnik-A/.test(e.tekst));
  await o.ctx.close();
}

await browser.close();
py.kill();
await new Promise(r => py.once("exit", r));
const d = await dnevnik();
zapisi("bezbednost", "harness: primarni prekidač uključen, preview ruta NIJE registrovana", d.some(z => z.vrsta === "spreman" && z.primarni === true && z.preview_ruta === false));
zapisi("bezbednost", "0 upisa u podatke", !d.some(z => z.vrsta === "UPIS-POKUSAN"));
zapisi("bezbednost", "0 spoljnih veza iz Python procesa", !d.some(z => /spolj/.test(z.vrsta)), JSON.stringify(d.filter(z => /spolj/.test(z.vrsta))).slice(0, 160));
zapisi("bezbednost", "0 spoljnih zahteva sa V2 stranica", spoljniV2.length === 0, spoljniV2.slice(0, 3).join(","));
zapisi("bezbednost", "V2 je slao SAMO GET", metodiV2.every(m => m.startsWith("GET ")), metodiV2.filter(m => !m.startsWith("GET ")).slice(0, 3).join(","));
zapisi("bezbednost", "nijedan token u konzoli, izlazu ni logu", !["vx-e2e-A", "vx-lazni-oporavak"].some(t => [konzola.join("\n"), izlaz.join("\n"), pyIzlaz].join("\n").includes(t)));
zapisi("bezbednost", "nijedna JS greška na V2 stranicama", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
