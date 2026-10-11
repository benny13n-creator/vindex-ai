// Vindex V2 NG — VCR001 T03: organizacija predmeta iz dokumenta kroz STVARAN V2 /app nad PRAVIM api.app koji upisuje.
// Pokretanje: `node tests/live-organizacija-e2e.mjs`. Server: tests/osb003_solo_server.py sa VX_GENOME_IZVORI=1 (Genome je
// simuliran i navodi „DOK-01“ za ključni datum i za rok za 5 dana; sve ostalo je stvarno: rute, worker, dispečer, Case
// Evolution, lanac odluka). Proverava se UI I baza.
//   1) dokument → Genome → hronologija prikazuje IZVOR datuma (dokument), rok upisan kao predlog (kandidat)
//   2) Case Action „Planirati rokove: rok iz dokumenta čeka vašu potvrdu“ u živom pregledu (poreklo: dokument)
//   3) advokat potvrdi rok na ekranu Danas → akcija se zatvara (trajni događaj → reconcile)
//   4) reload: stanje ostaje

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4524, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const dir = await mkdtemp(join(tmpdir(), "vx-org-"));
const PDF = join(dir, "Resenje o otkazu.pdf");
const gen = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
c = canvas.Canvas(r"${PDF}")
for i, r in enumerate(["GRADNJA INVEST DOO BEOGRAD", "Resenje o otkazu ugovora o radu", "Zaposleni: Marko Petrovic",
                       "Resenje je uruceno zaposlenom 17.03.2025. godine.", "Protiv ovog resenja moze se izjaviti zalba."]):
    c.drawString(60, 780 - i * 24, r)
