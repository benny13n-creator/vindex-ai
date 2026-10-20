// Vindex — Website V2: snimci STVARNIH V2 ekrana za javni sajt (site/snimci/).
// Pokretanje: `node tests/diagnostics/site-snimci.mjs` iz frontend-v2-ng/ (alat, nije test).
//
// Pravila (Website V2 mandat, Phase 6):
//   • ekran je pravi V2 (frontend-v2-ng/index.html, primarni prikaz kao /app u produkciji);
//   • podaci su IZMIŠLJENI (isti fiktivni predmeti kao src/demo-data.js), služi ih lokalni
//     fixture na 127.0.0.1; ništa ne ide u produkciju, Supabase ni spoljni host;
//   • nema AI odgovora, citata, presuda ni OCR rezultata — snimaju se samo ekrani čiji sadržaj
//     unosi advokat ili računa program (registar, Danas, rad na predmetu, naplata, dokumenti
//     bez izmišljenog izdvojenog teksta, prazno iskustvo kancelarije);
//   • sajt svaki snimak označava kao demonstracioni prikaz.
// Izlaz: PNG u ../site/snimci-izvor/ (van git-a) → scripts/gradi_sajt.py ih ne čita; WebP pravi
// `python scripts/snimci_webp.py`.

import { chromium } from "playwright";
import { readFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { pokreniFixture, json } from "../fixtures/api-fixture.mjs";
import { predmetiRuta, predmetDetaljRuta, kombinuj } from "../fixtures/predmeti-api.mjs";
import { rokoviRuta, naplataRuta } from "../fixtures/pisanje-api.mjs";

const KOREN = fileURLToPath(new URL("../../", import.meta.url));
const IZLAZ = fileURLToPath(new URL("../../../site/snimci-izvor/", import.meta.url));
await mkdir(IZLAZ, { recursive: true });
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TOKEN = "vx-sajt-demo-token";
const D = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const TS = (n) => new Date(Date.now() + n * 86400000).toISOString();

// Fiktivni predmeti (src/demo-data.js STANDARD). `sud` i `klijent` nisu kolone predmeta.
const IZVOR = [
  ["Naknada štete zbog povrede na radu", "radno", "P1 412/2026", "M. Petrović", "Gradnja Sever d.o.o.", -1],
  ["Raskid ugovora o zakupu poslovnog prostora", "privredno", "P 512/2026", "Lumen Trade d.o.o.", "R. Kostić", -2],
  ["Poništaj rešenja o utvrđivanju poreza na imovinu", "upravno", "U 8823/2025", "D. Jovanović", "Grad Beograd — Uprava javnih prihoda", -4],
  ["Izvršenje na osnovu verodostojne isprave", "izvrsno", "Iiv 2210/2026", "Agro Banat Promet d.o.o.", "Z. Popović", -6],
  ["Utvrđenje prava svojine na stanu", "parnicni", "P 1423/2025", "Lj. Đorđević", "B. Lukić", -8],
  ["Ostavinski postupak iza pok. R. Stojanovića", "vanparnicni", "O 977/2026", "N. Stojanović", "", -11],
  ["Razvod braka i vršenje roditeljskog prava", "porodicno", "P2 245/2026", "J. Marković", "S. Marković", -13],
  ["Poništaj odluke o otkazu ugovora o radu", "radno", "P1 98/2026", "Ž. Šećerović", "Metal Kop d.o.o.", -16],
];
const PREDMETI = IZVOR.map(([naziv, tip, broj, tuzilac, tuzeni, dana], i) => ({
  id: `p-${i + 1}`, user_id: "k-demo", naziv, tip, status: "aktivan", broj_predmeta: broj,
  tuzilac, tuzeni, opis: "", rizik: null, vrednost_spora: i === 0 ? 840000 : null,
  created_at: TS(dana - 40), updated_at: TS(dana), brisanje_zapoceto: null, assimilation_status: null, case_dna: null,
}));
const P1 = PREDMETI[0].id;
const KOR = {
  [TOKEN]: {
    id: "k-demo", predmeti: PREDMETI,
    beleske: { [P1]: [{ id: "b1", predmet_id: P1, sadrzaj: "Klijent dostavio medicinsku dokumentaciju; tražiti nalaz veštaka medicinske struke.", created_at: TS(-3) }] },
    hronologija: { [P1]: [
      { id: "h1", predmet_id: P1, datum: D(-120), dogadjaj: "Povreda na radu na gradilištu", izvor: "covek", created_at: TS(-30) },
      { id: "h2", predmet_id: P1, datum: D(-20), dogadjaj: "Podneta tužba", izvor: "covek", created_at: TS(-20) },
    ] },
    rokovi: [
      { id: "r1", predmet_id: P1, dogadjaj: "Rok za dostavljanje predloga za veštačenje", datum_iso: D(6), vrsta: "rok", izvor: "covek", odluka: "CONFIRMED" },
      { id: "r2", predmet_id: PREDMETI[1].id, dogadjaj: "Rok za odgovor na tužbu", datum_iso: D(9), vrsta: "rok", izvor: "ai" },
      { id: "r3", predmet_id: PREDMETI[4].id, dogadjaj: "Rok za uplatu predujma za veštačenje", datum_iso: D(12), vrsta: "rok", izvor: "covek", odluka: "CONFIRMED" },
    ],
    dogadjaji: [
      { tip: "rociste", datum: D(2), vreme: "10:30", predmet_id: PREDMETI[4].id, predmet_naziv: PREDMETI[4].naziv, detalji: { id: "ro1", sud: "Osnovni sud u Novom Sadu", sudnica: "14", status: "zakazano" } },
      { tip: "rociste", datum: D(15), vreme: "09:00", predmet_id: P1, predmet_naziv: PREDMETI[0].naziv, detalji: { id: "ro2", sud: "Osnovni sud u Novom Sadu", sudnica: "3", status: "zakazano" } },
    ],
    stavke: [],
  },
};
const DOKUMENTI = { [P1]: [
  { id: "d1", predmet_id: P1, user_id: "k-demo", naziv_fajla: "Tužba.docx", status: "indeksirano", velicina_kb: 42, redni_broj: 1, tip_dokaza: "podnesak", created_at: TS(-20), tekst_sadrzaj: "" },
  { id: "d2", predmet_id: P1, user_id: "k-demo", naziv_fajla: "Otpusna lista.pdf", status: "indeksirano", velicina_kb: 318, redni_broj: 2, tip_dokaza: "medicinska_dokumentacija", created_at: TS(-12), tekst_sadrzaj: "" },
  { id: "d3", predmet_id: P1, user_id: "k-demo", naziv_fajla: "Punomoćje.pdf", status: "indeksirano", velicina_kb: 96, redni_broj: 3, tip_dokaza: "punomocje", created_at: TS(-9), tekst_sadrzaj: "" },
] };

/* Rute koje fixture paketi ne pokrivaju: tačni ugovori iz komentara modula (src/*.js), prazni ili
 * deterministički odgovori. Nepoznata ruta se loguje i snimak se ne pravi (vidi kraj). */
const nepokriveno = new Set();
const dodatno = async (req, url, res) => {
  const p = url.pathname;
  if (p === "/api/workspace") {
    const s = (naslov, rok, prioritet, i, vrsta = "zadatak") => ({ vrsta, id: "w" + i, predmet_id: PREDMETI[i].id, predmet_naziv: PREDMETI[i].naziv, naslov, tip: "zadatak", prioritet, rok });
    json(res, 200, { danas: [s("Pripremiti predlog za veštačenje", D(0), "visok", 0)], kriticno: [], predstojece: [s("Proveriti uplatu predujma", D(5), "srednji", 4), s("Dopis klijentu o toku postupka", D(7), "nizak", 1)],
      za_pregled: [], na_cekanju: [], zavrseno_nedavno: [], ukupno_aktivnih: 3, degradirani_izvori: [], provera_potpuna: true });
    return true;
  }
  if (p === "/api/autonomy/work-items") { json(res, 404, { detail: "Not Found" }); return true; }   // produkcija: tabela ne postoji (136)
  if (/^\/api\/predmeti\/[^/]+\/genome-v2\/promene$/.test(p)) { json(res, 200, { promene: [], verzija: null, prethodna: null }); return true; }
  if (/^\/api\/case-actions\/predmeti\/[^/]+$/.test(p)) { json(res, 200, { akcije: [] }); return true; }
  if (p === "/api/rocista") {
    const id = url.searchParams.get("predmet_id");
    const r = KOR[TOKEN].dogadjaji.filter(d => d.predmet_id === id).map(d => ({ id: d.detalji.id, predmet_id: id, sud: d.detalji.sud, datum: d.datum, vreme: d.vreme, sudnica: d.detalji.sudnica, broj_predmeta_suda: PREDMETI.find(x => x.id === id).broj_predmeta, napomena: "" }));
    json(res, 200, { rocista: r, ukupno: r.length }); return true;
  }
  if (/^\/api\/zadaci\/predmet\//.test(p)) {
    json(res, 200, { zadaci: [{ id: "z1", naziv: "Pripremiti predlog za veštačenje", rok_datum: D(0), prioritet: "visok", status: "otvoren", updated_at: TS(-1) },
      { id: "z2", naziv: "Pribaviti platne listiće za poslednjih 12 meseci", rok_datum: D(4), prioritet: "srednji", status: "otvoren", updated_at: TS(-2) }] });
    return true;
  }
  if (p === "/klijenti") { json(res, 200, { klijenti: [], ukupno: 0 }); return true; }
  if (p === "/api/law-brain/znanje") {
    const prazno = { state: "EMPTY", stavke: [] };
    json(res, 200, { iskustvo: { state: "EMPTY", grupe: [] }, verifikovani_radovi: prazno, potvrdjene_lekcije: { ...prazno, kandidata: 0 }, memorija_kancelarije: { state: "EMPTY", stavke: [], veze: [] }, napomena: null, data_quality: {} });
    return true;
  }
  nepokriveno.add(req.method + " " + p);
  return false;
};

const f = await pokreniFixture(kombinuj(rokoviRuta(KOR), naplataRuta(KOR), predmetiRuta(KOR), predmetDetaljRuta(KOR, DOKUMENTI), dodatno));
const indeks = await readFile(KOREN + "index.html");
const browser = await chromium.launch();

async function snimi(ime, hash, { w = 1440, h = 900, ceka, pre, isecak } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, reducedMotion: "reduce" });
  await ctx.route("**/*", r => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") return r.abort();
    if (u.pathname === "/app") return r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: indeks });
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => { localStorage.setItem(k, v); }, [KLJUC, JSON.stringify({ access_token: TOKEN, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "k-demo", email: "advokat@primer.rs" } })]);
  const p = await ctx.newPage();
  const greske = [];
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(`http://127.0.0.1:${f.port}/app${hash}`);
  await p.evaluate(() => document.fonts.ready);
  if (ceka) {
    try { await p.waitForFunction(ceka, null, { timeout: 15000 }); }
    catch (e) {
      console.log(`NIJE UČITANO ${ime}:`, (await p.evaluate(() => document.body.innerText)).slice(0, 900).split(/\s*\n\s*/).filter(Boolean).join(" ¶ "));
      console.log("zahtevi:", f.zahtevi.slice(-12).map(z => z.metod + " " + z.putanja).join(", "), greske.join(" | "));
      await ctx.close(); return false;
    }
  }
  if (pre) await pre(p);
  await p.waitForTimeout(400);
  const putanja = IZLAZ + ime + ".png";
  if (isecak) await p.locator(isecak).screenshot({ path: putanja }); else await p.screenshot({ path: putanja });
  console.log(`snimak ${ime} (${w}x${h})${greske.length ? " GREŠKE: " + greske.join(" | ") : ""}`);
  await ctx.close();
  return greske.length === 0;
}

