// Vindex V2 NG — S10 KOMPLETAN TOK (šta advokat VIDI): jedan sintetički predmet kroz stvaran V2 /app u Chromium-u nad
// PRAVIM api.app koji upisuje (tests/osb003_solo_server.py, VX_KONTRADIKCIJE=1: stvarne rute, stvaran intake worker, stvaran
// OCR kad je Tesseract dostupan; simulirani su samo modeli, embedding i prijava). Ništa ne izlazi van 127.0.0.1.
// Pokretanje: `node tests/live-s10-bojan-ceo-tok-e2e.mjs` (stvaran OCR: VX_PYTHON = Python sa Tesseract-om).
//
//   1 opis i cilj → nov klijent → provera sukoba → jedan predmet
//   2 četiri formata (digitalni PDF, sken, fotografija, DOCX) → pregled → prikačivanje istom predmetu
//   3 Analiza: lažna (dve takse) i stvarna (dva datuma uručenja) protivrečnost su KANDIDATI → advokat odbacuje/potvrđuje
//   4 Danas: dva roka ISTOG dana nose SVOJE rečenice iz dokumenta → potvrdi jedan, odbij drugi
//   5 Rad: predlog ročišta iz dokumenta → „Proveri i zakaži“ → zakazano (dupli klik = jedno)
//   6 Naplata: stavka → faktura → izdata → plaćena
//   7 PDF i CSV preuzeti i pročitani
//   8 reload: sve ostaje; korisnik B ne vidi predmet; 0 spoljnih veza, bez JS grešaka i 5xx
// Pitanja (nadležnost, čl. 55a) i podsetnik kroz lokalni SMTP: tests/test_s10_bojan_ceo_tok.py (model se ne poziva).
import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4541, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const pauza = (ms) => new Promise(r => setTimeout(r, ms));

// „danas“ po Europe/Belgrade (kao server), ne po lokalnoj zoni mašine — inače se oko ponoći datumi razilaze
const DANAS_BG = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Belgrade", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const dan = (n) => { const d = new Date(`${DANAS_BG}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d; };
const sr = (d) => `${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}.${d.getUTCFullYear()}.`;
const iso = (d) => d.toISOString().slice(0, 10);
const SUTRA = dan(1), ZA_5 = dan(5), ROC = dan(3), ZA_10 = dan(10);

const dir = await mkdtemp(join(tmpdir(), "vx-s10-"));
const D = { pdf: join(dir, "01 Resenje digitalno.pdf"), docx: join(dir, "02 Nalog.docx"), sken: join(dir, "03 Dostavnica skenirana.pdf"),
            foto: join(dir, "04 Povratnica fotografija.png") };
const RESENJE = ["OSNOVNI SUD U NOVOM SADU", "Posl. br. P 7101/2026", "RESENJE",
  `Pripremno rociste zakazuje se za ${sr(ROC)} godine u 09:30 casova, sudnica 7.`,
  `Rok za odgovor na tuzbu istice ${sr(SUTRA)} godine.`, `Rok za uplatu sudske takse istice ${sr(SUTRA)} godine.`,
  "Resenje o otkazu je uruceno tuziocu 17.03.2025. godine."];
const NALOG = ["NALOG ZA UPLATU", "Posl. br. P 7101/2026", `Rok za uplatu dodatne sudske takse istice ${sr(ZA_5)} godine.`,
  "Posiljka je urucena primaocu 25.03.2025. godine."];