c.showPage(); c.save()`], { encoding: "utf-8" });
if (gen.status !== 0) { console.log(gen.stderr); process.exit(1); }

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_GENOME_IZVORI: "1" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const get = (p, opt = {}) => new Promise(r => { const q = http.request(BASE + p, { method: opt.method || "GET" }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); }); q.on("error", () => r({ s: 0, b: "" })); q.end(); });
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await get("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje (Genome sa izvorima)", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const stanje = async () => JSON.parse((await get("/__osb003/stanje")).b);
const obradi = async () => JSON.parse((await get("/__osb003/obradi", { method: "POST" })).b);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const spoljni = [], greskeJS = [], api500 = [];
await ctx.route("**/*", r => {
  const u = new URL(r.request().url());
  if (u.hostname !== "127.0.0.1") { spoljni.push(u.href); return r.abort(); }
  if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
  return r.continue();
});
await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
  [KLJUC, JSON.stringify({ access_token: "tok-A", refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "uid-A" } })]);
const p = await ctx.newPage();
p.setDefaultTimeout(8000);
p.on("pageerror", e => greskeJS.push(String(e)));
p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const txt = (id) => p.evaluate((i) => (document.getElementById(i) || {}).innerText || "", id);

// predmet (ručno) + dokument kroz prijem
await p.goto(BASE + "/app#/predmeti/nov");
await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
await p.fill("#nov-naziv", "Petrović protiv Gradnja Invest — otkaz");
await p.click("#nov-posalji");
zapisi("priprema", "predmet otvoren", await cekaj(() => /#\/predmeti\/[^/]+/.test(location.hash) && !/nov$/.test(location.hash)));
const hashPredmet = await p.evaluate(() => location.hash);
await p.click("#tab-prijem");
await p.setInputFiles("#pd-fajlovi", PDF);
await p.click("#pd-otpremi");
await cekaj(() => document.querySelectorAll("#pd-poslovi li").length === 1);
await obradi();
await cekaj(() => /Potvrđujem pregled|Prikači ovom predmetu/.test(document.getElementById("pd-poslovi").innerText), null, 20000);
if (/Potvrđujem pregled/.test(await txt("pd-poslovi"))) { await p.click('#pd-poslovi button:has-text("Potvrđujem pregled")'); await obradi(); }
await cekaj(() => /Prikači ovom predmetu/.test(document.getElementById("pd-poslovi").innerText), null, 20000);
await p.click('#pd-poslovi button:has-text("Prikači ovom predmetu")');
await cekaj(() => /Prikačeno ovom predmetu|Dokument je prikačen/.test(document.getElementById("pd-poslovi").innerText), null, 20000);
const ob = await obradi();
const s1 = await stanje();
zapisi("priprema", "dokument prikačen, događaji obrađeni bez greške", s1.dokumenti === 1 && s1.nedispecovano === 0 && ob.greske === 0, JSON.stringify(s1));
zapisi("1", "rok iz dokumenta upisan u hronologiju kao predlog (red postoji)", s1.hronologija >= 1, JSON.stringify(s1));

// 1) hronologija sa izvorom (Analiza)
await p.goto(BASE + "/app" + hashPredmet.replace(/\/[a-z-]+$/, "") + "/analiza").catch(() => {});
await p.click("#tab-analiza").catch(() => {});
zapisi("1", "Analiza: ključni datum prikazan", await cekaj(() => /Uručenje rešenja o otkazu/.test((document.getElementById("an-datumi") || {}).innerText || ""), null, 20000));
zapisi("1", "Analiza: datum nosi IZVOR — dokument predmeta", await cekaj(() => {
  const ul = document.getElementById("an-datumi"); if (!ul) return false;
  const li = [...ul.querySelectorAll("li")].find(x => /Uručenje rešenja o otkazu/.test(x.innerText));
  return !!li && !!li.querySelector("button") && /Resenje o otkazu/.test(li.innerText);
}, null, 10000), (await txt("an-datumi")).slice(0, 200));

// 2) akcija iz roka u živom pregledu (ponovno otvaranje predmeta — sveže čitanje akcija)
await p.goto(BASE + "/app" + hashPredmet);
await p.reload();
await p.click("#tab-pregled").catch(() => {});
zapisi("2", "živi pregled: „Planirati rokove“ — rok iz dokumenta čeka vašu potvrdu", await cekaj(() => {
  const t = (document.getElementById("zp-paznja") || {}).innerText || ""; return /Planirati rokove/.test(t) && /čeka vašu potvrdu/.test(t);
}, null, 20000), (await txt("zp-paznja")).slice(0, 300));
const s2 = await stanje();
zapisi("2", "akcija upisana (otvorena)", s2.akcije_otvorene >= 1, JSON.stringify(s2));

// 3) potvrda roka na ekranu Danas → akcija se zatvara
await p.goto(BASE + "/app#/danas");
zapisi("3", "Danas: predlog roka vidljiv sa „Potvrdi“", await cekaj(() => [...document.querySelectorAll("button")].some(b => /Potvrdi rok: .*Rok za žalbu/.test(b.getAttribute("aria-label") || "")), null, 20000));
await p.click('button[aria-label^="Potvrdi rok: Rok za žalbu"]');
zapisi("3", "potvrda zabeležena (poruka uspeha, ne „nepotvrđen“)", await cekaj(() => /je potvrđen: preuzeli ste ga za upotrebu/.test((document.getElementById("da-poruka") || {}).textContent || ""), null, 10000),
  await p.evaluate(() => (document.getElementById("da-poruka") || {}).textContent || ""));
await obradi();
await p.goto(BASE + "/app" + hashPredmet);
await p.click("#tab-pregled").catch(() => {});
zapisi("3", "posle potvrde akcija „čeka vašu potvrdu“ više nije u pregledu", await cekaj(() => {
  const z = document.getElementById("zp-paznja-stanje"), t = (document.getElementById("zp-paznja") || {}).innerText || "";
  return (z && !z.hidden) || (t && !/čeka vašu potvrdu/.test(t)) || (!t && document.getElementById("zp-blok") && !document.getElementById("zp-blok").hidden);
}, null, 20000), (await txt("zp-paznja")).slice(0, 200));
const s3 = await stanje();
zapisi("3", "akcija zatvorena u bazi", s3.akcije_otvorene < s2.akcije_otvorene, JSON.stringify([s2.akcije_otvorene, s3.akcije_otvorene]));

// 4) reload
await p.reload();
await p.click("#tab-pregled").catch(() => {});
zapisi("4", "posle reload-a akcija ostaje zatvorena", await cekaj(() => !/čeka vašu potvrdu/.test((document.getElementById("zp-paznja") || {}).innerText || ""), null, 15000));

const kraj = await stanje();
zapisi("bezbednost", "svi upisi pripadaju prijavljenom korisniku", JSON.stringify(kraj.vlasnici) === '["uid-A"]', JSON.stringify(kraj.vlasnici));
zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0 && kraj.spoljni_pokusaji === 0);
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 2), api500.slice(0, 3)]));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} ${pada ? "FAIL" : "PASS"}`);
process.exit(pada ? 1 : 0);
