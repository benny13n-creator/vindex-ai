// Vindex V2 NG — QA-03: srpski nazivi na STVARNIM V2 ekranima nad STARIM zapisima iz baze.
// Pokretanje: `node tests/live-nazivi-e2e.mjs`. Server: tests/osb003_solo_server.py (pravi api.app, baza u memoriji) sa
// VX_OSB003_SEME — sintetički redovi kakvi već postoje u produkciji (engleski `tip_dokaza` iz Smart Intake-a, srpski iz
// klasifikacije dokaza, interni potpisi `akter`, posao koji čeka pregled sa `law_cited`). Ništa van 127.0.0.1.
// Posle testa server vraća iste kolone tih redova: prikaz NIŠTA ne sme da promeni.

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, writeFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
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

const dir = await mkdtemp(join(tmpdir(), "vx-nazivi-"));
const PDF = join(dir, "Odgovor na tuzbu.pdf");
const gen = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
c = canvas.Canvas(r"${PDF}")
c.drawString(60, 780, "ODGOVOR NA TUZBU (sinteticki QA-03)")
c.showPage(); c.save()`], { encoding: "utf-8" });
if (gen.status !== 0) { console.log(gen.stderr); process.exit(1); }
const sha = createHash("sha256").update(await readFile(PDF)).digest("hex");

const P = "0a0a0a0a-1111-4000-8000-0000000000a1", J = "0a0a0a0a-2222-4000-8000-0000000000b2", ID = "0a0a0a0a-3333-4000-8000-0000000000c3";
const T = "2026-10-01T09:00:00+00:00";
const dok = (n, naziv, tip) => ({ id: `0a0a0a0a-4444-4000-8000-00000000000${n}`, predmet_id: P, user_id: "uid-A", naziv_fajla: naziv,
  tip_dokaza: tip, status: "obradjen", velicina_kb: 10 + n, redni_broj: n, created_at: T });
const hr = (n, akter, dogadjaj, vrsta) => ({ id: `0a0a0a0a-5555-4000-8000-00000000000${n}`, predmet_id: P, user_id: "uid-A", dogadjaj,
  datum: "2026-11-2" + n, datum_iso: "2026-11-2" + n, vaznost: "važan", akter, izvor: "AI_AUTONOMOUS", vrsta, created_at: T });
const ent = (n, tip, vrednost) => ({ id: `0a0a0a0a-6666-4000-8000-00000000000${n}`, document_id: ID, intake_job_id: J, entity_type: tip,
  value: vrednost, confidence: 0.95, reviewed: false, corrected_value: null, created_at: T });
const SEME = {
  predmeti: [{ id: P, user_id: "uid-A", naziv: "QA-03 sinteticki predmet", tip: "parnicno", status: "aktivan", opis: "",
    created_at: T, updated_at: T, case_dna: {}, observation_version: 0 }],
  predmet_dokumenti: [dok(1, "Ugovor.pdf", "contract"), dok(2, "Odgovor.pdf", "response"), dok(3, "Presuda.pdf", "sudska_odluka"),
    dok(4, "Nepoznato.pdf", "qa_interni_kod")],
  predmet_hronologija: [hr(1, "Pipeline (AI)", "Isporuka iz opisa", "rok"), hr(2, "Smart Intake", "Rok iz dokumenta (ugovor)", "rok"),
    hr(3, "Template (AI)", "Priprema podneska", null), hr(4, "Osnovni sud u Beogradu", "Zakazano ročište", null),
    hr(5, "Case Evolution Engine", "Stigao nov dokaz", null)],
  intake_jobs: [{ id: J, status: "awaiting_review", source: "dropzone", attempts: 0, uploaded_by: "uid-A", idempotency_key: "uid-A:" + sha,
    content_sha256: sha, storage_path: "uid-A/qa03", original_filename: "Odgovor na tuzbu.pdf", mime_type: "application/pdf",
    created_at: T, completed_at: T, predmet_id: null, assimilation_complete: false, finalizing_at: null, last_error: null }],
  intake_documents: [{ id: ID, intake_job_id: J, document_type: "response", classification_confidence: 0.92, ocr_used: false, created_at: T }],
  extracted_entities: [ent(1, "law_cited", "Zakon o obligacionim odnosima, clan 262"), ent(2, "case_number", "P 77/2025"),
    ent(3, "qa_interno_polje", "vrednost")],
};
const SEME_PUT = join(dir, "seme.json");
await writeFile(SEME_PUT, JSON.stringify(SEME), "utf-8");

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_OSB003_SEME: SEME_PUT };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const get = (p) => new Promise(r => { const q = http.request(BASE + p, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); }); q.on("error", () => r({ s: 0, b: "" })); q.end(); });
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await get("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app sa starim zapisima", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const pre = (await get("/__osb003/seme")).b;

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
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekst = (sel) => p.evaluate((s) => [...document.querySelectorAll(s)].map(e => e.innerText).join("\n"), sel);
const ENGLESKI = /\b(contract|response|lawsuit|law_cited|law cited|Pipeline|Smart Intake|Template \(AI\)|Case Evolution|Genome)\b/;

// ── Dosije: lista dokumenata i detalj ───────────────────────────────────────────────────────────────────────────────
await p.goto(`${BASE}/app#/predmeti/${P}/dokumenti`);
zapisi("dosije", "lista dokumenata učitana", await cekaj(() => document.querySelectorAll("#dok-lista .docs__item").length === 4));
const lista = await tekst("#dok-lista .docs__meta");
zapisi("dosije", "contract → „Ugovor“, response → „Odgovor na tužbu“, sudska_odluka → „Sudska odluka“",
  /Ugovor/.test(lista) && /Odgovor na tužbu/.test(lista) && /Sudska odluka/.test(lista), lista.replace(/\n/g, " | "));
