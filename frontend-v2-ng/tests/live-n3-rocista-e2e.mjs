// Vindex V2 NG — N3 ROČIŠTA I KALENDAR: stvaran V2 /app u Chromium-u nad PRAVIM api.app koji upisuje
// (tests/osb003_solo_server.py + sintetičko seme kroz VX_OSB003_SEME). Ništa ne izlazi van 127.0.0.1.
// Pokretanje: `node tests/live-n3-rocista-e2e.mjs`.
//
//   R1 Danas prikazuje samo ZAKAZANA ročišta (otkazano / odloženo / tuđe se ne vide kao predstojeće)
//   R2 održano / otkazano / vraćeno — stanje u bazi, u predmetu i u Danas
//   R3 odloženo + novi datum: staro ostaje kao istorija („odloženo“), novo je zakazano
//   R4 istovremena izmena: zastareo prikaz ne prepisuje novije stanje (409, lista osvežena)
//   R5 predlozi iz dokumenata (sudski poziv): izvor i citat, duplikat obaveštenja, prošlo/odloženo, nemoguć datum,
//      dokument bez teksta; predlog NIJE ročište dok ga advokat ne zakaže; odbacivanje trajno; B nema pristup
//   R6 prelaz na zimsko vreme (25.10.2026.) ne pomera „za koliko dana“
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4533, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const iso = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
const zaDana = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d; };
const sr = (d) => String(d.getDate()).padStart(2, "0") + "." + String(d.getMonth() + 1).padStart(2, "0") + "." + d.getFullYear() + ".";
const D3 = iso(zaDana(3)), D4 = iso(zaDana(4)), D5 = iso(zaDana(5)), D9 = iso(zaDana(9));
const P20 = zaDana(20), P30 = zaDana(30), P40 = zaDana(40), PROSLO = zaDana(-60);
const STARO = "2026-01-01T08:00:00+00:00";

const PA = "11111111-aaaa-4aaa-8aaa-000000000001", PA2 = "11111111-aaaa-4aaa-8aaa-000000000002", PB = "22222222-bbbb-4bbb-8bbb-000000000001";
const roc = (id, pid, uid, datum, status, o = {}) => ({ id, predmet_id: pid, user_id: uid, sud: "Osnovni sud u Beogradu", datum, vreme: "10:00:00",
  sudnica: "12", broj_predmeta_suda: "P 100/2026", status, napomena: null, created_at: STARO, updated_at: STARO, ...o });
const dok = (id, pid, uid, naziv, tekst) => ({ id, predmet_id: pid, user_id: uid, naziv_fajla: naziv, tekst_sadrzaj: tekst, created_at: STARO, uploaded_at: STARO });
const POZIV = `OSNOVNI SUD U BEOGRADU\nPosl. br. P 5521/2026\nPOZIV ZA ROČIŠTE\nU parničnom predmetu tužioca Milice Zlatić protiv tuženog Zlatna Linija DOO, `
  + `pripremno ročište zakazuje se za ${sr(P20)} godine u 10:00 časova, u sudnici broj 14.\nPoziva se stranka da pristupi.`;
