// Vindex V2 NG — RC kapija (S02 / B7): odluka advokata važi za SPORNU TAČKU, ne za jednu karticu.
// Pokretanje: `node tests/live-s02-tacka-vise-e2e.mjs`. Server: tests/osb003_solo_server.py uz VX_KONTRADIKCIJE=2 (PRAVI api.app;
// simulirani modeli). Genome predlaže DVE relacije u istoj tački („Datum urucenja resenja“) i jednu u drugoj (takse).
// Proverava: obe kartice tačke pre klika kažu da odluka važi za celu tačku (svih 2); kartica takse to ne kaže; potvrda sa
// jedne kartice aktivira obe i poruka to kaže (obuhvat odluke u audit zapisu: tests/test_s02_kontradikcije_potvrda.py).

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4529, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const dir = await mkdtemp(join(tmpdir(), "vx-s02t-"));
const DOK = { "Resenje.pdf": ["RESENJE", "Broj predmeta: P 6101/2026", "Rok za uplatu sudske takse istice 04.12.2026. godine.",
                              "Resenje o otkazu je uruceno tuziocu 17.03.2025. godine."],
              "Nalog.pdf": ["NALOG", "Broj predmeta: P 6101/2026", "Rok za uplatu dodatne sudske takse istice 27.11.2026. godine.",
                            "Posiljka je urucena primaocu 25.03.2025. godine."] };
for (const [ime, redovi] of Object.entries(DOK)) {
  const r = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
c = canvas.Canvas(r"${join(dir, ime)}")
for i, t in enumerate(${JSON.stringify(redovi)}):
    c.drawString(60, 780 - i * 24, t)
c.showPage(); c.save()`], { encoding: "utf-8" });
  if (r.status !== 0) { console.log(r.stderr); process.exit(1); }
}

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_KONTRADIKCIJE: "2" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, { method = "GET", token, telo } = {}) => new Promise(r => {
  const q = http.request(BASE + p, { method, headers: { ...(token ? { Authorization: "Bearer " + token } : {}), ...(telo ? { "Content-Type": "application/json" } : {}) } },
    s => { let b = ""; s.on("data", c => b += c); s.on("end", () => { let j = null; try { j = JSON.parse(b); } catch { } r({ s: s.statusCode, b, j }); }); });
  q.on("error", () => r({ s: 0, b: "", j: null })); if (telo) q.write(JSON.stringify(telo)); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const obradi = () => zahtev("/__osb003/obradi", { method: "POST" });

const pr = await zahtev("/api/predmeti", { method: "POST", token: "tok-A", telo: { naziv: "S02 tacka sa dve relacije", tip: "Parnica" } });
const PID = pr.j && pr.j.predmet && pr.j.predmet.id;
zapisi("priprema", "predmet otvoren", pr.s === 200 && !!PID, pr.b.slice(0, 200));
for (const ime of Object.keys(DOK)) {
  const fd = new FormData();
  fd.append("files", new Blob([await readFile(join(dir, ime))], { type: "application/pdf" }), ime);
  const up = await fetch(BASE + "/api/smart-intake/documents", { method: "POST", headers: { Authorization: "Bearer tok-A" }, body: fd });
  const uj = await up.json();
  const jid = uj.rezultati && uj.rezultati[0] && uj.rezultati[0].job_id;
  await obradi();
  await zahtev(`/api/smart-intake/jobs/${jid}/review/resolve`, { method: "POST", token: "tok-A" });
  const fin = await zahtev(`/api/smart-intake/jobs/${jid}/finalize`, { method: "POST", token: "tok-A", telo: { predmet_id: PID } });
  await obradi(); await obradi();
  zapisi("priprema", `${ime} prikačen predmetu`, fin.s === 200 && fin.j && fin.j.predmet_id === PID, fin.b.slice(0, 160));
}
const kon0 = ((await zahtev(`/api/predmeti/${PID}/genome-v2`, { token: "tok-A" })).j || {}).kontradikcije || { za_pregled: [], aktivne: [] };
const urucenje = kon0.za_pregled.filter(x => /Datum urucenja/.test(x.sporna_tacka || ""));
zapisi("api", "tačka „Datum urucenja“ ima dve relacije u istoj spornoj tački, takse jednu",
  urucenje.length === 2 && new Set(urucenje.map(x => x.odluka && x.odluka.issue_id)).size === 1 && kon0.za_pregled.length === 3 && kon0.aktivne.length === 0,
  `za_pregled=${kon0.za_pregled.map(x => x.sporna_tacka + "/" + x.relacija)}`);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
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
p.setDefaultTimeout(10000);
p.on("pageerror", e => greskeJS.push(String(e)));
p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const kartice = (sel) => p.evaluate((s) => [...document.querySelectorAll(s + " > li")].map(x => x.innerText.replace(/\s+/g, " ")), sel);

await p.goto(`${BASE}/app#/predmeti/${PID}/analiza`);
await cekaj(() => document.querySelectorAll("#an-kontr-pregled > li").length === 3);
let pregled = await kartice("#an-kontr-pregled");
const napomena = /Odluka važi za celu spornu tačku „Datum urucenja resenja“ — za svih 2 protivrečnosti u njoj\./;
zapisi("pre klika", "obe kartice tačke kažu da odluka važi za celu tačku (svih 2)",
  pregled.filter(t => /Datum urucenja/.test(t)).length === 2 && pregled.filter(t => /Datum urucenja/.test(t)).every(t => napomena.test(t)),
  pregled.join(" || ").slice(0, 400));
zapisi("pre klika", "kartica tačke sa jednom protivrečnošću ne nosi tu napomenu",
  pregled.filter(t => /uplatu takse/.test(t)).length === 1 && !pregled.some(t => /uplatu takse/.test(t) && /celu spornu tačku/.test(t)));

await p.click('#an-kontr-pregled > li:has-text("Datum urucenja resenja") >> nth=0 >> button[data-radnja="potvrdi"]');
await cekaj(() => document.querySelectorAll("#an-kontr-aktivne > li").length === 2 && !document.getElementById("an-kontr-poruka").hidden);
const aktivne = await kartice("#an-kontr-aktivne");
const poruka = await p.evaluate(() => document.getElementById("an-kontr-poruka").textContent);
zapisi("posle klika", "potvrda sa jedne kartice aktivira OBE relacije tačke; poruka to kaže",
  aktivne.length === 2 && aktivne.every(t => /Datum urucenja/.test(t)) && /cela sporna tačka — svih 2 protivrečnosti/.test(poruka),
  `${aktivne.length} | ${poruka}`);
const stanje = (await zahtev("/__osb003/stanje")).j || {};
const potvrde = (stanje.audit || stanje.audit_immutable || []).filter(x => x.action === "sporna_tacka_potvrdjena");
const kon1 = (await zahtev(`/api/predmeti/${PID}/genome-v2`, { token: "tok-A" })).j.kontradikcije;
zapisi("api", "posle potvrde: 2 aktivne (ista tačka), takse i dalje čeka odluku",
  kon1.aktivne.length === 2 && kon1.za_pregled.length === 1 && /uplatu takse/.test(kon1.za_pregled[0].sporna_tacka), JSON.stringify(potvrde).slice(0, 200));

zapisi("izolacija", "0 spoljnih veza", spoljni.length === 0, spoljni.slice(0, 3).join(", "));
zapisi("konzola", "0 JS grešaka, 0 odgovora 5xx", greskeJS.length === 0 && api500.length === 0, [...greskeJS, ...api500].slice(0, 3).join(" | "));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
