// Vindex V2 NG — QA-02: advokat menja vrstu JEDNOG dokumenta kroz STVARAN V2 /app nad PRAVIM api.app koji STVARNO upisuje.
// Pokretanje: `node tests/live-vrsta-dokumenta-e2e.mjs`. Server: tests/osb003_solo_server.py (stvarne rute, stvaran intake
// worker i dispečer događaja sa AI klasifikacijom dokaza — model zamenjen, uvek kaže „dopis“).
// Svaki korak se proverava u UI-ju I u bazi (GET /__osb003/stanje: vrste i brojevi, bez sadržaja).

import { chromium } from "playwright";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4537, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const dir = await mkdtemp(join(tmpdir(), "vx-qa02-"));
const TUZBA = join(dir, "tuzba_primer.pdf");
const gen = spawnSync(PY, ["-c", `
from reportlab.pdfgen import canvas
c = canvas.Canvas(r"${TUZBA}")
for i, r in enumerate(["TUZBA", "Osnovnom sudu u Beogradu", "Tuzilac: Petar Primerovic iz Beograda",
                       "Tuzeni: Primer Invest Test doo Beograd", "radi naknade stete zbog neispunjenja ugovora."]):
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

const np = await zahtev("/api/predmeti", { method: "POST", telo: { naziv: "QA-02 — vrsta dokumenta" }, token: "tok-A" });
const pid = (JSON.parse(np.b || "{}").predmet || {}).id;
zapisi("predmet", "predmet postoji i pripada A", np.s < 300 && typeof pid === "string" && pid.length === 36, String(np.s));

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const spoljni = [], greskeJS = [];
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
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const posao = () => p.evaluate(() => { const li = document.querySelector("#pd-poslovi .intake:last-child"); return li ? {
  tekst: li.innerText, dugmad: [...li.querySelectorAll("button")].map(b => b.textContent),
  izbor: [...li.querySelectorAll("select.intake__vrsta")].map(s => s.value),
  msg: li.querySelector(".intake__msg") && !li.querySelector(".intake__msg").hidden ? li.querySelector(".intake__msg").dataset.stanje + ":" + li.querySelector(".intake__msg").textContent : "" } : null; });
const poruka = () => cekaj(() => { const m = document.querySelector("#pd-poslovi .intake:last-child .intake__msg"); return !!m && !m.hidden && m.dataset.stanje !== "ucitavanje"; });
const klikni = (t) => p.locator("#pd-poslovi .intake:last-child button", { hasText: t }).first().click();
const docId = () => p.evaluate(() => { const s = document.querySelector("#pd-poslovi .intake:last-child select.intake__vrsta"); return s ? s.dataset.dokument : null; });

// 1) Prijem: AI kaže „tužba“ → advokat bira „žalba“ → prikaz i baza
await p.goto(`${BASE}/app#/predmeti/${pid}/prijem`);
await cekaj(() => !document.getElementById("odeljak-prijem").hidden);
await p.setInputFiles("#pd-fajlovi", TUZBA);
await p.click("#pd-otpremi");
await cekaj(() => document.querySelectorAll("#pd-poslovi .intake").length > 0);
await p.waitForTimeout(300);
await obradi();
const imaIzbor = await cekaj(() => !!document.querySelector("#pd-poslovi .intake:last-child select.intake__vrsta"), null, 20000);
let e = await posao(), st = await stanje();
zapisi("1.prijem", "UI nudi izbor vrste sa AI vrednošću „Tužba“; baza: lawsuit", imaIzbor && e.izbor.join() === "lawsuit" && e.tekst.includes("Tužba (pouzdanost")
  && st.vrste_prijema.join() === "lawsuit", JSON.stringify({ izbor: e.izbor, prijem: st.vrste_prijema }));
await p.selectOption("#pd-poslovi .intake:last-child select.intake__vrsta", "appeal");
await klikni("Sačuvaj vrstu");
await poruka();
await cekaj(() => document.querySelector("#pd-poslovi .intake:last-child").innerText.includes("odredio advokat"));
e = await posao(); st = await stanje();
zapisi("1.prijem", "UI: „Vrsta dokumenta je sačuvana: Žalba.“, prikaz Žalba + „odredio advokat“; baza: appeal, 1 audit zapis",
  e.msg === "uspeh:Vrsta dokumenta je sačuvana: Žalba." && e.tekst.includes("Žalba (pouzdanost") && e.tekst.includes("odredio advokat")
  && e.izbor.join() === "appeal" && st.vrste_prijema.join() === "appeal" && st.ispravke_vrste_audit === 1,
  JSON.stringify({ msg: e.msg, prijem: st.vrste_prijema, audit: st.ispravke_vrste_audit }));
const intakeDok = await docId();

await p.reload();
await cekaj(() => !document.getElementById("odeljak-prijem").hidden);
await p.setInputFiles("#pd-fajlovi", TUZBA);                 // isti sadržaj → isti posao (bez duplikata), stanje iz baze
await p.click("#pd-otpremi");
await cekaj(() => !!document.querySelector("#pd-poslovi .intake:last-child select.intake__vrsta"), null, 20000);
await cekaj(() => document.querySelector("#pd-poslovi .intake:last-child").innerText.includes("odredio advokat"));
e = await posao(); st = await stanje();
zapisi("1.prijem", "posle reload-a i ponovnog otvaranja posla i dalje Žalba, „odredio advokat“; bez novog dokumenta",
  e !== null && e.izbor.join() === "appeal" && e.tekst.includes("Žalba (pouzdanost") && st.vrste_prijema.length === 1, e ? e.izbor.join() : "nema posla");

// 2) Zastareo prikaz: drugi prozor je u međuvremenu izabrao „presuda“ → ovaj prozor ne gazi, prikazuje 409 i osvežava
const drugi = await zahtev(`/api/smart-intake/documents/${intakeDok}/vrsta`, { method: "POST", telo: { vrsta: "judgment", prethodna: "appeal" }, token: "tok-A" });
await p.selectOption("#pd-poslovi .intake:last-child select.intake__vrsta", "contract");
await klikni("Sačuvaj vrstu");
await poruka();
await cekaj(() => document.querySelector("#pd-poslovi .intake:last-child").innerText.includes("Presuda (pouzdanost"));
e = await posao(); st = await stanje();
zapisi("2.konflikt", "UI: „Vrsta nije promenjena: u međuvremenu…“, prikaz osvežen na Presudu; baza: judgment, bez ugovora",
  drugi.s === 200 && e.msg.startsWith("greska:Vrsta nije promenjena: u međuvremenu") && e.izbor.join() === "judgment"
  && st.vrste_prijema.join() === "judgment" && st.ispravke_vrste_audit === 2, JSON.stringify({ s: drugi.s, msg: e.msg.slice(0, 60), prijem: st.vrste_prijema }));

// 3) Prikačivanje + AI klasifikacija dokaza („dopis“) ne poništava ljudsku vrstu
await klikni("Potvrđujem pregled");
await cekaj(() => [...document.querySelectorAll("#pd-poslovi .intake:last-child button")].some(b => b.textContent === "Prikači ovom predmetu"), null, 20000);
await klikni("Prikači ovom predmetu");
await cekaj(() => document.querySelector("#pd-poslovi .intake:last-child").innerText.includes("Prikačeno ovom predmetu"));
const ob = await obradi();
st = await stanje();
zapisi("3.prikacivanje", "baza: u predmetu „judgment“ sa oznakom advokata posle AI klasifikacije; tvrdnje upisane",
  st.vrste_predmeta.join() === "tuzba_primer.pdf=judgment*" && ob.greske === 0 && st.nedispecovano === 0,
  JSON.stringify({ vrste: st.vrste_predmeta, ob, nedisp: st.nedispecovano }));
e = await posao();
zapisi("3.prikacivanje", "posle prikačivanja prijem više ne nudi izmenu vrste", e.izbor.length === 0, e.izbor.join());

// 4) Već prikačen dokument: izmena u predmetu (Dokumenti → dokument)
await p.goto(`${BASE}/app#/predmeti/${pid}/dokumenti`);
await p.reload();
await cekaj(() => document.querySelectorAll("#dok-lista li").length === 1, null, 15000);
const meta = await p.evaluate(() => document.querySelector("#dok-lista li").innerText);
await p.locator("#dok-lista li").first().click();
await cekaj(() => !!document.getElementById("dok-vrsta-izbor"));
const cinj = () => p.evaluate(() => { const dl = document.getElementById("dok-cinjenice"); const dt = [...dl.querySelectorAll("dt")].find(x => x.textContent === "Vrsta dokumenta");
  return dt ? dt.nextElementSibling.textContent : null; });
zapisi("4.predmet", "lista i detalj prikazuju „Presuda“; izbor postavljen na judgment",
  meta.includes("Presuda") && (await cinj()) === "Presuda" && (await p.inputValue("#dok-vrsta-izbor")) === "judgment", meta.slice(0, 80));
await p.selectOption("#dok-vrsta-izbor", "appeal");
await p.click("#dok-vrsta-sacuvaj");
await cekaj(() => { const m = document.getElementById("dok-vrsta-poruka"); return !!m && !m.hidden && m.dataset.stanje !== "ucitavanje"; });
const msgPredmet = () => p.evaluate(() => { const m = document.getElementById("dok-vrsta-poruka"); return m && !m.hidden ? m.dataset.stanje + ":" + m.textContent : ""; });
st = await stanje();
zapisi("4.predmet", "UI: „Vrsta dokumenta je sačuvana: Žalba.“ i činjenica Žalba; baza: appeal sa oznakom, 3 audit zapisa",
  (await msgPredmet()) === "uspeh:Vrsta dokumenta je sačuvana: Žalba." && (await cinj()) === "Žalba"
  && st.vrste_predmeta.join() === "tuzba_primer.pdf=appeal*" && st.ispravke_vrste_audit === 3, JSON.stringify({ m: await msgPredmet(), v: st.vrste_predmeta }));
await p.reload();
await cekaj(() => document.querySelectorAll("#dok-lista li").length === 1, null, 15000);
const posleReload = await p.evaluate(() => document.querySelector("#dok-lista li").innerText);
zapisi("4.predmet", "posle reload-a lista prikazuje Žalbu", posleReload.includes("Žalba"), posleReload.slice(0, 80));

// 5) Audit ne može da se upiše → nikad „sačuvano“; vrsta ostaje Žalba
await p.locator("#dok-lista li").first().click();
await cekaj(() => !!document.getElementById("dok-vrsta-izbor"));
await kvar("audit_immutable", "insert", true);
await p.selectOption("#dok-vrsta-izbor", "contract");
await p.click("#dok-vrsta-sacuvaj");
await cekaj(() => { const m = document.getElementById("dok-vrsta-poruka"); return !!m && !m.hidden && m.dataset.stanje !== "ucitavanje"; });
await kvar("audit_immutable", null, false);
st = await stanje();
const m5 = await msgPredmet();
zapisi("5.audit", "UI: „Ishod nije poznat…“ (ne „sačuvana“), prikaz Žalba; baza: appeal, i dalje 3 audit zapisa",
  m5.startsWith("nepoznato:Ishod nije poznat") && (await cinj()) === "Žalba" && st.vrste_predmeta.join() === "tuzba_primer.pdf=appeal*"
  && st.ispravke_vrste_audit === 3, JSON.stringify({ m5, v: st.vrste_predmeta }));

// 6) Izolacija
const dokPredmeta = await p.evaluate(() => document.querySelector("#dok-lista .docs__item").dataset.dok);
const tudj = await zahtev(`/api/evidence/predmeti/${pid}/dokumenti/${dokPredmeta}/vrsta`, { method: "POST", telo: { vrsta: "other", prethodna: "appeal" }, token: "tok-B" });
const tudjPrijem = await zahtev(`/api/smart-intake/documents/${intakeDok}/vrsta`, { method: "POST", telo: { vrsta: "other", prethodna: "judgment" }, token: "tok-B" });
st = await stanje();
zapisi("6.izolacija", "korisnik B: 404 u predmetu i u prijemu, ništa nije promenjeno", tudj.s === 404 && tudjPrijem.s === 404
  && st.vrste_predmeta.join() === "tuzba_primer.pdf=appeal*" && st.ispravke_vrste_audit === 3, `${tudj.s}/${tudjPrijem.s}`);
zapisi("6.izolacija", "nijedna veza van 127.0.0.1 (browser i server)", spoljni.length === 0 && st.spoljni_pokusaji === 0, spoljni.slice(0, 2).join());
zapisi("konzola", "bez grešaka stranice", greskeJS.length === 0, greskeJS.join(" | ").slice(0, 200));

await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