const gen = spawnSync(PY, ["-c", `
import fitz, docx
from reportlab.pdfgen import canvas
def pdf(put, redovi):
    c = canvas.Canvas(put)
    for i, r in enumerate(redovi):
        c.drawString(60, 780 - i * 24, r)
    c.showPage(); c.save()
def raster(redovi):
    d = fitz.open(); s = d.new_page(width=595, height=842); tw = fitz.TextWriter(s.rect)
    for i, r in enumerate(redovi):
        tw.append((50, 80 + i * 34), r, font=fitz.Font("helv"), fontsize=20)
    tw.write_text(s); png = s.get_pixmap(dpi=200).tobytes("png"); d.close(); return png
pdf(r"${D.pdf}", ${JSON.stringify(RESENJE)})
x = docx.Document()
for r in ${JSON.stringify(NALOG)}:
    x.add_paragraph(r)
x.save(r"${D.docx}")
k = fitz.open(); s2 = k.new_page(width=595, height=842)
s2.insert_image(s2.rect, stream=raster(["DOSTAVNICA", "Primalac: Stefan Primerovic", "Uruceno dana 05.02.2026. godine.", "Rok za zalbu istice ${sr(ZA_10)} godine."])); k.save(r"${D.sken}"); k.close()
open(r"${D.foto}", "wb").write(raster(["POVRATNICA", "Primalac: Beta Primer DOO", "Uruceno dana 06.02.2026. godine."]))
`], { encoding: "utf-8" });
if (gen.status !== 0) { console.log(gen.stderr); process.exit(1); }

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_KONTRADIKCIJE: "1" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, opt = {}) => new Promise(r => {
  const q = http.request(BASE + p, { method: opt.method || "GET", headers: opt.headers || {} }, s => { const ch = []; s.on("data", c => ch.push(c)); s.on("end", () => r({ s: s.statusCode, b: Buffer.concat(ch).toString("utf-8") })); });
  q.on("error", () => r({ s: 0, b: "" })); if (opt.telo) q.write(opt.telo); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await pauza(300); }
zapisi("server", "pravi api.app nad bazom koja upisuje (VX_KONTRADIKCIJE=1)", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const kao = (tok) => async (p, metod = "GET", telo) => { const r = await zahtev(p, { method: metod, headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json" }, telo: telo && JSON.stringify(telo) }); try { return { s: r.s, j: JSON.parse(r.b) }; } catch { return { s: r.s, j: null }; } };
const kaoA = kao("tok-A"), kaoB = kao("tok-B");
const zlatni = async () => JSON.parse((await zahtev("/__osb003/zlatni")).b);
const obradi = async () => JSON.parse((await zahtev("/__osb003/obradi", { method: "POST" })).b);

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
async function kontekst(tok, uid, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport, reducedMotion: "reduce", acceptDownloads: true });
  await ctx.route("**/*", r => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") { spoljni.push(u.href); return r.abort(); }
    if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
    [KLJUC, JSON.stringify({ access_token: tok, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: uid } })]);
  const p = await ctx.newPage();
  p.setDefaultTimeout(10000);
  p.on("pageerror", e => greskeJS.push(String(e)));
  p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
  return { ctx, p };
}
const { p } = await kontekst("tok-A", "uid-A");
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);
const ime = (put) => put.split(/[\\/]/).pop();
const posao = (imeF) => p.evaluate((i) => { const li = [...document.querySelectorAll("#pd-poslovi li.intake")].find(x => (x.querySelector(".intake__name") || {}).textContent === i); return li ? li.innerText : ""; }, imeF);
const klikPosao = (imeF, dugme) => p.evaluate(([i, t]) => {
  const li = [...document.querySelectorAll("#pd-poslovi li.intake")].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
  const b = li && [...li.querySelectorAll("button")].find(x => x.textContent === t && !x.disabled); if (b) b.click(); return !!b; }, [imeF, dugme]);
async function doKraja(imeF) {
  for (let krug = 0; krug < 6; krug++) {
    await cekaj((i) => { const li = [...document.querySelectorAll("#pd-poslovi li.intake")].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
      return li && /Potvrđujem pregled|Prikači ovom predmetu|Prikačeno ovom predmetu|Obrada nije uspela|NIJE prikačen/.test(li.innerText); }, imeF, 20000);
    const t = await posao(imeF);
    if (/Prikačeno ovom predmetu|Obrada nije uspela|NIJE prikačen/.test(t)) return t;
    if (/Potvrđujem pregled/.test(t)) { await klikPosao(imeF, "Potvrđujem pregled"); await pauza(300); await obradi(); continue; }
    await klikPosao(imeF, "Prikači ovom predmetu");
    await cekaj((i) => { const li = [...document.querySelectorAll("#pd-poslovi li.intake")].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
      return li && /Prikačeno ovom predmetu|NIJE prikačen|nije završeno/.test(li.innerText); }, imeF, 20000);
    await obradi();
  }
  return posao(imeF);
}

// ══ 1. opis i cilj → klijent → provera sukoba → predmet ═══════════════════════════════════════════════════════════
await p.goto(BASE + "/app#/"); await p.goto(BASE + "/app#/predmeti/nov");
await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
await p.click("#nov-rezim-opis");
await p.fill("#npo-opis", "Klijent Stefan Primerovic dobio je resenje o otkazu od Beta Primer DOO. Cilj: ponistaj resenja i isplata zarade. Oznaka S10-BOJAN.");
await p.click("#npo-predlozi");
await cekaj(() => !document.getElementById("npo-predlog").hidden);
await p.fill("#npo-naziv", "Primerovic protiv Beta Primer — S10");
await p.fill("#npo-ime", "Stefan"); await p.fill("#npo-prezime", "Primerovic"); await p.click("#npo-proveri");
await cekaj(() => !document.getElementById("npo-coi").hidden);
zapisi("1", "provera sukoba izvršena, otvaranje dozvoljeno", await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000), await tekstEl("npo-coi-naslov"));
await p.click("#npo-otvori");
await cekaj(() => /#\/predmeti\/[^/]+$/.test(location.hash) && !/nov$/.test(location.hash));
const PID = decodeURIComponent((await p.evaluate(() => location.hash)).split("/")[2]);
let z = await zlatni();
const pA = (await kaoA(`/api/predmeti/${PID}`)).j || {};
const opisA = String((pA.predmet || pA).opis || "");
zapisi("1", "tačno 1 predmet A sa opisom i ciljem, 1 klijent, 1 veza", z.predmeti.length === 1 && z.predmeti[0].id === PID && /Cilj:/.test(opisA) && /S10-BOJAN/.test(opisA)
  && z.klijenti.length === 1 && z.veze.length === 1 && z.veze[0].predmet_id === PID, JSON.stringify([z.predmeti, z.veze, opisA.slice(0, 80)]));

// ══ 2. četiri formata → pregled → prikačivanje ═════════════════════════════════════════════════════════════════════
await p.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID) + "/prijem");
await cekaj(() => { const f = document.getElementById("pd-forma"); return f && !f.closest("[hidden]"); });
await p.setInputFiles("#pd-fajlovi", [D.pdf, D.docx, D.sken, D.foto]);
await p.click("#pd-otpremi");
await cekaj(() => document.querySelectorAll("#pd-poslovi li.intake").length === 4);
await obradi();
const kraj = {};
for (const k of ["pdf", "docx", "sken", "foto"]) kraj[k] = await doKraja(ime(D[k]));
z = await zlatni();
const ocr = z.prijem_dokumenti.filter(x => x.ocr_used === true).length;
const dokPred = z.dokumenti.filter(x => x.predmet_id === PID);
console.log(`OCR: ${ocr > 0 ? "stvaran OCR je pročitao " + ocr + " dokument(a)" : "Tesseract nije dostupan — sken i fotografija vidljivo neprikačeni"}`);
zapisi("2", ocr > 0 ? "sva 4 formata prikačena ISTOM predmetu, sa tekstom" : "bez OCR-a: digitalni PDF i DOCX prikačeni, sken/foto NE (bez izmišljenog teksta)",
  ocr > 0 ? dokPred.length === 4 && dokPred.every(x => x.ima_tekst) : dokPred.length === 2 && [kraj.sken, kraj.foto].every(t => /nije izdvojen tekst/.test(t)),
  JSON.stringify(dokPred.map(x => [x.naziv_fajla, x.ima_tekst])));
