// Vindex V2 NG — N1 GOLDEN INTAKE CASE: jedan advokat, jedan klijent, opis spora, četiri dokumenta, JEDAN predmet —
// kroz STVARAN V2 /app u Chromium-u nad PRAVIM api.app koji upisuje (tests/osb003_solo_server.py: stvarne rute, stvaran
// intake worker i ekstraktor, stvarne provere vlasništva; SIMULIRANI su samo modeli — predlog iz opisa, klasifikacija,
// stranke iz slobodnog teksta —, embedding/Pinecone i prijava). Ništa ne izlazi van 127.0.0.1.
// Pokretanje: `node tests/live-zlatni-prijem-e2e.mjs`.
//
// OCR: ovaj test NE simulira OCR. Ako Tesseract nije instaliran (lokalni Windows), skenirani PDF i fotografija moraju
// VIDLJIVO da ne uspeju (bez izmišljenog teksta); stvaran OCR nad istim tipovima dokumenata meri
// tests/test_n1_zlatni_prijem.py u produkcionoj Docker slici (VINDEX_REQUIRE_OCR=1). Ishod se ispisuje kao „OCR: …“.
//
//   G) zlatni tok: opis → nov klijent → provera sukoba → predmet → 4 dokumenta → pregled + ispravka → prikačivanje → reload
//   E) granični slučajevi: dupli klik, nepoznat ishod (opis i dokument), nepodržan i lažan fajl, ponovljen sadržaj,
//      sukob interesa, tuđ predmet (B), promena korisnika tokom obrade
import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
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

// ── Četiri sintetička dokumenta (izmišljeni podaci) + dva loša ─────────────────────────────────────────────────────
const dir = await mkdtemp(join(tmpdir(), "vx-zlatni-"));
const D = {
  pdf: join(dir, "01 Tuzba digitalna.pdf"), sken: join(dir, "02 Resenje skenirano.pdf"),
  foto: join(dir, "03 Dostavnica fotografija.png"), docx: join(dir, "04 Ugovor o radu.docx"),
  doc: join(dir, "05 Stari ugovor.doc"), lazni: join(dir, "06 Lazni ugovor.docx"),
  pdf2: join(dir, "07 Opomena digitalna.pdf"), pdf3: join(dir, "08 Zalba digitalna.pdf"), pdf4: join(dir, "09 Prilog digitalni.pdf"), pdf5: join(dir, "10 Punomocje digitalno.pdf"), pdf6: join(dir, "11 Racun digitalni.pdf"),
};
const gen = spawnSync(PY, ["-c", `
import io
from reportlab.pdfgen import canvas
import fitz
from PIL import Image, ImageDraw
import docx
def pdf(put, redovi):
    c = canvas.Canvas(put)
    for i, r in enumerate(redovi):
        c.drawString(60, 780 - i * 24, r)
    c.showPage(); c.save()
pdf(r"${D.pdf}", ["OSNOVNI SUD U BEOGRADU", "Broj predmeta: P 5521/2026", "Tuzilac: Milica Zlatic iz Beograda",
                  "Tuzeni: Zlatna Linija DOO Beograd", "Tuzba radi ponistaja resenja o otkazu i isplate zarade od 210.000,00 dinara."])
pdf(r"${D.pdf2}", ["OPOMENA PRED TUZBU", "Poverilac: Milica Zlatic", "Duznik: Zlatna Linija DOO", "Iznos: 210.000,00 dinara."])
pdf(r"${D.pdf3}", ["ZALBA NA RESENJE O OTKAZU", "Zaliteljka: Milica Zlatic iz Beograda", "Protiv: Zlatna Linija DOO Beograd",
                   "Zalba se podnosi zbog nezakonitosti resenja o otkazu ugovora o radu."])
pdf(r"${D.pdf5}", ["PUNOMOCJE ZA ZASTUPANJE", "Vlastodavac: Petar Drugi iz Novog Sada", "Punomocnik: advokat iz Beograda",
                   "Punomocje se daje za zastupanje u parnicnom postupku."])
pdf(r"${D.pdf6}", ["RACUN ZA ADVOKATSKE USLUGE", "Klijent: Petar Drugi iz Novog Sada", "Iznos: 45.000,00 dinara",
                   "Racun se odnosi na sastav tuzbe i zastupanje."])
pdf(r"${D.pdf4}", ["PRILOG UZ ZALBU", "Platne liste za period od 01.11.2025. do 31.01.2026.", "Zaposlena: Milica Zlatic iz Beograda",
                   "Poslodavac: Zlatna Linija DOO Beograd"])
# skenirana strana BEZ tekstualnog sloja
d = fitz.open(); s = d.new_page(width=595, height=842); tw = fitz.TextWriter(s.rect)
for i, r in enumerate(["RESENJE O OTKAZU UGOVORA O RADU", "Zaposlena: Milica Zlatic", "Poslodavac: Zlatna Linija DOO",
                       "Resenje je uruceno 03.02.2026. godine."]):
    tw.append((50, 80 + i * 34), r, font=fitz.Font("helv"), fontsize=20)
tw.write_text(s); pix = s.get_pixmap(dpi=200); d.close()
k = fitz.open(); s2 = k.new_page(width=595, height=842); s2.insert_image(s2.rect, stream=pix.tobytes("png")); k.save(r"${D.sken}"); k.close()
# fotografija dokumenta (PNG)
im = Image.new("RGB", (1200, 700), "white"); dr = ImageDraw.Draw(im)
for i, r in enumerate(["DOSTAVNICA", "Primalac: Milica Zlatic", "Uruceno dana 05.02.2026."]):
    dr.text((60, 60 + i * 80), r, fill="black")
im.save(r"${D.foto}")
x = docx.Document()
for r in ["UGOVOR O RADU", "Poslodavac: Zlatna Linija DOO Beograd", "Zaposlena: Milica Zlatic", "Zarada: 70.000,00 dinara mesecno."]:
    x.add_paragraph(r)
x.save(r"${D.docx}")
open(r"${D.doc}", "wb").write(b"\\xd0\\xcf\\x11\\xe0 stari Word")
open(r"${D.lazni}", "wb").write(b"Ovo nije DOCX nego obican tekst sa pogresnom ekstenzijom.")
`], { encoding: "utf-8" });
if (gen.status !== 0) { console.log(gen.stderr); process.exit(1); }

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, opt = {}) => new Promise(r => {
  const q = http.request(BASE + p, { method: opt.method || "GET", headers: opt.headers || {} }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); });
  q.on("error", () => r({ s: 0, b: "" })); if (opt.telo) q.write(opt.telo); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const stanje = async () => JSON.parse((await zahtev("/__osb003/stanje")).b);
