// Vindex V2 NG — MIR001 C3b FINAL CLOSURE TASK-02: AI RADNI PREDLOG → IZRIČITO USVAJANJE → DOKUMENT ZA SUD kroz STVARAN
// V2 /app nad PRAVIM api.app koji STVARNO upisuje. Pokretanje: `node tests/live-c3b-usvajanje-e2e.mjs`.
// Server: tests/osb003_solo_server.py sa VX_AGENTI=1 i VX_NACRT_C3B=1 (zamenjen SAMO poziv modela: predlog sa
// AUTENTIČNIM izvodom iz DOK-07 i POGREŠNIM tumačenjem). Spis: Golden Case kroz stvaran prijem i OCR.
// Svaki korak se proverava u UI-ju I u bazi (GET /__osb003/stanje); DOCX se čita iz preuzetog fajla (python-docx).

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4533, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const sha = (t) => createHash("sha256").update(t, "utf8").digest("hex");

const dir = await mkdtemp(join(tmpdir(), "vx-c3b-"));
const gen = spawnSync(PY, ["-c", `
import sys, os, json; sys.path.insert(0, sys.argv[1])
from tests import mir001_golden_case as gc
for d in gc.DOKUMENTI:
    open(os.path.join(sys.argv[2], d["ime"]), "wb").write(gc.bajtovi(d))
print(json.dumps({"ocr": __import__("pytesseract").get_tesseract_version().public}))`, REPO, dir], { encoding: "utf-8", cwd: REPO });
if (gen.status !== 0) { console.log(gen.stderr.slice(-800)); zapisi("ocr", "Tesseract dostupan (sken mora kroz stvaran OCR)", false); process.exit(1); }
const FAJLOVI = (await readdir(dir)).sort().map(f => join(dir, f));

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_AGENTI: "1", VX_NACRT_C3B: "1" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, { method = "GET", telo = null, token = null } = {}) => new Promise(r => {
  const h = { "Content-Type": "application/json" };
  if (token) h.Authorization = "Bearer " + token;
  const q = http.request(BASE + p, { method, headers: h }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); });
  q.on("error", () => r({ s: 0, b: "" })); if (telo) q.write(JSON.stringify(telo)); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const stanje = async () => JSON.parse((await zahtev("/__osb003/stanje")).b);
const obradi = async () => JSON.parse((await zahtev("/__osb003/obradi", { method: "POST" })).b);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", acceptDownloads: true });
const spoljni = [], greskeJS = [], api500 = [];
await ctx.route("**/*", r => {
  const u = new URL(r.request().url());
  if (u.hostname !== "127.0.0.1" && u.protocol !== "blob:") { spoljni.push(u.href); return r.abort(); }
  if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
  return r.continue();
});
await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
  [KLJUC, JSON.stringify({ access_token: "tok-A", refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "uid-A" } })]);
