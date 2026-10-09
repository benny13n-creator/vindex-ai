// Vindex — NS004 Task 4: novi javni sajt, u pravom pregledaču nad stvarnim api.py.
// Pokretanje: `node tests/site-e2e.mjs` (Python iz VX_PYTHON ili `python`).
//
// Oba V2 prekidača su ISKLJUČENA (VX_E2E_SAJT=1): sajt mora da radi kao u
// produkciji pre bilo kakve aktivacije. Ništa ne izlazi van 127.0.0.1.
// Snimci: shots/site/ (nisu u git-u).

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const OUT = fileURLToPath(new URL("../shots/site/", import.meta.url));
await mkdir(OUT, { recursive: true });
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

const dir = await mkdtemp(join(tmpdir(), "vx-site-"));
const PORT = 4495;
const SISTEM = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "HOME",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "pythonLocation", "LD_LIBRARY_PATH"];
const env = Object.fromEntries(SISTEM.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
Object.assign(env, {
  SUPABASE_URL: "https://fake.supabase.co", SUPABASE_ANON_KEY: "fake-anon-key", SUPABASE_SERVICE_KEY: "fake-service-key",
  SUPABASE_JWT_SECRET: "fake-jwt-secret-longer-than-32-chars-ok", OPENAI_API_KEY: "sk-fake", PINECONE_API_KEY: "fake-pinecone",
  PINECONE_HOST: "https://fake.pinecone.io", FIELD_ENCRYPTION_KEY: "e".repeat(64), FOUNDER_EMAILS: "ci@example.com",
  PYTHONUTF8: "1", PYTHONUNBUFFERED: "1", VX_E2E_SAJT: "1", VX_E2E_LOG: join(dir, "h.jsonl"), VX_E2E_PORT: String(PORT),
});
const py = spawn(process.env.VX_PYTHON || "python", ["tests/v2_ng_e2e_harness.py"], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let pyIzlaz = "";
py.stdout.on("data", d => pyIzlaz += d); py.stderr.on("data", d => pyIzlaz += d);
const dohvati = (put) => new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: put }, s => { let b = ""; s.on("data", d => b += d); s.on("end", () => r({ status: s.statusCode, loc: s.headers.location || "", telo: b })); }).on("error", () => r({ status: 0 })));
let gotov = false;
for (let i = 0; i < 600 && !gotov; i++) { gotov = (await dohvati("/")).status === 200; if (!gotov) await new Promise(r => setTimeout(r, 200)); }
zapisi("harness", "stvaran api.py (oba V2 prekidača isključena) servira /", gotov, gotov ? "" : pyIzlaz.slice(-600));
if (!gotov) { py.kill(); process.exit(1); }
const BASE = `http://127.0.0.1:${PORT}`;

const browser = await chromium.launch();
const rgb = (s) => (s.match(/[\d.]+/g) || []).map(Number);
const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const kontrast = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };

for (const [ime, w, h] of [["1440", 1440, 900], ["1920", 1920, 1080], ["1024", 1024, 768], ["390", 390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [], lose = [], greske = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  const p = await ctx.newPage();
  p.on("response", r => { if (new URL(r.url()).hostname === "127.0.0.1" && r.status() >= 400) lose.push(r.status() + " " + new URL(r.url()).pathname); });
  p.on("console", m => { if (m.type() === "error") greske.push(m.text()); });
  p.on("pageerror", e => greske.push(String(e)));
  const odg = await p.goto(BASE + "/");
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(() => Promise.all([...document.images].map(i => i.decode().catch(() => {}))));
  await p.waitForTimeout(300);
  const r = await p.evaluate(() => {
    const logo = document.querySelector(".logo img");
    const cs = getComputedStyle(document.querySelector("h1"));
    return {
      preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      logo: { put: new URL(logo.currentSrc).pathname, nw: logo.naturalWidth, nh: logo.naturalHeight, w: logo.getBoundingClientRect().width, h: logo.getBoundingClientRect().height, filter: getComputedStyle(logo).filter },
      platno: !!document.getElementById("pozadina") && getComputedStyle(document.getElementById("pozadina")).pointerEvents === "none",
      h1: document.querySelectorAll("h1").length, h1font: cs.fontFamily,
      cta: [...document.querySelectorAll("a.dugme")].map(a => a.getAttribute("href")),
      fontovi: [...document.fonts].filter(f => f.status === "loaded").map(f => f.family + " " + f.weight),
      boje: [...document.querySelectorAll("h1, .vodeci, .korak p, .nacelo p, .meni a, .podnozje a, .dugme")].filter(e => e.getClientRects().length)
        .map(e => ({ t: e.tagName + "." + e.className, c: getComputedStyle(e).color, bg: getComputedStyle(e).backgroundColor })),
      animira: window.__vxPozadina ? window.__vxPozadina.animira : null,
    };
  });
  await p.screenshot({ path: join(OUT, `pocetna-${ime}.png`), fullPage: true });
  await p.screenshot({ path: join(OUT, `pocetna-${ime}-prvi-ekran.png`) });
  const g = `sajt@${ime}`;
  zapisi(g, "200, jedan h1 u Source Serif 4", odg.status() === 200 && r.h1 === 1 && r.h1font.includes("Source Serif 4"));
  zapisi(g, "bez horizontalnog preliva", !r.preliv);
  zapisi(g, "kanonski logo: /v2/site/brand/…EXACT_LOOK.svg, izvorna razmera, bez filtera", r.logo.put === "/v2/site/brand/Vindex_Transparent_EXACT_LOOK.svg" && r.logo.nw === 1183 && Math.abs(r.logo.w - r.logo.h * 1183 / 309) <= 0.5 && r.logo.filter === "none", JSON.stringify(r.logo));
  zapisi(g, "V2 potpisna pozadina, pointer-events: none; reduced motion = mirna", r.platno && r.animira === false, String(r.animira));
  zapisi(g, "svi pozivi na akciju vode na /app", r.cta.length >= 2 && r.cta.every(x => x === "/app"), r.cta.join(","));
  zapisi(g, "fontovi V2 (IBM Plex Sans, Source Serif 4) učitani sa istog izvora", r.fontovi.some(f => f.startsWith("IBM Plex Sans")) && r.fontovi.some(f => f.startsWith("Source Serif 4")), r.fontovi.join("|"));
  const losKontrast = r.boje.filter(b => {
    const pozadina = b.bg === "rgba(0, 0, 0, 0)" ? "rgb(13, 14, 16)" : b.bg;
    return kontrast(b.c, pozadina) < 4.5;
  });
  zapisi(g, "tekst i linkovi ≥ 4,5:1 na svojoj površini", losKontrast.length === 0, losKontrast.map(b => b.t).slice(0, 3).join(","));
  zapisi(g, "nijedan neuspeo lokalni resurs, nijedan spoljni zahtev", lose.length === 0 && spoljni.length === 0, [...lose, ...spoljni].slice(0, 3).join(","));
  zapisi(g, "nijedna greška u konzoli", greske.length === 0, greske.slice(0, 2).join(" | "));
  // NS005 Task 12: sajt sme da tvrdi SAMO ono što je dokazano u Task 1–11 (NS005_OVERNIGHT_EVIDENCE.md).
  const t12 = await p.evaluate(() => {
    const tekst = document.querySelector("main").innerText;
    const kor = [...document.querySelectorAll(".korak")], nac = [...document.querySelectorAll(".nacelo")];
    const mreza = (lista) => lista.map((e, i) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return { i, x: Math.round(r.left), lev: cs.borderLeftWidth, gor: cs.borderTopWidth }; });
    return { tekst, koraci: kor.map(e => e.querySelector("h3").textContent), nacela: nac.map(e => e.querySelector("h3").textContent), mk: mreza(kor), mn: mreza(nac) };
  });
  zapisi(g, "bez nedokazanih tvrdnji (podsetnici, SMS/Viber/WhatsApp, OCR/skeniranje, automatsko prepoznavanje, SEF, garancije)",
    !/podsetni|SMS|Viber|WhatsApp|OCR|skenir|automatsk|SEF|e-faktur|garant|100\s?%|bez greške|nikad ne greši/i.test(t12.tekst), (t12.tekst.match(/podsetni|SMS|Viber|WhatsApp|OCR|skenir|automatsk|SEF|e-faktur|garant/i) || [""])[0]);
  zapisi(g, "devet dokazanih koraka i šest načela", JSON.stringify(t12.koraci) === JSON.stringify(["Predmeti", "Klijenti", "Spisi i pretraga", "Pravno pitanje", "Praksa i stavovi", "Nacrt podneska", "Ročišta i rokovi", "Naplata", "Kancelarija"])
    && JSON.stringify(t12.nacela) === JSON.stringify(["Stvarni podaci", "Svoji predmeti", "Greška je greška", "Vi odlučujete", "Izvor uz odgovor", "Neizvestan ishod se kaže"]), t12.koraci.join(",") + " | " + t12.nacela.join(","));
  if (w > 960) zapisi(g, "mreža 3 kolone: prvi u redu bez leve crte, naredni redovi sa gornjom crtom",
    [t12.mk, t12.mn].every(m => m.every(c => (c.i % 3 === 0 ? c.lev === "0px" && c.x === m[0].x : c.lev !== "0px") && (c.i >= 3 ? c.gor !== "0px" : true))), JSON.stringify(t12.mk.slice(0, 4)));
  else zapisi(g, "jedna kolona: svi koraci poravnati levo, bez leve crte", t12.mk.every(c => c.x === t12.mk[0].x && c.lev === "0px"));
  await ctx.close();
}

// Tastatura: vidljiv fokus, preskok na sadržaj, poziv na akciju
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route("**/*", r => (new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort()));
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  const fokusi = [];
  for (let i = 0; i < 6; i++) {
    await p.keyboard.press("Tab");
    fokusi.push(await p.evaluate(() => { const a = document.activeElement, s = getComputedStyle(a);
      return { t: (a.textContent || a.getAttribute("aria-label") || "").trim().slice(0, 24), obris: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2 }; }));
  }
  zapisi("tastatura", "prvi Tab: „Preskoči na sadržaj“; svaki fokus ima vidljiv obris ≥ 2 px", fokusi[0].t === "Preskoči na sadržaj" && fokusi.every(f => f.obris), fokusi.map(f => f.t + (f.obris ? "" : "(!)")).join(" → "));
  zapisi("tastatura", "redosled: preskok → logo → navigacija → „Uđi u aplikaciju“", fokusi[1].t === "Vindex — početna" && fokusi.some(f => f.t === "Uđi u aplikaciju"));
  await ctx.close();
}
// Bez reduced motion: pozadina se kreće (ista V2 logika)
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "no-preference" });
  await ctx.route("**/*", r => (new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort()));
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  await p.waitForTimeout(600);
  zapisi("pokret", "bez reduced motion pozadina animira (V2 potpis), sa reduced motion je mirna (gore)", await p.evaluate(() => window.__vxPozadina && window.__vxPozadina.animira === true));
  await ctx.close();
}