const zlatni = async () => JSON.parse((await zahtev("/__osb003/zlatni")).b);
const obradi = async () => JSON.parse((await zahtev("/__osb003/obradi", { method: "POST" })).b);
const kaoB = (p, metod = "GET", telo) => zahtev(p, { method: metod, headers: { Authorization: "Bearer tok-B", "Content-Type": "application/json" }, telo });

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
let ubacen503 = false;                                   // E3c: test SAM vraća 503 za listu predmeta — to nije greška servera
async function kontekst(tok, uid) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.route("**/*", r => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") { spoljni.push(u.href); return r.abort(); }
    if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
    [KLJUC, JSON.stringify({ access_token: tok, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: uid } })]);
  const p = await ctx.newPage();
  p.setDefaultTimeout(8000);
  p.on("pageerror", e => greskeJS.push(String(e)));
  p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500 && !(ubacen503 && u.pathname === "/api/predmeti")) api500.push(`${s.status()} ${u.pathname}`); });
  return { ctx, p };
}
const { ctx, p } = await kontekst("tok-A", "uid-A");
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const vidljiv = (id) => p.evaluate((i) => { const e = document.getElementById(i); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; }, id);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);
const posao = (pref, ime) => p.evaluate(([pr, i]) => { const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i); return li ? li.innerText : ""; }, [pref, ime]);
const klikPosao = (pref, ime, dugme) => p.evaluate(([pr, i, t]) => {
  const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
  const b = li && [...li.querySelectorAll("button")].find(x => x.textContent === t && !x.disabled);
  if (b) b.click(); return !!b;
}, [pref, ime, dugme]);
const ime = (put) => put.split(/[\\/]/).pop();
const pauza = (ms) => new Promise(r => setTimeout(r, ms));

async function naNovPredmet() {
  // Kao advokat koji počinje NOV predmet: izlazi sa stranice pa otvara „Nov predmet“ (isti hash ne otvara pogled ponovo,
  // a nastavak iste sesije „Iz dokumenta“ namerno prikačuje dokumente upravo otvorenom predmetu).
  await p.goto(BASE + "/app#/");
  await p.goto(BASE + "/app#/predmeti/nov");
  await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
}
async function predlogIzOpisa(opis) {
  await p.click("#nov-rezim-opis");
  await p.fill("#npo-opis", opis);
  await p.click("#npo-predlozi");
  return cekaj(() => !document.getElementById("npo-predlog").hidden);
}
async function klijentICoi(imeK, prezime) {
  await p.fill("#npo-ime", imeK); await p.fill("#npo-prezime", prezime);
  await p.click("#npo-proveri");
  await cekaj(() => !document.getElementById("npo-coi").hidden);
}
/* Pregled, ispravka i prikačivanje jednog posla do kraja (ili do vidljivog neuspeha). Vraća završni tekst posla. */
async function doKraja(pref, imeF, { ispravi } = {}) {
  for (let krug = 0; krug < 6; krug++) {
    await cekaj(([pr, i]) => { const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
      return li && /Potvrđujem pregled|Prikači ovom predmetu|Otvori predmet iz ovog dokumenta|Prikačeno ovom predmetu|Obrada nije uspela|Ponovni pokušaj|već prikačen/.test(li.innerText); }, [pref, imeF], 20000);
    const t = await posao(pref, imeF);
    if (/Prikačeno ovom predmetu|Obrada nije uspela|već prikačen/.test(t)) return t;
    if (/Ponovni pokušaj/.test(t) && !/Potvrđujem pregled|Prikači/.test(t)) { await obradi(); await pauza(300); if (krug >= 3) return t; continue; }
    if (/Potvrđujem pregled/.test(t)) {
      if (ispravi) {
        const ok = await p.evaluate(([pr, i, polje, v]) => {
          const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
          const dd = li && li.querySelector(`dd[data-polje="${polje}"]`); const u = dd && dd.querySelector("input"); const b = dd && dd.querySelector("button");
          if (!u || !b) return false; u.value = v; b.click(); return true;
        }, [pref, imeF, ispravi.polje, ispravi.vrednost]);
        ispravi.uradjeno = ok;
        if (ok) await cekaj(([pr, i]) => { const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
          return li && /ispravljeno/.test(li.innerText); }, [pref, imeF], 10000);
        ispravi = null;
      }
      await klikPosao(pref, imeF, "Potvrđujem pregled");
      await cekaj(([pr, i]) => { const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
        return li && !/Potvrđujem pregled/.test(li.innerText); }, [pref, imeF], 10000);
      await obradi();
      continue;
    }
    const dugme = /Prikači ovom predmetu/.test(t) ? "Prikači ovom predmetu" : "Otvori predmet iz ovog dokumenta";
    await klikPosao(pref, imeF, dugme);
    await cekaj(([pr, i]) => { const li = [...document.querySelectorAll(`#${pr}-poslovi li.intake`)].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
      return li && /Prikačeno ovom predmetu|NIJE prikačen|nije završeno|je otvoren iz dokumenta/.test(li.innerText); }, [pref, imeF], 20000);
    await obradi();
  }
  return posao(pref, imeF);
}