const p = await ctx.newPage();
p.setDefaultTimeout(10000);
p.on("pageerror", e => greskeJS.push(String(e)));
p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
const cekaj = (fn, arg, ms = 20000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const txt = (id) => p.evaluate((i) => { const n = document.getElementById(i); return n ? n.textContent : null; }, id);

// ── 0) Spis: predmet + 7 dokumenata Golden Case-a kroz stvaran prijem (isto kao live-mir001-spis-e2e) ──
const np = await zahtev("/api/predmeti", { method: "POST", telo: { naziv: "Alfa Fiktiv protiv Beta Primer Gradnja (SINTETICKI, C3b)" }, token: "tok-A" });
const pid = (JSON.parse(np.b || "{}").predmet || {}).id;
zapisi("0.spis", "predmet napravljen", /^[0-9a-f-]{36}$/.test(pid || ""), String(pid));
await p.goto(`${BASE}/app#/predmeti/${pid}/prijem`);
await cekaj(() => !document.getElementById("odeljak-prijem").hidden);
await p.setInputFiles("#pd-fajlovi", FAJLOVI);
await p.click("#pd-otpremi");
await cekaj(() => document.querySelectorAll("#pd-poslovi .intake").length === 7);
await obradi();
await cekaj(() => [...document.querySelectorAll("#pd-poslovi .intake")].every(li => /Potvrđujem pregled|Prikači ovom predmetu|Prikačeno ovom predmetu/.test(li.innerText)), null, 40000);
for (let i = 0; i < 7; i++) {
  const li = p.locator("#pd-poslovi .intake").nth(i);
  if (await li.locator("button", { hasText: "Potvrđujem pregled" }).count()) { await li.locator("button", { hasText: "Potvrđujem pregled" }).first().click(); await p.waitForTimeout(400); }
  const prikaci = li.locator("button", { hasText: "Prikači ovom predmetu" });
  if (await prikaci.count()) await prikaci.first().click();
  await cekaj((i) => /Prikačeno ovom predmetu/.test(document.querySelectorAll("#pd-poslovi .intake")[i].innerText), i, 20000);
}
await obradi();
let st = await stanje();
zapisi("0.spis", "7 dokumenata u predmetu (stvaran prijem i OCR)", st.dokumenti === 7, JSON.stringify(st.dokumenti_po_predmetu));
const s0 = st;

// ── 1) Savetnik za nacrte: odgovor je AI RADNI PREDLOG (naslov to kaže rečima) ──
await p.goto(`${BASE}/app#/predmeti/${pid}/pitanje`);
await p.click("#tab-pitanje").catch(() => {});
await cekaj(() => !document.getElementById("ag-posalji").disabled && document.querySelectorAll("#ag-agent option").length === 6);
await p.selectOption("#ag-nacin", "pojedinacno");
await p.selectOption("#ag-agent", "drafting");
await p.fill("#ag-zadatak", "Sastavi podnesak tuzioca kojim se izjasnjava na nalaz vestaka (DOK-05) i na izjasnjenje tuzenog (DOK-06).");
await p.click("#ag-posalji");
await cekaj(() => !document.getElementById("ag-odgovor").hidden, null, 30000);
zapisi("1.predlog", "savetnik: naslov kaže „AI radni predlog — samo za pregled, ne ide u dokument za sud“",
  /AI radni predlog — samo za pregled, ne ide u dokument za sud/.test(await txt("ag-odgovor-naslov") || ""), await txt("ag-odgovor-naslov"));
await obradi();
st = await stanje();
const predlogRed = st.nacrti.find(x => x.tip === "nacrt_iz_spisa");
zapisi("1.predlog", "server: jedan poziv modela, jedna naplata, AI predlog na pregledu (nema dokumenta za sud)",
  st.pozivi_modela.filter(x => x === "agent:drafting:c3b").length === 1 && st.naplate - s0.naplate === 1 && !!predlogRed
  && !st.nacrti.some(x => x.tip === "dokument_za_sud"), JSON.stringify([st.pozivi_modela.slice(-2), st.naplate - s0.naplate, st.nacrti.map(x => x.tip)]));
const predlogSha = predlogRed && predlogRed.sha256;

// ── 2) Kartica Nacrt: AI predlog otvoren — tri dela, razlika rečima ──
await p.goto(`${BASE}/app#/predmeti/${pid}/nacrt`);
await cekaj(() => document.querySelectorAll("#nc-overa-lista .review").length === 1);
zapisi("2.ekran", "lista: „AI predlog — za pregled, ne izvozi se“", /AI predlog — za pregled, ne izvozi se/.test(await p.evaluate(() => document.querySelector("#nc-overa-lista .review__meta").textContent)));
await p.click('#nc-overa-lista .review button:has-text("Otvori")');
await cekaj(() => !document.getElementById("nc-usvajanje").hidden && document.querySelectorAll("#nc-stavke > li").length === 5);
let e = await p.evaluate(() => ({
  h: [...document.querySelectorAll("#nc-usvajanje .adopt__h")].map(x => x.textContent),
  staroPolje: !document.getElementById("nc-tekst").hidden, staraDugmad: !document.getElementById("nc-akcije").hidden,
  sud: document.getElementById("nc-sud-tekst").value, stanjeSud: document.getElementById("nc-sud-stanje").textContent,
  stavke: [...document.querySelectorAll("#nc-stavke > li")].map(li => ({ t: li.querySelector(".adopt__text").textContent, s: li.querySelector(".adopt__state").textContent,
    meta: [...li.querySelectorAll(".adopt__meta")].map(m => m.textContent).join(" | ") })),
  tacke: document.querySelectorAll("#nc-tacke > li").length,
  odluke: [...document.querySelectorAll("#nc-tacke select")].map(x => x.value),
}));
zapisi("2.ekran", "tri dela sa naslovima: AI predlog (NE ide u dokument) / procesne informacije / tekst koji će biti izvezen",
  /AI predlog — samo za pregled\. Ovaj tekst NE ide u dokument za sud/.test(e.h[0]) && /Procesne informacije/.test(e.h[1]) && /Tekst koji će biti izvezen u dokument za sud/.test(e.h[2]), JSON.stringify(e.h));
zapisi("2.ekran", "staro polje i dugmad (Sačuvaj/Odobri/DOCX nad AI tekstom) nisu ponuđeni", !e.staroPolje && !e.staraDugmad);
zapisi("2.ekran", "dokument za sud je prazan; ništa iz AI predloga nije u njemu", e.sud === "" && /još ne postoji/.test(e.stanjeSud), e.stanjeSud);
const pog = e.stavke.findIndex(x => /sud odbio/.test(x.t));
zapisi("2.ekran", "pogrešno tumačenje uz AUTENTIČAN izvod: prikazano kao AI predlog, izvor „nije proveren“, nije odlučeno",
  pog >= 0 && /„Sud prihvata predlog za dopunu vestacenja\.“/.test(e.stavke[pog].t) && /nisu provereni\): DOK-07/.test(e.stavke[pog].meta)
  && /Nije odlučeno — nije u dokumentu za sud/.test(e.stavke[pog].s), JSON.stringify(e.stavke[pog]));
