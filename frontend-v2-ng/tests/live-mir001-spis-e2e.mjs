// Vindex V2 NG — MIR001 TASK-02: ceo Golden Case spis (7 procesnih dokumenata, jedan skeniran) kroz STVARAN V2 /app
// (Prijem → Prikači → Dokumenti) nad PRAVIM api.app koji STVARNO upisuje. Pokretanje: `node tests/live-mir001-spis-e2e.mjs`.
// Server: tests/osb003_solo_server.py (stvarne rute, stvaran intake worker i dispečer, STVARAN Tesseract ako je na PATH-u;
// simulirani modeli/embedding/prijava). Svaki korak se proverava u UI-ju I u bazi (GET /__osb003/stanje).
// Bez Tesseract-a test PADA (sken mora proći kroz stvaran OCR) — nikad tiho preskakanje.

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4531, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

// Golden Case PDF-ovi iz istog determinističkog korpusa koji koriste Python testovi (tests/mir001_golden_case.py)
const dir = await mkdtemp(join(tmpdir(), "vx-mir001-"));
const gen = spawnSync(PY, ["-c", `
import sys, os, json; sys.path.insert(0, sys.argv[1])
from tests import mir001_golden_case as gc
for d in gc.DOKUMENTI:
    open(os.path.join(sys.argv[2], d["ime"]), "wb").write(gc.bajtovi(d))
print(json.dumps({"ocr": __import__("pytesseract").get_tesseract_version().public}))`, REPO, dir], { encoding: "utf-8", cwd: REPO });
if (gen.status !== 0) { console.log(gen.stderr.slice(-800)); zapisi("ocr", "Tesseract dostupan (sken mora kroz stvaran OCR)", false); process.exit(1); }
zapisi("ocr", "Tesseract dostupan serveru", true, gen.stdout.trim().split("\n").pop());
const FAJLOVI = (await readdir(dir)).sort().map(f => join(dir, f));
zapisi("korpus", "7 dokumenata Golden Case-a generisano", FAJLOVI.length === 7, String(FAJLOVI.length));

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, { method = "GET", telo = null, token = null } = {}) => new Promise(r => {
  const h = { "Content-Type": "application/json" };
  if (token) h.Authorization = "Bearer " + token;
  const q = http.request(BASE + p, { method, headers: h }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); });
  q.on("error", () => r({ s: 0, b: "" })); if (telo) q.write(JSON.stringify(telo)); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const stanje = async () => JSON.parse((await zahtev("/__osb003/stanje")).b);
const obradi = async () => JSON.parse((await zahtev("/__osb003/obradi", { method: "POST" })).b);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const spoljni = [], greskeJS = [];
await ctx.route("**/*", r => {
  const u = new URL(r.request().url());
  if (u.hostname !== "127.0.0.1") { spoljni.push(u.href); return r.abort(); }
  if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
  return r.continue();
});
await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
  [KLJUC, JSON.stringify({ access_token: "tok-A", refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "uid-A" } })]);
const p = await ctx.newPage();
p.setDefaultTimeout(10000);
p.on("pageerror", e => greskeJS.push(String(e)));
const cekaj = (fn, arg, ms = 20000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);

// 1) Nov predmet kroz V2 formu „Nov predmet“ — kao advokat, ne kroz API
await p.goto(`${BASE}/app#/predmeti/nov`);
const forma = await cekaj(() => !document.getElementById("nov-predmet").hidden && !!document.getElementById("nov-naziv"), null, 10000);
let pid = null;
if (forma) {
  await p.fill("#nov-naziv", "Alfa Fiktiv protiv Beta Primer Gradnja (P 9901/2026, SINTETICKI)");
  const odgovor = p.waitForResponse(r => new URL(r.url()).pathname === "/api/predmeti" && r.request().method() === "POST");
  await p.fill("#nov-tip", "Privredni spor");
  await p.click("#nov-posalji");
  const r = await odgovor.catch(() => null);
  pid = r ? ((await r.json().catch(() => ({}))).predmet || {}).id : null;
}
zapisi("1.predmet", "predmet napravljen kroz V2 formu „Nov predmet“", /^[0-9a-f-]{36}$/.test(pid || ""), String(pid));
if (!pid) {   // forma nije pronađena — ne prikrivamo: ovaj korak je već PAD; ostatak ide kroz API da bi se merio prijem
  const np = await zahtev("/api/predmeti", { method: "POST", telo: { naziv: "Alfa Fiktiv protiv Beta Primer Gradnja (SINTETICKI)" }, token: "tok-A" });
  pid = (JSON.parse(np.b || "{}").predmet || {}).id;
}

// 2) Prijem: svih 7 fajlova jednim izborom i jednim „Otpremi“
await p.goto(`${BASE}/app#/predmeti/${pid}/prijem`);
await cekaj(() => !document.getElementById("odeljak-prijem").hidden);
await p.setInputFiles("#pd-fajlovi", FAJLOVI);
await p.click("#pd-otpremi");
const poslovi7 = await cekaj(() => document.querySelectorAll("#pd-poslovi .intake").length === 7);
zapisi("2.prijem", "UI prikazuje 7 poslova prijema", poslovi7, String(await p.evaluate(() => document.querySelectorAll("#pd-poslovi .intake").length)));
const o = await obradi();
zapisi("2.prijem", "stvaran worker obradio svih 7 (bez grešaka dispečera)", o.poslova >= 7 && o.greske === 0, JSON.stringify(o));

