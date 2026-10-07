// Vindex V2 NG — NS002 Task 6: legacy Service Worker ne sme da zameni V2 preview.
// Pokretanje: `node tests/live-sw-isolation.mjs` (podiže tests/v2_ng_e2e_harness.py).
//
// Stvaran Chromium, STVARAN root /sw.js koji servira api.py, STVARNA preview ruta.
// Negativna kontrola: offline navigacija na /app MORA dati legacy shell iz keša
// (dokaz da je SW zaista aktivan i da test prepoznaje legacy shell). Tek onda:
// offline /v2/preview/ NE SME dati legacy shell.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TOKEN = "vx-e2e-A";
const SNIMCI = ["sw-preview-online.png", "sw-preview-offline.png"];
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}

const dir = await mkdtemp(join(tmpdir(), "vx-sw-"));
const LOG = join(dir, "harness.jsonl");
const PORT = 4493;
const SISTEM = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "pythonLocation", "LD_LIBRARY_PATH"];
const env = Object.fromEntries(SISTEM.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
Object.assign(env, {
  SUPABASE_URL: "https://fake.supabase.co", SUPABASE_ANON_KEY: "fake-anon-key", SUPABASE_SERVICE_KEY: "fake-service-key",
  SUPABASE_JWT_SECRET: "fake-jwt-secret-longer-than-32-chars-ok", OPENAI_API_KEY: "sk-fake", PINECONE_API_KEY: "fake-pinecone",
  PINECONE_HOST: "https://fake.pinecone.io", FIELD_ENCRYPTION_KEY: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  FOUNDER_EMAILS: "ci@example.com", PYTHONUTF8: "1", PYTHONUNBUFFERED: "1",
  VINDEX_V2_NG_PREVIEW_ENABLED: "1", VX_E2E_LOG: LOG, VX_E2E_PORT: String(PORT),
});
const py = spawn(process.env.VX_PYTHON || "python", ["tests/v2_ng_e2e_harness.py"], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let pyIzlaz = ""; py.stdout.on("data", d => pyIzlaz += d); py.stderr.on("data", d => pyIzlaz += d);
let gotov = false;
for (let i = 0; i < 600 && !gotov; i++) {
  gotov = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/v2/preview/" }, s => { s.resume(); r(s.statusCode === 200); }).on("error", () => r(false)));
  if (!gotov) await new Promise(r => setTimeout(r, 200));
}
zapisi("harness", "stvarna FastAPI aplikacija se podiže sa preview-om", gotov, gotov ? "" : pyIzlaz.slice(-600));
if (!gotov) { py.kill(); process.exit(1); }
const BASE = `http://127.0.0.1:${PORT}`;
const LEGACY = (html) => html.includes("/static/vindex.js");
const browser = await chromium.launch();
const ses = JSON.stringify({ access_token: TOKEN, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "korisnik-A", email: "a@primer.test" } });
const spoljni = [], konzola = [];

async function kontekst(saSesijom) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", serviceWorkers: "allow" });
  await ctx.route("**/*", (r) => {
    const h = new URL(r.request().url()).hostname;
    if (h === "127.0.0.1") return r.continue();
    let izvor = "-"; try { izvor = new URL(r.request().frame().url()).pathname; } catch {}
    spoljni.push({ url: r.request().url().slice(0, 80), izvor }); return r.abort();
  });
  if (saSesijom) await ctx.addInitScript(([k, v]) => localStorage.setItem(k, v), [KLJUC, ses]);
  return ctx;
}