const vidljiv = (sel) => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); return !!e && !e.closest('[hidden]') && e.getClientRects().length > 0; })()`;
let ok = true;
ok &= await snimi("registar", "", { ceka: () => document.querySelectorAll("#rows tr").length >= 8 });
ok &= await snimi("registar-mobilni", "", { w: 390, h: 844, ceka: () => document.querySelectorAll("#rows tr").length >= 8 });
ok &= await snimi("danas", "#/danas", { h: 1100, ceka: new Function("return " + vidljiv("#da-predlozi .review") + " && " + vidljiv("#da-kalendar .today__item")) });
ok &= await snimi("rad-predmeta", `#/predmeti/${P1}/rad`, { h: 1200, ceka: new Function("return " + vidljiv("#zd-lista li") + " || " + vidljiv("#roc-lista li")) });
ok &= await snimi("dokumenti", `#/predmeti/${P1}/dokumenti`, { ceka: new Function("return " + vidljiv("#tab-dokumenti[aria-current]") + " || document.querySelectorAll('.doc-list li, .docs li').length >= 3") });
ok &= await snimi("znanje", "#/znanje", { ceka: new Function("return " + vidljiv("#zn-naslov")) });
await browser.close();
await f.zatvori();
if (nepokriveno.size) console.log("NEPOKRIVENE RUTE:", [...nepokriveno].join(", "));
process.exit(ok ? 0 : 1);