const SEME = {
  predmeti: [
    { id: PA, user_id: "uid-A", naziv: "Zlatić protiv Zlatna Linija", status: "aktivan", created_at: STARO },
    { id: PA2, user_id: "uid-A", naziv: "Drugi predmet A", status: "aktivan", created_at: STARO },
    { id: PB, user_id: "uid-B", naziv: "TAJNI predmet B", status: "aktivan", created_at: STARO },
  ],
  rocista: [
    roc("r-zak", PA, "uid-A", D3, "zakazano"),
    roc("r-otk", PA, "uid-A", D4, "otkazano", { sud: "OTKAZANI sud" }),
    roc("r-odl", PA, "uid-A", D5, "odlozeno", { sud: "ODLOZENI sud" }),
    roc("r-a2", PA2, "uid-A", D9, "zakazano", { sud: "Viši sud u Beogradu", vreme: "09:00:00" }),
    roc("r-b", PB, "uid-B", D3, "zakazano", { sud: "TAJNI sud B" }),
  ],
  predmet_dokumenti: [
    dok("d-poziv", PA, "uid-A", "Poziv za rociste.pdf", POZIV),
    dok("d-poziv2", PA, "uid-A", "Poziv za rociste (kopija).pdf", POZIV.replace("Poziva se stranka", "Ponovljena dostava. Poziva se stranka")),
    dok("d-odlaganje", PA, "uid-A", "Zapisnik sa rocista.pdf", `OSNOVNI SUD U BEOGRADU\nZAPISNIK\nRočište zakazano za ${sr(P30)} godine odlaže se. `
      + `Novo ročište zakazuje se za ${sr(P40)} godine u 09:30 časova, sudnica 7.`),
    dok("d-proslo", PA, "uid-A", "Stari zapisnik.pdf", `Ročište je održano dana ${sr(PROSLO)} godine u 11:00 časova.`),
    dok("d-los-datum", PA, "uid-A", "Los OCR.pdf", "Ročište se zakazuje za 31.02.2027. godine u 10:00 časova."),
    dok("d-sken", PA, "uid-A", "Sken bez teksta.pdf", ""),
    dok("d-b", PB, "uid-B", "Poziv B.pdf", `Ročište se zakazuje za ${sr(P20)} godine u 12:00 časova. TAJNO B`),
  ],
};
const dir = await mkdtemp(join(tmpdir(), "vx-n3-"));
const semePut = join(dir, "seme.json");
await writeFile(semePut, JSON.stringify(SEME));

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_OSB003_SEME: semePut };
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
const rocistaA = async (pid = PA) => (json(await kaoA(`/api/rocista?predmet_id=${pid}&limit=100`)) || { rocista: [] }).rocista;

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
async function kontekst(o = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", timezoneId: "Europe/Belgrade", ...o });
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
  return { ctx, p };
}
const { ctx, p } = await kontekst();
const cekaj = (fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);
async function danas() {
  await p.goto(BASE + "/app#/predmeti");
  await p.goto(BASE + "/app#/danas");
  await cekaj(() => { const e = document.getElementById("da-kalendar"); return e && (e.children.length > 0 || /nema/i.test(document.body.innerText)); });
  await p.waitForTimeout(400);
  return p.evaluate(() => [...document.querySelectorAll("#da-kalendar li, #da-obaveze li")].map(x => x.innerText.replace(/\s+/g, " ")));
}
async function rad(pid = PA) {
  await p.goto(BASE + "/app#/predmeti");
  await p.goto(BASE + `/app#/predmeti/${pid}/rad`);
  await cekaj(() => document.querySelectorAll("#roc-lista .hearing").length > 0);
}
const stavke = () => p.evaluate(() => [...document.querySelectorAll("#roc-lista .hearing")].map(x => x.innerText.replace(/\s+/g, " ")));
const klikRociste = (deo, dugme) => p.evaluate(([d, t]) => {
  const li = [...document.querySelectorAll("#roc-lista .hearing")].find(x => x.innerText.includes(d));
  const b = li && [...li.querySelectorAll("button")].find(x => x.textContent.trim() === t && !x.disabled);
  if (b) b.click(); return !!b;
}, [deo, dugme]);
const status = async (id) => ((await rocistaA()).find(r => r.id === id) || {}).status;

// ══ R1 Danas ═════════════════════════════════════════════════════════════════════════════════════════════════════
let d = await danas();
const sve = d.join(" | ");
zapisi("R1", "Danas prikazuje zakazana ročišta oba predmeta A", /Osnovni sud u Beogradu/.test(sve) && /Viši sud u Beogradu/.test(sve), sve);
zapisi("R1", "otkazano i odloženo ročište se NE prikazuju kao predstojeće", !/OTKAZANI sud|ODLOZENI sud/.test(sve), sve);
zapisi("R1", "ročište advokata B se ne vidi", !/TAJNI/.test(sve), sve);

