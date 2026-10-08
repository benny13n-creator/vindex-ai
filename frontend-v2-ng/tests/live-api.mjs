// Vindex V2 NG — Task 2: read-only API transport (src/api.js).
// Pokretanje: `node tests/live-api.mjs` (sam podiže fixture server).
//
// Svaki ishod se meri kroz STVARAN fetch u Chromium-u prema loopback fixture-u:
// 200 / 401 / 403 / 404 / 429 / 5xx / pokvaren JSON / pogrešan oblik / pukla
// veza / AbortController. Proverava se i da greška NIKAD nije prazan rezultat,
// da Authorization postoji samo uz token, da nema kolačića, ponavljanja,
// `user_id` parametra ni zahteva ka drugom hostu, i da token nije ni u jednom
// izlazu (konzola stranice, rezultat, izlaz testa).

import { chromium } from "playwright";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";

const TOKEN = "vx-api-test-token-NE-SME-U-LOG-91be";
let pada = 0, ukupno = 0;
const izlazTesta = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const linija = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlazTesta.push(linija); console.log(linija);
}

const f = await pokreniFixture(async (req, url, res) => {
  const p = url.pathname;
  if (p === "/api/ok") return json(res, 200, { predmeti: [{ id: "a" }], ukupno: 1 }), true;
  if (p === "/api/echo") return json(res, 200, { auth: req.headers.authorization ? "postoji" : "nema", metod: req.method, upit: url.search }), true;
  if (p === "/api/401") return json(res, 401, { detail: "Unauthorized" }), true;
  if (p === "/api/403") return json(res, 403, { detail: "Forbidden" }), true;
  if (p === "/api/404") return json(res, 404, { detail: "Not found" }), true;
  if (p === "/api/429") return json(res, 429, { error: "Rate limit" }, { "Retry-After": "17" }), true;
  if (p === "/api/500") return json(res, 500, { detail: "boom" }), true;
  if (p === "/api/503") return json(res, 503, "<html>Service Unavailable</html>"), true;
  if (p === "/api/500-prazna-lista") return json(res, 500, { predmeti: [], ukupno: 0 }), true;
  if (p === "/api/pokvaren-json") { res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"predmeti": [ {"id": '); return true; }
  if (p === "/api/niz") return json(res, 200, [1, 2, 3]), true;
  if (p === "/api/null") return json(res, 200, "null"), true;
  if (p === "/api/html") { res.writeHead(200, { "Content-Type": "text/html" }); res.end("<html>login</html>"); return true; }
  if (p === "/api/prekid") { req.socket.destroy(); return true; }
  if (p === "/api/sporo") { await new Promise(r => setTimeout(r, 3000)); if (!res.destroyed) json(res, 200, { kasno: true }); return true; }
  if (p === "/api/preusmeri") { res.writeHead(302, { Location: "https://example.com/" }); res.end(); return true; }
  return false;
});

const browser = await chromium.launch();
const ctx = await browser.newContext();
const page = await ctx.newPage();
const konzola = [];
page.on("console", m => konzola.push(m.text()));
page.on("pageerror", e => konzola.push(String(e)));
const spoljni = [];
page.on("request", q => { const u = new URL(q.url()); if (u.hostname !== "127.0.0.1") spoljni.push(q.url()); });
await page.goto(`http://127.0.0.1:${f.port}/`);

const poziv = (putanja, opcije = {}) => page.evaluate(async ([putanja, opcije, TOKEN]) => {
  const o = Object.assign({}, opcije);
  if (o.saTokenom) { o.token = TOKEN; delete o.saTokenom; }
  if (o.oblikPredmeti) { o.oblik = (d) => Array.isArray(d.predmeti); delete o.oblikPredmeti; }
  return window.VxApi.get(putanja, o);
}, [putanja, opcije, TOKEN]);

const sviRezultati = [];
async function ocekuj(naziv, putanja, kod, opcije = {}, status) {
  const r = await poziv(putanja, opcije);
  sviRezultati.push(r);
  const ok = r.ok === false && r.greska && r.greska.kod === kod && (status === undefined || r.status === status) && !("podaci" in r);
  zapisi("status", naziv, ok, JSON.stringify(r).slice(0, 120));
  return r;
}

// ── Uspeh ────────────────────────────────────────────────────────────────
{
  const r = await poziv("/api/ok", { saTokenom: true });
  sviRezultati.push(r);
  zapisi("status", "200 JSON → ok + podaci", r.ok === true && r.status === 200 && r.podaci.ukupno === 1 && r.podaci.predmeti[0].id === "a");
}

// ── Svaka greška je strukturisana i NIJE prazan rezultat ─────────────────
await ocekuj("401 → AUTH_REQUIRED", "/api/401", "AUTH_REQUIRED", { saTokenom: true }, 401);
await ocekuj("403 → FORBIDDEN", "/api/403", "FORBIDDEN", { saTokenom: true }, 403);
await ocekuj("404 → NOT_FOUND", "/api/404", "NOT_FOUND", { saTokenom: true }, 404);
const r429 = await ocekuj("429 → RATE_LIMITED", "/api/429", "RATE_LIMITED", { saTokenom: true }, 429);
zapisi("status", "429 nosi Retry-After", r429.greska && r429.greska.retryAfter === "17");
await ocekuj("500 → SERVER_ERROR", "/api/500", "SERVER_ERROR", { saTokenom: true }, 500);
await ocekuj("503 (HTML telo) → SERVER_ERROR", "/api/503", "SERVER_ERROR", { saTokenom: true }, 503);
await ocekuj("500 sa telom {predmeti:[]} → i dalje SERVER_ERROR, ne prazna lista", "/api/500-prazna-lista", "SERVER_ERROR", { saTokenom: true }, 500);
await ocekuj("pokvaren JSON → INVALID_RESPONSE", "/api/pokvaren-json", "INVALID_RESPONSE", { saTokenom: true });
await ocekuj("JSON niz umesto objekta → INVALID_RESPONSE", "/api/niz", "INVALID_RESPONSE", { saTokenom: true });
await ocekuj("JSON null → INVALID_RESPONSE", "/api/null", "INVALID_RESPONSE", { saTokenom: true });
await ocekuj("HTML umesto JSON-a → INVALID_RESPONSE", "/api/html", "INVALID_RESPONSE", { saTokenom: true });
await ocekuj("oblik ne odgovara (oblik validator) → INVALID_RESPONSE", "/api/echo", "INVALID_RESPONSE", { saTokenom: true, oblikPredmeti: true });
await ocekuj("pukla veza → NETWORK_ERROR", "/api/prekid", "NETWORK_ERROR", { saTokenom: true }, 0);
await ocekuj("preusmerenje na drugi host → NETWORK_ERROR (ne prati se)", "/api/preusmeri", "NETWORK_ERROR", { saTokenom: true });

// ── Abort ────────────────────────────────────────────────────────────────
{
  const r = await page.evaluate(async (TOKEN) => {
    const c = new AbortController();
    const t0 = performance.now();
    const p = window.VxApi.get("/api/sporo", { token: TOKEN, signal: c.signal });
    setTimeout(() => c.abort(), 100);
    const r = await p;
    return { r, ms: performance.now() - t0 };
  }, TOKEN);
  sviRezultati.push(r.r);
  zapisi("abort", "AbortController → ABORTED", r.r.ok === false && r.r.greska.kod === "ABORTED", JSON.stringify(r.r));
  zapisi("abort", "otkazivanje je odmah (ne čeka spor odgovor)", r.ms < 1500, `${Math.round(r.ms)} ms`);
  const vec = await page.evaluate(async () => { const c = new AbortController(); c.abort(); return window.VxApi.get("/api/ok", { signal: c.signal }); });
  zapisi("abort", "već otkazan signal → ABORTED, zahtev se ne šalje", vec.ok === false && vec.greska.kod === "ABORTED");
}

// ── Zaglavlja i parametri ────────────────────────────────────────────────
{
  // Kolačić MORA postojati na izvoru, inače bi provera „nema kolačića“ bila prazna.
  await page.evaluate(() => { document.cookie = "vx_test_kolacic=1; path=/"; });
  zapisi("zaglavlja", "kontrola: kolačić postoji na izvoru", (await page.evaluate(() => document.cookie)).includes("vx_test_kolacic=1"));
  f.zahtevi.length = 0;
  await poziv("/api/echo", { saTokenom: true, parametri: { status: "aktivan", limit: 500 } });
  const z = f.zahtevi[0];
  zapisi("zaglavlja", "Authorization: Bearer <token> kada token postoji", z && z.auth === `Bearer ${TOKEN}`);
  zapisi("zaglavlja", "metod je GET", z && z.metod === "GET");
  zapisi("zaglavlja", "parametri stižu kao upit", z && z.parametri.status === "aktivan" && z.parametri.limit === "500");
  zapisi("zaglavlja", "nema kolačića (credentials: omit)", z && z.kolacic === null);
  f.zahtevi.length = 0;
  await poziv("/api/echo", {});
  zapisi("zaglavlja", "bez tokena nema Authorization zaglavlja", f.zahtevi[0] && f.zahtevi[0].auth === null);
  f.zahtevi.length = 0;
  await poziv("/api/echo", { token: "" });
  zapisi("zaglavlja", "prazan token ne šalje „Bearer “", f.zahtevi[0] && f.zahtevi[0].auth === null);
}

// ── Konfiguracione greške: zahtev se NE šalje ────────────────────────────
for (const [naziv, putanja, opcije] of [
  ["apsolutni URL drugog hosta", "https://evil.example/api/predmeti", { saTokenom: true }],
  ["protokol-relativna putanja //host", "//evil.example/api/predmeti", { saTokenom: true }],
  ["putanja van /api/", "/index.html", { saTokenom: true }],
  ["upit u putanji umesto parametara", "/api/predmeti?user_id=x", { saTokenom: true }],
  ["user_id parametar", "/api/predmeti", { saTokenom: true, parametri: { user_id: "tudji" } }],
  ["USER_ID (velika slova)", "/api/predmeti", { saTokenom: true, parametri: { USER_ID: "tudji" } }],
  ["uid parametar", "/api/predmeti", { saTokenom: true, parametri: { uid: "tudji" } }],
]) {
  f.zahtevi.length = 0;
  const r = await poziv(putanja, opcije);
  sviRezultati.push(r);
  zapisi("konfiguracija", `${naziv} → CONFIG_ERROR, ništa poslato`, r.ok === false && r.greska.kod === "CONFIG_ERROR" && f.zahtevi.length === 0, JSON.stringify(r).slice(0, 100));
}

// ── Samo čitanje: modul ne izlaže ništa osim get ─────────────────────────
{
  const api = await page.evaluate(() => ({ kljucevi: Object.keys(window.VxApi), zamrznut: Object.isFrozen(window.VxApi) }));
  // NS005: pisanje je odvojena funkcija `send` (tests/live-send.mjs); `get` i dalje samo čita.
  zapisi("samo-citanje", "VxApi izlaže tačno get i send (bez delete) i zamrznut je", api.kljucevi.slice().sort().join(",") === "get,send" && api.zamrznut, api.kljucevi.join(","));
  const metodi = new Set(f.zahtevi.map(z => z.metod));
  zapisi("samo-citanje", "fixture je primio samo GET", [...metodi].every(m => m === "GET"), [...metodi].join(","));
}

// ── Bez ponavljanja ──────────────────────────────────────────────────────
// Meri se na DVA nivoa. (1) Aplikacija: koliko puta src/api.js pozove fetch —
// mora tačno jednom, za svaku klasu ishoda. (2) Server: za 500/429 tačno jedan
// zahtev. Za puklu vezu Chromium-ov mrežni sloj SAM ponovi idempotentan GET
// jednom kada je veza pukla na PONOVO KORIŠĆENOM keep-alive soketu (dokazano:
// na svežoj vezi stiže tačno jedan zahtev). To nije ponavljanje aplikacije i
// ograničeno je na jedan pokušaj — zato je tu granica „najviše 2“, ne „1“.
await page.evaluate(() => {
  const izvorni = window.fetch;
  window.__vxFetchPoziva = 0;
  window.fetch = function () { window.__vxFetchPoziva++; return izvorni.apply(this, arguments); };
});
for (const putanja of ["/api/500", "/api/429", "/api/prekid", "/api/401", "/api/pokvaren-json"]) {
  f.zahtevi.length = 0;
  await page.evaluate(() => { window.__vxFetchPoziva = 0; });
  await poziv(putanja, { saTokenom: true });
  await page.waitForTimeout(300);
  const fetchPoziva = await page.evaluate(() => window.__vxFetchPoziva);
  zapisi("bez-ponavljanja", `${putanja}: aplikacija poziva fetch tačno jednom`, fetchPoziva === 1, `${fetchPoziva}`);
  const naServeru = f.zahtevi.filter(z => z.putanja === putanja).length;
  const granica = putanja === "/api/prekid" ? 2 : 1;
  zapisi("bez-ponavljanja", `${putanja}: server prima ${granica === 1 ? "tačno jedan" : "najviše dva (mrežni sloj pregledača)"} zahtev`, naServeru >= 1 && naServeru <= granica, `${naServeru}`);
}

zapisi("izolacija", "nijedan zahtev ka hostu van 127.0.0.1", spoljni.length === 0, spoljni.join(","));

await browser.close();
await f.zatvori();

// ── Token ne sme biti nigde osim u Authorization zaglavlju ──────────────
const tekstRezultata = JSON.stringify(sviRezultati);
zapisi("token", "token nije ni u jednom rezultatu/grešci", !tekstRezultata.includes(TOKEN));
zapisi("token", "token nije u konzoli stranice", !konzola.join("\n").includes(TOKEN), `${konzola.length} poruka`);
zapisi("token", "token nije u izlazu testa", !izlazTesta.join("\n").includes(TOKEN));

console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
