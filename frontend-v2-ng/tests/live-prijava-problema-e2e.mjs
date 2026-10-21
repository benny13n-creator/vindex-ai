// Vindex V2 NG — Website V3: prijava problema ili predloga iz aplikacije (stvaran api.py + Chromium).
// Pokretanje: `node tests/live-prijava-problema-e2e.mjs` (Python iz VX_PYTHON ili `python`).
//
// Harness: tests/v2_ng_e2e_harness.py (primarni /app, lažni Supabase koji PUCA na svaki upis,
// lažni tokeni, nijedna veza van 127.0.0.1). Ishod rute podrške se u većini provera zadaje
// kroz `route` (uspeh, 503, 429, prekid), a jedna provera ide do STVARNE rute: bez baze i bez
// SMTP-a ona mora vratiti 503, a dijalog ne sme reći „primljeno“.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const OUT = fileURLToPath(new URL("../shots/prijava-problema/", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}

await mkdir(OUT, { recursive: true });
const dir = await mkdtemp(join(tmpdir(), "vx-prijava-"));
const LOG = join(dir, "harness.jsonl");
const PORT = 4497;
const SISTEM = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "pythonLocation", "LD_LIBRARY_PATH"];
const env = Object.fromEntries(SISTEM.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
Object.assign(env, {
  SUPABASE_URL: "https://fake.supabase.co", SUPABASE_ANON_KEY: "fake-anon-key", SUPABASE_SERVICE_KEY: "fake-service-key",
  SUPABASE_JWT_SECRET: "fake-jwt-secret-longer-than-32-chars-ok", OPENAI_API_KEY: "sk-fake", PINECONE_API_KEY: "fake-pinecone",
  PINECONE_HOST: "https://fake.pinecone.io", FIELD_ENCRYPTION_KEY: "f".repeat(64),
  FOUNDER_EMAILS: "ci@example.com", PYTHONUTF8: "1", PYTHONUNBUFFERED: "1",
  VINDEX_V2_NG_PRIMARY_ENABLED: "1", VX_E2E_LOG: LOG, VX_E2E_PORT: String(PORT),
  // `spremno`: harness tada prihvata lažni token i za `shared.deps.get_current_user` (ruta podrške).
  VX_E2E_AUTONOMIJA: "spremno",
  GIT_SHA: "5eedc0de5eedc0de5eedc0de5eedc0de5eedc0de",
});
const py = spawn(process.env.VX_PYTHON || "python", ["tests/v2_ng_e2e_harness.py"], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let pyIzlaz = "";
py.stdout.on("data", d => pyIzlaz += d); py.stderr.on("data", d => pyIzlaz += d);
let gotov = false;
for (let i = 0; i < 600 && !gotov; i++) {
  gotov = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/app" }, s => { s.resume(); r(s.statusCode === 200); }).on("error", () => r(false)));
  if (!gotov) await new Promise(r => setTimeout(r, 200));
}
zapisi("harness", "stvaran api.py sa primarnim prekidačem servira /app", gotov, gotov ? "" : pyIzlaz.slice(-800));
if (!gotov) { py.kill(); process.exit(1); }
const BASE = `http://127.0.0.1:${PORT}`;

const browser = await chromium.launch();
const ses = (id, token) => JSON.stringify({ access_token: token, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const cekaj = (p, fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const greske = [];

/** `odgovor`: null = stvarna ruta; "prekid" = prekinuta veza; objekat = route.fulfill. */
async function otvori(pocetna, { sirina = 1440, visina = 900, odgovor = null } = {}) {
  const ctx = await browser.newContext({ viewport: { width: sirina, height: visina }, reducedMotion: "reduce" });
  const poslato = [];
  await ctx.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") return r.abort();
    if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
    if (u.pathname === "/api/support/poruka") {
      poslato.push({ telo: JSON.parse(r.request().postData() || "{}"), zaglavlja: r.request().headers() });
      if (odgovor === "prekid") return r.abort("connectionreset");
      if (odgovor) return r.fulfill(odgovor);
    }
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, pocetna]);
  const p = await ctx.newPage();
  p.on("pageerror", e => greske.push("PAGEERROR " + e));
  await p.goto(BASE + "/app");
  return { ctx, p, poslato };
}
const stanje = (p) => p.evaluate(() => {
  const d = document.getElementById("prijava-dugme"), dl = document.getElementById("prijava-dijalog"), i = document.getElementById("prijava-ishod");
  const b = d && d.getBoundingClientRect();
  return {
    dugme: !!d && !d.hidden && getComputedStyle(d).display !== "none", oznaka: d && d.getAttribute("aria-label"),
    uEkranu: !!b && b.left >= 0 && b.top >= 0 && b.right <= innerWidth && b.bottom <= innerHeight, velicina: b ? [b.width, b.height] : null,
    otvoren: !!dl && dl.open, fokus: document.activeElement && document.activeElement.id,
    ishod: i && !i.hidden ? i.textContent : "", uloga: i && i.getAttribute("role"),
    greska: (document.getElementById("prijava-greska") || {}).hidden === false ? document.getElementById("prijava-greska").textContent : "",
    opis: (document.getElementById("prijava-opis") || {}).value, ekran: (document.getElementById("prijava-ekran") || {}).textContent,
  };
});
const OPIS = "Lista predmeta se ne učitava posle prijave.";
async function posalji(p, opis = OPIS, kategorija = "ai") {
  await p.click("#prijava-dugme");
  await p.selectOption("#prijava-kategorija", kategorija);
  await p.fill("#prijava-opis", opis);
  await p.click("#prijava-posalji");
}

// P1: bez prijave nema kontrole
{
  const o = await otvori(null);
  await cekaj(o.p, () => document.getElementById("empty").dataset.stanje === "bez-prijave");
  const s = await stanje(o.p);
  zapisi("P1.bez-prijave", "neprijavljen korisnik ne vidi dugme za prijavu problema", !s.dugme, JSON.stringify(s.dugme));
  await o.ctx.close();
}

// P2: prijavljen — dugme, dijalog, tastatura, ESC, fokus
for (const [sirina, visina] of [[1440, 900], [390, 844]]) {
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"), { sirina, visina });
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  let s = await stanje(o.p);
  zapisi(`P2.@${sirina}`, "dugme vidljivo u ekranu, sa pristupačnim nazivom, cilj ≥ 44 px", s.dugme && s.uEkranu && s.oznaka === "Prijavi problem ili pošalji predlog" && s.velicina[0] >= 44 && s.velicina[1] >= 44, JSON.stringify(s.velicina));
  await o.p.screenshot({ path: join(OUT, `zatvoreno-${sirina}.png`) });
  await o.p.focus("#prijava-dugme");
  await o.p.keyboard.press("Enter");
  s = await stanje(o.p);
  zapisi(`P2.@${sirina}`, "Enter otvara dijalog; fokus na izboru vrste; uz poruku piše naziv ekrana", s.otvoren && s.fokus === "prijava-kategorija" && s.ekran === "Predmeti", JSON.stringify(s));
  const unutra = await o.p.evaluate(() => { const b = document.getElementById("prijava-dijalog").getBoundingClientRect(); return b.left >= 0 && b.right <= innerWidth && b.top >= 0 && b.bottom <= innerHeight; });
  zapisi(`P2.@${sirina}`, "dijalog stane u ekran", unutra);
  await o.p.screenshot({ path: join(OUT, `otvoreno-${sirina}.png`) });
  await o.p.keyboard.press("Escape");
  s = await stanje(o.p);
  zapisi(`P2.@${sirina}`, "ESC zatvara dijalog i vraća fokus na dugme", !s.otvoren && s.fokus === "prijava-dugme", JSON.stringify({ o: s.otvoren, f: s.fokus }));
  await o.ctx.close();
}

// P3: validacija — kratak opis se ne šalje
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"), { odgovor: { status: 200, contentType: "application/json", body: "{}" } });
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  await posalji(o.p, "kratko");
  const s = await stanje(o.p);
  zapisi("P3.validacija", "opis kraći od 10 znakova: greška uz polje, ništa nije poslato", /najmanje 10/.test(s.greska) && o.poslato.length === 0 && s.otvoren, JSON.stringify(s.greska));
  await o.ctx.close();
}

// P4: uspeh — tačno telo, token i ključ idempotentnosti, istinita poruka sa brojem
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"), { odgovor: { status: 200, contentType: "application/json",
    body: JSON.stringify({ ok: true, sacuvano: true, obavesteno: false, broj: "abcdef12", message: "x" }) } });
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  await posalji(o.p);
  await cekaj(o.p, () => !document.getElementById("prijava-ishod").hidden);
  const s = await stanje(o.p);
  const z = o.poslato[0] || { telo: {}, zaglavlja: {} };
  zapisi("P4.uspeh", "telo je SAMO kategorija, opis i naziv ekrana (bez ID-a predmeta, korisnika i snimka)",
    JSON.stringify(Object.keys(z.telo)) === JSON.stringify(["kategorija", "poruka", "kontekst"]) && z.telo.kategorija === "ai" && z.telo.poruka === OPIS && z.telo.kontekst === "Predmeti", JSON.stringify(z.telo));
  zapisi("P4.uspeh", "token u Authorization i Idempotency-Key u zaglavlju", z.zaglavlja.authorization === "Bearer vx-e2e-A" && /^[0-9a-f-]{36}$/.test(z.zaglavlja["idempotency-key"] || ""));
  zapisi("P4.uspeh", "poruka: primljena i sačuvana pod brojem; polje očišćeno; uloga status", /sačuvana pod brojem abcdef12/.test(s.ishod) && s.opis === "" && s.uloga === "status", s.ishod);
  await o.p.screenshot({ path: join(OUT, `uspeh-1440.png`) });
  await o.p.click("#prijava-zatvori");
  zapisi("P4.uspeh", "Zatvori vraća korisnika na rad (dijalog zatvoren, registar i dalje prikazan)", await o.p.evaluate(() => !document.getElementById("prijava-dijalog").open && document.querySelectorAll("#rows tr").length > 0));
  await o.ctx.close();
}

