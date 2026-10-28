// Vindex V2 NG — N6 IZVEŠTAJI: iz stvarnog V2 /app (Chromium) preuzimaju se izveštaj o predmetu (PDF) i evidencija
// naplate (CSV) nad PRAVIM api.app (tests/osb003_solo_server.py + seme); sadržaj fajla se proverava (PDF tekst čita
// pymupdf). Ništa ne izlazi van 127.0.0.1. Pokretanje: `node tests/live-n6-izvestaji-e2e.mjs`.
import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4536, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const STARO = "2026-01-01T08:00:00+00:00";
const PA = "77777777-aaaa-4aaa-8aaa-000000000001", PB = "88888888-bbbb-4bbb-8bbb-000000000001";
const g = new Date().getFullYear(), danas = new Date().toISOString().slice(0, 10);
const SEME = {
  predmeti: [{ id: PA, user_id: "uid-A", naziv: "Zlatić protiv Đorđević", status: "aktivan", tip: "parnica", opis: "Naknada štete", created_at: STARO },
             { id: PB, user_id: "uid-B", naziv: "TAJNI B", status: "aktivan", created_at: STARO }],
  predmet_hronologija: [{ id: "h-dog", user_id: "uid-A", predmet_id: PA, dogadjaj: "Podneta tužba", datum_iso: `${g}-01-10`, vaznost: "informativan", vrsta: "dogadjaj" },
                        { id: "h-ai", user_id: "uid-A", predmet_id: PA, dogadjaj: "Rok za odgovor (AI predlog)", datum_iso: `${g}-12-10`, vaznost: "važan", vrsta: "rok", izvor: "AI_AUTONOMOUS" }],
  rocista: [{ id: "r-1", user_id: "uid-A", predmet_id: PA, sud: "Osnovni sud u Beogradu", sudnica: "14", datum: `${g}-11-20`, vreme: "10:00:00", status: "odlozeno", created_at: STARO }],
  billing_entries: [{ id: "e-1", user_id: "uid-A", predmet_id: PA, opis: "Sastav tužbe", tip: "ostalo", iznos_rsd: 1234.56, obracunato: true, faktura_id: "f-1", datum: danas },
                    { id: "e-b", user_id: "uid-B", predmet_id: PB, opis: "TAJNA stavka", tip: "ostalo", iznos_rsd: 9, obracunato: false, datum: danas }],
  fakture: [{ id: "f-1", user_id: "uid-A", predmet_id: PA, broj_fakture: `${g}/0007`, status: "placena", iznos_sa_pdv: 1481.47, iznos_bez_pdv: 1234.56, pdv_iznos: 246.91, datum_fakture: danas, klijent_naziv: "Milica Zlatić", created_at: STARO }],
  timer_sessions: [], tarifne_stavke_custom: [],
};
const dir = await mkdtemp(join(tmpdir(), "vx-n6-"));
await writeFile(join(dir, "seme.json"), JSON.stringify(SEME));
const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_OSB003_SEME: join(dir, "seme.json") };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p) => new Promise(r => { const q = http.request(BASE + p, s => { s.resume(); s.on("end", () => r(s.statusCode)); }); q.on("error", () => r(0)); q.end(); });
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")) === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app sa sintetičkim semenom", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", acceptDownloads: true });
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
p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });

// ══ PDF ══
await p.goto(BASE + `/app#/predmeti/${PA}`);
await p.waitForSelector("#iz-pdf", { state: "visible" });
const [dl] = await Promise.all([p.waitForEvent("download"), p.click("#iz-pdf")]);
const pdfPut = join(dir, "izvestaj.pdf"); await dl.saveAs(pdfPut);
const izv = spawnSync(PY, ["-c", "import sys,pymupdf;print('\\n'.join(s.get_text() for s in pymupdf.open(sys.argv[1])))", pdfPut], { encoding: "utf-8", env });
const t = izv.stdout || "";
zapisi("PDF", "preuzet iz predmeta, naziv predmeta sa srpskim slovima ispravan", (await readFile(pdfPut)).subarray(0, 4).toString() === "%PDF" && t.includes("Zlatić protiv Đorđević"), t.slice(0, 120));
zapisi("PDF", "ročište sa stanjem (odloženo), AI rok označen [NEPOTVRĐENO], događaj bez oznake", /odloženo/.test(t) && t.includes("[NEPOTVRĐENO] Rok za odgovor (AI predlog)")
  && t.includes("Podneta tužba") && !t.includes("[NEPOTVRĐENO] Podneta"), t.slice(0, 600));
zapisi("PDF", "nema podataka advokata B", !/TAJN/.test(t));
zapisi("PDF", "poruka o preuzimanju", /je preuzet/.test(await p.textContent("#iz-poruka")), await p.textContent("#iz-poruka"));

// ══ CSV ══
await p.goto(BASE + "/app#/predmeti");
await p.goto(BASE + `/app#/predmeti/${PA}/naplata`);
await p.waitForSelector("#np-csv", { state: "visible" });
const [dl2] = await Promise.all([p.waitForEvent("download"), p.click("#np-csv")]);
const csvPut = join(dir, "evidencija.csv"); await dl2.saveAs(csvPut);
const csv = (await readFile(csvPut, "utf-8")).replace(/^﻿/, "");
const redovi = csv.trim().split(/\r?\n/).map(r => r.split(";"));
zapisi("CSV", "evidencija naplate: zaglavlje sa statusom fakture, stavka A sa „plaćena“, bez stavke B",
  redovi[0].slice(-2).join("|") === "Broj fakture|Status fakture" && redovi.some(r => r.includes("Sastav tužbe") && r.at(-1) === "plaćena" && r.at(-2) === `${g}/0007`)
  && !csv.includes("TAJNA"), csv.slice(0, 300));

zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 3), api500.slice(0, 3)]));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