zapisi("dosije", "nepoznata oznaka prikazana kao nepoznata, ne kao pravni pojam", /Nepoznata vrsta dokumenta \(oznaka „qa_interni_kod“\)/.test(lista));
zapisi("dosije", "nijedan engleski/interni naziv u listi", !ENGLESKI.test(lista), lista.replace(/\n/g, " | "));
await p.click(`#dok-lista .docs__item[data-dok="${SEME.predmet_dokumenti[0].id}"]`);
zapisi("dosije", "detalj: „Vrsta dokumenta“ = Ugovor (ne contract)",
  await cekaj(() => /Vrsta dokumenta\s*Ugovor/.test(document.getElementById("dok-cinjenice").innerText)), await tekst("#dok-cinjenice"));

// ── Hronologija: interni nazivi procesa sa zadržanim poreklom; ime suda doslovno ──────────────────────────────────────
await p.goto(`${BASE}/app#/predmeti/${P}/rad`);
zapisi("hronologija", "hronologija učitana", await cekaj(() => document.querySelectorAll("#hron-lista li").length === 5));
const hron = await tekst("#hron-lista li");
zapisi("hronologija", "Pipeline (AI) → „AI predlog iz opisa predmeta“", /AI predlog iz opisa predmeta/.test(hron));
zapisi("hronologija", "Smart Intake → „AI predlog iz otpremljenog dokumenta“", /AI predlog iz otpremljenog dokumenta/.test(hron));
zapisi("hronologija", "Template (AI) → „Šablon predmeta“ (statički katalog, ne model)", /Šablon predmeta/.test(hron));
zapisi("hronologija", "Case Evolution Engine → „Sistem — praćenje predmeta“", /Sistem — praćenje predmeta/.test(hron));
zapisi("hronologija", "stvarni akter (sud) ostaje doslovno", /Osnovni sud u Beogradu/.test(hron));
zapisi("hronologija", "nijedan interni naziv procesa", !ENGLESKI.test(hron), hron.replace(/\n/g, " | "));

// ── Prijem: postojeći posao (isti sadržaj već poslat) — vrsta i izdvojena polja ─────────────────────────────────────
await p.goto(`${BASE}/app#/predmeti/${P}/prijem`);
zapisi("prijem", "forma prijema prikazana", await cekaj(() => { const f = document.getElementById("pd-fajlovi"); return f && !f.closest("[hidden]"); }));
await p.setInputFiles("#pd-fajlovi", PDF);
await p.click("#pd-otpremi");
zapisi("prijem", "prikazan POSTOJEĆI posao (stari zapis), bez novog", await cekaj(() => /već bio poslat/.test(document.getElementById("pd-poslovi").innerText)
  && /Odgovor na tužbu/.test(document.getElementById("pd-poslovi").innerText)), (await tekst("#pd-poslovi")).slice(0, 300));
const prijem = await tekst("#pd-poslovi");
zapisi("prijem", "vrsta: response → „Odgovor na tužbu“", /Odgovor na tužbu \(pouzdanost 92%\)/.test(prijem), prijem.replace(/\n/g, " | ").slice(0, 400));
zapisi("prijem", "polje: law_cited → „Navedeni propis“", /Navedeni propis/.test(prijem));
zapisi("prijem", "poznato polje: case_number → „Broj predmeta“", /Broj predmeta/.test(prijem));
zapisi("prijem", "nepoznato polje prikazano kao nepoznato", /Nepoznato polje \(oznaka „qa_interno_polje“\)/.test(prijem));
zapisi("prijem", "nijedan engleski naziv (response/law_cited)", !ENGLESKI.test(prijem), prijem.replace(/\n/g, " | ").slice(0, 400));

// ── Analiza: naslov odeljka bez internog naziva procesa ───────────────────────────────────────────────────────────
await p.goto(`${BASE}/app#/predmeti/${P}/analiza`);
const naslov = await p.evaluate(() => [document.getElementById("an-genome-naslov").textContent,
  document.querySelector('[data-an-skok="an-genome-naslov"]').textContent]);
zapisi("analiza", "„Genome“ zamenjen sa „Slika predmeta“ (naslov i skok)", naslov[0] === "Slika predmeta" && naslov[1] === "Slika predmeta", naslov.join(" / "));

// ── Podaci nepromenjeni ───────────────────────────────────────────────────────────────────────────────────────────
const posle = (await get("/__osb003/seme")).b;
zapisi("podaci", "stari zapisi u bazi identični pre i posle (tip_dokaza, akter, document_type, entity_type…)", pre === posle && pre.length > 100);
zapisi("podaci", "originalne vrednosti i dalje engleske/interne u bazi (prikaz ih ne prepisuje)",
  /"tip_dokaza": ?"contract"/.test(posle) && /"akter": ?"Pipeline \(AI\)"/.test(posle) && /"entity_type": ?"law_cited"/.test(posle) && /"document_type": ?"response"/.test(posle));
zapisi("bezbednost", "0 JS grešaka", greskeJS.length === 0, greskeJS.join(" | ").slice(0, 300));
zapisi("bezbednost", "0 zahteva van 127.0.0.1", spoljni.length === 0, spoljni.slice(0, 3).join(" "));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
