// Vindex V2 NG — OSB002 Task 2: isključena autonomija (pre migracije 136) nad STVARNIM api.py i STVARNIM V2 /app.
// Pokretanje: `node tests/live-pre136-e2e.mjs`. Harness: tests/v2_ng_e2e_harness.py sa VX_E2E_AUTONOMIJA:
//   pre136  — tabele migracije 136 ne postoje (PGRST205), kao produkcija danas → SVE provere moraju proći;
//   spremno — POZITIVNA KONTROLA: tabela postoji i vraća spreman rad → provere „ništa pripremljeno nije prikazano"
//             MORAJU pasti. Ako kontrola prođe, test ne meri ništa i ceo skript pada.
// Ništa ne izlazi van 127.0.0.1 (čuvar soketa u harness-u + presretanje u pregledaču); svaki upis/RPC puca.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const RAD = "0000c0de-0000-4000-8000-000000000001";   // id spremnog rada u kontroli (tests/v2_ng_e2e_harness.py)
const PREDMET = "aaaa0136-0000-4000-8000-00000000000a"; // UUID predmet korisnika A (isti fajl)
const SISTEM = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "pythonLocation", "LD_LIBRARY_PATH"];
// Dugmad odluke glase „Prihvatam“/„Odbacujem“ (index.html #vpr-prihvati/#vpr-odbaci). OSB002: raniji obrazac
// /prihvati|odbaci/ nije pogađao nijedno od njih — provera akcija je bila slepa. Zato i koren reči i elementi po id-u.
const AKCIJE = /prihvat|odbac|predloži kao znanje/i;
const ODLUKA_ID = ["vpr-odluka-blok", "vpr-prihvati", "vpr-odbaci", "vpr-znanje-blok"];
const TVRDNJA = /Vindex je pripremio|pripremljen rad|Pripremljeno za pregled|Priprema za ročište/i;

