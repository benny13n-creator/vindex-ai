// Vindex V2 NG — Task 1: granica DEMO / LIVE i dev API proxy.
// Pokretanje: `node tests/live-runtime.mjs` (sam podiže svoje servere; ne treba 4317).
//
// Dokazuje:
//  • DEMO je podrazumevan i nepromenjen (12 predmeta, demo podaci postoje);
//  • LIVE nikad ne učitava demo podatke (VX_DEMO ne postoji, nijedan demo
//    naziv ni obaveza nisu u DOM-u) i ne tvrdi „nema predmeta“;
//  • neispravna konfiguracija pada glasno (ne prelazi u DEMO);
//  • dev proxy odbija svaki ne-loopback cilj i ne pokreće se;
//  • proxy prosleđuje samo GET, Authorization stiže do backend-a, ali se nikad
//    ne pojavljuje u izlazu servera;
//  • bez proxy podešavanja `/api/*` nikad ne izlazi sa mašine.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import http from "node:http";
import { fileURLToPath } from "node:url";

const KOREN = fileURLToPath(new URL("..", import.meta.url));
const TOKEN = "vx-test-token-NE-SME-U-LOG-7f3a9c";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

function pokreniServer(port, env = {}) {
  const deca = spawn(process.execPath, ["serve.mjs", String(port)], {
    cwd: KOREN, env: { ...process.env, ...env }, stdio: ["ignore", "pipe", "pipe"],
  });
  const izlaz = { tekst: "" };
  deca.stdout.on("data", d => { izlaz.tekst += d; });
  deca.stderr.on("data", d => { izlaz.tekst += d; });
  const kraj = new Promise(r => deca.on("exit", (kod) => r(kod)));
  return { deca, izlaz, kraj };
}
async function spreman(port) {
  for (let i = 0; i < 100; i++) {
    const ok = await new Promise(r => http.get({ host: "127.0.0.1", port, path: "/" }, s => { s.resume(); r(true); }).on("error", () => r(false)));
    if (ok) return true;
    await new Promise(r => setTimeout(r, 50));
  }
  return false;
}
function zahtev(port, metod, putanja, zaglavlja = {}) {
  return new Promise((r) => {
    const z = http.request({ host: "127.0.0.1", port, method: metod, path: putanja, headers: zaglavlja }, (s) => {
      let telo = ""; s.on("data", d => telo += d); s.on("end", () => r({ status: s.statusCode, telo }));
    });
    z.on("error", (e) => r({ status: 0, telo: String(e) }));
    z.end();
  });
}

// ── Fixture backend (loopback) ────────────────────────────────────────────
const primljeno = [];
const backend = http.createServer((req, res) => {
  primljeno.push({ metod: req.method, putanja: req.url, auth: req.headers.authorization || null });
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ predmeti: [], ukupno: 0, limit: 200, offset: 0 }));
});
await new Promise(r => backend.listen(0, "127.0.0.1", r));
const BPORT = backend.address().port;

// ── 1. Browser: DEMO / LIVE / neispravno ─────────────────────────────────
const SPORT = 4391;
const glavni = pokreniServer(SPORT);
zapisi("server", "statički server se podiže", await spreman(SPORT));
const browser = await chromium.launch();

async function otvori(upit) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const p = await ctx.newPage();
  const greske = [];
  const mreza = [];
  p.on("pageerror", e => greske.push(String(e)));
  p.on("console", m => { if (m.type() === "error") greske.push(m.text()); });
  p.on("request", q => { if (new URL(q.url()).pathname.startsWith("/api/")) mreza.push(q.url()); });
  await p.goto(`http://127.0.0.1:${SPORT}/${upit}`);
  await p.evaluate(() => document.fonts.ready);
  return { p, ctx, greske, mreza };
}

// Svi demo nazivi i naslovi obaveza, pročitani iz STVARNOG DEMO ekrana.
const d = await otvori("");
const demoInfo = await d.p.evaluate(() => ({
  rezim: window.VxRuntime && window.VxRuntime.rezim,
  imaDemo: !!window.VX_DEMO,
  redovi: document.querySelectorAll("#rows tr").length,
  nazivi: window.VX_DEMO ? window.VX_DEMO.predmeti.map(p => p.naziv) : [],
  obaveze: window.VX_DEMO ? window.VX_DEMO.paznja.map(s => s.naslov) : [],
  klijenti: window.VX_DEMO ? window.VX_DEMO.predmeti.map(p => p.klijent) : [],
}));
zapisi("demo", "bez parametra režim je DEMO", demoInfo.rezim === "demo", demoInfo.rezim);
zapisi("demo", "DEMO ima demo podatke i 12 redova", demoInfo.imaDemo && demoInfo.redovi === 12, `redova=${demoInfo.redovi}`);
zapisi("demo", "DEMO bez JS grešaka", d.greske.length === 0, d.greske.join(" | "));
zapisi("demo", "DEMO ne šalje nijedan /api zahtev", d.mreza.length === 0, d.mreza.join(","));
const demoRedovi = await d.p.locator("#rows").innerText();
await d.ctx.close();