zapisi("2.ekran", "8 procesnih tačaka, nijedna unapred odlučena", e.tacke === 8 && e.odluke.every(x => x === ""), JSON.stringify(e.odluke));
const kandidat = await p.evaluate(() => document.querySelector('#nc-tacke li[data-tacka="ODLUKE_SUDA"]').innerText);
zapisi("2.ekran", "procesne informacije: doslovan izvod iz DOK-07 kao kandidat, „značenje nije utvrđeno“",
  /DOK-07 — „Sud prihvata predlog za dopunu vestacenja\.“/.test(kandidat) && /značenje nije utvrđeno/.test(kandidat), kandidat.slice(0, 200));
// izvorni dokument dostupan iz same stavke
await p.locator("#nc-stavke > li").nth(pog).locator("details summary").first().click();
zapisi("2.ekran", "izvor DOK-07 se otvara iz stavke (tekst dokumenta iz spisa)", await cekaj((i) => /Sud prihvata predlog za dopunu vestacenja/.test(
  document.querySelectorAll("#nc-stavke > li")[i].querySelector("details pre").textContent), pog));

// ── 3) Odobrenje praznog dokumenta: ne prolazi ──
await p.click("#nc-sud-odobri");
zapisi("3.prazno", "prazan dokument za sud se ne odobrava (poruka, bez upisa)", await cekaj(() => /prazan/.test(document.getElementById("nc-sud-poruka").textContent))
  && !(await stanje()).nacrti.some(x => x.tip === "dokument_za_sud"));

// ── 4) Usvajanje stavki: tačne usvojene, pogrešna odbijena, upozorenje AI neodlučeno ──
const klik = async (i, dugme) => { await p.locator("#nc-stavke > li").nth(i).locator("button", { hasText: dugme }).click(); await p.waitForTimeout(250);
  await cekaj(() => !document.querySelector("#nc-usvajanje button[disabled]")); };