// P5: neuspesi — nikad „primljeno“, tekst ostaje
for (const [naziv, odgovor, ocekivano] of [
  ["503 (nije sačuvana ni poslata)", { status: 503, contentType: "application/json", body: '{"detail":"x"}' }, /Nije potvrđeno da je prijava primljena/],
  ["prekid veze", "prekid", /Nije potvrđeno da je prijava primljena/],
  ["429 (previše prijava)", { status: 429, contentType: "application/json", body: '{"detail":"x"}' }, /više prijava u kratkom roku/],
  ["401 (istekla sesija)", { status: 401, contentType: "application/json", body: '{"detail":"x"}' }, /Sesija je istekla/],
]) {
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"), { odgovor });
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  await posalji(o.p);
  await cekaj(o.p, () => !document.getElementById("prijava-ishod").hidden);
  const s = await stanje(o.p);
  zapisi("P5.neuspeh", `${naziv}: istinita poruka (role=alert), bez „primljena“, tekst ostaje u polju`,
    ocekivano.test(s.ishod) && !/primljena i/.test(s.ishod) && s.uloga === "alert" && s.opis === OPIS, s.ishod);
  await o.ctx.close();
}

// P6: STVARNA ruta (bez simulacije) — dva puta do api.py.
//  a) Pregledač (sa Idempotency-Key): sloj idempotentnosti ovog harness-a ne prihvata lažni token,
//     pa zahtev ne stiže do rute; dijalog ipak ne sme reći „primljena“.
//  b) Isti token direktno na rutu (bez ključa): lažna baza odbija upis, SMTP nije podešen → 503.
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"));
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  const odg = o.p.waitForResponse(r => new URL(r.url()).pathname === "/api/support/poruka", { timeout: 15000 }).catch(() => null);
  await posalji(o.p);
  const r = await odg;
  await cekaj(o.p, () => !document.getElementById("prijava-ishod").hidden);
  const s = await stanje(o.p);
  zapisi("P6.stvarna-ruta", "pregledač → stvaran api.py bez potvrde: dijalog nikad ne kaže „primljena“, tekst ostaje",
    !!r && !r.ok() && !/primljena i/.test(s.ishod) && s.uloga === "alert" && s.opis === OPIS, `${r && r.status()} — ${s.ishod}`);
  const direktno = await o.p.request.post(BASE + "/api/support/poruka", {
    headers: { Authorization: "Bearer vx-e2e-A", "Content-Type": "application/json" },
    data: { kategorija: "tehnicko", poruka: OPIS, kontekst: "Predmeti" } });
  const upisi = (await readFile(LOG, "utf8")).split(/\r?\n/).filter(Boolean).map(l => JSON.parse(l))
    .filter(z => z.vrsta === "UPIS-POKUSAN" && z.put === "/api/support/poruka").map(z => z.tabela);
  zapisi("P6.stvarna-ruta", "ruta bez baze i bez SMTP-a: 503 i bez „ok:true“ (pokušan upis u support_tickets je odbijen)",
    direktno.status() === 503 && !(await direktno.text()).replace(/\s/g, "").includes('"ok":true') && upisi.includes("support_tickets"),
    `${direktno.status()} upis: ${[...new Set(upisi)].join(",")}`);
  await o.ctx.close();
}

