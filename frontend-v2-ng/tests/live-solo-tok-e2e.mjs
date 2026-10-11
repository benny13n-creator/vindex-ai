// Vindex V2 NG — OSB003 Task 7: JEDAN solo tok kroz STVARAN V2 /app u Chromium-u nad PRAVIM api.app koji STVARNO upisuje.
// Pokretanje: `node tests/live-solo-tok-e2e.mjs`. Server: tests/osb003_solo_server.py (stvarne rute, stvaran intake worker
// i dispečer; simulirani modeli, embedding i prijava). Ništa ne izlazi van 127.0.0.1.
// Svaki korak se proverava i u UI-ju i u bazi (GET /__osb003/stanje, samo brojevi) — UI uspeh bez upisa = PAD.

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4521, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
let STRANA = null, SLIKA = 0;
const zapisi = (g, n, ok, d = "") => {
  ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`);
  if (!ok && STRANA && process.env.VX_SLIKE) STRANA.screenshot({ path: join(process.env.VX_SLIKE, `pad-${++SLIKA}-${g}.png`) }).catch(() => {});
};

const dir = await mkdtemp(join(tmpdir(), "vx-solo-"));
const PDF = join(dir, "Resenje o otkazu.pdf");
const gen = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
c = canvas.Canvas(r"${PDF}")
for i, r in enumerate(["OSNOVNI SUD U BEOGRADU", "Broj predmeta: P 4321/2026", "Tuzilac: Marko Petrovic iz Beograda",
                       "Tuzeni: Gradnja Invest DOO Beograd", "Resenje o otkazu je uruceno zaposlenom 17.03.2025. godine.",
                       "Predmet: ponistaj resenja o otkazu i isplata zarade od 480.000,00 dinara."]):
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
zapisi("server", "pravi api.app (primarni V2 /app) nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
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
STRANA = p;
p.on("pageerror", e => greskeJS.push(String(e)));
p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekst = () => p.evaluate(() => document.body.innerText);

// 1) Danas
await p.goto(BASE + "/app#/danas");
zapisi("danas", "Danas se učitao", await cekaj(() => { const rl = document.getElementById("rl-stanje"); return rl && rl.dataset.stanje !== "ucitavanje"; }));
zapisi("danas", "nov korisnik bez predmeta: nema bloka „Vindex je pripremio“ (autonomija isključena)", !/Vindex je pripremio/.test(await tekst()));

// 2) Nov predmet (registar → „Nov predmet")
await p.click('.sidenav__item:has-text("Predmeti")').catch(() => {});
await cekaj(() => { const l = document.getElementById("nov-predmet-link"); return l && !l.hidden; }, null, 8000);
await p.click("#nov-predmet-link").catch(() => {});
await p.fill("#nov-naziv", "Petrovic protiv Gradnja Invest").catch(() => {});
await p.fill("#nov-tip", "Radni spor").catch(() => {});
await p.fill("#nov-opis", "Nezakonit otkaz").catch(() => {});
await p.click("#nov-posalji").catch(() => {});
const naPredmetu = await cekaj(() => /^#\/predmeti\/[0-9a-f-]{36}/.test(location.hash));
const pid = naPredmetu ? (await p.evaluate(() => location.hash)).match(/[0-9a-f-]{36}/)[0] : null;
let st = await stanje();
zapisi("predmet", "nov predmet napravljen kroz UI i upisan u bazu sa vlasnikom A", naPredmetu && st.predmeti === 1 && st.vlasnici.join() === "uid-A", JSON.stringify({ hash: pid, predmeti: st.predmeti }));

// 3) Klijent i veza
await p.click("#kl-otvori").catch(() => {});
await p.click("#kl-nov-prekidac").catch(() => {});
await p.fill("#kl-ime", "Marko").catch(() => {});
await p.fill("#kl-prezime", "Petrovic").catch(() => {});
await p.click("#kl-nov-sacuvaj").catch(() => {});
await cekaj(() => { const b = document.getElementById("kl-povezi"); return b && !b.disabled && b.offsetParent !== null; }, null, 8000);
await p.click("#kl-povezi").catch(() => {});
for (let i = 0; i < 40 && (await stanje()).veze < 1; i++) await p.waitForTimeout(250);
await cekaj(() => !/Klijent se povezuje/.test(document.body.innerText), null, 8000);
st = await stanje();
zapisi("klijent", "klijent napravljen i povezan sa predmetom (UI → baza)", st.klijenti === 1 && st.veze === 1, JSON.stringify({ klijenti: st.klijenti, veze: st.veze }));

// 4) Prijem dokumenta: otpremanje → obrada → pregled → prikačivanje
await p.click("#tab-prijem").catch(() => {});
await p.setInputFiles("#pd-fajlovi", PDF).catch(e => zapisi("prijem", "izbor fajla", false, String(e).slice(0, 120)));
await p.click("#pd-otpremi").catch(() => {});
await p.waitForTimeout(800);
const o1 = await obradi();
const pregled = await cekaj(() => /Potvrđujem pregled|Prikači ovom predmetu/.test(document.body.innerText), null, 20000);
zapisi("prijem", "dokument otpremljen, obrađen i ponuđen za pregled", pregled && o1.poslova >= 1, JSON.stringify(o1));
if (await p.locator("text=Potvrđujem pregled").count()) { await p.click("text=Potvrđujem pregled").catch(() => {}); await p.waitForTimeout(600); }
await cekaj(() => /Prikači ovom predmetu/.test(document.body.innerText), null, 10000);
await p.click("text=Prikači ovom predmetu").catch(() => {});
await p.waitForTimeout(800);
const o2 = await obradi();
st = await stanje();
zapisi("prijem", "prikačen dokument postoji u bazi, događaji obrađeni bez greške", st.dokumenti === 1 && st.nedispecovano === 0 && o2.greske === 0, JSON.stringify({ dok: st.dokumenti, o2 }));
zapisi("dokazi", "tvrdnje iz dokumenta su upisane (ispravka c148d342/db5255d2 u stvarnom toku)", st.tvrdnje >= 1, `tvrdnje=${st.tvrdnje}`);
zapisi("genome", "Genome osvežen (verzija 1)", st.genome_verzije.includes(1), JSON.stringify(st.genome_verzije));

// 5) Dokumenti
await p.click("#tab-dokumenti").catch(() => {});
zapisi("dokumenti", "kartica Dokumenti prikazuje otpremljen dokument", await cekaj(() => /Resenje o otkazu/.test(document.getElementById("dok-lista")?.innerText || ""), null, 10000));

// 6) Pregled (Living Matter) i Rad na predmetu (Case Actions)
await p.click("#tab-pregled").catch(() => {});
zapisi("zivi", "Pregled predmeta se učitao", await cekaj(() => { const b = document.getElementById("zp-blok"); return b && !b.closest("[hidden]"); }, null, 10000));
await p.click("#tab-analiza").catch(() => {});
zapisi("zivi", "Analiza prikazuje tvrdnju iz dokumenta (17.03.2025)", await cekaj(() => /17\.03\.2025/.test(document.body.innerText), null, 10000));
await p.click("#tab-rad").catch(() => {});
zapisi("akcije", "Rad na predmetu se učitao bez greške", await cekaj(() => document.querySelector("#tab-rad[aria-selected='true'], #tab-rad.is-active, #tab-rad[aria-current]") !== null || /Beleške|Sledeće/.test(document.body.innerText), null, 8000));

// 7) Pravno pitanje (model simuliran — tekst odgovora nije pravna tvrdnja)
await p.click("#tab-pitanje").catch(() => {});
await p.fill("#pp-pitanje", "Da li je otkaz zakonito uručen?").catch(() => {});
await p.click("#pp-posalji").catch(() => {});
zapisi("pitanje", "odgovor prikazan sa izvorom (Član 185)", await cekaj(() => /Simuliran odgovor/.test(document.getElementById("pp-odgovor")?.innerText || "") && /185/.test(document.body.innerText), null, 15000));

// 8) Nacrt (model simuliran) — mora nositi napomenu o advokatskom pregledu
await p.click("#tab-nacrt").catch(() => {});
await p.selectOption("#nc-tip", "tuzba_naknada_stete").catch(() => {});
await p.fill("#nc-opis", "Tužba radi poništaja rešenja o otkazu i isplate zarade zaposlenom Marku Petroviću.").catch(() => {});
await p.click("#nc-generisi").catch(() => {});
zapisi("nacrt", "nacrt generisan i označen za pregled advokata", await cekaj(() => /mora pregledati advokat|pregledan od strane ovlašćenog advokata/i.test(document.getElementById("nc-rezultat")?.innerText || document.body.innerText), null, 15000));

// 9) Greška API-ja: Rad na predmetu dobija 500 → jasno stanje greške, navigacija i dalje radi
await p.route("**/api/case-actions/**", r => r.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"x"}' }));
await p.click("#tab-rad").catch(() => {});
await p.waitForTimeout(1200);
const t9 = await tekst();
zapisi("greska", "posle 500 nema lažnog „nema akcija“, prikazana je greška ili ništa", !/Nema (otvorenih )?akcija|Sve je završeno/.test(t9) || /greš|nije učitan|pokušajte/i.test(t9));
await p.unroute("**/api/case-actions/**");
await p.goto(BASE + "/app#/danas");
zapisi("greska", "navigacija na Danas posle greške radi", await cekaj(() => { const rl = document.getElementById("rl-stanje"); return rl && rl.dataset.stanje !== "ucitavanje"; }));

// 10) Manji ekran: isti predmet se otvara
await p.setViewportSize({ width: 1024, height: 768 });
await p.goto(BASE + `/app#/predmeti/${pid}`);
zapisi("ekran", "predmet se otvara i na 1024×768", await cekaj(() => /Petrovic protiv Gradnja Invest/.test(document.body.innerText), null, 10000));

await browser.close();
st = await stanje();
zapisi("bezbednost", "nijedan spoljni zahtev (pregledač i Python)", spoljni.length === 0 && st.spoljni_pokusaji === 0, spoljni.slice(0, 2).join(","));
zapisi("bezbednost", "nijedan upis u autonomy tabele", st.autonomy_upisi === 0);
zapisi("bezbednost", "svi redovi pripadaju korisniku A", st.vlasnici.join() === "uid-A", st.vlasnici.join());
zapisi("kvalitet", "nijedna JS greška", greskeJS.length === 0, greskeJS.slice(0, 2).join(" | "));
zapisi("kvalitet", "nijedan neočekivan 5xx sa servera", api500.length === 0, api500.slice(0, 4).join(","));
console.log("modeli pozvani:", st.pozivi_modela.join(","));
srv.kill();
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