// ══ R2 održano / otkazano / vraćeno ═════════════════════════════════════════════════════════════════════════════
await rad();
let s = await stavke();
zapisi("R2", "predmet prikazuje i istoriju (otkazano, odloženo) i zakazano, sa stanjem", s.length === 3 && s.some(x => /otkazano/.test(x)) && s.some(x => /odloženo/.test(x)), JSON.stringify(s));
const imaAkcije = await klikRociste("P 100/2026 · zakazano", "Otkazano");
await cekaj(() => /otkazano/.test(document.getElementById("roc-poruka").textContent + " ") || /Ročište je označeno/.test(document.getElementById("roc-poruka").textContent));
await p.waitForTimeout(500);
zapisi("R2", "zakazano ročište → „Otkazano“: baza, predmet i Danas usklađeni", imaAkcije && await status("r-zak") === "otkazano"
  && !(await danas()).join(" ").includes(sr(zaDana(3)).slice(0, 6) + " Osnovni"), JSON.stringify([imaAkcije, await status("r-zak"), await tekstEl("roc-poruka")]));
await rad();
const vraceno = await klikRociste(sr(zaDana(3)), "Vrati na zakazano");
await p.waitForTimeout(800);
zapisi("R2", "greškom otkazano → „Vrati na zakazano“", vraceno && await status("r-zak") === "zakazano", JSON.stringify([vraceno, await status("r-zak")]));

// ══ R4 istovremena izmena: drugi tab ga je u međuvremenu označio kao održano ═════════════════════════════════════
await rad();
const izmena = await kaoA("/api/rocista/r-zak", "PATCH", { status: "odrzano" });
const preKlik = await status("r-zak");
await klikRociste(sr(zaDana(3)), "Otkazano");
await cekaj(() => /izmenjeno u međuvremenu/i.test(document.getElementById("roc-poruka").textContent));
zapisi("R4", "zastareo prikaz: klik „Otkazano“ ne prepisuje „održano“ iz drugog taba (409, poruka, lista osvežena)",
  izmena.s === 200 && preKlik === "odrzano" && await status("r-zak") === "odrzano" && /izmenjeno u međuvremenu/i.test(await tekstEl("roc-poruka")),
  JSON.stringify([izmena.s, await status("r-zak"), await tekstEl("roc-poruka")]));
await kaoA("/api/rocista/r-zak", "PATCH", { status: "zakazano" });

// ══ R3 odloženo + novi datum ═════════════════════════════════════════════════════════════════════════════════════
await rad();
await klikRociste(sr(zaDana(3)), "Odloženo");
await cekaj(() => !document.getElementById("roc-forma").hidden);
const pre = await p.evaluate(() => ({ sud: document.getElementById("roc-sud").value, broj: document.getElementById("roc-broj").value, datum: document.getElementById("roc-datum").value }));
zapisi("R3", "„Odloženo“ označava staro i otvara zakazivanje novog sa istim sudom i brojem (datum prazan)",
  await status("r-zak") === "odlozeno" && pre.sud === "Osnovni sud u Beogradu" && pre.broj === "P 100/2026" && pre.datum === "", JSON.stringify([await status("r-zak"), pre]));
await p.fill("#roc-datum", D9); await p.fill("#roc-vreme", "11:30");
await p.click("#roc-sacuvaj");
await cekaj(() => /Ročište je zakazano/.test(document.getElementById("roc-poruka").textContent));
let lista = await rocistaA();
const novo = lista.find(r => r.datum === D9 && r.predmet_id === PA);
zapisi("R3", "novo ročište zakazano u ISTOM predmetu; staro ostaje kao „odloženo“ (istorija sačuvana)",
  !!novo && novo.status === "zakazano" && lista.find(r => r.id === "r-zak").status === "odlozeno" && /odlo/i.test(novo.napomena || ""), JSON.stringify(lista.map(r => [r.datum, r.status, r.napomena])));