// 3) Za svaki posao: pregled (ako traži) → „Prikači ovom predmetu“
await cekaj(() => [...document.querySelectorAll("#pd-poslovi .intake")].every(li => /Potvrđujem pregled|Prikači ovom predmetu|Prikačeno ovom predmetu/.test(li.innerText)), null, 40000);
for (let i = 0; i < 7; i++) {
  const li = p.locator("#pd-poslovi .intake").nth(i);
  if (await li.locator("button", { hasText: "Potvrđujem pregled" }).count()) {
    await li.locator("button", { hasText: "Potvrđujem pregled" }).first().click();
    await p.waitForTimeout(400);
  }
  const prikaci = li.locator("button", { hasText: "Prikači ovom predmetu" });
  if (await prikaci.count()) await prikaci.first().click();
  await cekaj((i) => /Prikačeno ovom predmetu/.test(document.querySelectorAll("#pd-poslovi .intake")[i].innerText), i, 20000);
}
await obradi();
const ui = await p.evaluate(() => [...document.querySelectorAll("#pd-poslovi .intake")].map(li => li.innerText));
let st = await stanje();
zapisi("3.prikacivanje", "UI: svih 7 „Prikačeno ovom predmetu“", ui.filter(t => /Prikačeno ovom predmetu/.test(t)).length === 7,
  ui.map(t => t.split("\n")[0]).join(" | ").slice(0, 300));
zapisi("3.prikacivanje", "baza: tačno 7 dokumenata, svi u jednom predmetu, 7 poslova prikačeno",
  st.dokumenti === 7 && JSON.stringify(st.dokumenti_po_predmetu) === "[7]" && st.poslovi_prikaceni === 7, JSON.stringify({ d: st.dokumenti, pp: st.dokumenti_po_predmetu, pr: st.poslovi_prikaceni }));
const skenUI = ui.find(t => /Nalaz i misljenje vestaka/.test(t)) || "";
zapisi("3.prikacivanje", "UI za sken prikazuje „tekst pročitan OCR-om“", /tekst pročitan OCR-om/.test(skenUI), skenUI.slice(0, 160).replace(/\n/g, " / "));
zapisi("3.prikacivanje", "nijedan lažan uspeh: nema „NIJE prikačen“ ni „Ishod nije poznat“", !ui.some(t => /NIJE prikačen|Ishod nije poznat/.test(t)));

// 4) Dvostruko „Otpremi“ istih fajlova → isti poslovi, bez novih dokumenata
await p.setInputFiles("#pd-fajlovi", FAJLOVI);
await p.click("#pd-otpremi");
await p.waitForTimeout(1500);
await obradi();
st = await stanje();
zapisi("4.ponavljanje", "ponovljeno otpremanje istih 7 fajlova: i dalje 7 dokumenata", st.dokumenti === 7 && st.poslovi_prikaceni === 7, JSON.stringify(st.dokumenti_po_predmetu));

// 5) Dokumenti predmeta posle reload-a + tekst skena iz OCR-a
await p.goto(`${BASE}/app#/predmeti/${pid}/dokumenti`);
await p.reload();
const lista = await cekaj(() => document.querySelectorAll("#dok-lista li").length === 7, null, 15000);
const imena = await p.evaluate(() => [...document.querySelectorAll("#dok-lista li")].map(li => li.innerText).join(" | "));
zapisi("5.dokumenti", "posle reload-a predmet prikazuje tačno 7 dokumenata spisa", lista && ["01 Tuzba", "02 Odgovor", "03 Podnesak tuzioca", "04 Podnesak tuzenog",
  "05 Nalaz", "06 Izjasnjenje", "07 Zapisnik"].every(x => imena.includes(x)), imena.slice(0, 300));
await p.locator("#dok-lista li", { hasText: "05 Nalaz" }).first().click().catch(() => {});
const ocrTekst = await cekaj(() => /hidroizolacija na spoju atike/.test((document.getElementById("dok-tekst") || {}).textContent || "")
  && /Visina stete iznosi 3\.150\.000/.test((document.getElementById("dok-tekst") || {}).textContent || ""), null, 10000);
zapisi("5.dokumenti", "tekst skeniranog nalaza (iz stvarnog OCR-a) vidljiv u predmetu", ocrTekst);

// 6) Izolacija
const tudj = await zahtev(`/api/predmeti/${pid}`, { token: "tok-B" });
st = await stanje();
zapisi("6.izolacija", "korisnik B ne vidi predmet A", tudj.s === 404 || tudj.s === 403, String(tudj.s));
zapisi("6.izolacija", "svi upisi pripadaju A", st.vlasnici.join() === "uid-A", st.vlasnici.join());
zapisi("6.izolacija", "nijedna veza van 127.0.0.1 (browser i server)", spoljni.length === 0 && st.spoljni_pokusaji === 0, spoljni.slice(0, 2).join());
zapisi("konzola", "bez grešaka stranice", greskeJS.length === 0, greskeJS.join(" | ").slice(0, 200));

await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