// ══ G) ZLATNI TOK ═════════════════════════════════════════════════════════════════════════════════════════════════
await naNovPredmet();
const OPIS = "Klijentkinja Milica Zlatić dobila je rešenje o otkazu od Zlatna Linija DOO. Cilj: poništaj rešenja o otkazu, "
  + "vraćanje na rad i isplata neisplaćene zarade. Oznaka ZLATNI-7731.";
zapisi("G", "predlog iz opisa stigao (model simuliran)", await predlogIzOpisa(OPIS));
await p.fill("#npo-naziv", "Zlatić protiv Zlatna Linija — otkaz");
await klijentICoi("Milica", "Zlatić");
zapisi("G", "provera sukoba izvršena; čisto → otvaranje dozvoljeno", await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000), await tekstEl("npo-coi-naslov"));
await p.click("#npo-otvori");
zapisi("G", "predmet otvoren → prelaz na predmet", await cekaj(() => /#\/predmeti\/[^/]+$/.test(location.hash) && !/nov$/.test(location.hash)));
const PID = decodeURIComponent((await p.evaluate(() => location.hash)).split("/")[2]);
let z = await zlatni();
const predmetA = z.predmeti.find(x => x.id === PID);
zapisi("G", "tačno 1 predmet, vlasnik A, opis spora i cilj sačuvani", z.predmeti.length === 1 && predmetA && predmetA.user_id === "uid-A" && predmetA.opis_sacuvan, JSON.stringify(z.predmeti));
const KID = z.klijenti.length === 1 ? z.klijenti[0].id : null;
zapisi("G", "tačno 1 klijent (A) i veza klijent–predmet", z.klijenti.length === 1 && z.klijenti[0].user_id === "uid-A"
  && z.veze.length === 1 && z.veze[0].predmet_id === PID && z.veze[0].klijent_id === KID, JSON.stringify([z.klijenti, z.veze]));
zapisi("G", "rok iz predloga NIJE upisan bez potvrde", z.rokovi.length === 0, JSON.stringify(z.rokovi));

await p.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID) + "/prijem");
await cekaj(() => { const f = document.getElementById("pd-forma"); return f && !f.closest("[hidden]"); });
await p.setInputFiles("#pd-fajlovi", [D.pdf, D.sken, D.foto, D.docx]);
await p.click("#pd-otpremi");
zapisi("G", "4 dokumenta primljena u jednom otpremanju", await cekaj(() => document.querySelectorAll("#pd-poslovi li.intake").length === 4), await tekstEl("pd-poruka"));
await obradi();
const ispravka = { polje: "defendant", vrednost: "Zlatna Linija DOO Beograd (ispravljeno)" };
const kraj = {};
kraj.pdf = await doKraja("pd", ime(D.pdf), { ispravi: ispravka });
zapisi("G", "advokat je ispravio izdvojen podatak (tuženi) pre prikačivanja", ispravka.uradjeno === true, kraj.pdf.slice(0, 300));
for (const k of ["sken", "foto", "docx"]) kraj[k] = await doKraja("pd", ime(D[k]));
z = await zlatni();
const ocr = z.prijem_dokumenti.filter(x => x.ocr_used === true).length;
const posloviA = z.poslovi.filter(j => j.uploaded_by === "uid-A");
const dokPred = z.dokumenti.filter(x => x.predmet_id === PID);
const bezTeksta = dokPred.filter(x => !x.ima_tekst).map(x => x.naziv_fajla);
const ocrDostupan = ocr > 0;
console.log(`OCR: ${ocrDostupan ? "stvaran OCR je pročitao " + ocr + " dokument(a)" : "Tesseract nije dostupan u ovom okruženju — skenirani PDF i fotografija bez teksta"}`);
const OCEKIVANO = ocrDostupan ? 4 : 2;
zapisi("G", ocrDostupan ? "sva 4 dokumenta su prikačena ISTOM predmetu (1 predmet, 4 dokumenta)" : "bez OCR-a: 2 čitljiva dokumenta prikačena ISTOM predmetu, nijedan drugi predmet",
  z.predmeti.length === 1 && dokPred.length === OCEKIVANO && z.dokumenti.length === OCEKIVANO && new Set(dokPred.map(x => x.posao)).size === OCEKIVANO,
  JSON.stringify(z.dokumenti.map(x => [x.naziv_fajla, x.predmet_id === PID])));
