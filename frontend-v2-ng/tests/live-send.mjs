// Vindex V2 NG — NS005 Task 1: bezbedan transport za pisanje (VxApi.send).
// Pokretanje: `node tests/live-send.mjs` (sam podiže fixture server).
//
// Stvaran fetch u Chromium-u prema loopback fixture-u. Dokazuje:
//  • POST/PATCH nose JSON ili FormData, Bearer token tekuće sesije, bez kolačića;
//  • drugi metodi, drugi host, putanja van /api/ i polje vlasnika → ništa poslato;
//  • 400/401/403/404/409/413/415/422/429/5xx → strukturisan neuspeh, nikad uspeh;
//  • mreža/prekid/otkazivanje POSLE slanja → ishod NEPOZNAT (ne „nije sačuvano“);
//  • nijedno ponavljanje; token nije ni u jednom izlazu.

import { chromium } from "playwright";
import { pokreniFixture, json } from "./fixtures/api-fixture.mjs";

const TOKEN = "vx-send-test-token-NE-SME-U-LOG-77c3";
let pada = 0, ukupno = 0;
const izlazTesta = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const linija = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlazTesta.push(linija); console.log(linija);
}

const tela = [];
function procitajTelo(req) {
  return new Promise((r) => { const d = []; req.on("data", c => d.push(c)); req.on("end", () => r(Buffer.concat(d).toString("utf8"))); });
}

