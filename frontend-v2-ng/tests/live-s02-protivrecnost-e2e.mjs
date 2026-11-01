// Vindex V2 NG — S02 / B7 (odluka osnivača A): AI protivrečnost je KANDIDAT dok je advokat ne potvrdi.
// Pokretanje: `node tests/live-s02-protivrecnost-e2e.mjs`. Server: tests/osb003_solo_server.py uz VX_KONTRADIKCIJE=1 (PRAVI
// api.app, stvarne rute, stvaran intake worker i dispečer; simulirani modeli, embedding i prijava). Ništa ne izlazi van 127.0.0.1.
// Tok: dva PDF-a kroz Smart Intake → Genome predlaže lažnu (dve različite takse) i stvarnu (datum uručenja) protivrečnost →
// Analiza: oba kandidata, sa oba izvora, bez aktivnih i bez radnje → advokat potvrdi stvarnu, odbaci lažnu → aktivna je samo
// potvrđena, radnja samo za nju, odbačena u istoriji. Korisnik B ne može da odluči. Svaki korak proveren u UI-ju i u API-ju.

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4527, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const dir = await mkdtemp(join(tmpdir(), "vx-s02-"));
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

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_KONTRADIKCIJE: "1" };
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

// Priprema kroz stvarne rute (isti put kao čarobnjak prijema): predmet → dva dokumenta → finalize → događaji.
const pr = await zahtev("/api/predmeti", { method: "POST", token: "tok-A", telo: { naziv: "S02 protivrecnosti", tip: "Parnica" } });
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
const g0 = await zahtev(`/api/predmeti/${PID}/genome-v2`, { token: "tok-A" });
const kon0 = g0.j && g0.j.kontradikcije;
zapisi("api", "dva kandidata za pregled, nijedna aktivna", !!kon0 && kon0.aktivne.length === 0 && kon0.za_pregled.length === 2,
  kon0 ? `aktivne=${kon0.aktivne.length} za_pregled=${kon0.za_pregled.length}` : g0.b.slice(0, 200));
const akcije = async () => ((await zahtev(`/api/case-actions/predmeti/${PID}`, { token: "tok-A" })).j || {});
const razresiti = (a) => ((a.akcije || a.actions || a.stavke || []).filter(x => (x.tip || x.action_type) === "RAZRESITI_KONTRADIKCIJU" && (x.status || "open") === "open"));
zapisi("api", "nepotvrđeni kandidati ne prave radnju „Razrešiti kontradikciju“", razresiti(await akcije()).length === 0);

// Browser — mobilni prikaz (390 px), stvaran V2 /app.
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
const ekran = () => p.evaluate(() => ({
  aktivne: [...document.querySelectorAll("#an-kontr-aktivne > li")].map(x => ({ stanje: x.dataset.stanje, t: x.innerText.replace(/\s+/g, " ") })),
  pregled: [...document.querySelectorAll("#an-kontr-pregled > li")].map(x => ({ stanje: x.dataset.stanje, t: x.innerText.replace(/\s+/g, " "),
    izvori: x.querySelectorAll(".an-sub > li").length, dugmad: x.querySelectorAll("[data-radnja]").length })),
  // zatvorene su u sklopljenom <details>: innerText je prazan dok se ne otvori, pa se čita textContent
  zatvorene: [...document.querySelectorAll("#an-kontr-zatvorene > li")].map(x => ({ stanje: x.dataset.stanje, t: x.textContent.replace(/\s+/g, " ") })),
  naslovPregleda: !document.getElementById("an-kontr-pregled-naslov").hidden ? document.getElementById("an-kontr-pregled-naslov").textContent : null,
  poruka: document.getElementById("an-kontr-poruka").hidden ? null : document.getElementById("an-kontr-poruka").textContent,
  preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
}));
await p.goto(`${BASE}/app#/predmeti/${PID}/analiza`);
await cekaj(() => document.querySelectorAll("#an-kontr-pregled > li").length === 2);
let e = await ekran();
zapisi("pregled", "oba kandidata pod „Predlozi analize — nisu potvrđeni“, nijedan aktivan",
  e.aktivne.length === 0 && e.pregled.length === 2 && /nisu potvrđeni/.test(e.naslovPregleda || ""), JSON.stringify(e).slice(0, 300));