d = await danas();
zapisi("R3", "Danas: novi datum je tu, odloženi nije", d.join(" ").includes(sr(zaDana(9)).slice(0, 5)) && !d.some(x => x.includes(sr(zaDana(3)).slice(0, 5)) && /Osnovni/.test(x)), JSON.stringify(d));

// ══ R5 predlozi iz dokumenata ════════════════════════════════════════════════════════════════════════════════════
await rad();
await cekaj(() => document.querySelectorAll("#roc-predlozi li").length > 0);
const predlozi = await p.evaluate(() => [...document.querySelectorAll("#roc-predlozi li")].map(x => x.innerText.replace(/\s+/g, " ")));
zapisi("R5", "dva predloga: poziv (dva dokumenta, jedan predlog) i novo ročište iz zapisnika — ne staro, ne prošlo, ne nemoguć datum",
  predlozi.length === 2 && predlozi.some(x => x.includes(sr(P20)) && /10:00/.test(x)) && predlozi.some(x => x.includes(sr(P40)) && /09:30/.test(x))
  && !predlozi.some(x => x.includes(sr(PROSLO)) || x.includes(sr(P30)) || /31\.02/.test(x)), JSON.stringify(predlozi));
zapisi("R5", "predlog nosi izvor (dokument i citat) i jasno je označen kao NEZAKAZAN predlog", predlozi.some(x => /Poziv za rociste\.pdf/.test(x) && /kopija/.test(x) && /zakazuje se/.test(x))
  && predlozi.every(x => /nije zakazano/i.test(x)), JSON.stringify(predlozi));
zapisi("R5", "dokument bez teksta je vidljivo naveden (iz njega se ročište ne može predložiti)", /1 dokument.*bez (čitljivog )?teksta/i.test(await tekstEl("roc-predlozi-stanje")), await tekstEl("roc-predlozi-stanje"));
lista = await rocistaA();
zapisi("R5", "predlog NIJE ročište: u bazi nema ročišta za predložene datume", !lista.some(r => r.datum === iso(P20) || r.datum === iso(P40)), JSON.stringify(lista.map(r => r.datum)));
// prihvatanje: forma popunjena iz predloga, advokat proverava i zakazuje
await p.evaluate((dat) => { const li = [...document.querySelectorAll("#roc-predlozi li")].find(x => x.innerText.includes(dat)); const b = li && [...li.querySelectorAll("button")].find(x => /Proveri i zakaži/.test(x.textContent)); if (b) b.click(); }, sr(P20));
await cekaj(() => !document.getElementById("roc-forma").hidden);
const forma = await p.evaluate(() => Object.fromEntries(["roc-sud", "roc-datum", "roc-vreme", "roc-sudnica", "roc-broj", "roc-napomena"].map(i => [i, document.getElementById(i).value])));
zapisi("R5", "„Proveri i zakaži“ popunjava formu iz dokumenta (sud, datum, vreme, sudnica, broj, izvor) — ništa još nije upisano",
  forma["roc-sud"] === "Osnovni sud u Beogradu" && forma["roc-datum"] === iso(P20) && forma["roc-vreme"] === "10:00" && forma["roc-sudnica"] === "14"
  && forma["roc-broj"] === "P 5521/2026" && /Poziv za rociste\.pdf/.test(forma["roc-napomena"]) && !(await rocistaA()).some(r => r.datum === iso(P20)), JSON.stringify(forma));
