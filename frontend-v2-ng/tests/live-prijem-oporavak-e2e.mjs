// Vindex V2 NG — OCR001: prikačivanje dokumenta predmetu kroz STVARAN V2 /app nad PRAVIM api.app koji STVARNO upisuje,
// uz kvarove na granici baze i proces ubijen posle zauzeća finalizacije. Pokretanje: `node tests/live-prijem-oporavak-e2e.mjs`.
// Server: tests/osb003_solo_server.py (stvarne rute, stvaran intake worker i dispečer; simulirani modeli/embedding/prijava).
// Svaki korak se proverava u UI-ju I u bazi (GET /__osb003/stanje, samo brojevi) — „prikačeno“ u UI-ju bez reda u bazi = PAD.

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4528, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

// Tri izmišljena dokumenta (digitalni tekst; stvaran OCR meri tests/test_ocr001_ocr_korpus.py u produkcionoj slici).
const dir = await mkdtemp(join(tmpdir(), "vx-ocr001-"));
const DOK = {
  tuzba: join(dir, "01_tuzba_digital_lat.pdf"),
  dostavnica: join(dir, "02_dostavnica.pdf"),
  zapisnik: join(dir, "03_zapisnik.pdf"),
};
const gen = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
for put, redovi in ((r"${DOK.tuzba}", ["OSNOVNI SUD U BEOGRADU", "Broj predmeta: P 4321/2026", "Interna oznaka: TEST-2026-014",
                                       "Tuzilac: Petar Primerovic iz Beograda", "Tuzeni: Primer Invest Test doo Beograd",
                                       "Tuzeni duguje iznos od 47.912,00 RSD.", "Tuzba je dostavljena tuzenom 17.03.2025."]),
                    (r"${DOK.dostavnica}", ["DOSTAVNICA", "Primalac: Primer Invest Test doo", "Uruceno dana 25.03.2025. godine."]),
                    (r"${DOK.zapisnik}", ["ZAPISNIK O PRIJEMU", "Oznaka: TEST-2026-014", "Datum dostave je sporan: 17.03.2025. ili 25.03.2025.",
                                          "Navodno je ostavljen rok za odgovor, sto nije provereno."])):
    c = canvas.Canvas(put)
    for i, r in enumerate(redovi):
        c.drawString(60, 780 - i * 24, r)
    c.showPage(); c.save()`], { encoding: "utf-8" });
if (gen.status !== 0) { console.log(gen.stderr); process.exit(1); }

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
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
const kvar = (tabela, radnja, ukljucen) => zahtev("/__osb003/kvar", { method: "POST", telo: { tabela, radnja, ukljucen } });
const zauzece = (starost_s) => zahtev("/__osb003/zauzece", { method: "POST", telo: { starost_s } });

const np = await zahtev("/api/predmeti", { method: "POST", telo: { naziv: "QA OCR001 — TEST-2026-014" }, token: "tok-A" });
const pid = (JSON.parse(np.b || "{}").predmet || {}).id;
zapisi("predmet", "predmet postoji i pripada A", np.s < 300 && /^[0-9a-f-]{36}$/.test(pid || ""), String(np.s));

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const spoljni = [], greskeJS = [], finalizacije = [];
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
p.on("response", s => { const u = new URL(s.url()); if (/\/finalize$/.test(u.pathname)) finalizacije.push(s.status()); });
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const posao = () => p.evaluate(() => { const li = document.querySelector("#pd-poslovi .intake:last-child"); return li ? {
  tekst: li.innerText, dugmad: [...li.querySelectorAll("button")].map(b => b.textContent),
  msg: li.querySelector(".intake__msg") && !li.querySelector(".intake__msg").hidden ? li.querySelector(".intake__msg").dataset.stanje + ":" + li.querySelector(".intake__msg").textContent : "" } : null; });
const dugme = (t) => cekaj((t) => { const li = document.querySelector("#pd-poslovi .intake:last-child"); return !!li && [...li.querySelectorAll("button")].some(b => b.textContent === t); }, t, 20000);
const klikni = (t) => p.locator("#pd-poslovi .intake:last-child button", { hasText: t }).first().click();
const poruka = () => cekaj(() => { const m = document.querySelector("#pd-poslovi .intake:last-child .intake__msg"); return !!m && !m.hidden && m.dataset.stanje !== "ucitavanje"; });

async function doPrikacivanja(fajl) {
  await p.goto(`${BASE}/app#/predmeti/${pid}/prijem`);
  await cekaj(() => !document.getElementById("odeljak-prijem").hidden);
  await p.setInputFiles("#pd-fajlovi", fajl);
  await p.click("#pd-otpremi");
  await cekaj((n) => document.querySelectorAll("#pd-poslovi .intake").length > n, await p.evaluate(() => document.querySelectorAll("#pd-poslovi .intake").length));
  await p.waitForTimeout(300);
  await obradi();
  await cekaj(() => /Potvrđujem pregled|Prikači ovom predmetu|u toku ili je upravo prekinuto/.test(document.getElementById("pd-poslovi").innerText), null, 20000);
  if (await p.locator("#pd-poslovi button", { hasText: "Potvrđujem pregled" }).count()) { await klikni("Potvrđujem pregled"); await p.waitForTimeout(500); }
}