await obradi(); await obradi();

// ══ 3. Analiza: kandidati → odbaci lažnu, potvrdi stvarnu ═════════════════════════════════════════════════════════
await p.goto(`${BASE}/app#/predmeti/${PID}/analiza`);
const kand = await cekaj(() => document.querySelectorAll("#an-kontr-pregled > li").length === 2, null, 20000);
const prPre = await p.evaluate(() => [...document.querySelectorAll("#an-kontr-pregled > li")].map(x => x.innerText.replace(/\s+/g, " ")));
zapisi("3", "obe AI protivrečnosti su NEPOTVRĐENI kandidati sa oba izvora, nijedna aktivna", kand && prPre.every(t => /nepotvrđena/.test(t) && /Izvor: 01 Resenje digitalno\.pdf/.test(t) && /Izvor: 02 Nalog\.docx/.test(t))
  && (await p.evaluate(() => document.querySelectorAll("#an-kontr-aktivne > li").length)) === 0, JSON.stringify(prPre).slice(0, 400));
await p.click('#an-kontr-pregled > li:has-text("uplatu takse") button[data-radnja="odbij"]');
await p.click('#an-kontr-pregled > li:has-text("uplatu takse") button[data-radnja="odbij-potvrda"]');
await cekaj(() => document.querySelectorAll("#an-kontr-pregled > li").length === 1);
await p.click('#an-kontr-pregled > li:has-text("Datum urucenja resenja") button[data-radnja="potvrdi"]');
await cekaj(() => document.querySelectorAll("#an-kontr-aktivne > li").length === 1);
await obradi();
const g3 = (await kaoA(`/api/predmeti/${PID}/genome-v2`)).j.kontradikcije;
zapisi("3", "aktivna samo potvrđena (uručenje), lažna (takse) u istoriji kao odbijena", g3.aktivne.map(x => x.sporna_tacka).join() === "Datum urucenja resenja"
  && g3.zatvorene.some(x => /takse/.test(x.sporna_tacka) && x.stanje === "ODBIJENA") && g3.za_pregled.length === 0, JSON.stringify(g3).slice(0, 300));

