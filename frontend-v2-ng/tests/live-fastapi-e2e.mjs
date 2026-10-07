// Vindex V2 NG — NS002 Task 5: stvaran pregledač + STVARNA FastAPI aplikacija, isti izvor.
// Pokretanje: `node tests/live-fastapi-e2e.mjs` (podiže tests/v2_ng_e2e_harness.py;
// Python iz VX_PYTHON ili `python`, sa instaliranim requirements.txt).
//
// Pregledač učitava /v2/preview/?rezim=live koji servira api.py, šalje stvarne
// HTTP zahteve, i izvršava se stvarna ruta lista_predmeta. Zamenjeni su samo
// rezultat prijave i Supabase izvor (vidi harness). Ništa ne sme van 127.0.0.1:
// ni pregledač (route čuvar) ni Python (čuvar soketa) — svaki pokušaj je FAIL.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const SVI_TOKENI = ["vx-e2e-A", "vx-e2e-B", "vx-e2e-240", "vx-e2e-prazan", "vx-e2e-1037", "vx-e2e-sporiA", "vx-e2e-xss", "vx-e2e-opozvan"];
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}

// ── Harness: okruženje OD NULE, samo lažne vrednosti ─────────────────────
const dir = await mkdtemp(join(tmpdir(), "vx-e2e-"));
const LOG = join(dir, "harness.jsonl");
const PORT = 4491;
const SISTEM = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "pythonLocation", "LD_LIBRARY_PATH"];
const env = Object.fromEntries(SISTEM.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
Object.assign(env, {
  SUPABASE_URL: "https://fake.supabase.co", SUPABASE_ANON_KEY: "fake-anon-key", SUPABASE_SERVICE_KEY: "fake-service-key",
  SUPABASE_JWT_SECRET: "fake-jwt-secret-longer-than-32-chars-ok", OPENAI_API_KEY: "sk-fake", PINECONE_API_KEY: "fake-pinecone",
  PINECONE_HOST: "https://fake.pinecone.io", FIELD_ENCRYPTION_KEY: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  FOUNDER_EMAILS: "ci@example.com", PYTHONUTF8: "1", PYTHONUNBUFFERED: "1",
  VINDEX_V2_NG_PREVIEW_ENABLED: "1", VX_E2E_LOG: LOG, VX_E2E_PORT: String(PORT),
});
const py = spawn(process.env.VX_PYTHON || "python", ["tests/v2_ng_e2e_harness.py"], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let pyIzlaz = "";
py.stdout.on("data", d => pyIzlaz += d); py.stderr.on("data", d => pyIzlaz += d);
let gotov = false;
for (let i = 0; i < 600 && !gotov; i++) {
  gotov = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/v2/preview/" }, s => { s.resume(); r(s.statusCode === 200); }).on("error", () => r(false)));
  if (!gotov) await new Promise(r => setTimeout(r, 200));
}
zapisi("harness", "stvarna FastAPI aplikacija servira /v2/preview/ (preview uključen samo u testu)", gotov, gotov ? "" : pyIzlaz.slice(-800));
if (!gotov) { py.kill(); process.exit(1); }
const BASE = `http://127.0.0.1:${PORT}`;

const dnevnik = async () => (await readFile(LOG, "utf8")).split("\n").filter(Boolean).map(l => JSON.parse(l));
const upiti = async () => (await dnevnik()).filter(z => z.vrsta === "upit" && z.tabela === "predmeti");

// ── Pregledač: samo loopback; beleži metod svakog zahteva ───────────────
const browser = await chromium.launch();
const spoljni = [], metodi = [], konzola = [];
const ses = (id, token) => JSON.stringify({ access_token: token, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id, email: id + "@primer.test" } });

async function otvori(pocetna) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.route("**/*", (r) => {
    const h = new URL(r.request().url()).hostname;
    if (h === "127.0.0.1" || h === "localhost") return r.continue();
    spoljni.push(r.request().url()); return r.abort();
  });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, pocetna]);
  const p = await ctx.newPage();
  p.on("request", q => metodi.push(q.method() + " " + new URL(q.url()).pathname));
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`${BASE}/v2/preview/?rezim=live`);
  await p.waitForFunction(() => { const e = document.getElementById("empty"); return !e.hidden ? e.dataset.stanje !== "ucitavanje" : document.querySelectorAll("#rows tr").length > 0; }, null, { timeout: 20000 }).catch(() => {});
  const drugi = await ctx.newPage();
  await drugi.goto(`${BASE}/v2/preview/src/tokens.css`);
  return { ctx, p, drugi };
}
const postavi = (o, v) => o.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ekran = (p) => p.evaluate(() => ({
  ids: [...document.querySelectorAll("#rows tr")].map(t => t.dataset.id),
  stanje: document.getElementById("empty").hidden ? "registar" : (document.getElementById("empty").dataset.stanje || ""),
  naslov: document.getElementById("empty-title").textContent,
  broj: document.getElementById("count").textContent,
  tekst: document.body.innerText, memorija: window.__vxPredmetaUMemoriji(),
}));
const cekaj = (p, fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const samo = (e, vlasnik) => e.ids.length > 0 && e.ids.every(id => id.startsWith(vlasnik + "-"));

// 1. Korisnik A — 12 predmeta (+3 zatvorena na serveru)
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"));
  const e = await ekran(o.p);
  zapisi("1.A-12", "12 aktivnih predmeta korisnika A, broj „12 predmeta“", e.ids.length === 12 && samo(e, "korisnik-A") && e.broj === "12 predmeta", `${e.ids.length} ${e.broj}`);
  const u = (await upiti()).filter(x => x.eq.some(([k, v]) => k === "user_id" && v === "korisnik-A"));
  zapisi("1.A-12", "stvarna ruta: filter vlasnika iz prijave (user_id = korisnik-A)", u.length >= 1);
  zapisi("5.status", "stvarna ruta: status=aktivan na serveru; zatvoreni predmeti nisu prikazani", u.every(x => x.eq.some(([k, v]) => k === "status" && v === "aktivan")) && !e.ids.some(id => /-009\d\d$/.test(id)));
  zapisi("summary", "stvarna ruta koristi summary projekciju (bez case_dna)", u.every(x => x.select.includes("tuzilac") && !x.select.includes("case_dna") && x.select !== "*"), u[0] && u[0].select);
  await o.ctx.close();
}
// 2. 240 predmeta
{
  const o = await otvori(ses("korisnik-240", "vx-e2e-240"));
  const e = await ekran(o.p);
  zapisi("2.240", "svih 240 prikazano, bez duplikata", e.ids.length === 240 && new Set(e.ids).size === 240 && e.broj === "240 predmeta", `${e.ids.length}`);
  await o.ctx.close();
}
// 3. 0 predmeta
{
  const o = await otvori(ses("korisnik-prazan", "vx-e2e-prazan"));
  const e = await ekran(o.p);
  zapisi("3.prazno", "uspešno čitanje, 0 predmeta → „Nema aktivnih predmeta“", e.stanje === "prazno" && e.naslov === "Nema aktivnih predmeta" && e.broj === "0 predmeta", `${e.stanje}`);
  await o.ctx.close();
}
// 4. 401 — token koji server ne prihvata
{
  const o = await otvori(ses("korisnik-X", "vx-e2e-opozvan"));
  const e = await ekran(o.p);
  zapisi("4.401", "401 iz stvarne rute → „greska-prijava“, NIJE prazna kancelarija", e.stanje === "greska-prijava" && e.ids.length === 0 && !/Nema aktivnih/.test(e.naslov), e.stanje);
  await o.ctx.close();
}
// 6. Straničenje — 1037 predmeta, 7 u brisanju
{
  const pre = (await upiti()).length;
  const o = await otvori(ses("korisnik-1037", "vx-e2e-1037"));
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 1000);
  const e = await ekran(o.p);
  const u = (await upiti()).slice(pre).filter(x => x.eq.some(([k, v]) => k === "user_id" && v === "korisnik-1037"));
  const opsezi = u.map(x => x.opseg && x.opseg[0]).filter(x => x !== null);
  zapisi("6.stranice", "stvarna ruta pozvana za offset 0, 500, 1000", [0, 500, 1000].every(o2 => opsezi.includes(o2)), opsezi.join(","));
  zapisi("6.stranice", "1030 jedinstvenih (7 u brisanju izostavljeno), broj = prikazani", e.ids.length === 1030 && new Set(e.ids).size === 1030 && e.broj === "1030 predmeta", `${e.ids.length} ${e.broj}`);
  await o.ctx.close();
}
// 7. Odjava + 8. A → B
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"));
  await postavi(o, ses("korisnik-B", "vx-e2e-B"));
  await cekaj(o.p, () => [...document.querySelectorAll("#rows tr")].some(t => t.dataset.id.startsWith("korisnik-B")));
  const b = await ekran(o.p);
  zapisi("8.A→B", "posle promene sesije: samo predmeti B", samo(b, "korisnik-B") && b.ids.length === 12, `${b.ids.slice(0, 1)}`);
  await postavi(o, null);
  await cekaj(o.p, () => document.getElementById("empty").dataset.stanje === "bez-prijave");
  const x = await ekran(o.p);
  zapisi("7.odjava", "odjava: nijedan predmet na ekranu ni u memoriji", x.stanje === "bez-prijave" && x.ids.length === 0 && x.memorija === 0 && !/Predmet korisnik-B/.test(x.tekst), x.stanje);
  await o.ctx.close();
}
// 9. Zakasneli A (1,5 s na serveru) posle B
{
  const o = await otvori(null);
  await postavi(o, ses("korisnik-sporiA", "vx-e2e-sporiA"));
  await cekaj(o.p, () => document.getElementById("empty").dataset.stanje === "ucitavanje");
  await postavi(o, ses("korisnik-B", "vx-e2e-B"));
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length === 12);
  await new Promise(r => setTimeout(r, 2200));
  const e = await ekran(o.p);
  zapisi("9.zakasneli", "ekran ostaje B posle zakasnelog odgovora za A", samo(e, "korisnik-B"), e.ids.slice(0, 1).join(","));
  await o.ctx.close();
}
// 10. Zlonameran naziv
{
  const o = await otvori(ses("korisnik-xss", "vx-e2e-xss"));
  const r = await o.p.evaluate(() => ({ el: document.querySelectorAll("#rows img, #rows script").length, xss: window.__xss }));
  zapisi("10.xss", "HTML iz stvarnog odgovora je tekst, ništa se ne izvršava", r.el === 0 && r.xss === undefined, JSON.stringify(r));
  await o.ctx.close();
}
// 11. ?user_id=B sa tokenom A — direktan zahtev ka stvarnoj ruti
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"));
  const pre = (await upiti()).length;
  const r = await o.p.evaluate(async () => {
    const z = JSON.parse(localStorage.getItem("sb-czsxymueizfqrbbgqqob-auth-token"));
    const odg = await fetch("/api/predmeti?view=summary&status=aktivan&user_id=korisnik-B", { headers: { Authorization: "Bearer " + z.access_token } });
    const t = await odg.json();
    return { status: odg.status, ids: t.predmeti.map(p => p.id) };
  });
  const u = (await upiti()).slice(pre);
  zapisi("11.user_id", "falsifikovan ?user_id=B uz token A: server vraća samo A", r.status === 200 && r.ids.length === 12 && r.ids.every(id => id.startsWith("korisnik-A-")), `${r.ids.length}`);
  zapisi("11.user_id", "stvarni upit: user_id = korisnik-A, nikad korisnik-B", u.length >= 1 && u.every(x => x.eq.some(([k, v]) => k === "user_id" && v === "korisnik-A") && !x.eq.some(([k, v]) => k === "user_id" && v === "korisnik-B")));
  const vxApi = await o.p.evaluate(async () => (await window.VxApi.get("/api/predmeti", { parametri: { user_id: "korisnik-B" } })).greska.kod);
  zapisi("11.user_id", "V2 transport ni ne šalje user_id (CONFIG_ERROR)", vxApi === "CONFIG_ERROR", vxApi);
  await o.ctx.close();
}

