// Vindex V2 NG — N5 EVIDENCIJA NAPLATE: stvaran V2 /app u Chromium-u nad PRAVIM api.app (tests/osb003_solo_server.py +
// sintetičko seme). Ništa ne izlazi van 127.0.0.1, ništa se ne šalje klijentu ni u SEF. `node tests/live-n5-naplata-e2e.mjs`.
//   B1 stavke sa decimalama → tačan zbir u predmetu
//   B2 nacrt → izdata → plaćena (dugmad u predmetu, stanje u bazi)
//   B3 zastareo prikaz (drugi tab je stornirao) → ništa ne prepisuje
//   B4 dva istovremena zaustavljanja tajmera → JEDNA stavka
//   B5 korisnik B nema pristup
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4535, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const STARO = "2026-01-01T08:00:00+00:00";
const PA = "55555555-aaaa-4aaa-8aaa-000000000001", PB = "66666666-bbbb-4bbb-8bbb-000000000001";
const SEME = {
  predmeti: [{ id: PA, user_id: "uid-A", naziv: "Zlatić protiv Zlatna Linija", status: "aktivan", created_at: STARO },
             { id: PB, user_id: "uid-B", naziv: "TAJNI B", status: "aktivan", created_at: STARO }],
  billing_entries: [{ id: "e-b", user_id: "uid-B", predmet_id: PB, opis: "TAJNA stavka B", tip: "ostalo", iznos_rsd: 9999, obracunato: false, datum: "2026-10-01" }],
  fakture: [], timer_sessions: [], tarifne_stavke_custom: [],
};
const dir = await mkdtemp(join(tmpdir(), "vx-n5-"));
await writeFile(join(dir, "seme.json"), JSON.stringify(SEME));
const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_OSB003_SEME: join(dir, "seme.json") };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, opt = {}) => new Promise(r => {
  const q = http.request(BASE + p, { method: opt.method || "GET", headers: opt.headers || {} }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); });
  q.on("error", () => r({ s: 0, b: "" })); if (opt.telo) q.write(opt.telo); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app sa sintetičkim semenom", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const kao = (tok) => (p, metod = "GET", telo) => zahtev(p, { method: metod, headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json" }, telo: telo && JSON.stringify(telo) });
const kaoA = kao("tok-A"), kaoB = kao("tok-B");
const json = (r) => { try { return JSON.parse(r.b); } catch { return null; } };

// seme kroz stvarne rute: dve stavke sa decimalama, jedna na nacrtu fakture
const e1 = json(await kaoA("/billing/entries", "POST", { predmet_id: PA, opis: "Sastav tužbe", iznos_rsd: 1234.56 }));
const e2 = json(await kaoA("/billing/entries", "POST", { predmet_id: PA, opis: "Pristup ročištu", iznos_rsd: 765.44 }));
const f = json(await kaoA("/billing/faktura", "POST", { predmet_id: PA, entry_ids: [e1.entry.id, e2.entry.id], klijent_naziv: "Milica Zlatić", pdv_stopa: 20 }));
zapisi("seme", "dve stavke i nacrt fakture kroz stvarne rute", !!(f && f.faktura && f.faktura.status === "nacrt"), JSON.stringify(f && f.faktura && [f.faktura.status, f.faktura.iznos_sa_pdv]));
const FID = f.faktura.id;
const e3 = json(await kaoA("/billing/entries", "POST", { predmet_id: PA, opis: "Podnesak", iznos_rsd: 500 }));
const f2 = json(await kaoA("/billing/faktura", "POST", { predmet_id: PA, entry_ids: [e3.entry.id], klijent_naziv: "Milica Zlatić", pdv_stopa: 0 }));
const FID2 = f2.faktura.id, BROJ2 = f2.faktura.broj_fakture;
const statusF2 = async () => ((json(await kaoA("/billing/faktura?limit=200")) || { fakture: [] }).fakture.find(x => x.id === FID2) || {}).status;
const statusF = async () => ((json(await kaoA("/billing/faktura?limit=200")) || { fakture: [] }).fakture.find(x => x.id === FID) || {}).status;

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
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
const cekaj = (fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);
async function naplata() {
  await p.goto(BASE + "/app#/predmeti");
  await p.goto(BASE + `/app#/predmeti/${PA}/naplata`);
  await cekaj(() => document.querySelectorAll("#np-fakture li").length > 0 && !document.getElementById("np-zbir").hidden);
}
const faktura = () => p.evaluate(() => [...document.querySelectorAll("#np-fakture li")].map(x => x.innerText.replace(/\s+/g, " ")).join(" | "));
const klik = (t, broj = "2026/0001") => p.evaluate(([t, broj]) => { const li = [...document.querySelectorAll("#np-fakture li")].find(x => x.innerText.includes(broj));
  const b = li && [...li.querySelectorAll("button")].find(x => x.textContent === t && !x.disabled); if (b) b.click(); return !!b; }, [t, broj]);
const faktura1 = () => p.evaluate(() => [...document.querySelectorAll("#np-fakture li")].filter(x => x.innerText.includes("2026/0001")).map(x => x.innerText.replace(/\s+/g, " ")).join(""));

