// Vindex V2 NG — VCR001 T02: čarobnjak za prijem kroz STVARAN V2 /app u Chromium-u nad PRAVIM api.app koji upisuje.
// Pokretanje: `node tests/live-prijem-carobnjak-e2e.mjs`. Server: tests/osb003_solo_server.py (stvarne rute, stvaran intake
// worker; simulirani su samo modeli — predlog iz opisa i klasifikacija —, embedding i prijava). Ništa van 127.0.0.1.
// Svaki korak se proverava u UI-ju I u bazi (GET /__osb003/stanje, samo brojevi): UI uspeh bez upisa = PAD.
//   A) problem prvo: opis → predlog → ispravka → nov klijent → provera sukoba → otvori → predmet + veza, rok NE upisan
//   B) dokument prvo: PDF → obrada → pregled → „Otvori predmet iz ovog dokumenta“ → drugi PDF prikačen ISTOM predmetu
//   C) provera sukoba: klijent čije ime je stranka u aktivnom predmetu → otvaranje zaustavljeno, bez kategorične tvrdnje
//   D) ponovno učitavanje: oba predmeta i njihovi dokumenti ostaju

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4523, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const dir = await mkdtemp(join(tmpdir(), "vx-carobnjak-"));
const PDF1 = join(dir, "Tuzba Petrovic.pdf"), PDF2 = join(dir, "Resenje o otkazu.pdf");
const gen = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
for put, redovi in ((r"${PDF1}", ["OSNOVNI SUD U BEOGRADU", "Broj predmeta: P 4321/2026", "Tuzilac: Marko Petrovic iz Beograda",
                                  "Tuzeni: Gradnja Invest DOO Beograd", "Tuzba radi ponistaja resenja o otkazu i isplate zarade."]),
                    (r"${PDF2}", ["GRADNJA INVEST DOO BEOGRAD", "Resenje o otkazu ugovora o radu", "Zaposleni: Marko Petrovic",
                                  "Resenje je uruceno zaposlenom 17.03.2025. godine.", "Razlog: tehnoloski visak."])):
    c = canvas.Canvas(put)
    for i, r in enumerate(redovi):
        c.drawString(60, 780 - i * 24, r)
    c.showPage(); c.save()`], { encoding: "utf-8" });
if (gen.status !== 0) { console.log(gen.stderr); process.exit(1); }

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const get = (p, opt = {}) => new Promise(r => { const q = http.request(BASE + p, { method: opt.method || "GET" }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); }); q.on("error", () => r({ s: 0, b: "" })); q.end(); });
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await get("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
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
const vidljiv = (id) => p.evaluate((i) => { const e = document.getElementById(i); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; }, id);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);
async function naNovPredmet() {
  await p.goto(BASE + "/app#/predmeti/nov");
  await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
}

// ── A) problem prvo ──────────────────────────────────────────────────────────────────────────────────────────────
await naNovPredmet();
zapisi("A", "tri ulaza u isti pogled (Ručno / Iz opisa / Iz dokumenta)", await vidljiv("nov-rezim-opis") && await vidljiv("nov-rezim-dokument") && await vidljiv("nov-forma"));
await p.click("#nov-rezim-opis");
zapisi("A", "„Iz opisa problema“ prikazuje opis, ručna forma skrivena", await vidljiv("npo-opis") && !(await vidljiv("nov-forma")));
await p.fill("#npo-opis", "Klijentkinja Jovana Nikolić radi u firmi Delta Promet DOO, poslodavac joj tri meseca ne isplaćuje zaradu, ukupno oko 320.000 dinara.");
await p.click("#npo-predlozi");
zapisi("A", "predlog iz opisa stigao i prikazan za proveru", await cekaj(() => !document.getElementById("npo-predlog").hidden));
zapisi("A", "predlog popunjava polja (naziv, protivna strana, vrsta, vrednost)",
  (await p.inputValue("#npo-naziv")) === "Nikolic protiv Delta Promet — zarada" && (await p.inputValue("#npo-protivna")) === "Delta Promet DOO"
  && (await p.inputValue("#npo-vrsta")) === "radni spor" && (await p.inputValue("#npo-vrednost")) === "320.000 RSD");
zapisi("A", "rok iz opisa je PREDLOG: prikazan, potvrda NIJE označena", await vidljiv("npo-rok-okvir") && !(await p.isChecked("#npo-rok-upisi"))
  && /ne upisuje se dok ne potvrdite/.test(await tekstEl("npo-rok-tekst")));
zapisi("A", "potrebni dokumenti prikazani", /Ugovor o radu/.test(await tekstEl("npo-dokumenti")));
let s0 = await stanje();
zapisi("A", "predlog NIŠTA ne upisuje (0 predmeta, 0 klijenata)", s0.predmeti === 0 && s0.klijenti === 0 && s0.pozivi_modela.includes("ekstrakcija"), JSON.stringify(s0));
zapisi("A", "otvaranje zaključano dok nema klijenta i provere sukoba", await p.isDisabled("#npo-otvori"));
await p.fill("#npo-naziv", "Nikolić protiv Delta Promet — neisplaćena zarada");          // advokat ispravlja predlog
await p.fill("#npo-ime", "Jovana"); await p.fill("#npo-prezime", "Nikolić");
zapisi("A", "bez provere sukoba i dalje zaključano", await p.isDisabled("#npo-otvori"));
await p.click("#npo-proveri");
zapisi("A", "provera sukoba prikazana", await cekaj(() => !document.getElementById("npo-coi").hidden));
zapisi("A", "čisto → otvaranje dozvoljeno", await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000), await tekstEl("npo-coi-naslov"));
await p.click("#npo-otvori");
zapisi("A", "otvoren predmet → prelaz na predmet", await cekaj(() => /#\/predmeti\/[^/]+/.test(location.hash) && !/nov$/.test(location.hash)));
const hashA = await p.evaluate(() => location.hash);
let s1 = await stanje();
zapisi("A", "upis: 1 predmet, 1 klijent, 1 veza klijent–predmet", s1.predmeti === 1 && s1.klijenti === 1 && s1.veze === 1, JSON.stringify(s1));
zapisi("A", "rok iz opisa NIJE upisan bez potvrde", s1.hronologija === 0, JSON.stringify(s1));
zapisi("A", "ispravljen naziv je naziv predmeta", await cekaj(() => /neisplaćena zarada/.test(document.getElementById("predmet-naslov").textContent)));

// ── B) dokument prvo ─────────────────────────────────────────────────────────────────────────────────────────────
await naNovPredmet();
await p.click("#nov-rezim-dokument");
zapisi("B", "„Iz dokumenta“ prikazuje prijem sa izborom strane klijenta", await vidljiv("nd-fajlovi") && await vidljiv("nd-klijent-strana"));
await p.selectOption("#nd-klijent-strana", "plaintiff");
await p.setInputFiles("#nd-fajlovi", PDF1);
await p.click("#nd-otpremi");
zapisi("B", "dokument primljen (posao u listi)", await cekaj(() => document.querySelectorAll("#nd-poslovi li").length === 1));
await obradi();
await cekaj(() => /Potvrđujem pregled|Otvori predmet iz ovog dokumenta/.test(document.getElementById("nd-poslovi").innerText), null, 20000);
if (/Potvrđujem pregled/.test(await tekstEl("nd-poslovi"))) { await p.click('#nd-poslovi button:has-text("Potvrđujem pregled")'); await obradi(); }
zapisi("B", "posle obrade: „Otvori predmet iz ovog dokumenta“", await cekaj(() => /Otvori predmet iz ovog dokumenta/.test(document.getElementById("nd-poslovi").innerText), null, 20000));
await p.click('#nd-poslovi button:has-text("Otvori predmet iz ovog dokumenta")');
zapisi("B", "predmet otvoren iz dokumenta (poruka + link)", await cekaj(() => !document.getElementById("nd-otvoren").hidden, null, 20000), (await tekstEl("nd-poslovi")).slice(0, 300));
const porukaB = await tekstEl("nd-poslovi");
zapisi("B", "ishod klijenta i provere sukoba je istinit (zakazano, ne rezultat)", /Klijent iz dokumenta je povezan|Klijent NIJE povezan|Klijent nije povezan/.test(porukaB)
  && (!/sukob/i.test(porukaB) || /zakazana u pozadini — to nije rezultat|NIJE zakazana/.test(porukaB)), porukaB.slice(0, 400));
let s2 = await stanje();
zapisi("B", "upis: drugi predmet sa 1 dokumentom", s2.predmeti === 2 && s2.dokumenti === 1, JSON.stringify(s2));
await p.setInputFiles("#nd-fajlovi", PDF2);
await p.click("#nd-otpremi");
await cekaj(() => document.querySelectorAll("#nd-poslovi li").length === 2);
await obradi();
await cekaj(() => /Potvrđujem pregled|Prikači ovom predmetu/.test(document.querySelectorAll("#nd-poslovi li")[1].innerText), null, 20000);
if (/Potvrđujem pregled/.test(await p.evaluate(() => document.querySelectorAll("#nd-poslovi li")[1].innerText))) {
  await p.click('#nd-poslovi li:nth-child(2) button:has-text("Potvrđujem pregled")'); await obradi();
}
zapisi("B", "drugi dokument: „Prikači ovom predmetu“ (istom, ne nov)", await cekaj(() => /Prikači ovom predmetu/.test(document.querySelectorAll("#nd-poslovi li")[1].innerText), null, 20000));
await p.click('#nd-poslovi li:nth-child(2) button:has-text("Prikači ovom predmetu")');
await cekaj(() => /Prikačeno ovom predmetu|Dokument je prikačen/.test(document.querySelectorAll("#nd-poslovi li")[1].innerText), null, 20000);
let s3 = await stanje();
zapisi("B", "upis: i dalje 2 predmeta; predmet iz dokumenta ima 2 dokumenta", s3.predmeti === 2 && s3.dokumenti === 2 && JSON.stringify(s3.dokumenti_po_predmetu) === "[0,2]", JSON.stringify(s3));
await obradi();
let s3b = await stanje();
zapisi("B", "dokumenti dobijaju tvrdnje (lanac posle prijema radi)", s3b.tvrdnje > 0 && s3b.nedispecovano === 0, JSON.stringify(s3b));
await p.click("#nd-otvori-predmet");
zapisi("B", "„Otvori predmet“ vodi na predmet iz dokumenta", await cekaj(() => /#\/predmeti\/[^/]+/.test(location.hash) && !/nov$/.test(location.hash)));
const hashB = await p.evaluate(() => location.hash);
zapisi("B", "predmet prikazuje 2 dokumenta", await cekaj(() => /2/.test(document.getElementById("dok-broj").textContent), null, 10000), await tekstEl("dok-broj"));

// ── C) provera sukoba: ime klijenta je stranka u AKTIVNOM predmetu ─────────────────────────────────────────────────
await naNovPredmet();
await p.click("#nov-rezim-opis");
await p.fill("#npo-opis", "Gradnja Invest DOO želi da je zastupamo u sporu sa bivšim zaposlenim oko otpremnine i zarade.");
await p.click("#npo-predlozi");
await cekaj(() => !document.getElementById("npo-predlog").hidden);
await p.fill("#npo-ime", "Gradnja"); await p.fill("#npo-prezime", "Invest DOO");
await p.click("#npo-proveri");
await cekaj(() => !document.getElementById("npo-coi").hidden);
const coiNaslov = await tekstEl("npo-coi-naslov"), coiTelo = await tekstEl("npo-coi-telo");
zapisi("C", "nalaz u aktivnom predmetu → „mogući sukob … potrebna provera“", /Mogući sukob interesa u aktivnom predmetu — potrebna provera/.test(coiNaslov), coiNaslov);
zapisi("C", "bez kategorične tvrdnje („ne možete zastupati“)", !/ne možete zastupati/i.test(coiNaslov + coiTelo) && /nije utvrđen sukob/.test(coiTelo));
zapisi("C", "otvaranje zaustavljeno (isto pravilo kao povezivanje u kartici Klijenti)", await p.isDisabled("#npo-otvori"));
let s4 = await stanje();
zapisi("C", "ništa nije upisano", s4.predmeti === 2, JSON.stringify(s4));

// ── D) ponovno učitavanje ──────────────────────────────────────────────────────────────────────────────────────────
await p.goto(BASE + "/app" + hashA); await p.reload();
zapisi("D", "posle reload-a predmet iz opisa ostaje (ispravljen naziv)", await cekaj(() => /neisplaćena zarada/.test(document.getElementById("predmet-naslov").textContent)));
await p.goto(BASE + "/app" + hashB); await p.reload();
zapisi("D", "posle reload-a predmet iz dokumenta ima 2 dokumenta", await cekaj(() => /2/.test(document.getElementById("dok-broj").textContent), null, 10000));

const kraj = await stanje();
zapisi("bezbednost", "svi upisi pripadaju prijavljenom korisniku", JSON.stringify(kraj.vlasnici) === '["uid-A"]', JSON.stringify(kraj.vlasnici));
zapisi("bezbednost", "0 spoljnih veza (pregledač i server)", spoljni.length === 0 && kraj.spoljni_pokusaji === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 2), api500.slice(0, 3)]));
zapisi("modeli", "simulirani su samo modeli (ekstrakcija, klasifikacija)", kraj.pozivi_modela.every(x => ["ekstrakcija", "pitanje", "nacrt"].includes(x)), JSON.stringify(kraj.pozivi_modela));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} ${pada ? "FAIL" : "PASS"}`);
process.exit(pada ? 1 : 0);