// P7: naziv ekrana nikad ne nosi identifikator predmeta
{
  const o = await otvori(ses("korisnik-A", "vx-e2e-A"));
  await cekaj(o.p, () => document.querySelectorAll("#rows tr").length > 0);
  const nazivi = await o.p.evaluate(() => ["#/predmet/11111111-2222-3333-4444-555555555555/analiza", "#/danas", "#/znanje", "#/nesto?x=1"].map(h => window.VxPrijavaProblema.nazivEkrana(h)));
  zapisi("P7.kontekst", "#/predmet/<id>/… → „Predmet“ (bez ID-a); Danas, Znanje; nepoznato → Predmeti", JSON.stringify(nazivi) === JSON.stringify(["Predmet", "Danas", "Znanje", "Predmeti"]), nazivi.join(","));
  await o.ctx.close();
}

await browser.close();
py.kill();
await new Promise(r => py.once("exit", r));
const d = (await readFile(LOG, "utf8")).split("\n").filter(Boolean).map(l => JSON.parse(l));
zapisi("bezbednost", "0 spoljnih veza iz Python procesa", !d.some(z => /spolj/.test(z.vrsta)));
zapisi("bezbednost", "nijedan token u izlazu ni logu harness-a", ![...izlaz, pyIzlaz].some(t => t.includes("vx-e2e-A")));
zapisi("bezbednost", "nijedna JS greška na V2 stranici", greske.length === 0, greske.slice(0, 2).join(" | "));
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS   (snimci: shots/prijava-problema/)`);
process.exit(pada ? 1 : 0);