// ── 1. Stvaran root /sw.js, scope "/" ───────────────────────────────────
const ctx = await kontekst(true);
const p = await ctx.newPage();
p.on("console", m => konzola.push(m.text())); p.on("pageerror", e => konzola.push("PAGEERROR " + e));
const odgovori = [];
p.on("response", r => odgovori.push({ put: new URL(r.url()).pathname, izSW: r.fromServiceWorker(), status: r.status() }));
await p.goto(`${BASE}/v2/preview/?rezim=live`);
const reg = await p.evaluate(async () => { const r = await navigator.serviceWorker.register("/sw.js"); await navigator.serviceWorker.ready; return { scope: r.scope, skripta: (r.active || r.installing || r.waiting).scriptURL }; });
zapisi("sw", "postojeći /sw.js registrovan sa scope „/“", reg.scope === `${BASE}/` && reg.skripta === `${BASE}/sw.js`, JSON.stringify(reg));
// Legacy /app jednom online: SW kešira /app navigaciju i precache /offline.
await p.goto(`${BASE}/app`);
await p.waitForTimeout(800);
odgovori.length = 0;
await p.goto(`${BASE}/v2/preview/?rezim=live`);
await p.waitForFunction(() => document.querySelectorAll("#rows tr").length === 12, null, { timeout: 20000 }).catch(() => {});
const kontrolisan = await p.evaluate(() => !!navigator.serviceWorker.controller && navigator.serviceWorker.controller.scriptURL);
zapisi("sw", "preview stranica je pod kontrolom legacy SW-a (uslov testa)", kontrolisan === `${BASE}/sw.js`, String(kontrolisan));
zapisi("sw", "LIVE pod SW-om radi: 12 predmeta", (await p.evaluate(() => document.querySelectorAll("#rows tr").length)) === 12);
const v2Odg = odgovori.filter(o => o.put.startsWith("/v2/"));
zapisi("sw", "nijedan /v2/ odgovor nije poslužen iz SW-a (bypass, bez respondWith)", v2Odg.length > 0 && v2Odg.every(o => !o.izSW), `${v2Odg.length} odgovora, iz SW: ${v2Odg.filter(o => o.izSW).length}`);
const api = odgovori.filter(o => o.put === "/api/predmeti");
zapisi("sw", "/api/predmeti ide stvarnom mrežom (network-first, 200)", api.length > 0 && api.every(o => o.status === 200), JSON.stringify(api.slice(0, 2)));
const kes = await p.evaluate(async () => { const out = []; for (const n of await caches.keys()) { const c = await caches.open(n); for (const r of await c.keys()) out.push(new URL(r.url).pathname); } return out; });
zapisi("kes", "SW keš ne sadrži nijedan /v2/ resurs", !kes.some(u => u.startsWith("/v2/")), kes.filter(u => u.startsWith("/v2/")).join(","));
zapisi("kes", "SW keš ne sadrži nijedan /api/ odgovor (nijedan prijavljeni odgovor)", !kes.some(u => u.startsWith("/api/")), kes.filter(u => u.startsWith("/api/")).join(","));
zapisi("kes", "kontrola: keš postoji i sadrži legacy /offline i /app", kes.includes("/offline") && kes.includes("/app"), kes.slice(0, 6).join(","));
await p.screenshot({ path: join(dir, SNIMCI[0]) });

// ── 2. Pad mreže ─────────────────────────────────────────────────────────
await ctx.setOffline(true);
let appHtml = "";
try { await p.goto(`${BASE}/app`, { timeout: 10000 }); appHtml = await p.content(); } catch (e) { appHtml = "GREŠKA " + e.message; }
zapisi("offline", "NEGATIVNA KONTROLA: offline /app → legacy shell iz SW keša (SW je zaista aktivan)", LEGACY(appHtml), appHtml.slice(0, 80));
let v2Html = "", v2Greska = "";
try { await p.goto(`${BASE}/v2/preview/?rezim=live`, { timeout: 10000 }); v2Html = await p.content(); } catch (e) { v2Greska = e.message.split("\n")[0]; try { v2Html = await p.content(); } catch { v2Html = ""; } }
zapisi("offline", "offline /v2/preview/ NIJE legacy index.html", !LEGACY(v2Html), v2Greska || v2Html.slice(0, 80));
zapisi("offline", "ishod je mrežna greška pregledača (dozvoljen ishod)", /ERR_INTERNET_DISCONNECTED|ERR_FAILED|net::/.test(v2Greska) || /chrome-error/.test(p.url()), v2Greska || p.url());
await p.screenshot({ path: join(dir, SNIMCI[1]) }).catch(() => {});
await ctx.setOffline(false);
await ctx.close();

// ── 3. Bez prijave: shell postoji, API kaže 401 ─────────────────────────
{
  const c = await kontekst(false);
  const q = await c.newPage();
  const r = await q.goto(`${BASE}/v2/preview/?rezim=live`);
  const st = await q.evaluate(async () => (await fetch("/api/predmeti?view=summary&status=aktivan")).status);
  const stanje = await q.evaluate(() => document.getElementById("empty").dataset.stanje);
  zapisi("bez-prijave", "shell se servira (200), GET /api/predmeti bez tokena → 401", r.status() === 200 && st === 401, `${r.status()} / ${st}`);
  zapisi("bez-prijave", "ekran kaže „bez-prijave“, ne prazna kancelarija", stanje === "bez-prijave", stanje);
  const regs = await q.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length);
  zapisi("sw", "V2 sam ne registruje nijedan Service Worker", regs === 0, `${regs}`);
  // Putanje van preview-a, kroz stvaran pregledač.
  for (const put of ["/v2/preview/src/..%2f..%2fapi.py", "/v2/preview/%2e%2e/%2e%2e/api.py", "/v2/preview/src/%2e%2e/serve.mjs",
    "/v2/preview//etc/passwd", "/v2/preview/src/app.js%00.txt", "/v2/preview/..;/api.py", "/v2/preview/tests/v2_ng_e2e_harness.py"]) {
    const o = await q.evaluate(async (u) => { const r = await fetch(u); return { s: r.status, t: (await r.text()).slice(0, 4000) }; }, put);
    zapisi("putanje", `${put} → odbijeno, bez sadržaja fajla`, o.s >= 400 && !/from fastapi|import |def |VINDEX_LOCAL_API_ORIGIN/.test(o.t), `${o.s}`);
  }
  await c.close();
}