const f = await pokreniFixture(async (req, url, res) => {
  const p = url.pathname;
  const telo = await procitajTelo(req);
  tela.push({ putanja: p, metod: req.method, telo, tip: req.headers["content-type"] || null });
  if (p === "/api/echo") return json(res, 200, { metod: req.method, tip: req.headers["content-type"] || null, duzina: telo.length, id: "novi-1" }), true;
  const m = /^\/api\/status\/(\d{3})$/.exec(p);
  if (m) {
    const s = Number(m[1]);
    if (s === 422) return json(res, 422, { detail: [{ loc: ["body", "naziv"], msg: "field required SECRET-COLUMN predmeti.user_id", type: "missing" }, { loc: ["body", "<script>"], msg: "x" }] }), true;
    if (s === 429) return json(res, 429, { detail: "Rate" }, { "Retry-After": "9" }), true;
    return json(res, s, { detail: "tabela predmeti kolona user_id SQL detalj" }), true;
  }
  if (p === "/api/prekid") { req.socket.destroy(); return true; }
  if (p === "/api/sporo") { await new Promise(r => setTimeout(r, 2500)); if (!res.destroyed) json(res, 200, { kasno: true }); return true; }
  if (p === "/api/nije-json") { res.writeHead(201, { "Content-Type": "text/plain" }); res.end("Created"); return true; }
  if (p === "/api/prazno") { res.writeHead(204); res.end(); return true; }
  if (p === "/api/preusmeri") { res.writeHead(307, { Location: "https://example.com/upis" }); res.end(); return true; }
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
await ctx.addCookies([{ name: "vx_kolacic", value: "ne-sme", url: `http://127.0.0.1:${f.port}/` }]);
await page.evaluate(() => {
  window.__fetchPoziva = 0;
  const orig = window.fetch.bind(window);
  window.fetch = (...a) => { window.__fetchPoziva++; return orig(...a); };
});

const sviRezultati = [];
const send = (putanja, opcije = {}) => page.evaluate(async ([putanja, opcije, TOKEN]) => {
  const o = Object.assign({}, opcije);
  if (o.saTokenom) { o.token = TOKEN; delete o.saTokenom; }
  if (o.formData) { const fd = new FormData(); for (const [k, v] of Object.entries(o.formData)) fd.append(k, v); o.telo = fd; delete o.formData; }
  if (o.oblikId) { o.oblik = (d) => typeof d.id === "string"; delete o.oblikId; }
  return window.VxApi.send(putanja, o);
}, [putanja, opcije, TOKEN]).then(r => { sviRezultati.push(r); return r; });
const poziva = () => page.evaluate(() => window.__fetchPoziva);
const nuluj = () => { f.zahtevi.length = 0; tela.length = 0; return page.evaluate(() => { window.__fetchPoziva = 0; }); };

// ── Uspeh: JSON i FormData ───────────────────────────────────────────────
{
  await nuluj();
  const r = await send("/api/echo", { saTokenom: true, telo: { naziv: "Predmet X" } });
  const z = f.zahtevi[0] || {};
  zapisi("uspeh", "POST JSON → ok + podaci", r.ok === true && r.status === 200 && r.podaci.metod === "POST", JSON.stringify(r).slice(0, 100));
  zapisi("uspeh", "server dobija Authorization: Bearer <token tekuće sesije>", z.auth === "Bearer " + TOKEN);
  zapisi("uspeh", "telo je JSON sa Content-Type application/json", tela[0] && tela[0].tip === "application/json" && JSON.parse(tela[0].telo).naziv === "Predmet X");
  zapisi("uspeh", "kolačić se ne šalje", z.kolacic === null, String(z.kolacic));
}
{
  await nuluj();
  const r = await send("/api/echo", { saTokenom: true, metod: "PATCH", telo: { status: "aktivan" } });
  zapisi("uspeh", "PATCH → ok", r.ok === true && f.zahtevi[0] && f.zahtevi[0].metod === "PATCH");
}
{
  await nuluj();
  const r = await send("/api/echo", { saTokenom: true, formData: { naziv: "spis.pdf" } });
  zapisi("uspeh", "FormData → multipart sa granicom koju postavlja pregledač", r.ok === true && /^multipart\/form-data; boundary=/.test(tela[0] && tela[0].tip || ""), tela[0] && tela[0].tip);
}
{
  await nuluj();
  const r = await send("/api/echo", { saTokenom: true, telo: {}, oblikId: true });
  zapisi("uspeh", "oblik provera prolazi za ispravan odgovor", r.ok === true && r.podaci && r.podaci.id === "novi-1");
}
{
  await nuluj();
  const r = await send("/api/nije-json", { saTokenom: true, telo: {} });
  zapisi("uspeh", "2xx bez JSON tela → upis prihvaćen, podaci null, označeno neispravanOdgovor", r.ok === true && r.podaci === null && r.neispravanOdgovor === true);
  const r2 = await send("/api/prazno", { saTokenom: true, telo: {} });
  zapisi("uspeh", "204 → upis prihvaćen, neispravanOdgovor (nema podataka)", r2.ok === true && r2.podaci === null && r2.neispravanOdgovor === true);
}

// ── Ništa se ne šalje: metod, adresa, vlasnik, token ─────────────────────
for (const [naziv, putanja, opcije] of [
  ["metod PUT nije dozvoljen", "/api/echo", { saTokenom: true, metod: "PUT", telo: {} }],
  ["metod DELETE nije dozvoljen", "/api/echo", { saTokenom: true, metod: "DELETE" }],
  ["metod GET nije pisanje", "/api/echo", { saTokenom: true, metod: "GET" }],
  ["apsolutni URL drugog hosta", "https://evil.example/api/echo", { saTokenom: true, telo: {} }],
  ["protokol-relativna putanja //host", "//evil.example/api/echo", { saTokenom: true, telo: {} }],
  ["putanja van /api/", "/index.html", { saTokenom: true, telo: {} }],
  ["upit u putanji", "/api/echo?user_id=x", { saTokenom: true, telo: {} }],
  ["sličan prefiks /klijentix", "/klijentix", { saTokenom: true, telo: {} }],
  ["izlazak iz /api/ preko ..", "/api/../index.html", { saTokenom: true, telo: {} }],
  ["segment . u putanji", "/api/./echo", { saTokenom: true, telo: {} }],
  ["fragment u putanji", "/api/echo#x", { saTokenom: true, telo: {} }],
  ["obrnuta kosa crta", "/api/x\\..\\..\\index.html", { saTokenom: true, telo: {} }],
  ["user_id u telu", "/api/echo", { saTokenom: true, telo: { naziv: "x", user_id: "tudji" } }],
  ["USER_ID (velika slova) u telu", "/api/echo", { saTokenom: true, telo: { USER_ID: "tudji" } }],
  ["owner_id u telu", "/api/echo", { saTokenom: true, telo: { owner_id: "tudji" } }],
  ["tenant_id u telu", "/api/echo", { saTokenom: true, telo: { tenant_id: "tudji" } }],
  ["user_id u FormData", "/api/echo", { saTokenom: true, formData: { user_id: "tudji" } }],
]) {
  await nuluj();
  const r = await send(putanja, opcije);
  zapisi("odbijeno-lokalno", `${naziv} → CONFIG_ERROR, ništa poslato`, r.ok === false && r.greska.kod === "CONFIG_ERROR" && f.zahtevi.length === 0 && (await poziva()) === 0, JSON.stringify(r).slice(0, 90));
}
{
  await nuluj();
  const r = await send("/api/echo", { telo: { naziv: "x" } });
  zapisi("odbijeno-lokalno", "bez tokena → AUTH_REQUIRED, ništa poslato (pisanje nikad bez Authorization)", r.ok === false && r.greska.kod === "AUTH_REQUIRED" && f.zahtevi.length === 0);
  const r2 = await send("/api/echo", { token: "", telo: { naziv: "x" } });
  zapisi("odbijeno-lokalno", "prazan token → AUTH_REQUIRED, ništa poslato", r2.ok === false && r2.greska.kod === "AUTH_REQUIRED" && f.zahtevi.length === 0);
}
{
  await nuluj();
  const r = await page.evaluate(async (T) => { const c = new AbortController(); c.abort(); return window.VxApi.send("/api/echo", { token: T, telo: {}, signal: c.signal }); }, TOKEN);
  sviRezultati.push(r);
  zapisi("odbijeno-lokalno", "već otkazan signal → ABORTED, ništa poslato, ishod poznat (ništa nije upisano)", r.greska && r.greska.kod === "ABORTED" && !r.greska.ishodNepoznat && f.zahtevi.length === 0);
}

{
  // `/klijenti` (postojeći CRM ruter bez /api prefiksa) je JEDINI dozvoljen izuzetak.
  await nuluj();
  const r = await send("/klijenti", { saTokenom: true, telo: { ime: "Ana" } });
  zapisi("granica", "/klijenti je dozvoljen (zahtev poslat na isti izvor)", f.zahtevi.length === 1 && f.zahtevi[0].putanja === "/klijenti" && r.greska && r.greska.kod === "NOT_FOUND", JSON.stringify(r).slice(0, 80));
}

// ── Odbijanje servera: strukturisano, nikad uspeh ────────────────────────
const OCEKIVANO = { 400: "BAD_REQUEST", 401: "AUTH_REQUIRED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 413: "TOO_LARGE",
                    415: "UNSUPPORTED_MEDIA", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED", 500: "SERVER_ERROR", 502: "SERVER_ERROR", 503: "SERVER_ERROR" };
for (const [s, kod] of Object.entries(OCEKIVANO)) {
  await nuluj();
  const r = await send(`/api/status/${s}`, { saTokenom: true, telo: { naziv: "x" } });
  const ok = r.ok === false && r.greska.kod === kod && r.status === Number(s) && !("podaci" in r);
  zapisi("status", `${s} → ${kod}`, ok, JSON.stringify(r).slice(0, 110));
  const nepoznat = Number(s) >= 500;
  zapisi("status", `${s}: ishodNepoznat=${nepoznat} (${nepoznat ? "server je možda upisao" : "server je odbio upis"})`, r.greska && r.greska.ishodNepoznat === nepoznat);
  zapisi("bez-ponavljanja", `${s}: tačno jedan zahtev`, f.zahtevi.length === 1 && (await poziva()) === 1, `${f.zahtevi.length}/${await poziva()}`);
}
{
  await nuluj();
  const r = await send("/api/status/422", { saTokenom: true, telo: {} });
  zapisi("status", "422 nosi samo imena polja (naziv), bez sirovog teksta servera", JSON.stringify(r.greska.polja) === '["naziv"]' && !JSON.stringify(r).includes("SECRET-COLUMN"), JSON.stringify(r.greska));
  const r2 = await send("/api/status/500", { saTokenom: true, telo: {} });
  zapisi("status", "telo greške servera (SQL detalj) ne prolazi u rezultat", !JSON.stringify(r2).includes("SQL") && !JSON.stringify(r2).includes("kolona"));
  const r3 = await send("/api/status/429", { saTokenom: true, telo: {} });
  zapisi("status", "429 prenosi Retry-After", r3.greska.retryAfter === "9");
}

// ── Ishod nepoznat: zahtev je stigao, odgovor nije ───────────────────────
{
  await nuluj();
  const r = await send("/api/prekid", { saTokenom: true, telo: { naziv: "x" } });
  zapisi("ishod-nepoznat", "prekid veze posle slanja → OUTCOME_UNKNOWN + ishodNepoznat", r.ok === false && r.greska.kod === "OUTCOME_UNKNOWN" && r.greska.ishodNepoznat === true, JSON.stringify(r).slice(0, 100));
  zapisi("ishod-nepoznat", "zahtev JESTE stigao do servera (zato ishod nije „nije sačuvano“)", tela.length >= 1 && tela.every(t => t.putanja === "/api/prekid"), JSON.stringify(tela.map(t => t.putanja)));
  zapisi("ishod-nepoznat", "poruka ne tvrdi da nije sačuvano", !/nije sa[cč]uvan/i.test(r.greska.poruka), r.greska.poruka);
  zapisi("bez-ponavljanja", "prekid: VxApi poziva fetch tačno jednom (sloj ne ponavlja)", (await poziva()) === 1);
  // POZNATO OGRANIČENJE (ne kvar ovog sloja): kada se PONOVO KORIŠĆENA keep-alive
  // veza prekine pre ijednog bajta odgovora, sam Chromium ponovo šalje zahtev
  // (pretpostavlja da je server zatvorio neaktivnu vezu). JavaScript to ne može da
  // spreči; jedina zaštita je idempotentni ključ na serveru (van NS005). Beleži se
  // izmereno, ne skriva se.
  console.log(`INFO  [ogranicenje] server je primio ${tela.length} zahtev(a) za 1 fetch na ponovo korišćenoj vezi`);
}
{
  // Ista situacija na SVEŽOJ vezi (novi kontekst): pregledač nema razlog da ponovi.
  const c2 = await browser.newContext();
  const p2 = await c2.newPage();
  await p2.goto(`http://127.0.0.1:${f.port}/`);
  await nuluj();
  const r = await p2.evaluate((T) => window.VxApi.send("/api/prekid", { token: T, telo: { naziv: "x" } }), TOKEN);
  sviRezultati.push(r);
  const prekidi = f.zahtevi.filter(z => z.putanja === "/api/prekid").length;
  zapisi("bez-ponavljanja", "sveža veza: server prima tačno jedan zahtev, ishod nepoznat", prekidi === 1 && r.greska && r.greska.ishodNepoznat === true, `zahteva=${prekidi}`);
  await c2.close();
}
{
  await nuluj();
  const r = await page.evaluate(async (T) => {
    const c = new AbortController();
    const p = window.VxApi.send("/api/sporo", { token: T, telo: { naziv: "x" }, signal: c.signal });
    setTimeout(() => c.abort(), 300);
    return p;
  }, TOKEN);
  sviRezultati.push(r);
  zapisi("ishod-nepoznat", "otkazivanje u letu → ABORTED + ishodNepoznat (upis je možda izvršen)", r.greska && r.greska.kod === "ABORTED" && r.greska.ishodNepoznat === true, JSON.stringify(r).slice(0, 100));
  zapisi("bez-ponavljanja", "otkazivanje: tačno jedan zahtev", f.zahtevi.length === 1);
}
{
  await nuluj();
  const r = await send("/api/preusmeri", { saTokenom: true, telo: { naziv: "x" } });
  zapisi("izolacija", "preusmerenje se ne prati (upis ne ide na drugi host) → ishod nepoznat", r.ok === false && r.greska.ishodNepoznat === true && spoljni.length === 0, JSON.stringify(r).slice(0, 90));
}

// ── GET ostaje isti; modul izlaže tačno get i send ───────────────────────
{
  const api = await page.evaluate(() => ({ kljucevi: Object.keys(window.VxApi).sort().join(","), zamrznut: Object.isFrozen(window.VxApi) }));
  zapisi("granica", "VxApi izlaže tačno get i send i zamrznut je (nema delete)", api.kljucevi === "get,send" && api.zamrznut, api.kljucevi);
}

await browser.close();
await f.zatvori();

zapisi("izolacija", "nijedan zahtev ka hostu van 127.0.0.1", spoljni.length === 0, spoljni.join(","));
zapisi("token", "token nije ni u jednom rezultatu/grešci", !JSON.stringify(sviRezultati).includes(TOKEN));
zapisi("token", "token nije u konzoli stranice", !konzola.join("\n").includes(TOKEN), konzola.length + " poruka");
zapisi("token", "token nije u izlazu testa", !izlazTesta.join("\n").includes(TOKEN));

console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