// ══ 4. Danas: dva roka istog dana, svaki sa SVOJOM rečenicom → potvrdi / odbij ═══════════════════════════════════════
const kandidati = (await kaoA(`/api/rokovi/kandidati?od=${iso(dan(0))}&dana=30`)).j.rokovi.filter(r => r.predmet_id === PID);
const odg = kandidati.find(r => /odgovor na tuzbu istice/.test(r.dogadjaj)), taksa = kandidati.find(r => /uplatu sudske takse istice/.test(r.dogadjaj));
zapisi("4", "kandidati istog dana nose svoje rečenice iz dokumenta (ne samo „2. rok sa istim datumom“)", !!odg && !!taksa && odg.datum_iso === iso(SUTRA)
  && taksa.datum_iso === iso(SUTRA), JSON.stringify(kandidati.map(r => [r.dogadjaj, r.datum_iso])));
await p.goto(BASE + "/app#/danas");
await cekaj((ids) => ids.every(id => document.querySelector(`#da-predlozi .review[data-rok="${id}"]`)), [odg && odg.id, taksa && taksa.id], 15000);
const tekstRoka = (id) => p.evaluate((i) => (document.querySelector(`#da-predlozi .review[data-rok="${i}"]`) || {}).innerText || "", id);
const tOdg = await tekstRoka(odg && odg.id), tTaksa = await tekstRoka(taksa && taksa.id);
zapisi("4", "Danas: advokat VIDI koja je koja obaveza", /odgovor na tuzbu/.test(tOdg) && /uplatu sudske takse/.test(tTaksa) && !/uplatu sudske takse/.test(tOdg), JSON.stringify([tOdg, tTaksa]).slice(0, 400));
const zalba = kandidati.find(r => /zalbu istice/.test(r.dogadjaj));
if (ocr > 0) {
  await cekaj((i) => !!document.querySelector(`#da-predlozi .review[data-rok="${i}"]`), zalba && zalba.id, 10000);
  const tZalba = await tekstRoka(zalba && zalba.id);
  zapisi("4", "Danas: rok sa skena nosi „OCR, proveriti“ i svoju rečenicu", /OCR, proveriti/.test(tZalba) && /zalbu istice/.test(tZalba), tZalba.slice(0, 200));
}
await p.click(`#da-predlozi .review[data-rok="${odg.id}"] button:nth-of-type(1)`);
await cekaj((i) => !document.querySelector(`#da-predlozi .review[data-rok="${i}"]`) || /potvrđen/i.test(document.querySelector(`#da-predlozi .review[data-rok="${i}"]`).innerText), odg.id);
await p.goto(BASE + "/app#/"); await p.goto(BASE + "/app#/danas");
await cekaj((i) => !!document.querySelector(`#da-predlozi .review[data-rok="${i}"]`), taksa.id);
await p.click(`#da-predlozi .review[data-rok="${taksa.id}"] button:nth-of-type(2)`);
await pauza(800);
const stanja = Object.fromEntries((await kaoA(`/api/rokovi/kandidati?od=${iso(dan(0))}&dana=30`)).j.rokovi.filter(r => r.predmet_id === PID).map(r => [r.id, r.stanje_odluke]));
zapisi("4", "odluke zabeležene: odgovor potvrđen, taksa odbijena, dodatna taksa i dalje čeka", stanja[odg.id] === "CONFIRMED" && stanja[taksa.id] === "REJECTED"
  && Object.entries(stanja).some(([id, s]) => id !== odg.id && id !== taksa.id && s === "UNCONFIRMED"), JSON.stringify(stanja));