await browser.close();
py.kill();
await new Promise(r => py.once("exit", r));

// ── Globalne provere ─────────────────────────────────────────────────────
const d = await dnevnik();
zapisi("bezbednost", "0 upisa (lažni Supabase puca na svaki upis)", !d.some(z => z.vrsta === "UPIS-POKUSAN"), JSON.stringify(d.filter(z => z.vrsta === "UPIS-POKUSAN")).slice(0, 120));
zapisi("bezbednost", "0 spoljnih veza iz Python procesa (Supabase/OpenAI/Pinecone/…)", !d.some(z => /spolj/.test(z.vrsta)), JSON.stringify(d.filter(z => /spolj/.test(z.vrsta))).slice(0, 160));
zapisi("bezbednost", "0 spoljnih zahteva iz pregledača", spoljni.length === 0, spoljni.slice(0, 3).join(","));
const neGet = metodi.filter(m => !m.startsWith("GET "));
zapisi("bezbednost", "pregledač je slao SAMO GET", neGet.length === 0, neGet.slice(0, 3).join(","));
zapisi("bezbednost", "preview ruta je bila registrovana u stvarnoj aplikaciji", d.some(z => z.vrsta === "spreman" && z.preview_ruta === true));
const sviTekstovi = [konzola.join("\n"), izlaz.join("\n"), pyIzlaz, JSON.stringify(d)].join("\n");
zapisi("bezbednost", "nijedan token u konzoli, izlazu, logu servera ni dnevniku harness-a", !SVI_TOKENI.some(t => sviTekstovi.includes(t)));
zapisi("bezbednost", "nijedna JS greška stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