const dd = await otvori("?rezim=demo");
zapisi("demo", "?rezim=demo je identičan podrazumevanom DEMO", (await dd.p.locator("#rows").innerText()) === demoRedovi);
await dd.ctx.close();

const ZABRANJENO = [...demoInfo.nazivi, ...demoInfo.obaveze, ...demoInfo.klijenti.filter(k => k.length > 6)];

async function proveriBezDemoa(upit, ocekivanoStanje, oznaka) {
  const o = await otvori(upit);
  const info = await o.p.evaluate(() => ({
    rezim: window.VxRuntime && window.VxRuntime.rezim,
    vxDemo: typeof window.VX_DEMO,
    redovi: document.querySelectorAll("#rows tr").length,
    stavke: document.querySelectorAll("#attention li").length,
    stanje: document.getElementById("empty").dataset.stanje || "",
    praznoVidljivo: !document.getElementById("empty").hidden,
    naslov: document.getElementById("empty-title").textContent,
    tekstStrane: document.body.innerText,
    pretragaIskljucena: document.getElementById("pretraga").disabled,
    panelStanje: document.getElementById("attention-empty").dataset.stanje || "",
    panelNaslov: document.querySelector("#attention-empty .panel__empty-title").textContent,
  }));
  zapisi(oznaka, "VX_DEMO ne postoji", info.vxDemo === "undefined", info.vxDemo);
  zapisi(oznaka, "nijedan red registra", info.redovi === 0, `redova=${info.redovi}`);
  zapisi(oznaka, "nijedna stavka u panelu", info.stavke === 0, `stavki=${info.stavke}`);
  const procureli = ZABRANJENO.filter(z => info.tekstStrane.includes(z));
  zapisi(oznaka, "nijedan demo naziv/obaveza/klijent u tekstu strane", procureli.length === 0, procureli.slice(0, 3).join(" | "));
  zapisi(oznaka, `stanje registra je „${ocekivanoStanje}“ i vidljivo`, info.stanje === ocekivanoStanje && info.praznoVidljivo, info.stanje);
  zapisi(oznaka, "ne tvrdi „Nema aktivnih predmeta“", !/Nema aktivnih predmeta/.test(info.naslov), info.naslov);
  zapisi(oznaka, "pretraga je isključena", info.pretragaIskljucena);
  zapisi(oznaka, "panel ne tvrdi „nema obaveza/rokova“", info.panelStanje === "nepovezano" && !/Nema (stavki|obaveza|rokova)/.test(info.panelNaslov), info.panelNaslov);
  zapisi(oznaka, "bez JS grešaka", o.greske.length === 0, o.greske.join(" | "));
  // Klik na sortiranje ne sme da „oživi“ registar ni prazno stanje.
  // Registar je sakriven, pa se rukovalac okida direktno (isto što bi uradio
  // skripta ili tastatura kad bi dugme postalo dostupno).
  await o.p.evaluate(() => document.querySelector('.cases th[data-kljuc="naziv"] .sort').dispatchEvent(new MouseEvent("click", { bubbles: true })));
  await o.p.evaluate(() => { const i = document.getElementById("pretraga"); i.value = "a"; i.dispatchEvent(new Event("input", { bubbles: true })); });
  const posle = await o.p.evaluate(() => ({ redovi: document.querySelectorAll("#rows tr").length, stanje: document.getElementById("empty").dataset.stanje, naslov: document.getElementById("empty-title").textContent }));
  zapisi(oznaka, "sortiranje ne menja stanje u „prazno“", posle.redovi === 0 && posle.stanje === ocekivanoStanje && !/Nema aktivnih/.test(posle.naslov), posle.naslov);
  await o.ctx.close();
}