// Pravne stranice iz podnožja i povučene marketinške rute
for (const put of ["/privacy", "/terms", "/security", "/bezbednosni-list", "/dpa", "/ai-disclosure"]) {
  zapisi("pravne", `${put} odgovara 200`, (await dohvati(put)).status === 200);
}
const POVUCENE = { "/kako-radi": "/#rad", "/sposobnosti": "/#rad", "/za-advokate": "/#rad", "/web3": "/", "/bezbednost": "/#nacela",
  "/vizija": "/", "/tehnologija": "/", "/beta": "/#pristup", "/kontakt": "/#pristup" };
for (const [put, cilj] of Object.entries(POVUCENE)) {
  const r = await dohvati(put);
  zapisi("povucene", `${put} → 301 ${cilj}, bez starog sadržaja`, r.status === 301 && r.loc === cilj && !/<html/i.test(r.telo), `${r.status} ${r.loc}`);
}
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route("**/*", r => (new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort()));
  const p = await ctx.newPage();
  await p.goto(BASE + "/beta");
  const r = await p.evaluate(() => ({ put: location.pathname + location.hash, forma: document.querySelectorAll("form").length, tekst: document.body.innerText }));
  zapisi("povucene", "/beta u pregledaču: početna #pristup, bez forme i bez starih tvrdnji", r.put === "/#pristup" && r.forma === 0 && !/Founding|Digitalna imovina|lista čekanja/i.test(r.tekst), r.put);
  await ctx.close();
}
{
  const sm = await dohvati("/sitemap.xml");
  const loc = [...sm.telo.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => new URL(m[1]).pathname);
  zapisi("seo", "sitemap: početna i pravne stranice, nijedna povučena", loc.includes("/") && !Object.keys(POVUCENE).some(p => loc.includes(p)), loc.join(","));
}

await browser.close();
py.kill();
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS   (snimci: shots/site/)`);
process.exit(pada ? 1 : 0);