const idx = (re) => e.stavke.findIndex(x => re.test(x.t));
await p.fill("#nc-sud-tekst", "MOJ UVOD (nesačuvan)");
await p.locator("#nc-stavke > li").nth(idx(/^PRIVREDNOM SUDU/)).locator("button", { hasText: "Proverio sam" }).click();
zapisi("4.nesacuvano", "usvajanje uz nesačuvan tekst (dokument još ne postoji): odbijeno uz poruku, tekst ostaje, ništa upisano",
  await cekaj(() => /Prvo sačuvajte izmene teksta/.test(document.getElementById("nc-sud-poruka").textContent))
  && (await p.inputValue("#nc-sud-tekst")) === "MOJ UVOD (nesačuvan)" && !(await stanje()).nacrti.some(x => x.tip === "dokument_za_sud"));
await p.fill("#nc-sud-tekst", "");
await p.selectOption('#nc-tacke li[data-tacka="NALOG"] select', "NEPOZNATO");
await klik(idx(/^PRIVREDNOM SUDU/), "Proverio sam");
zapisi("4.nesacuvano", "nesačuvan izbor tačke preživljava nastanak dokumenta za sud (prvo usvajanje) i označen je",
  (await p.inputValue('#nc-tacke li[data-tacka="NALOG"] select')) === "NEPOZNATO"
  && /Nesačuvana izmena/.test(await p.evaluate(() => document.querySelector('#nc-tacke li[data-tacka="NALOG"]').innerText)));
await klik(idx(/hidroizolacija/), "Proverio sam");
await klik(idx(/osporava navode/), "Proverio sam");
await klik(pog, "Ne usvajam");
e = await p.evaluate(() => ({ sud: document.getElementById("nc-sud-tekst").value,
  s: [...document.querySelectorAll("#nc-stavke > li .adopt__state")].map(x => x.textContent) }));
zapisi("4.usvajanje", "dokument za sud = samo usvojene stavke (bez pogrešne i bez upozorenja AI)",
  /hidroizolacija/.test(e.sud) && /osporava navode/.test(e.sud) && !/sud odbio/.test(e.sud) && !/⚠/.test(e.sud) && !/VINDEX/.test(e.sud), e.sud.slice(0, 300));
zapisi("4.usvajanje", "svaka stavka pokazuje svoju odluku rečima", e.s.filter(x => /^Usvojeno u dokument za sud/.test(x)).length === 3
  && e.s.filter(x => /^Ne usvajam/.test(x)).length === 1 && e.s.filter(x => /^Nije odlučeno/.test(x)).length === 1, JSON.stringify(e.s));
st = await stanje();
let dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("4.usvajanje", "baza: odluke o stavkama upisane (3 USVOJENO, 1 ODBACENO), dokument na čekanju, AI predlog NEPROMENJEN",
  dok && dok.status === "pending" && dok.usvajanje.stavke.filter(x => x.odluka === "USVOJENO").length === 3 && dok.usvajanje.stavke.filter(x => x.odluka === "ODBACENO").length === 1
  && st.nacrti.find(x => x.tip === "nacrt_iz_spisa").sha256 === predlogSha, JSON.stringify(dok && dok.usvajanje.stavke.map(x => x.id + x.odluka)));

// ── 5) Advokat dopisuje svoj tekst; odobrenje bez odluka o tačkama ne prolazi ──
const SVOJ = "Tuzilac predlaze da sud o dopuni vestacenja postupi u skladu sa resenjem od 15.07.2026. godine.";
// R1: stavka sa izvodom servera pokazuje šta ulazi u dokument (izvod bez interne oznake); stavka sa „(DOK-05)“ upozorava
const r1 = await p.evaluate((i) => { const li = document.querySelectorAll("#nc-stavke > li"); return { pog: li[i].innerText,
  tacna: [...li].find(x => /hidroizolacija/.test(x.innerText)).innerText }; }, pog);