// 1) Upis dokumenta ne uspe (ruta završi bez izuzetka) → nikad „prikačeno“; ponovni pokušaj → tačno jedan dokument
await doPrikacivanja(DOK.tuzba);
await dugme("Prikači ovom predmetu");
await kvar("predmet_dokumenti", "insert", true);
await klikni("Prikači ovom predmetu");
await poruka();
await dugme("Ponovi prikačivanje");
let e = await posao(), st = await stanje();
await kvar("predmet_dokumenti", null, false);
zapisi("1.upis", "UI: „Dokument NIJE prikačen“, bez „Prikačeno“; baza: 0 dokumenata, posao nije prikačen",
  /^greska:Dokument NIJE prikačen/.test(e.msg) && !/Prikačeno ovom predmetu|Dokument je prikačen/.test(e.tekst) && st.dokumenti === 0 && st.poslovi_prikaceni === 0,
  JSON.stringify({ msg: e.msg.slice(0, 80), dok: st.dokumenti }));
zapisi("1.upis", "zauzeće oslobođeno odmah (nema 120 s čekanja)", st.poslovi_zauzeti === 0, String(st.poslovi_zauzeti));
await klikni("Ponovi prikačivanje");
await cekaj(() => /Prikačeno ovom predmetu/.test(document.querySelector("#pd-poslovi .intake:last-child").innerText));
e = await posao(); st = await stanje();
zapisi("1.upis", "ponovljeno: UI „Dokument je prikačen“ i „Prikačeno ovom predmetu“; baza: tačno 1 dokument, posao prikačen",
  /^uspeh:Dokument je prikačen/.test(e.msg) && st.dokumenti === 1 && st.poslovi_prikaceni === 1, JSON.stringify({ msg: e.msg.slice(0, 60), dok: st.dokumenti }));

// 2) Baza pada usred prikačivanja (izuzetak posle zauzeća — oblik QA incidenta) → 503, „ishod nepoznat“, odmah ponovljivo
await doPrikacivanja(DOK.dostavnica);
await dugme("Prikači ovom predmetu");
await kvar("predmet_dokumenti", "*", true);
await klikni("Prikači ovom predmetu");
await poruka();
await p.waitForTimeout(800);
await kvar("predmet_dokumenti", null, false);
e = await posao(); st = await stanje();
zapisi("2.pad_baze", "UI: „Ishod nije poznat“ + ponovo pročitano stanje; baza: dokument nije dodat, zauzeće oslobođeno",
  /^nepoznato:Ishod nije poznat/.test(e.msg) && st.dokumenti === 1 && st.poslovi_zauzeti === 0, JSON.stringify({ msg: e.msg.slice(0, 50), dok: st.dokumenti, z: st.poslovi_zauzeti }));
zapisi("2.pad_baze", "posle čitanja stanja odmah se nudi prikačivanje (incident: 409 narednih 120 s)", await dugme("Prikači ovom predmetu"));
await klikni("Prikači ovom predmetu");
await cekaj(() => /Prikačeno ovom predmetu/.test(document.querySelector("#pd-poslovi .intake:last-child").innerText));
st = await stanje();
zapisi("2.pad_baze", "ponovljeno: tačno 2 dokumenta u predmetu, bez duplikata", st.dokumenti === 2 && st.poslovi_prikaceni === 2, String(st.dokumenti));