zapisi("G", "svaki dokument nosi poreklo (posao prijema A) i vlasnika A", dokPred.every(x => x.user_id === "uid-A" && posloviA.some(j => j.id === x.posao && j.predmet_id === PID && j.prikacen)),
  JSON.stringify(z.poslovi));
zapisi("G", "digitalni PDF i DOCX imaju izdvojen tekst", dokPred.filter(x => /01 Tuzba|04 Ugovor/.test(x.naziv_fajla)).every(x => x.ima_tekst));
if (ocrDostupan) zapisi("G", "OCR: sken i fotografija pročitani stvarnim OCR-om", bezTeksta.length === 0, JSON.stringify(bezTeksta));
else {
  zapisi("G", "bez OCR-a: sken i fotografija NISU prikačeni i nisu dobili izmišljen tekst", !dokPred.some(x => x.naziv_fajla === ime(D.sken) || x.naziv_fajla === ime(D.foto))
    && bezTeksta.length === 0, JSON.stringify(dokPred.map(x => x.naziv_fajla)));
  zapisi("G", "bez OCR-a: razlog je tačno rečen, bez lažnog „ponovite prikačivanje“", [kraj.sken, kraj.foto].every(t => /nije izdvojen tekst/.test(t) && /neće pomoći/.test(t)
    && !/Ponovi prikačivanje/.test(t) && !/Ponovite prikačivanje/.test(t)), JSON.stringify([kraj.sken.slice(-300), kraj.foto.slice(-300)]));
  zapisi("G", "bez OCR-a: nigde ne piše „tekst pročitan OCR-om“", ![kraj.sken, kraj.foto].some(t => /pročitan OCR-om/.test(t)) && ocr === 0, JSON.stringify(z.prijem_dokumenti));
}
const isp = z.ispravke.find(x => x.tip === "defendant");
const posaoPdf = posloviA.find(j => j.ime === ime(D.pdf));
zapisi("G", "ispravka je vezana za tačan dokument; original nije obrisan", !!isp && !!posaoPdf && isp.posao === posaoPdf.id
  && isp.ispravka === ispravka.vrednost && isp.original !== isp.ispravka, JSON.stringify(z.ispravke));
zapisi("G", "nijedan rok iz dokumenata nije potvrđen bez advokata", z.rokovi.every(r => r.stanje !== "CONFIRMED" && r.stanje !== "potvrdjen"), JSON.stringify(z.rokovi));

// reload: predmet, klijent, dokumenti i njihova stanja se ponovo učitavaju
await p.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID)); await p.reload();
zapisi("G", "posle reload-a: naziv predmeta", await cekaj(() => /Zlatić protiv Zlatna Linija/.test(document.getElementById("predmet-naslov").textContent)));
zapisi("G", "posle reload-a: klijent je povezan", await cekaj(() => /Zlatić/.test(document.getElementById("predmet-klijenti").textContent), null, 10000), await tekstEl("predmet-klijenti"));
zapisi("G", `posle reload-a: ${OCEKIVANO} dokumenta u predmetu`, await cekaj((n) => document.getElementById("dok-broj").textContent === String(n), OCEKIVANO, 10000), await tekstEl("dok-broj"));
await cekaj(() => { const b = document.getElementById("izmena-otvori"); return b && !b.hidden; }, null, 10000);
await p.click("#izmena-otvori");
zapisi("G", "posle reload-a: opis spora sa ciljem je dostupan za nastavak rada", await cekaj(() => /ZLATNI-7731/.test((document.getElementById("izm-opis") || {}).value || "")
  && /Cilj: poništaj rešenja o otkazu/.test(document.getElementById("izm-opis").value), null, 10000));
// ponovo otpremljen isti sadržaj posle reload-a → postojeći posao, sa sačuvanom ispravkom
await p.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID) + "/prijem");
await cekaj(() => { const f = document.getElementById("pd-forma"); return f && !f.closest("[hidden]"); });
const posloviPre = (await zlatni()).poslovi.length;
await p.setInputFiles("#pd-fajlovi", [D.pdf]);
await p.click("#pd-otpremi");
await cekaj(() => document.querySelectorAll("#pd-poslovi li.intake").length === 1);
await cekaj(() => /Prikačeno ovom predmetu/.test(document.getElementById("pd-poslovi").innerText), null, 15000);
const ponovo = await tekstEl("pd-poslovi");
z = await zlatni();
zapisi("E", "ponovljen isti sadržaj: bez novog posla i bez novog dokumenta", z.poslovi.length === posloviPre && z.dokumenti.length === OCEKIVANO
  && /već bio poslat/.test(ponovo) && /Prikačeno ovom predmetu/.test(ponovo), ponovo.slice(0, 300));
zapisi("E", "ponovljen sadržaj prikazuje sačuvanu ispravku", /ispravljeno/.test(ponovo) && ponovo.includes(ispravka.vrednost), ponovo.slice(0, 400));