zapisi("4.R1", "stavka sa izvodom: „U dokument za sud ulazi“ isti izvod BEZ interne oznake DOK-07 (pregled je zadržava)",
  /U dokument za sud ulazi \(izvod bez interne oznake spisa\)/.test(r1.pog) && /\(zapisnik sa rocista \(sinteticki predmet\), 15\.07\.2026\.: „Sud prihvata/.test(r1.pog)
  && /\(DOK-07, zapisnik/.test(r1.pog), r1.pog.slice(0, 300));
zapisi("4.R1", "stavka sa „(DOK-05)“ upozorava da sud oznaku ne poznaje i da blokira odobrenje", /Sadrži internu oznaku spisa \(DOK-nn\)/.test(r1.tacna));
await p.fill("#nc-sud-tekst", (await p.inputValue("#nc-sud-tekst")) + "\n\n" + SVOJ);
await p.selectOption('#nc-tacke li[data-tacka="ROK"] select', "NEPOZNATO");
await p.click("#nc-sud-sacuvaj");
await cekaj(() => /sačuvan/.test(document.getElementById("nc-sud-poruka").textContent));
zapisi("5.nesacuvano", "čuvanje teksta ne briše nesačuvan izbor tačke (označen „Nesačuvana izmena“)",
  (await p.inputValue('#nc-tacke li[data-tacka="ROK"] select')) === "NEPOZNATO"
  && /Nesačuvana izmena/.test(await p.evaluate(() => document.querySelector('#nc-tacke li[data-tacka="ROK"]').innerText)));
await p.click("#nc-sud-odobri");
await cekaj(() => /nesačuvane odluke/.test(document.getElementById("nc-sud-poruka").textContent));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("5.tacke", "nesačuvana odluka o tački: odobrenje zaustavljeno pre servera (poruka), dokument na čekanju",
  dok.status === "pending" && /nesačuvane odluke o procesnim informacijama/.test(await txt("nc-sud-poruka")), await txt("nc-sud-poruka"));
await p.selectOption('#nc-tacke li[data-tacka="ROK"] select', "");
await p.click("#nc-sud-odobri");
await cekaj(() => /ne može da se odobri/.test(document.getElementById("nc-sud-poruka").textContent));
const razlozi2 = await p.evaluate(() => [...document.querySelectorAll("#nc-razlozi li")].map(x => x.textContent));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("5.tacke", "bez odluka o procesnim tačkama: nije odobreno, razlog prikazan", dok.status === "pending" && razlozi2.some(x => /Procesne tačke bez vaše odluke/.test(x)), JSON.stringify(razlozi2));

// ── 6) Procesne tačke: ispravka odluke suda + „nepoznato“ za ostale ──
await p.selectOption('#nc-tacke li[data-tacka="ODLUKE_SUDA"] select', "ISPRAVLJENO");
await p.fill('#nc-tacke li[data-tacka="ODLUKE_SUDA"] textarea', "Sud je 15.07.2026. PRIHVATIO predlog za dopunu vestacenja (DOK-07).\n");
await p.fill('#nc-tacke li[data-tacka="ROK"] textarea', "Opis bez odluke.");
await p.click("#nc-tacke-sacuvaj");
zapisi("6.tacke", "opis bez izabrane odluke: ne čuva se tiho (poruka, ništa upisano)",
  await cekaj(() => /Uz opis izaberite i odluku/.test(document.getElementById("nc-sud-poruka").textContent))
  && Object.keys((await stanje()).nacrti.find(x => x.tip === "dokument_za_sud").usvajanje.procesne_tacke || {}).length === 0);
await p.fill('#nc-tacke li[data-tacka="ROK"] textarea', "");
for (const k of ["OSNOVNI_ZAHTEV", "DODATNI_ZAHTEV", "POVLACENJE_IZMENA", "NALOG", "UPLATA", "ROK", "NEDOSTAJUCI_DOKUMENT"])
  await p.selectOption(`#nc-tacke li[data-tacka="${k}"] select`, "NEPOZNATO");
await p.click("#nc-tacke-sacuvaj");
await cekaj(() => /sačuvane \(8\)/.test(document.getElementById("nc-sud-poruka").textContent));
zapisi("6.tacke", "opis sa novim redom na kraju: posle čuvanja nema „Nesačuvana izmena“ (poređenje kao server)",
  !/Nesačuvana izmena/.test(await p.evaluate(() => document.getElementById("nc-tacke").innerText)));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("6.tacke", "baza: 8 odluka advokata (ODLUKE_SUDA = ISPRAVLJENO sa njegovim opisom), upisao uid-A",
  Object.keys(dok.usvajanje.procesne_tacke).length === 8 && dok.usvajanje.procesne_tacke.ODLUKE_SUDA.odluka === "ISPRAVLJENO"
  && /PRIHVATIO/.test(dok.usvajanje.procesne_tacke.ODLUKE_SUDA.tekst) && Object.values(dok.usvajanje.procesne_tacke).every(x => x.by === "uid-A"));

zapisi("6.tacke", "sačuvana odluka se ne može vratiti na „— izaberite —“ (opcija onemogućena)",
  await p.evaluate(() => document.querySelector('#nc-tacke li[data-tacka="ODLUKE_SUDA"] select option[value=""]').disabled));
await p.fill('#nc-tacke li[data-tacka="ODLUKE_SUDA"] textarea', "Sud je odbio dopunu (izmenjen opis, nesacuvan).");
await p.click("#nc-sud-odobri");
await cekaj(() => /nesačuvane odluke/.test(document.getElementById("nc-sud-poruka").textContent));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("6.B1", "izmenjen SAMO opis sačuvane tačke (odluka ista), nije sačuvan → odobrenje zaustavljeno; baza: stari opis, na čekanju",
  dok.status === "pending" && /PRIHVATIO/.test(dok.usvajanje.procesne_tacke.ODLUKE_SUDA.tekst), JSON.stringify(dok.usvajanje.procesne_tacke.ODLUKE_SUDA));
await p.fill('#nc-tacke li[data-tacka="ODLUKE_SUDA"] textarea', dok.usvajanje.procesne_tacke.ODLUKE_SUDA.tekst);
await p.selectOption('#nc-tacke li[data-tacka="UPLATA"] select', "POTVRDJENO");
await p.fill('#nc-tacke li[data-tacka="UPLATA"] textarea', "Predujam je uplacen (nesacuvano).");
await p.click("#nc-sud-odobri");
await cekaj(() => /nesačuvane odluke/.test(document.getElementById("nc-sud-poruka").textContent));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("6.B1", "izbor tačke promenjen na ekranu, nije sačuvan → odobrenje zaustavljeno; baza: na čekanju, UPLATA i dalje NEPOZNATO; izbor ostaje na ekranu",
  dok.status === "pending" && dok.usvajanje.procesne_tacke.UPLATA.odluka === "NEPOZNATO"
  && (await p.inputValue('#nc-tacke li[data-tacka="UPLATA"] select')) === "POTVRDJENO", JSON.stringify([dok.status, dok.usvajanje.procesne_tacke.UPLATA]));
await p.selectOption('#nc-tacke li[data-tacka="UPLATA"] select', "NEPOZNATO");
await p.fill('#nc-tacke li[data-tacka="UPLATA"] textarea', "");

// R1: interna oznaka u usvojenom tekstu zaustavlja odobrenje (ništa se ne briše); advokat je zamenjuje
await p.click("#nc-sud-odobri");
await cekaj(() => /ne može da se odobri/.test(document.getElementById("nc-sud-poruka").textContent));
const razloziR1 = await p.evaluate(() => [...document.querySelectorAll("#nc-razlozi li")].map(x => x.textContent).join(" | "));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("6.R1", "usvojen tekst sa „(DOK-05)“: odobrenje zaustavljeno, razlog navodi oznaku i dokument; tekst nije promenjen",
  dok.status === "pending" && /DOK-05 = 05 Nalaz i misljenje vestaka\.pdf/.test(razloziR1) && /\(DOK-05\)/.test(await p.inputValue("#nc-sud-tekst")), razloziR1);
await p.fill("#nc-sud-tekst", (await p.inputValue("#nc-sud-tekst")).replace(" (DOK-05)", " u nalazu od 15.06.2026. godine").replace(" (DOK-06)", ""));
await p.click("#nc-sud-sacuvaj");
await cekaj(() => /sačuvan/.test(document.getElementById("nc-sud-poruka").textContent));

// ── 7) Odobrenje → DOCX = tačno odobren tekst ──
const ekranTekst = await p.inputValue("#nc-sud-tekst");
await p.click("#nc-sud-odobri");
await cekaj(() => /je odobren/.test(document.getElementById("nc-sud-poruka").textContent));
st = await stanje(); dok = st.nacrti.find(x => x.tip === "dokument_za_sud");
zapisi("7.odobrenje", "baza: odobren TAČNO tekst sa ekrana (sha256), bez upisa u znanje", dok.status === "approved" && dok.usvajanje.odobreno
  && dok.usvajanje.odobreno.sha256 === sha(ekranTekst) && dok.sha256 === sha(ekranTekst) && !dok.pinecone_indexed && st.vektori === s0.vektori,
  JSON.stringify([dok.status, (dok.usvajanje.odobreno || {}).sha256 === sha(ekranTekst)]));
e = await p.evaluate(() => ({ ro: document.getElementById("nc-sud-tekst").readOnly, docx: !document.getElementById("nc-sud-docx").hidden,
  stanje: document.getElementById("nc-sud-stanje").textContent, dugmad: document.querySelectorAll("#nc-stavke button").length }));
zapisi("7.odobrenje", "ekran: tekst zaključan, nema više usvajanja, „sistem nije proverio da su tvrdnje tačne“",
  e.ro && e.docx && e.dugmad === 0 && /sistem nije proverio da su tvrdnje tačne/.test(e.stanje), JSON.stringify(e));
if (process.env.VX_SNIMAK_C3B) await p.screenshot({ path: process.env.VX_SNIMAK_C3B, fullPage: true });   // dokaz za pregled (opciono)
const [preuzimanje] = await Promise.all([p.waitForEvent("download", { timeout: 15000 }).catch(() => null), p.click("#nc-sud-docx")]);
const putanja = preuzimanje ? join(dir, "Dokument_za_sud.docx") : null;
if (preuzimanje) await preuzimanje.saveAs(putanja);
const citaj = putanja ? spawnSync(PY, ["-I", "-c", `
import sys, json, docx
d = docx.Document(sys.argv[1])
print(json.dumps({"p": [x.text for x in d.paragraphs], "f": [x.text for s in d.sections for x in s.footer.paragraphs],
                  "h": [x.text for s in d.sections for x in s.header.paragraphs]}, ensure_ascii=False))`, putanja], { encoding: "utf-8" }) : { status: 1 };
const D = citaj.status === 0 ? JSON.parse(citaj.stdout) : null;
const ocekivano = ekranTekst.split("\n").filter(x => x.trim());
zapisi("7.docx", "DOCX: pasusi = odobren tekst (red po red), bez naslova „NACRT IZ SPISA“, bez podnožja „Vindex AI“, bez internih napomena",
  !!D && JSON.stringify(D.p.filter(x => x.trim())) === JSON.stringify(ocekivano) && !D.p.join("\n").includes("NACRT IZ SPISA")
  && D.f.join("").trim() === "" && !/VINDEX|INTERNE NAPOMENE|⚠|sud odbio|DOK-\d/.test(D.p.join("\n")), D ? JSON.stringify([D.p.length, ocekivano.length, D.f]) : citaj.stderr);
zapisi("7.docx", "advokatov sopstveni tekst je u DOCX-u", !!D && D.p.includes(SVOJ));

// ── 8) Posle reload-a: isto stanje; nova verzija ne nasleđuje odobrenje ──
await p.reload();
await cekaj(() => document.querySelectorAll("#nc-overa-lista .review").length === 2);
const meta = await p.evaluate(() => [...document.querySelectorAll("#nc-overa-lista .review__meta")].map(x => x.textContent).join(" | "));
zapisi("8.trajno", "lista posle reload-a: AI predlog + „dokument za sud — odobren“", /dokument za sud — odobren/.test(meta) && /AI predlog/.test(meta), meta);
await p.locator("#nc-overa-lista .review", { hasText: "Dokument za sud" }).locator("button").first().click();
await cekaj(() => !document.getElementById("nc-usvajanje").hidden && document.getElementById("nc-sud-tekst").value !== "");
zapisi("8.trajno", "otvoren odobren dokument: isti tekst, zaključan", (await p.inputValue("#nc-sud-tekst")) === ekranTekst && await p.evaluate(() => document.getElementById("nc-sud-tekst").readOnly));
await p.click("#nc-sud-nova");
await cekaj(() => /Nova verzija 2/.test(document.getElementById("nc-sud-poruka").textContent));
st = await stanje();
const v = st.nacrti.filter(x => x.tip === "dokument_za_sud").sort((a, b) => a.usvajanje.verzija - b.usvajanje.verzija);
zapisi("8.verzija", "nova verzija: na čekanju, bez odobrenja i bez odluka; v1 ostaje odobrena; ekran nije zaključan",
  v.length === 2 && v[0].status === "approved" && v[1].status === "pending" && !v[1].usvajanje.odobreno && Object.keys(v[1].usvajanje.procesne_tacke).length === 0
  && v[1].sha256 === v[0].sha256 && !(await p.evaluate(() => document.getElementById("nc-sud-tekst").readOnly)), JSON.stringify(v.map(x => [x.status, x.usvajanje.verzija])));
const izboriV2 = await p.evaluate(() => [...document.querySelectorAll("#nc-tacke select")].map(x => x.value));
zapisi("8.verzija", "ekran nove verzije: nijedna tačka nije izabrana (ne nasleđuje odluke iz v1), nema „Nesačuvana izmena“",
  izboriV2.length === 8 && izboriV2.every(x => x === "") && !/Nesačuvana izmena/.test(await p.evaluate(() => document.getElementById("nc-tacke").innerText)), JSON.stringify(izboriV2));
await cekaj(() => document.querySelectorAll("#nc-overa-lista .review").length === 3);
await p.locator("#nc-overa-lista .review", { hasText: "verzija 2" }).locator("button", { hasText: "Odbij" }).click();
zapisi("8.verzija", "„Odbij“ iz liste za otvorenu verziju 2: ekran se osvežava sa servera (odbijena, bez dugmadi)",
  await cekaj(() => /Ova verzija dokumenta za sud je odbijena/.test(document.getElementById("nc-sud-stanje").textContent)
    && document.getElementById("nc-sud-odobri").hidden && document.getElementById("nc-sud-tekst").readOnly));

// ── 9) Izolacija, trošak, bezbednost ──
const tudj = await zahtev(`/api/staging/${v[0].id}`, { token: "tok-B" });
const tudjDocx = await zahtev(`/api/staging/${v[0].id}/docx`, { method: "POST", token: "tok-B" });
st = await stanje();
zapisi("9.verzija", "baza: v2 odbijena, v1 i dalje odobrena", st.nacrti.filter(x => x.tip === "dokument_za_sud").map(x => x.status).sort().join() === "approved,rejected");
zapisi("9.izolacija", "drugi korisnik: dokument za sud 404, DOCX 404", tudj.s === 404 && tudjDocx.s === 404, `${tudj.s}/${tudjDocx.s}`);
const predlogDocx = await zahtev(`/api/staging/${predlogRed.id}/docx`, { method: "POST", token: "tok-A" });
const opsti = await zahtev(`/api/nacrti/export/docx`, { method: "POST", telo: { tekst: "x".repeat(40), naslov: "X", tip: "nacrt_iz_spisa" }, token: "tok-A" });
zapisi("9.granica", "AI predlog se ne izvozi (409), ni opštim izvozom (409)", predlogDocx.s === 409 && opsti.s === 409, `${predlogDocx.s}/${opsti.s}`);
st = await stanje();
zapisi("9.trosak", "usvajanje ne poziva model i ne naplaćuje (ukupno 1 poziv nacrta, 1 naplata)",
  st.pozivi_modela.filter(x => x.startsWith("agent:drafting")).length === 1 && st.naplate - s0.naplate === 1, JSON.stringify([st.pozivi_modela.length, st.naplate - s0.naplate]));
zapisi("9.trosak", "AI predlog nepromenjen do kraja (sha256)", st.nacrti.find(x => x.tip === "nacrt_iz_spisa").sha256 === predlogSha);
zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0 && st.spoljni_pokusaji === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 2), api500.slice(0, 3)]));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} ${pada ? "FAIL" : "PASS"}`);
process.exit(pada ? 1 : 0);