// Od Task 3 LIVE bez sesije prijavljuje „bez-prijave“ (pre bilo kakvog izvora
// podataka). Kriterijum Task 1 je isti: nema demo podataka, nema „prazne kancelarije“.
await proveriBezDemoa("?rezim=live", "bez-prijave", "live");
await proveriBezDemoa("?rezim=xyz", "neispravna-konfiguracija", "neispravno:xyz");
await proveriBezDemoa("?rezim=LIVE", "neispravna-konfiguracija", "neispravno:LIVE");
await proveriBezDemoa("?rezim=", "neispravna-konfiguracija", "neispravno:prazno");
await proveriBezDemoa("?rezim=live&predmeti=veliko", "bez-prijave", "live+demo-scenario");

await browser.close();
glavni.deca.kill();

// ── 2. Dev proxy: odbijanje ne-loopback ciljeva ──────────────────────────
const LOSI = [
  "https://vindex.rs", "http://vindex.rs:80", "https://vindex-ai-production.up.railway.app",
  "https://czsxymueizfqrbbgqqob.supabase.co", "http://10.0.0.5:8000", "http://192.168.1.10:8000",
  "http://localhost.evil.com:8000", "http://127.0.0.1.nip.io:8000", "http://[::1]:8000",
  "http://user:pw@127.0.0.1:8000", "http://127.0.0.1", "http://127.0.0.1:8000/api",
  "https://127.0.0.1:8000", "nije-url", "",
];
let port = 4400;
for (const losi of LOSI) {
  const s = pokreniServer(port++, { VINDEX_LOCAL_API_ORIGIN: losi });
  const kod = await Promise.race([s.kraj, new Promise(r => setTimeout(() => r("radi"), 4000))]);
  if (kod === "radi") s.deca.kill();
  zapisi("proxy-odbija", JSON.stringify(losi), kod === 1 && /odbijen/.test(s.izlaz.tekst), `izlaz=${kod}`);
}

// ── 3. Dev proxy: loopback radi, samo GET, token se ne loguje ────────────
for (const host of ["127.0.0.1", "localhost"]) {
  const PP = port++;
  const s = pokreniServer(PP, { VINDEX_LOCAL_API_ORIGIN: `http://${host}:${BPORT}` });
  zapisi("proxy", `${host}: server se podiže`, await spreman(PP));
  primljeno.length = 0;
  const r = await zahtev(PP, "GET", "/api/predmeti?status=aktivan&limit=500", { Authorization: `Bearer ${TOKEN}` });
  zapisi("proxy", `${host}: GET stiže do lokalnog backend-a sa istom putanjom`, r.status === 200 && primljeno.length === 1 && primljeno[0].putanja === "/api/predmeti?status=aktivan&limit=500", `status=${r.status}`);
  zapisi("proxy", `${host}: Authorization stiže do backend-a nepromenjen`, primljeno[0] && primljeno[0].auth === `Bearer ${TOKEN}`);
  zapisi("proxy", `${host}: odgovor backend-a se prenosi`, r.telo.includes('"ukupno":0'));
  for (const m of ["POST", "PUT", "PATCH", "DELETE"]) {
    primljeno.length = 0;
    const w = await zahtev(PP, m, "/api/predmeti", { Authorization: `Bearer ${TOKEN}` });
    zapisi("proxy", `${host}: ${m} → 405 i ne stiže do backend-a`, w.status === 405 && primljeno.length === 0, `status=${w.status} stiglo=${primljeno.length}`);
  }
  const st = await zahtev(PP, "GET", "/index.html");
  zapisi("proxy", `${host}: statika i dalje radi`, st.status === 200);
  s.deca.kill(); await s.kraj;
  zapisi("proxy", `${host}: token se NE pojavljuje u izlazu servera`, !s.izlaz.tekst.includes(TOKEN) && !/authorization/i.test(s.izlaz.tekst));
}

// ── 4. Bez proxy podešavanja /api nikad ne izlazi ────────────────────────
{
  const PP = port++;
  const env = { ...process.env }; delete env.VINDEX_LOCAL_API_ORIGIN;
  const deca = spawn(process.execPath, ["serve.mjs", String(PP)], { cwd: KOREN, env, stdio: "ignore" });
  await spreman(PP);
  primljeno.length = 0;
  const r = await zahtev(PP, "GET", "/api/predmeti", { Authorization: `Bearer ${TOKEN}` });
  zapisi("bez-proxyja", "GET /api/predmeti → 404, ništa ne izlazi", r.status === 404 && primljeno.length === 0, `status=${r.status}`);
  deca.kill();
}

backend.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