// ══ E) GRANIČNI SLUČAJEVI ═════════════════════════════════════════════════════════════════════════════════════════
// E1 nepodržan i lažan dokument (u istom predmetu)
await p.setInputFiles("#pd-fajlovi", [D.doc]);
await p.click("#pd-otpremi");
zapisi("E", "nepodržan .doc: odbijen pre slanja, sa razlogom", await cekaj(() => /Nije poslato: 05 Stari ugovor\.doc/.test(document.getElementById("pd-poruka").textContent), null, 5000), await tekstEl("pd-poruka"));
const preLaznog = (await zlatni()).poslovi.length;
await p.setInputFiles("#pd-fajlovi", [D.lazni]);
await p.click("#pd-otpremi");
await cekaj(() => /06 Lazni ugovor\.docx/.test(document.getElementById("pd-poruka").textContent), null, 10000);
z = await zlatni();
const tLazni = await tekstEl("pd-poruka");
zapisi("E", "lažan DOCX (tekst pod .docx): odbijen po SADRŽAJU pri otpremanju, bez posla i bez čuvanja",
  z.poslovi.length === preLaznog && !z.poslovi.some(j => j.ime === ime(D.lazni)) && /nije Word \(DOCX\) dokument/.test(tLazni), tLazni.slice(0, 300));