zapisi("pregled", "svaki kandidat: oznaka „nepotvrđena“, obe tvrdnje sa izvorom, dugmad Potvrdi/Odbaci",
  e.pregled.every(x => x.stanje === "NEPOTVRDJENA" && /nepotvrđena — predlog analize/.test(x.t) && x.izvori === 2 && x.dugmad === 2
    && /Izvor: Resenje\.pdf/.test(x.t) && /Izvor: Nalog\.pdf/.test(x.t)));
zapisi("mobilni", "390 px: bez vodoravnog preliva", !e.preliv);

// Advokat potvrđuje stvarnu protivrečnost (datum uručenja).
await p.click('#an-kontr-pregled > li:has-text("Datum urucenja resenja") button[data-radnja="potvrdi"]');
await cekaj(() => document.querySelectorAll("#an-kontr-aktivne > li").length === 1 && !document.getElementById("an-kontr-poruka").hidden);
e = await ekran();
zapisi("potvrda", "potvrđena je aktivna („potvrdio advokat“), druga i dalje čeka odluku",
  e.aktivne.length === 1 && /Datum urucenja/.test(e.aktivne[0].t) && e.aktivne[0].stanje === "AKTIVNA" && /potvrdio advokat/.test(e.aktivne[0].t)
    && e.pregled.length === 1 && /uplatu takse/.test(e.pregled[0].t) && /Potvrdili ste protivrečnost/.test(e.poruka || ""), JSON.stringify(e).slice(0, 300));
await obradi();
zapisi("potvrda", "radnja „Razrešiti kontradikciju“ postoji samo za potvrđenu", razresiti(await akcije()).length === 1);

// Korisnik B pokušava da odluči o tački A — 404, ništa se ne menja.
const pregledApi = (await zahtev(`/api/predmeti/${PID}/genome-v2`, { token: "tok-A" })).j.kontradikcije.za_pregled;
const issueTakse = pregledApi[0].odluka.issue_id;
const b1 = await zahtev(`/api/predmeti/${PID}/sporne-tacke/${issueTakse}/potvrdi`, { method: "POST", token: "tok-B" });
const b2 = await zahtev(`/api/predmeti/${PID}/sporne-tacke/${issueTakse}/odbij`, { method: "POST", token: "tok-B" });
const b3 = await zahtev(`/api/predmeti/${PID}/sporne-tacke/${issueTakse}/potvrdi`, { method: "POST" });
const bezVidjenog = await zahtev(`/api/predmeti/${PID}/sporne-tacke/${issueTakse}/potvrdi`, { method: "POST", token: "tok-A", telo: {} });
zapisi("izolacija", "API poziv bez viđenog stanja i sadržaja: 409, ništa se ne beleži", bezVidjenog.s === 409, String(bezVidjenog.s));
zapisi("izolacija", "korisnik B: 404 na potvrdu i odbijanje; bez prijave odbijeno", b1.s === 404 && b2.s === 404 && [401, 403].includes(b3.s),
  `${b1.s}/${b2.s}/${b3.s}`);