async function prolaz(rezim, PORT) {
  const rez = [];
  const zapisi = (grupa, naziv, ok, detalj = "") => rez.push({ grupa, naziv, ok: !!ok, detalj });
  const dir = await mkdtemp(join(tmpdir(), "vx-pre136-"));
  const LOG = join(dir, "harness.jsonl");
  const env = Object.fromEntries(SISTEM.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
  Object.assign(env, {
    SUPABASE_URL: "https://fake.supabase.co", SUPABASE_ANON_KEY: "fake-anon-key", SUPABASE_SERVICE_KEY: "fake-service-key",
    SUPABASE_JWT_SECRET: "fake-jwt-secret-longer-than-32-chars-ok", OPENAI_API_KEY: "sk-fake", PINECONE_API_KEY: "fake-pinecone",
    PINECONE_HOST: "https://fake.pinecone.io", FIELD_ENCRYPTION_KEY: "f".repeat(64), FOUNDER_EMAILS: "ci@example.com",
    PYTHONUTF8: "1", PYTHONUNBUFFERED: "1", VINDEX_V2_NG_PRIMARY_ENABLED: "1", VX_E2E_LOG: LOG, VX_E2E_PORT: String(PORT),
    VX_E2E_AUTONOMIJA: rezim, GIT_SHA: "5eedc0de5eedc0de5eedc0de5eedc0de5eedc0de",
  });
  const py = spawn(process.env.VX_PYTHON || "python", ["tests/v2_ng_e2e_harness.py"], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  let pyIzlaz = "";
  py.stdout.on("data", d => pyIzlaz += d); py.stderr.on("data", d => pyIzlaz += d);
  let gotov = false;
  for (let i = 0; i < 600 && !gotov; i++) {
    gotov = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/app" }, s => { s.resume(); r(s.statusCode === 200); }).on("error", () => r(false)));
    if (!gotov) await new Promise(r => setTimeout(r, 200));
  }
  zapisi("harness", `stvaran api.py (primarni V2 /app), režim ${rezim}`, gotov, gotov ? "" : pyIzlaz.slice(-800));
  if (!gotov) { py.kill(); return rez; }
  const BASE = `http://127.0.0.1:${PORT}`;
  const browser = await chromium.launch();
  const spoljni = [], metodi = [], konzola = [], odgovori = {};
  const ses = (id, token) => JSON.stringify({ access_token: token, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
  const cekaj = (p, fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") { spoljni.push(u.href); return r.abort(); }
    if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
    [KLJUC, ses("korisnik-A", "vx-e2e-A")]);
  const p = await ctx.newPage();
  p.on("request", q => { const u = new URL(q.url()); if (u.pathname.startsWith("/api/")) metodi.push(q.method() + " " + u.pathname); });
  p.on("response", async s => {
    const u = new URL(s.url());
    if (u.pathname === "/api/workspace" || u.pathname.startsWith("/api/autonomy/")) {
      try { odgovori[u.pathname] = { status: s.status(), telo: await s.json() }; } catch { odgovori[u.pathname] = { status: s.status() }; }
    }
  });
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  const vidljivo = (id) => p.evaluate((id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0; }, id);
  const ekran = () => p.evaluate((re) => {
    const vid = (e) => !!e && !e.closest("[hidden]") && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
    return { tekst: document.body.innerText,
      akcije: [...document.querySelectorAll("button, a")].filter(vid).map(b => (b.textContent || "").trim()).filter(t => new RegExp(re, "i").test(t)) };
  }, AKCIJE.source);

  // 1) Danas
  await p.goto(BASE + "/app#/danas");
  const danas = await cekaj(p, () => { const rl = document.getElementById("rl-stanje"); return rl && rl.dataset.stanje !== "ucitavanje" && (document.getElementById("rl-korpe").children.length > 0 || !rl.hidden); });
  zapisi("danas", "ekran Danas se učitao", danas);
  await p.waitForTimeout(400);
  const w = odgovori["/api/workspace"];
  zapisi("api", "GET /api/workspace → 200, vindex_je_pripremio_stanje = NIJE_UKLJUCENO, lista prazna",
    w && w.status === 200 && w.telo && w.telo.vindex_je_pripremio_stanje === "NIJE_UKLJUCENO" && Array.isArray(w.telo.vindex_je_pripremio) && w.telo.vindex_je_pripremio.length === 0,
    w ? `${w.status} ${w.telo && w.telo.vindex_je_pripremio_stanje}` : "nema odgovora");
  const d1 = await ekran();
  zapisi("danas", "blok „Vindex je pripremio“ NIJE prikazan", !(await vidljivo("dp-blok")));
  zapisi("danas", "nigde tvrdnja da je rad pripremljen", !TVRDNJA.test(d1.tekst));
  zapisi("danas", "nijedna vidljiva akcija autonomnog rada", d1.akcije.length === 0, d1.akcije.join(","));

  // 2) Predmet: registar → predmet (Pregled, gde stoji „pripremljen rad predmeta") → Dokumenti
  await p.click('.sidenav__item:has-text("Predmeti")').catch(() => {});
  zapisi("nav", "Predmeti: registar korisnika A", await cekaj(p, () => document.querySelectorAll("#rows tr").length > 0));
  await p.click(`#rows tr[data-id="${PREDMET}"] .case__name`).catch(() => {});
  zapisi("nav", "otvaranje predmeta", await cekaj(p, (id) => location.hash.startsWith("#/predmeti/" + id), PREDMET));
  await cekaj(p, () => !!document.getElementById("zp-prip-blok"), null, 8000);
  await p.waitForTimeout(800);
  const lista = odgovori["/api/autonomy/work-items"];
  zapisi("api", "GET /api/autonomy/work-items (Pregled predmeta) → stanje NIJE_UKLJUCENO, 0 stavki",
    lista && lista.status === 200 && lista.telo && lista.telo.stanje === "NIJE_UKLJUCENO" && (lista.telo.stavke || []).length === 0,
    lista ? `${lista.status} ${lista.telo && lista.telo.stanje}` : "nema odgovora");
  const d2 = await ekran();
  zapisi("predmet", "Pregled predmeta: blok pripremljenog rada NIJE prikazan", !(await vidljivo("zp-prip-blok")));
  zapisi("predmet", "Pregled predmeta: nema tvrdnje ni akcije autonomnog rada", !TVRDNJA.test(d2.tekst) && d2.akcije.length === 0, d2.akcije.join(","));
  await p.click("#tab-dokumenti").catch(() => {});
  zapisi("nav", "kartica Dokumenti prikazuje dokumente predmeta", await cekaj(p, () => document.querySelectorAll("#dok-lista button").length > 0));

  // 3) Direktna adresa rada (#/pripremljeno/<id>) — ne sme da ponudi prihvatanje/odbacivanje
  await p.goto(BASE + "/app#/pripremljeno/" + RAD);
  await cekaj(p, () => { const e = document.getElementById("pripremljeno-pogled"); return !!e && !e.hidden; }, null, 8000);
  await p.waitForTimeout(1200);
  const det = odgovori["/api/autonomy/work-items/" + RAD];
  zapisi("api", "GET /api/autonomy/work-items/{id} → 404 (rad ne može da postoji bez migracije 136)", det && det.status === 404, det ? String(det.status) : "nema odgovora");
  const d3 = await ekran();
  const odlukaVidljiva = [];
  for (const id of ODLUKA_ID) if (await vidljivo(id)) odlukaVidljiva.push(id);
  zapisi("rad", "direktna adresa rada: nijedna akcija prihvati/odbaci", d3.akcije.length === 0 && odlukaVidljiva.length === 0,
    [...d3.akcije, ...odlukaVidljiva].join(","));

  // 4) Nazad na Danas
  await p.goto(BASE + "/app#/danas");
  const nazad = await cekaj(p, () => { const rl = document.getElementById("rl-stanje"); return rl && rl.dataset.stanje !== "ucitavanje"; });
  zapisi("nav", "povratak na Danas, blok i dalje skriven", nazad && !(await vidljivo("dp-blok")));

  await browser.close();
  py.kill();
  await new Promise(r => py.once("exit", r));
  const dn = (await readFile(LOG, "utf8")).split("\n").filter(Boolean).map(l => JSON.parse(l));
  zapisi("bezbednost", "upit na autonomy_work_items je stvarno prošao kroz simulirani režim", dn.some(z => z.vrsta === "AUTONOMIJA-UPIT" && z.tabela === "autonomy_work_items"));
  zapisi("bezbednost", "0 upisa i 0 RPC: nema naplate, nema upisa radnog proizvoda, nema zauzimanja ciklusa",
    !dn.some(z => z.vrsta === "UPIS-POKUSAN"), JSON.stringify(dn.filter(z => z.vrsta === "UPIS-POKUSAN")).slice(0, 200));
  zapisi("bezbednost", "0 poziva /api/cron/* i nijedan POST na /api/autonomy/*", !metodi.some(m => /\/api\/cron\/|^POST \/api\/autonomy\//.test(m)),
    metodi.filter(m => /cron|^POST \/api\/autonomy/.test(m)).join(","));
  zapisi("bezbednost", "V2 je slao SAMO GET", metodi.every(m => m.startsWith("GET ")), metodi.filter(m => !m.startsWith("GET ")).slice(0, 3).join(","));
  zapisi("bezbednost", "0 spoljnih veza (pregledač i Python — nema poziva modela)", spoljni.length === 0 && !dn.some(z => /spolj/.test(z.vrsta)), spoljni.slice(0, 2).join(","));
  zapisi("bezbednost", "nijedna JS greška", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).slice(0, 2).join(" | "));
  await rm(dir, { recursive: true, force: true });
  return rez;
}

const ispisi = (naslov, rez) => { console.log(`\n== ${naslov}`); for (const r of rez) console.log(`${r.ok ? "PASS" : "FAIL"}  [${r.grupa}] ${r.naziv}${r.detalj ? " — " + r.detalj : ""}`); };
const pre = await prolaz("pre136", 4497);
ispisi("pre136 (produkcija danas): sve mora proći", pre);
const kon = await prolaz("spremno", 4498);
ispisi("POZITIVNA KONTROLA (tabela postoji, spreman rad): provere izloženosti MORAJU pasti", kon);

const prePada = pre.filter(r => !r.ok);
const ocekivano = ["blok „Vindex je pripremio“ NIJE prikazan", "nigde tvrdnja da je rad pripremljen",
  "Pregled predmeta: blok pripremljenog rada NIJE prikazan", "direktna adresa rada: nijedna akcija prihvati/odbaci"];
const kontrolaUhvatila = ocekivano.every(n => kon.some(r => r.naziv === n && !r.ok));
const kontrolaHarness = kon.some(r => r.grupa === "harness" && r.ok);
console.log(`\npre136: ${pre.length - prePada.length}/${pre.length} PASS; kontrola: ${kon.filter(r => !r.ok).length} provera palo (očekivano: ${ocekivano.length}+)`);
if (prePada.length) { console.log("NEUSPEH: isključena autonomija nije dokazana"); process.exit(1); }
if (!kontrolaHarness || !kontrolaUhvatila) { console.log("NEUSPEH: pozitivna kontrola NIJE pala — test ne razlikuje izložen od skrivenog rada"); process.exit(1); }
console.log("OK: isključena autonomija dokazana, kontrola osetljivosti pala kako treba");
process.exit(0);