// ══ B1 zbir ══
await naplata();
const zbir = await p.evaluate(() => document.getElementById("np-zbir").innerText.replace(/\s+/g, " "));
zapisi("B1", "zbir stavki predmeta tačan na dve decimale (1.234,56 + 765,44 + 500,00 = 2.500,00) i bez stavke advokata B", /2\.500,00/.test(zbir) && !/9\.999/.test(zbir), zbir);
zapisi("B1", "faktura: 2.400,00 RSD sa PDV-om, nacrt", /2\.400,00 RSD/.test(await faktura1()) && /nacrt/.test(await faktura1()), await faktura1());

// ══ B2 nacrt → izdata → plaćena ══
zapisi("B2", "nacrt nudi „Označi kao izdatu“", await klik("Označi kao izdatu"));
await cekaj(() => /označena kao izdata/.test(document.getElementById("np-faktura-poruka").textContent));
zapisi("B2", "izdata u bazi; poruka kaže da nije poslata klijentu ni u SEF", await statusF() === "izdata" && /nije poslata klijentu ni prijavljena u SEF/.test(await tekstEl("np-faktura-poruka")), await tekstEl("np-faktura-poruka"));
await cekaj(() => [...document.querySelectorAll("#np-fakture li button")].some(b => b.textContent === "Plaćena"));
zapisi("B2", "izdata nudi „Plaćena“", await klik("Plaćena"));
await cekaj(() => /označena kao plaćena/.test(document.getElementById("np-faktura-poruka").textContent));
zapisi("B2", "plaćena u bazi i u predmetu; nudi samo „Vrati na neplaćenu“", await statusF() === "placena" && /plaćena/.test(await faktura1())
  && await p.evaluate(() => [...[...document.querySelectorAll("#np-fakture li")].find(x => x.innerText.includes("2026/0001")).querySelectorAll("button")].map(b => b.textContent).join("|")) === "Vrati na neplaćenu", await faktura1());
await naplata();
zapisi("B2", "posle osvežavanja stanje „plaćena“ ostaje", /plaćena/.test(await faktura1()));

// ══ B3 zastareo prikaz: ekran vidi NACRT druge fakture, drugi tab je u međuvremenu izda; klik „Storniraj“ ne sme da prođe ══
await naplata();
await kaoA(`/billing/faktura/${FID2}/status`, "PATCH", { status: "izdata", iz_statusa: "nacrt" });     // drugi tab: izda…
await kaoA(`/billing/faktura/${FID2}/status`, "PATCH", { status: "stornirana", iz_statusa: "izdata" }); // …pa stornira
await klik("Označi kao izdatu", BROJ2);
await cekaj(() => /u međuvremenu promenjen/.test(document.getElementById("np-faktura-poruka").textContent));
zapisi("B3", "zastareo prikaz: „Označi kao izdatu“ nad nacrtom ne menja fakturu koja je u međuvremenu stornirana (409, poruka)", await statusF2() === "stornirana"
  && /u međuvremenu promenjen/.test(await tekstEl("np-faktura-poruka")), JSON.stringify([await statusF2(), await tekstEl("np-faktura-poruka")]));
await cekaj((b) => [...document.querySelectorAll("#np-fakture li")].some(x => x.innerText.includes(b) && /stornirana/.test(x.innerText)), BROJ2);
zapisi("B3", "posle 409 lista je osvežena (druga faktura prikazana kao stornirana, bez dugmadi)", await p.evaluate((b) => { const li = [...document.querySelectorAll("#np-fakture li")].find(x => x.innerText.includes(b)); return !!li && /stornirana/.test(li.innerText) && !li.querySelector("button"); }, BROJ2));
zapisi("B3", "V2 ne nudi storno (stavke bi ostale trajno obračunate)", await p.evaluate(() => ![...document.querySelectorAll("#np-fakture button")].some(b => /Storn/.test(b.textContent))));

// ══ B4 tajmer ══
await kaoA("/billing/timer/start", "POST", { predmet_id: PA, opis: "Priprema ročišta" });
const pre = (json(await kaoA(`/billing/entries?predmet_id=${PA}`)) || { entries: [] }).entries.length;
const stop = await Promise.all([1, 2].map(() => kaoA("/billing/timer/stop", "POST", { kreiraj_entry: true })));
const posle = (json(await kaoA(`/billing/entries?predmet_id=${PA}`)) || { entries: [] }).entries.length;
zapisi("B4", "dva istovremena zaustavljanja tajmera → TAČNO jedna nova stavka", posle === pre + 1 && stop.filter(r => r.s === 200).length === 1, JSON.stringify([stop.map(r => r.s), pre, posle]));

// ══ B5 izolacija ══
const bP = await kaoB(`/billing/faktura/${FID}/status`, "PATCH", { status: "izdata" });
const bL = json(await kaoB(`/billing/entries?predmet_id=${PA}`));
zapisi("B5", "B ne menja fakturu A (404) i ne vidi stavke A", bP.s === 404 && !!bL && bL.entries.every(e => e.user_id !== "uid-A"), JSON.stringify([bP.s, bL && bL.entries.length]));

zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 3), api500.slice(0, 3)]));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