// E2 dupli klik na prikačivanje: novi dokument, dva klika → jedan dokument
await p.setInputFiles("#pd-fajlovi", [D.pdf2]);
await p.click("#pd-otpremi");
await cekaj(() => [...document.querySelectorAll("#pd-poslovi li.intake")].some(x => /07 Opomena/.test(x.innerText)));
await obradi();
for (let i = 0; i < 3; i++) {
  const t = await posao("pd", ime(D.pdf2));
  if (/Prikači ovom predmetu/.test(t)) break;
  if (/Potvrđujem pregled/.test(t)) { await klikPosao("pd", ime(D.pdf2), "Potvrđujem pregled"); await pauza(400); await obradi(); }
  await cekaj(([i]) => [...document.querySelectorAll("#pd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i && /Prikači ovom predmetu|Potvrđujem pregled/.test(x.innerText)), [ime(D.pdf2)], 10000);
}
await p.evaluate((i) => {
  const li = [...document.querySelectorAll("#pd-poslovi li.intake")].find(x => (x.querySelector(".intake__name") || {}).textContent === i);
  const b = li && [...li.querySelectorAll("button")].find(x => x.textContent === "Prikači ovom predmetu");
  if (b) { b.click(); b.click(); b.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })); }
}, ime(D.pdf2));
await cekaj(([i]) => [...document.querySelectorAll("#pd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i && /Prikačeno ovom predmetu/.test(x.innerText)), [ime(D.pdf2)], 20000);
z = await zlatni();
zapisi("E", "dupli klik na prikačivanje: tačno jedan novi dokument", z.dokumenti.filter(x => x.naziv_fajla === ime(D.pdf2)).length === 1 && z.predmeti.length === 1,
  JSON.stringify(z.dokumenti.map(x => x.naziv_fajla)));

// E3 nepoznat ishod pri otvaranju predmeta IZ OPISA: server upiše, veza pukne pre odgovora
await naNovPredmet();
await predlogIzOpisa("Klijent Petar Probni traži naknadu štete od Probna Gradnja DOO zbog oštećenja stana. Oznaka NEPOZNAT-01.");
await p.fill("#npo-naziv", "Probni protiv Probna Gradnja — šteta");
await klijentICoi("Petar", "Probni");
await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000);
await p.route("**/api/intake/kreiraj", async (r) => { await r.fetch(); await r.abort("connectionreset"); });
await p.click("#npo-otvori");
await cekaj(() => /nepoznat|Ishod|otvoren/i.test(document.getElementById("npo-poruka").textContent) && document.getElementById("npo-poruka").dataset.stanje !== "ucitavanje", null, 15000);
await p.unroute("**/api/intake/kreiraj");
const porukaE3 = await tekstEl("npo-poruka");
await pauza(6000);                                                          // posle serverskog prozora od 5 s za dupli naziv
if (!(await p.isDisabled("#npo-otvori")) && /#\/predmeti\/nov/.test(await p.evaluate(() => location.hash))) {
  await p.click("#npo-otvori");
  await cekaj(() => document.getElementById("npo-poruka").dataset.stanje !== "ucitavanje", null, 10000);
}
z = await zlatni();
const probni = z.predmeti.filter(x => x.naziv === "Probni protiv Probna Gradnja — šteta");
zapisi("E", "nepoznat ishod (iz opisa): ponovni pokušaj ne pravi drugi predmet", probni.length === 1, `${probni.length} predmeta; poruka: ${porukaE3}`);
zapisi("E", "nepoznat ishod (iz opisa): advokat dobija postojeći predmet, ne lažnu grešku",
  probni.length === 1 && (await cekaj((id) => location.hash.includes(encodeURIComponent(id)), probni[0] && probni[0].id, 5000)), porukaE3);

// E4 nepoznat ishod pri otvaranju predmeta IZ DOKUMENTA: predmet nastane, odgovor se izgubi; drugi dokument ide ISTOM predmetu
await naNovPredmet();
await p.click("#nov-rezim-dokument");
await p.selectOption("#nd-klijent-strana", "plaintiff");
await p.setInputFiles("#nd-fajlovi", [D.pdf3]);
await p.click("#nd-otpremi");
await cekaj(() => document.querySelectorAll("#nd-poslovi li.intake").length === 1);
await obradi();
for (let i = 0; i < 3; i++) {
  await cekaj(([i]) => [...document.querySelectorAll("#nd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i && /Otvori predmet iz ovog dokumenta|Potvrđujem pregled/.test(x.innerText)), [ime(D.pdf3)], 10000);
  const t = await posao("nd", ime(D.pdf3));
  if (/Otvori predmet iz ovog dokumenta/.test(t)) break;
  if (/Potvrđujem pregled/.test(t)) { await klikPosao("nd", ime(D.pdf3), "Potvrđujem pregled"); await pauza(400); await obradi(); }
}
const predPre = (await zlatni()).predmeti.length;
await p.route("**/api/smart-intake/jobs/*/finalize", async (r) => { await r.fetch(); await r.abort("connectionreset"); });
await klikPosao("nd", ime(D.pdf3), "Otvori predmet iz ovog dokumenta");
await pauza(1500);
await p.unroute("**/api/smart-intake/jobs/*/finalize");
await cekaj(([i]) => [...document.querySelectorAll("#nd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i && !/Otvaranje predmeta iz dokumenta/.test(x.innerText)
  && /prikačen|Prikačeno|otvoren/i.test(x.innerText)), [ime(D.pdf3)], 15000);
const tE4 = await posao("nd", ime(D.pdf3));
z = await zlatni();
zapisi("E", "nepoznat ishod (iz dokumenta): server je otvorio tačno 1 predmet", z.predmeti.length === predPre + 1, `${z.predmeti.length - predPre}`);
zapisi("E", "nepoznat ishod (iz dokumenta): UI prepoznaje predmet kao OVAJ, ne „drugi vaš predmet“",
  !/drugom vašem predmetu/.test(tE4) && !(await p.evaluate(() => document.getElementById("nd-otvoren").hidden)), tE4.slice(0, 300));
// drugi, NOV dokument iste sesije mora da ide u ISTI predmet (ranije: „Otvori predmet iz ovog dokumenta“ → drugi predmet)
await p.setInputFiles("#nd-fajlovi", [D.pdf4]);
await p.click("#nd-otpremi");
await cekaj(() => document.querySelectorAll("#nd-poslovi li.intake").length === 2);
await obradi();
const tE4b = await doKraja("nd", ime(D.pdf4));
z = await zlatni();
const noviPred = z.predmeti.find(x => z.dokumenti.some(d => d.predmet_id === x.id && d.naziv_fajla === ime(D.pdf3)));
zapisi("E", "nepoznat ishod (iz dokumenta): drugi dokument je prikačen ISTOM predmetu, bez trećeg predmeta",
  z.predmeti.length === predPre + 1 && !!noviPred && z.dokumenti.some(d => d.predmet_id === noviPred.id && d.naziv_fajla === ime(D.pdf4))
  && /Prikačeno ovom predmetu/.test(tE4b), JSON.stringify([z.predmeti.length - predPre, tE4b.slice(-200)]));
// dokument već prikačen ZLATNOM predmetu se ne kopira u novi
await p.setInputFiles("#nd-fajlovi", [D.docx]);
await p.click("#nd-otpremi");
await cekaj(() => document.querySelectorAll("#nd-poslovi li.intake").length === 3);
await cekaj(() => /drugom vašem predmetu|Prikačeno ovom predmetu/.test(document.querySelectorAll("#nd-poslovi li.intake")[2].innerText), null, 15000);
const tE4c = await p.evaluate(() => document.querySelectorAll("#nd-poslovi li.intake")[2].innerText);
z = await zlatni();
zapisi("E", "dokument već prikačen drugom predmetu se ne kopira u novi",
  /drugom vašem predmetu/.test(tE4c) && z.dokumenti.filter(d => d.naziv_fajla === ime(D.docx)).length === 1 && z.predmeti.length === predPre + 1, tE4c.slice(0, 300));

// E4d nepoznat ishod (iz dokumenta) kad zahtev NIJE stigao do servera: drugi dokument ne sme da otvori predmet
await naNovPredmet();
await p.click("#nov-rezim-dokument");
await p.selectOption("#nd-klijent-strana", "plaintiff");
await p.setInputFiles("#nd-fajlovi", [D.pdf5, D.pdf6]);
await p.click("#nd-otpremi");
await cekaj(() => document.querySelectorAll("#nd-poslovi li.intake").length === 2);
await obradi();
for (const f of [D.pdf5, D.pdf6]) {
  for (let i = 0; i < 3; i++) {
    await cekaj(([i]) => [...document.querySelectorAll("#nd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i && /Otvori predmet iz ovog dokumenta|Potvrđujem pregled/.test(x.innerText)), [ime(f)], 10000);
    const t = await posao("nd", ime(f));
    if (/Otvori predmet iz ovog dokumenta/.test(t)) break;
    if (/Potvrđujem pregled/.test(t)) { await klikPosao("nd", ime(f), "Potvrđujem pregled"); await pauza(400); await obradi(); }
  }
}
const predPreD = (await zlatni()).predmeti.length;
await p.route("**/api/smart-intake/jobs/*/finalize", (r) => r.abort("connectionreset"));       // nikad ne stiže do servera
await klikPosao("nd", ime(D.pdf5), "Otvori predmet iz ovog dokumenta");
await cekaj(([i]) => [...document.querySelectorAll("#nd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i
  && /još nije otvoren|Ishod nije poznat/.test(x.innerText)), [ime(D.pdf5)], 20000);
await p.unroute("**/api/smart-intake/jobs/*/finalize");
await klikPosao("nd", ime(D.pdf6), "Otvori predmet iz ovog dokumenta");
await pauza(1500);
const tDrugi = await posao("nd", ime(D.pdf6));
zapisi("E", "nepoznat ishod (iz dokumenta, zahtev nije stigao): drugi dokument NE otvara predmet i to kaže",
  (await zlatni()).predmeti.length === predPreD && /upravo otvara iz drugog dokumenta/.test(tDrugi), tDrugi.slice(-250));
await cekaj(([i]) => [...document.querySelectorAll("#nd-poslovi li.intake")].some(x => (x.querySelector(".intake__name") || {}).textContent === i
  && [...x.querySelectorAll("button")].some(b => b.textContent === "Otvori predmet iz ovog dokumenta" && !b.disabled)), [ime(D.pdf5)], 10000);
await klikPosao("nd", ime(D.pdf5), "Otvori predmet iz ovog dokumenta");
zapisi("E", "isti dokument ponavlja otvaranje → tačno 1 predmet", await cekaj(() => !document.getElementById("nd-otvoren").hidden, null, 20000)
  && (await zlatni()).predmeti.length === predPreD + 1, `${(await zlatni()).predmeti.length - predPreD}`);
const tD2 = await doKraja("nd", ime(D.pdf6));
z = await zlatni();
const predD = z.predmeti.find(x => z.dokumenti.some(d => d.predmet_id === x.id && d.naziv_fajla === ime(D.pdf5)));
zapisi("E", "drugi dokument je zatim prikačen ISTOM predmetu", !!predD && z.dokumenti.some(d => d.predmet_id === predD.id && d.naziv_fajla === ime(D.pdf6))
  && z.predmeti.length === predPreD + 1 && /Prikačeno ovom predmetu/.test(tD2), tD2.slice(-200));

// E3b nepoznat ishod (iz opisa) kad zahtev NIJE stigao do servera: proverom liste → „nije otvoren“, ponovni pokušaj → 1 predmet
await naNovPredmet();
await predlogIzOpisa("Klijent Ana Treca traži raskid ugovora o zakupu sa Treca Nekretnine DOO. Oznaka NEPOZNAT-02.");
await p.fill("#npo-naziv", "Treća protiv Treća Nekretnine — zakup");
await klijentICoi("Ana", "Treća");
await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000);
await p.route("**/api/intake/kreiraj", (r) => r.abort("connectionreset"));
await p.click("#npo-otvori");
const nijeOtvoren = await cekaj(() => /NIJE otvoren \(provereno/.test(document.getElementById("npo-poruka").textContent), null, 15000);
await p.unroute("**/api/intake/kreiraj");
zapisi("E", "nepoznat ishod (iz opisa, zahtev nije stigao): provera liste kaže „nije otvoren“, ponovni pokušaj dozvoljen",
  nijeOtvoren && !(await p.isDisabled("#npo-otvori")), await tekstEl("npo-poruka"));
await p.click("#npo-otvori");
await cekaj(() => /#\/predmeti\/[^/]+$/.test(location.hash) && !/nov$/.test(location.hash), null, 15000);
z = await zlatni();
zapisi("E", "ponovni pokušaj posle „nije otvoren“ → tačno 1 predmet", z.predmeti.filter(x => x.naziv === "Treća protiv Treća Nekretnine — zakup").length === 1);

// E3c nepoznat ishod (iz opisa) kad se lista ne može pročitati: otvaranje pod tim nazivom zaključano
await naNovPredmet();
await predlogIzOpisa("Klijent Ivan Cetvrti traži naknadu štete od Cetvrta Gradnja DOO zbog kašnjenja radova. Oznaka NEPOZNAT-03.");
const NAZIV3 = "Četvrti protiv Četvrta Gradnja — kašnjenje";
await p.fill("#npo-naziv", NAZIV3);
await klijentICoi("Ivan", "Četvrti");
await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000);
ubacen503 = true;
await p.route("**/api/predmeti?*", (r) => r.fulfill({ status: 503, contentType: "application/json", body: "{}" }));
await p.route("**/api/intake/kreiraj", async (r) => { await r.fetch(); await r.abort("connectionreset"); });
await p.click("#npo-otvori");
const zakljucano = await cekaj(() => /zaključano/.test(document.getElementById("npo-poruka").textContent), null, 15000);
await p.unroute("**/api/intake/kreiraj"); await p.unroute("**/api/predmeti?*"); ubacen503 = false;
await p.fill("#npo-naziv", NAZIV3 + "x"); await p.fill("#npo-naziv", NAZIV3);
zapisi("E", "lista nečitljiva posle nepoznatog ishoda: otvaranje pod istim nazivom ostaje zaključano (i posle izmene pa vraćanja naziva)",
  zakljucano && await p.isDisabled("#npo-otvori"), await tekstEl("npo-poruka"));
z = await zlatni();
zapisi("E", "zaključano: tačno 1 predmet tog naziva", z.predmeti.filter(x => x.naziv === NAZIV3).length === 1);

// E5 sukob interesa: ime klijenta je stranka u AKTIVNOM predmetu (tuženi iz zlatnog predmeta)
await naNovPredmet();
await predlogIzOpisa("Zlatna Linija DOO želi da je zastupamo protiv bivše zaposlene u radnom sporu. Oznaka SUKOB-01.");
await klijentICoi("Zlatna Linija", "DOO");
const coiT = await tekstEl("npo-coi-naslov");
zapisi("E", "sukob interesa: otvaranje zaustavljeno, bez kategorične tvrdnje", await p.isDisabled("#npo-otvori") && /sukob/i.test(coiT) && !/ne možete zastupati/i.test(coiT), coiT);

// E6 korisnik B: nema pristupa ničemu od A (stvarne rute, token B)
z = await zlatni();
const jA = z.poslovi.find(j => j.ime === ime(D.pdf));
const rB = {
  predmet: (await kaoB(`/api/predmeti/${encodeURIComponent(PID)}`)).s,
  dokument: (await kaoB(`/api/predmeti/${encodeURIComponent(PID)}/dokumenti/${encodeURIComponent(dokPred[0].id)}/preview`)).s,
  posao: (await kaoB(`/api/smart-intake/jobs/${jA.id}`)).s,
  ispravka: (await kaoB(`/api/smart-intake/entities/${isp.entity_id}/correct`, "POST", JSON.stringify({ corrected_value: "B menja" }))).s,
  prikaci: (await kaoB(`/api/smart-intake/jobs/${jA.id}/finalize`, "POST", JSON.stringify({ predmet_id: PID }))).s,
  kreiraj: (await kaoB(`/api/intake/kreiraj`, "POST", JSON.stringify({ klijent_id: KID, naziv: "B uzima klijenta A" }))).s,
};
const lista = JSON.parse((await kaoB(`/api/predmeti?view=summary`)).b || "{}");
z = await zlatni();
zapisi("E", "B: tuđ predmet, dokumenti, posao, ispravka, prikačivanje i klijent A su nedostupni", Object.values(rB).every(s => s === 404 || s === 403)
  && (lista.predmeti || []).length === 0, JSON.stringify(rB));
zapisi("E", "B nije ništa promenio kod A", z.ispravke.find(x => x.entity_id === isp.entity_id).ispravka === ispravka.vrednost
  && !z.predmeti.some(x => x.user_id === "uid-B") && z.veze.every(v => z.predmeti.find(x => x.id === v.predmet_id).user_id === "uid-A"), JSON.stringify(z.veze));
const { ctx: ctxB, p: pB } = await kontekst("tok-B", "uid-B");
await pB.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID));
zapisi("E", "B u pregledaču: predmet A se ne prikazuje", await pB.waitForFunction(() => !document.getElementById("predmet-stanje").hidden, null, { timeout: 10000 }).then(() => true, () => false)
  && !/Zlatić/.test(await pB.evaluate(() => document.body.innerText)));
await ctxB.close();

// E7 promena korisnika tokom obrade: A otpremi, pa se sesija promeni u B pre obrade → UI briše poslove A
await p.goto(BASE + "/app#/predmeti/" + encodeURIComponent(PID) + "/prijem");
await cekaj(() => { const f = document.getElementById("pd-forma"); return f && !f.closest("[hidden]"); });
await p.setInputFiles("#pd-fajlovi", [D.pdf3]);
await p.click("#pd-otpremi");
await cekaj(() => document.querySelectorAll("#pd-poslovi li.intake").length === 1);
await p.evaluate(([k]) => {
  localStorage.setItem(k, JSON.stringify({ access_token: "tok-B", refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "uid-B" } }));
  window.dispatchEvent(new StorageEvent("storage", { key: k }));
}, [KLJUC]);
await obradi();
zapisi("E", "promena korisnika tokom obrade: poslovi A nestaju iz prikaza", await cekaj(() => document.querySelectorAll("#pd-poslovi li.intake").length === 0
  && !/Zlatić/.test(document.body.innerText), null, 10000));
z = await zlatni();
zapisi("E", "promena korisnika: ništa nije prikačeno bez odluke advokata", z.dokumenti.filter(x => x.naziv_fajla === ime(D.pdf3)).length <= 1
  && z.dokumenti.every(x => x.user_id === "uid-A"), JSON.stringify(z.dokumenti.map(x => x.naziv_fajla)));

const kraj2 = await stanje();
zapisi("bezbednost", "0 spoljnih veza (pregledač i server)", spoljni.length === 0 && kraj2.spoljni_pokusaji === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 2), api500.slice(0, 3)]));
zapisi("modeli", "simulirani su samo modeli (ekstrakcija iz opisa)", kraj2.pozivi_modela.every(x => ["ekstrakcija"].includes(x)), JSON.stringify(kraj2.pozivi_modela));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} ${pada ? "FAIL" : "PASS"}`);
process.exit(pada ? 1 : 0);