await p.evaluate(() => { const b = document.getElementById("roc-sacuvaj"); b.click(); b.click(); });   // dupli klik
await cekaj(() => /Ročište je zakazano/.test(document.getElementById("roc-poruka").textContent));
await p.waitForTimeout(600);
lista = await rocistaA();
zapisi("R5", "zakazano iz predloga: TAČNO jedno ročište (dupli klik), u ovom predmetu, sa izvorom u napomeni",
  lista.filter(r => r.datum === iso(P20)).length === 1 && /Poziv za rociste\.pdf/.test(lista.find(r => r.datum === iso(P20)).napomena || ""), JSON.stringify(lista.filter(r => r.datum === iso(P20))));
await cekaj(() => [...document.querySelectorAll("#roc-predlozi li")].length === 1);
zapisi("R5", "zakazan predlog nestaje iz predloga", await p.evaluate((dat) => ![...document.querySelectorAll("#roc-predlozi li")].some(x => x.innerText.includes(dat)), sr(P20)));
// odbacivanje
await p.evaluate((dat) => { const li = [...document.querySelectorAll("#roc-predlozi li")].find(x => x.innerText.includes(dat)); const b = li && [...li.querySelectorAll("button")].find(x => /Odbaci/.test(x.textContent)); if (b) b.click(); }, sr(P40));
await cekaj(() => document.querySelectorAll("#roc-predlozi li").length === 0);
await rad();
await p.waitForTimeout(1200);
zapisi("R5", "odbačen predlog ostaje odbačen posle osvežavanja; nije napravljeno ročište", (await p.evaluate(() => document.querySelectorAll("#roc-predlozi li").length)) === 0
  && !(await rocistaA()).some(r => r.datum === iso(P40)));
// izolacija
const bp = await kaoB(`/api/rocista/predlozi?predmet_id=${PA}`);
const bo = await kaoB("/api/rocista/predlozi/odbaci", "POST", { predmet_id: PA, kljuc: iso(P20) + "|10:00" });
const ap = (await kaoA(`/api/rocista/predlozi?predmet_id=${PB}`)).s;
const bSvoj = json(await kaoB(`/api/rocista/predlozi?predmet_id=${PB}`));
zapisi("R5", "B ne čita ni ne odbacuje predloge predmeta A (404); A ne čita B; B vidi samo svoj dokument",
  bp.s === 404 && bo.s === 404 && ap === 404 && bSvoj && bSvoj.predlozi.length === 1 && !JSON.stringify(bSvoj).includes("Zlati"), JSON.stringify([bp.s, bo.s, ap, bSvoj && bSvoj.predlozi.length]));
const bPatch = await kaoB("/api/rocista/r-zak", "PATCH", { status: "otkazano" });
zapisi("R5", "B ne može da menja ročište A", bPatch.s === 404 && await status("r-zak") === "odlozeno", String(bPatch.s));

// ══ R6 prelaz na zimsko vreme ════════════════════════════════════════════════════════════════════════════════════
const k6 = await kontekst();
await k6.p.clock.setFixedTime(new Date("2026-10-24T22:30:00+02:00"));      // subota uveče; 25.10. u 03:00 sat ide unazad
const dst = await kaoA("/api/rocista", "POST", { predmet_id: PA2, sud: "DST sud", datum: "2026-10-26", vreme: "08:00" });
await k6.p.goto(BASE + "/app#/danas");
await k6.p.waitForFunction(() => /DST sud/.test(document.body.innerText), null, { timeout: 12000 }).catch(() => {});
const dstTekst = await k6.p.evaluate(() => { const li = [...document.querySelectorAll("#da-kalendar li, #da-obaveze li")].find(x => /DST sud/.test(x.innerText)); return li ? li.innerText.replace(/\s+/g, " ") : ""; });
zapisi("R6", "ročište 26.10.2026. gledano 24.10. uveče (preko prelaza na zimsko vreme) = „za 2 dana“", dst.s === 200 && /za 2 dana/.test(dstTekst), dstTekst);
await k6.ctx.close();

zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 3), api500.slice(0, 3)]));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