// ── 4. Token nigde ───────────────────────────────────────────────────────
{
  const c = await kontekst(true);
  const q = await c.newPage();
  q.on("console", m => konzola.push(m.text()));
  await q.goto(`${BASE}/v2/preview/?rezim=live`);
  await q.waitForFunction(() => document.querySelectorAll("#rows tr").length === 12, null, { timeout: 20000 }).catch(() => {});
  const t = await q.evaluate((tok) => ({
    url: location.href.includes(tok),
    atributi: [...document.querySelectorAll("*")].some(e => [...e.attributes].some(a => a.value.includes(tok))),
    tekst: document.body.innerText.includes(tok) || document.documentElement.outerHTML.includes(tok),
  }), TOKEN);
  zapisi("token", "token nije u URL-u, atributima DOM-a ni tekstu/HTML-u", !t.url && !t.atributi && !t.tekst, JSON.stringify(t));
  await c.close();
}

await browser.close();
py.kill(); await new Promise(r => py.once("exit", r));
const d = (await readFile(LOG, "utf8")).split("\n").filter(Boolean).map(l => JSON.parse(l));
const sve = [konzola.join("\n"), izlaz.join("\n"), pyIzlaz, JSON.stringify(d), SNIMCI.join(",")].join("\n");
zapisi("token", "token nije u konzoli, izlazu, logu servera, dnevniku ni imenima snimaka", !sve.includes(TOKEN));
const spolj = d.filter(z => /spolj/.test(z.vrsta));
const izV2 = spolj.filter(z => !z.put || z.put === "-" || z.put.startsWith("/v2/") || z.put.startsWith("/api/predmeti"));
const upisi = d.filter(z => z.vrsta === "UPIS-POKUSAN");
const upisiV2 = upisi.filter(z => !z.put || z.put === "-" || z.put.startsWith("/v2/") || z.put.startsWith("/api/predmeti"));
zapisi("bezbednost", "0 upisa iz V2 preview-a i /api/predmeti (ili bez pripisane rute)", upisiV2.length === 0, JSON.stringify(upisiV2.slice(0, 3)));
console.log(`INFO  [legacy-kontrola] blokirani upisi legacy /app stranice: ${upisi.length} — ${[...new Set(upisi.map(z => z.put + "→" + z.tabela + "." + z.metod))].join(", ") || "nema"}`);
zapisi("bezbednost", "0 spoljnih pokušaja iz V2 preview-a i /api/predmeti (ili bez pripisane rute)", izV2.length === 0, JSON.stringify(izV2.slice(0, 3)));
// Zahtevi koje legacy SW pravi iz SVOG konteksta (CDN cache-first) nemaju
// stranicu-izvor. Oni se pripisuju dokazivo: host mora biti referenciran u
// legacy index.html, a NIJEDAN V2 fajl ne sme referencirati taj host.
const hostovi = (t) => new Set((t.match(/https?:\/\/[a-zA-Z0-9.-]+/g) || []).map(u => new URL(u).hostname));
const legacyHost = hostovi(await readFile(join(REPO, "index.html"), "utf8"));
const v2Tekst = [await readFile(join(REPO, "frontend-v2-ng/index.html"), "utf8"),
  ...await Promise.all(["runtime", "api", "session", "live", "predmeti", "demo-data", "signature-background", "app"].map(f => readFile(join(REPO, `frontend-v2-ng/src/${f}.js`), "utf8")))].join("\n");
const v2Host = hostovi(v2Tekst);
const sV2 = spoljni.filter(z => z.izvor.startsWith("/v2/"));
const bezIzvora = spoljni.filter(z => z.izvor === "-");
const neobjasnjeni = bezIzvora.filter(z => { const h = new URL(z.url).hostname; return !legacyHost.has(h) || v2Host.has(h); });
zapisi("bezbednost", "0 spoljnih zahteva pregledača sa V2 stranica", sV2.length === 0, JSON.stringify(sV2.slice(0, 2)));
zapisi("bezbednost", "zahtevi bez izvora idu samo na hostove legacy index.html koje V2 ne referencira", neobjasnjeni.length === 0, JSON.stringify(neobjasnjeni.slice(0, 2)));
const spoljniV2 = [...sV2, ...neobjasnjeni];
console.log(`INFO  [legacy-kontrola] blokirani spoljni zahtevi pregledača sa legacy stranica: ${spoljni.length - spoljniV2.length} — ${[...new Set(spoljni.filter(z => !spoljniV2.includes(z)).map(z => z.izvor + "→" + new URL(z.url).hostname))].join(", ") || "nema"}`);
const legacyPutanje = [...new Set(spolj.map(z => z.put + "→" + z.host))];
console.log(`INFO  [legacy-kontrola] blokirani spoljni pokušaji legacy /app stranice tokom negativne kontrole (nisu napustili mašinu): ${spolj.length} — ${legacyPutanje.join(", ") || "nema"}`);
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