// ══ 5. ročište iz dokumenta → „Proveri i zakaži“ → zakazano ═══════════════════════════════════════════════════════
await p.goto(BASE + "/app#/predmeti"); await p.goto(BASE + `/app#/predmeti/${PID}/rad`);
await cekaj(() => document.querySelectorAll("#roc-predlozi li").length > 0, null, 15000);
const predlozi = await p.evaluate(() => [...document.querySelectorAll("#roc-predlozi li")].map(x => x.innerText.replace(/\s+/g, " ")));
zapisi("5", "predlog ročišta iz dokumenta, sa izvorom, označen kao nezakazan; u bazi nema ročišta", predlozi.length === 1 && predlozi[0].includes(sr(ROC)) && /09:30/.test(predlozi[0])
  && /nije zakazano/i.test(predlozi[0]) && ((await kaoA(`/api/rocista?predmet_id=${PID}`)).j.rocista || []).length === 0, JSON.stringify(predlozi));
await p.evaluate(() => { const b = [...document.querySelectorAll("#roc-predlozi li button")].find(x => /Proveri i zakaži/.test(x.textContent)); if (b) b.click(); });
await cekaj(() => !document.getElementById("roc-forma").hidden);
await p.evaluate(() => { const b = document.getElementById("roc-sacuvaj"); b.click(); b.click(); });
await cekaj(() => /Ročište je zakazano/.test(document.getElementById("roc-poruka").textContent));
await pauza(600);
const roc = (await kaoA(`/api/rocista?predmet_id=${PID}`)).j.rocista || [];
zapisi("5", "tačno jedno zakazano ročište (dupli klik), datum i vreme iz dokumenta", roc.length === 1 && roc[0].datum === iso(ROC) && /^09:30/.test(roc[0].vreme || ""), JSON.stringify(roc));

// ══ 6. naplata: stavka → faktura → izdata → plaćena ═══════════════════════════════════════════════════════════════
await p.goto(BASE + "/app#/predmeti"); await p.goto(BASE + `/app#/predmeti/${PID}/naplata`);
await cekaj(() => { const f = document.getElementById("np-forma"); return f && !f.closest("[hidden]"); });
await p.fill("#np-opis", "Priprema odgovora na tuzbu"); await p.fill("#np-iznos", "1234.56");
await p.click("#np-dodaj");
await cekaj(() => document.querySelectorAll("#np-stavke input[data-stavka]").length === 1);
await p.check("#np-stavke input[data-stavka]");
await p.fill("#np-klijent", "Stefan Primerovic"); await p.selectOption("#np-pdv", "20");
await p.click("#np-faktura-dugme");
await cekaj(() => document.querySelectorAll("#np-fakture li").length === 1);
const klikF = (t) => p.evaluate((t) => { const b = [...document.querySelectorAll("#np-fakture li button")].find(x => x.textContent === t && !x.disabled); if (b) b.click(); return !!b; }, t);
await klikF("Označi kao izdatu");
await cekaj(() => [...document.querySelectorAll("#np-fakture li button")].some(b => b.textContent === "Plaćena"));
await klikF("Plaćena");
await cekaj(() => /plaćena/.test(document.getElementById("np-fakture").innerText));
const fakt = (await kaoA(`/billing/faktura?limit=50`)).j;
const lista = ((fakt && fakt.fakture) || []).filter(f => f.predmet_id === PID);
zapisi("6", "faktura je „plaćena“ (ručno označeno), iznos sa PDV-om tačan", Array.isArray(lista) && lista.length === 1 && lista[0].status === "placena"
  && Math.abs(Number(lista[0].iznos_sa_pdv) - 1481.47) < 0.005, JSON.stringify(lista).slice(0, 300));

// ══ 7. PDF i CSV — stvarno preuzeti i pročitani ════════════════════════════════════════════════════════════════════
await p.goto(BASE + `/app#/predmeti/${PID}`);
await p.waitForSelector("#iz-pdf", { state: "visible" });
const [dl] = await Promise.all([p.waitForEvent("download"), p.click("#iz-pdf")]);
const pdfPut = join(dir, "izvestaj.pdf"); await dl.saveAs(pdfPut);
const pt = (spawnSync(PY, ["-c", "import sys,pymupdf;print(' '.join(' '.join(s.get_text() for s in pymupdf.open(sys.argv[1])).split()))", pdfPut], { encoding: "utf-8", env }).stdout || "");
zapisi("7", "PDF: naziv, odbijen rok [ODBIJENO], nepotvrđen [NEPOTVRĐENO], potvrđen bez oznake, ročište", pt.includes("Primerovic protiv Beta Primer")
  && /\[ODBIJENO\] Rok iz dokumenta: Rok za uplatu sudske takse/.test(pt) && /\[NEPOTVRĐENO\] Rok iz dokumenta: Rok za uplatu dodatne/.test(pt)
  && /Rok iz dokumenta: Rok za odgovor na tuzbu/.test(pt) && !/\[(NEPOTVRĐENO|ODBIJENO)\] Rok iz dokumenta: Rok za odgovor/.test(pt) && pt.includes("09:30"), pt.slice(0, 900));