// 3) Proces ubijen posle zauzeća (sveže zauzeće ostaje) → „u toku ili upravo prekinuto“, bez dugmeta; po zastarevanju oporavak
await doPrikacivanja(DOK.zapisnik);
await dugme("Prikači ovom predmetu");
await zauzece(0);
await p.reload();
await cekaj(() => !document.getElementById("odeljak-prijem").hidden);
await p.setInputFiles("#pd-fajlovi", DOK.zapisnik);                        // isti sadržaj → isti posao (bez duplikata)
await p.click("#pd-otpremi");
const uToku = await cekaj(() => /Prikačivanje je u toku ili je upravo prekinuto/.test(document.getElementById("pd-poslovi").innerText), null, 20000);
e = await posao();
zapisi("3.prekid", "posle ponovnog učitavanja: „u toku ili upravo prekinuto“, bez dugmeta za prikačivanje, bez „Prikačeno“",
  uToku && !e.dugmad.some(b => /Prikači|Ponovi/.test(b)) && !/Prikačeno ovom predmetu/.test(e.tekst), e.dugmad.join(","));
const r409 = await zahtev(`/api/smart-intake/jobs/${await p.evaluate(() => document.querySelector("#pd-poslovi .intake:last-child").dataset.posao)}/finalize`,
  { method: "POST", telo: { predmet_id: pid }, token: "tok-A" });
zapisi("3.prekid", "server za to vreme odbija novo prikačivanje (409), bez upisa", r409.s === 409 && (await stanje()).dokumenti === 2, String(r409.s));
await zauzece(121);
zapisi("3.prekid", "kad zauzeće zastari, praćenje stanja ponovo nudi prikačivanje", await dugme("Prikači ovom predmetu"));
await klikni("Prikači ovom predmetu");
await cekaj(() => /Prikačeno ovom predmetu/.test(document.querySelector("#pd-poslovi .intake:last-child").innerText));
st = await stanje();
zapisi("3.prekid", "oporavak: tačno 3 dokumenta, sva 3 posla prikačena, nijedno zauzeće", st.dokumenti === 3 && st.poslovi_prikaceni === 3 && st.poslovi_zauzeti === 0, JSON.stringify(st.dokumenti_po_predmetu));

// 4) Ponovno učitavanje: lista dokumenata predmeta i izvorni tekst (D3)
await p.goto(`${BASE}/app#/predmeti/${pid}/dokumenti`);
await p.reload();
const lista = await cekaj(() => document.querySelectorAll("#dok-lista li").length === 3, null, 15000);
const imena = await p.evaluate(() => [...document.querySelectorAll("#dok-lista li")].map(li => li.innerText).join(" | "));
zapisi("4.ucitavanje", "posle reload-a predmet prikazuje tačno 3 prikačena dokumenta", lista && /01_tuzba_digital_lat/.test(imena) && /02_dostavnica/.test(imena) && /03_zapisnik/.test(imena), imena.slice(0, 200));
await p.locator("#dok-lista li", { hasText: "02_dostavnica" }).first().click().catch(() => {});
const izvor = await cekaj(() => /Primalac: Primer Invest Test doo/.test((document.getElementById("dok-tekst") || {}).textContent || ""), null, 10000);
zapisi("4.ucitavanje", "izvorni tekst dokumenta se čita iz predmeta", izvor);

// 5) Izolacija
const jid = (await p.evaluate(() => null)) || null;
const tudj = await zahtev(`/api/predmeti/${pid}`, { token: "tok-B" });
st = await stanje();
zapisi("5.izolacija", "korisnik B ne vidi predmet A", tudj.s === 404 || tudj.s === 403, String(tudj.s));
zapisi("5.izolacija", "svi upisi pripadaju A", st.vlasnici.join() === "uid-A", st.vlasnici.join());
zapisi("5.izolacija", "nijedna veza van 127.0.0.1 (browser i server)", spoljni.length === 0 && st.spoljni_pokusaji === 0, spoljni.slice(0, 2).join());
zapisi("konzola", "bez grešaka stranice", greskeJS.length === 0, greskeJS.join(" | ").slice(0, 200));
void jid;

await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