// Advokat odbacuje lažnu (dve različite takse).
await p.click('#an-kontr-pregled > li:has-text("uplatu takse") button[data-radnja="odbij"]');
const dvostepeno = await p.evaluate(() => {
  const li = [...document.querySelectorAll("#an-kontr-pregled > li")].find(x => /uplatu takse/.test(x.innerText));
  const b = li && li.querySelector('button[data-radnja="odbij-potvrda"]');
  return { naoruzano: !!b && /Potvrdite odbacivanje/.test(b.textContent), jos_u_pregledu: !!li };
});
zapisi("odbijanje", "prvi klik samo traži potvrdu odbacivanja — ništa nije poslato", dvostepeno.naoruzano && dvostepeno.jos_u_pregledu, JSON.stringify(dvostepeno));
await p.click('#an-kontr-pregled > li:has-text("uplatu takse") button[data-radnja="odbij-potvrda"]');
await cekaj(() => document.querySelectorAll("#an-kontr-pregled > li").length === 0 && /Odbacili ste/.test(document.getElementById("an-kontr-poruka").textContent));
e = await ekran();
zapisi("odbijanje", "odbačena nije među aktivnim ni u pregledu; ostaje u zatvorenim kao „odbacili ste je“",
  e.aktivne.length === 1 && e.pregled.length === 0
    && e.zatvorene.some(x => x.stanje === "ODBIJENA" && /uplatu takse/.test(x.t) && /odbacili ste je/.test(x.t) && /Ipak potvrdi/.test(x.t)),
  JSON.stringify(e).slice(0, 300));
await obradi();
zapisi("odbijanje", "i dalje tačno jedna radnja (odbačena je ne dobija)", razresiti(await akcije()).length === 1);

// Ponovno osvežavanje analize: odluke opstaju, nema duplikata.
await zahtev(`/api/predmeti/${PID}/case-dna/refresh`, { method: "POST", token: "tok-A" });
await obradi();
const kon2 = (await zahtev(`/api/predmeti/${PID}/genome-v2`, { token: "tok-A" })).j.kontradikcije;
zapisi("osvežavanje", "posle novog Genome-a: 1 aktivna (potvrđena), 0 za pregled, odbačena ostaje odbačena",
  kon2.aktivne.length === 1 && kon2.za_pregled.length === 0 && kon2.zatvorene.some(x => x.stanje === "ODBIJENA"),
  `a=${kon2.aktivne.length} p=${kon2.za_pregled.length} z=${kon2.zatvorene.map(x => x.stanje)}`);
zapisi("osvežavanje", "radnja se ne duplira", razresiti(await akcije()).length === 1);

// Zastareo prozor: prikaz je učitan, a druga sesija u međuvremenu promeni odluku — klik u starom prozoru ne sme da
// zabeleži ništa (server poredi stanje koje je advokat VIDEO).
await p.goto(`${BASE}/app#/predmeti/${PID}/analiza`);
await p.reload();
await cekaj(() => document.querySelectorAll("#an-kontr-aktivne > li").length === 1);
const aktivnaApi = (await zahtev(`/api/predmeti/${PID}/genome-v2`, { token: "tok-A" })).j.kontradikcije.aktivne[0];
const druga = await zahtev(`/api/predmeti/${PID}/sporne-tacke/${aktivnaApi.odluka.issue_id}/odbij`, { method: "POST", token: "tok-A",
  telo: { ocekivano: { status: aktivnaApi.odluka.status, odluka_at: aktivnaApi.odluka.odluka_at, sadrzaj: aktivnaApi.odluka.sadrzaj } } });
const auditPre = (await zahtev("/__osb003/stanje")).j;
await p.click('#an-kontr-aktivne > li button[data-radnja="odbij"]');
await p.click('#an-kontr-aktivne > li button[data-radnja="odbij-potvrda"]');
await cekaj(() => /promenilo/.test(document.getElementById("an-kontr-poruka").textContent));
const porukaZastarelo = await p.evaluate(() => document.getElementById("an-kontr-poruka").textContent);
zapisi("zastarelo", "druga sesija je odlučila: stari prozor dobija „stanje se promenilo“, ništa nije zabeleženo",
  druga.s === 200 && /promenilo/.test(porukaZastarelo) && /Ništa nije zabeleženo/.test(porukaZastarelo)
    && JSON.stringify((await zahtev("/__osb003/stanje")).j) === JSON.stringify(auditPre), porukaZastarelo);

zapisi("izolacija", "0 spoljnih veza", spoljni.length === 0, spoljni.slice(0, 3).join(", "));
zapisi("konzola", "0 JS grešaka, 0 odgovora 5xx", greskeJS.length === 0 && api500.length === 0, [...greskeJS, ...api500].slice(0, 3).join(" | "));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