await p.goto(BASE + "/app#/predmeti"); await p.goto(BASE + `/app#/predmeti/${PID}/naplata`);
await p.waitForSelector("#np-csv", { state: "visible" });
const [dl2] = await Promise.all([p.waitForEvent("download"), p.click("#np-csv")]);
const csv = (await readFile(await dl2.path(), "utf-8")).replace(/^﻿/, "");
const red = csv.trim().split(/\r?\n/).map(r => r.split(";")).find(r => r.includes("Priprema odgovora na tuzbu"));
zapisi("7", "CSV: stavka sa tačnim decimalnim iznosom i statusom „plaćena“", !!red && red[7] === "1234.56" && red.at(-1) === "plaćena", JSON.stringify(red));

// ══ 8. reload: sve ostaje; korisnik B ne vidi ništa ═════════════════════════════════════════════════════════════
await p.goto(BASE + `/app#/predmeti/${PID}`); await p.reload();
const docs = ocr > 0 ? "4" : "2";
zapisi("8", "posle reload-a: klijent, dokumenti i naziv predmeta", await cekaj((n) => document.getElementById("dok-broj").textContent === n
  && /Primerovic/.test(document.getElementById("predmet-klijenti").textContent) && /Primerovic protiv Beta Primer/.test(document.getElementById("predmet-naslov").textContent), docs, 15000));
const g8 = (await kaoA(`/api/predmeti/${PID}/genome-v2`)).j.kontradikcije;
zapisi("8", "posle reload-a odluke o protivrečnostima ostaju", g8.aktivne.length === 1 && g8.za_pregled.length === 0);
const rB = { predmet: (await kaoB(`/api/predmeti/${PID}`)).s, genome: (await kaoB(`/api/predmeti/${PID}/genome-v2`)).s, pdf: (await kaoB(`/api/predmeti/${PID}/pdf-export`)).s,
             rok: (await kaoB(`/api/rokovi/${kandidati.find(r => r.id !== odg.id && r.id !== taksa.id).id}/potvrdi`, "POST", {})).s,
             rociste: (await kaoB(`/api/rocista/${roc[0].id}`, "PATCH", { status: "otkazano" })).s };
zapisi("8", "korisnik B: predmet, analiza, PDF, rok i ročište A nedostupni (403/404)", Object.values(rB).every(s => s === 403 || s === 404), JSON.stringify(rB));
const { ctx: ctxB, p: pB } = await kontekst("tok-B", "uid-B");
await pB.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID));
zapisi("8", "B u pregledaču: predmet A se ne prikazuje", await pB.waitForFunction(() => !document.getElementById("predmet-stanje").hidden, null, { timeout: 10000 }).then(() => true, () => false)
  && !/Primerovic/.test(await pB.evaluate(() => document.body.innerText)));
await ctxB.close();

// ══ mobilni (390 px): ključni ekrani bez vodoravnog preliva ═════════════════════════════════════════════════════════
const { ctx: ctxM, p: pm } = await kontekst("tok-A", "uid-A", { width: 390, height: 844 });
const preliv = {};
for (const [n, put] of [["predmet", `/predmeti/${PID}`], ["analiza", `/predmeti/${PID}/analiza`], ["danas", "/danas"], ["rad", `/predmeti/${PID}/rad`], ["naplata", `/predmeti/${PID}/naplata`]]) {
  await pm.goto(BASE + "/app#/"); await pm.goto(BASE + "/app#" + put); await pauza(1200);
  preliv[n] = await pm.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
}
zapisi("mobilni", "390 px: predmet, analiza, Danas, rad i naplata bez vodoravnog preliva", Object.values(preliv).every(x => !x), JSON.stringify(preliv));
await ctxM.close();

zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 3), api500.slice(0, 3)]));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
