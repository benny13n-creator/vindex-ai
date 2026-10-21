// Vindex — Website V2: javni sajt (7 stranica) i pre-auth ulaz, u pravom pregledaču nad stvarnim api.py.
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

// ── Website V2: sve javne stranice × šest širina ekrana ──────────────────────
// Website V3: /razvoj je povučen (301 → /funkcionalnosti; planovi razvoja nisu javni).
const STRANICE = ["/", "/kako-radi", "/funkcionalnosti", "/za-advokate", "/bezbednost", "/beta"];
const CTA = "Prijavi se za rani pristup";
const EKRANI = [["360", 360, 740], ["390", 390, 844], ["768", 768, 1024], ["1280", 1280, 800], ["1440", 1440, 900], ["1920", 1920, 1080]];
const ime = (put) => put === "/" ? "pocetna" : put.slice(1);
async function kontekst(opcije = {}) {
  // Legacy /app-legacy registruje /sw.js; pri prvoj instalaciji `controllerchange` ponovo učitava stranicu
  // (static/vindex.js), pa bi merenje palo usred navigacije. Ponašanje SW-a meri e2e:sw-isolation.
  const ctx = await browser.newContext({ reducedMotion: "reduce", serviceWorkers: "block", ...opcije });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  return { ctx, spoljni };
}

for (const [ek, w, h] of EKRANI) {
  const { ctx, spoljni } = await kontekst({ viewport: { width: w, height: h } });
  const p = await ctx.newPage();
  const lose = [], greske = [];
  p.on("response", r => { if (new URL(r.url()).hostname === "127.0.0.1" && r.status() >= 400) lose.push(r.status() + " " + new URL(r.url()).pathname); });
  p.on("console", m => { if (m.type() === "error") greske.push(m.text()); });
  p.on("pageerror", e => greske.push(String(e)));
  for (const put of STRANICE) {
    const odg = await p.goto(BASE + put);
    await p.evaluate(() => document.fonts.ready);
    await p.evaluate(() => Promise.all([...document.images].map(i => { i.loading = "eager"; return i.decode().catch(() => {}); })));
    await p.waitForTimeout(150);
    const r = await p.evaluate(() => {
      const vidljiv = (e) => { const b = e.getBoundingClientRect(); return e.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true, opacityProperty: true }) && b.width > 0 && b.height > 0; };
      const tekstualni = [...document.querySelectorAll("body *")].filter(e => vidljiv(e) && [...e.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim()));
      const sirina = document.documentElement.clientWidth;
      const pozadina = (e) => { for (let x = e; x; x = x.parentElement) { const c = getComputedStyle(x).backgroundColor, a = c.startsWith("rgba") ? parseFloat(c.split(",")[3]) : 1; if (a >= 0.95) return c; } return "rgb(13, 14, 16)"; };
      const logo = document.querySelector(".logo img");
      return {
        preliv: document.documentElement.scrollWidth > sirina,
        izvanEkrana: tekstualni.filter(e => e.getBoundingClientRect().right > sirina + 1).map(e => e.tagName + ":" + e.textContent.trim().slice(0, 30)).slice(0, 3),
        h1: document.querySelectorAll("h1").length, h1font: getComputedStyle(document.querySelector("h1")).fontFamily,
        najmanji: Math.min(...tekstualni.map(e => parseFloat(getComputedStyle(e).fontSize))),
        kontrast: tekstualni.map(e => ({ t: e.tagName + "." + e.className + ":" + e.textContent.trim().slice(0, 24), c: getComputedStyle(e).color, bg: pozadina(e) })),
        cta: [...document.querySelectorAll("a.dugme")].map(a => a.getAttribute("href")),
        ciljevi: [...document.querySelectorAll("a.dugme, button, summary, input, select, textarea")].filter(vidljiv)
          .filter(e => e.getBoundingClientRect().height < 40).map(e => e.tagName + ":" + (e.textContent || e.id).trim().slice(0, 20)),
        logo: { put: new URL(logo.currentSrc).pathname, w: logo.getBoundingClientRect().width, h: logo.getBoundingClientRect().height, nw: logo.naturalWidth },
        fontovi: [...document.fonts].filter(f => f.status === "loaded").map(f => f.family),
        slike: [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src),
      };
    });
    const g = `${ime(put)}@${ek}`;
    const losKontrast = r.kontrast.filter(b => kontrast(b.c, b.bg) < 4.5);
    zapisi(g, "200, jedan h1 u Source Serif 4, V2 fontovi učitani", odg.status() === 200 && r.h1 === 1 && r.h1font.includes("Source Serif 4")
      && r.fontovi.includes("IBM Plex Sans") && r.fontovi.includes("Source Serif 4"));
    zapisi(g, "bez horizontalnog preliva i bez teksta van ekrana", !r.preliv && r.izvanEkrana.length === 0, r.izvanEkrana.join(" | "));
    zapisi(g, "najmanji vidljiv tekst ≥ 12 px; tekst ≥ 4,5:1 na svojoj površini", r.najmanji >= 12 && losKontrast.length === 0,
      `min ${r.najmanji}px ${losKontrast.slice(0, 2).map(b => b.t + " " + kontrast(b.c, b.bg).toFixed(2)).join(" | ")}`);
    zapisi(g, "dugmad i polja visine ≥ 40 px", r.ciljevi.length === 0, r.ciljevi.join(","));
    zapisi(g, "svi pozivi na akciju vode samo na /beta ili /app, a /beta je ponuđen", r.cta.includes("/beta") && r.cta.every(x => x === "/beta" || x === "/app"), r.cta.join(","));
    zapisi(g, "kanonski logo u izvornoj razmeri", r.logo.put === "/v2/site/brand/vindex-logo-tamna.png" && r.logo.nw === 357 && Math.abs(r.logo.w - r.logo.h * 357 / 305) <= 0.5);
    zapisi(g, "sve slike učitane", r.slike.length === 0, r.slike.join(","));
    if (["390", "1440"].includes(ek)) await p.screenshot({ path: join(OUT, `${ime(put)}-${ek}.png`), fullPage: true });
    if (ek === "1440" && put === "/") await p.screenshot({ path: join(OUT, `pocetna-1440-prvi-ekran.png`) });
  }
  zapisi(`sajt@${ek}`, "nijedan neuspeo lokalni resurs, nijedan spoljni zahtev, nijedna greška u konzoli",
    lose.length === 0 && spoljni.length === 0 && greske.length === 0, [...lose, ...spoljni, ...greske].slice(0, 3).join(" | "));
  await ctx.close();
}

// ── Prvi ekran: naslov, opis i primarni poziv vidljivi bez pomeranja ─────────
for (const [ek, w, h] of [["390", 390, 844], ["1440", 1440, 900]]) {
  const { ctx } = await kontekst({ viewport: { width: w, height: h } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  await p.evaluate(() => document.fonts.ready);
  const r = await p.evaluate(() => {
    const u = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return b.top >= 0 && b.bottom <= innerHeight; };
    const a = document.querySelector('.uvod a.dugme[href="/beta"]');
    return { h1: u("h1"), opis: u(".uvod .vodeci"), cta: u('.uvod a.dugme[href="/beta"]'), ctaTekst: a.textContent.trim(), h1px: parseFloat(getComputedStyle(document.querySelector("h1")).fontSize) };
  });
  zapisi(`prvi-ekran@${ek}`, "naslov (≥ 34 px), opis i „Prijavi se za rani pristup“ vidljivi bez pomeranja", r.h1 && r.opis && r.cta && r.ctaTekst === CTA && r.h1px >= 34, JSON.stringify(r));
  await ctx.close();
}

// ── Tastatura i mobilni meni ────────────────────────────────────────────────
{
  const { ctx } = await kontekst({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  const fokusi = [];
  for (let i = 0; i < 8; i++) {
    await p.keyboard.press("Tab");
    fokusi.push(await p.evaluate(() => { const a = document.activeElement, s = getComputedStyle(a);
      return { t: (a.textContent || a.getAttribute("aria-label") || "").trim().slice(0, 24), obris: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2 }; }));
  }
  zapisi("tastatura", "prvi Tab: „Preskoči na sadržaj“; svaki fokus ima vidljiv obris ≥ 2 px", fokusi[0].t === "Preskoči na sadržaj" && fokusi.every(f => f.obris), fokusi.map(f => f.t + (f.obris ? "" : "(!)")).join(" → "));
  zapisi("tastatura", "redosled: preskok → logo → navigacija → Prijava → Prijavi se za rani pristup",
    JSON.stringify(fokusi.map(f => f.t)) === JSON.stringify(["Preskoči na sadržaj", "Vindex — početna", "Kako radi", "Funkcionalnosti", "Za advokate", "Bezbednost", "Prijava", CTA.slice(0, 24)]), fokusi.map(f => f.t).join(" → "));
  await p.keyboard.press("Shift+Tab"); await p.keyboard.press("Shift+Tab");
  await p.goto(BASE + "/");
  await p.keyboard.press("Tab"); await p.keyboard.press("Enter");
  zapisi("tastatura", "preskok vodi fokus na sadržaj", await p.evaluate(() => location.hash === "#sadrzaj"));
  await ctx.close();
}
{
  const { ctx } = await kontekst({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  const pre = await p.evaluate(() => ({ meni: getComputedStyle(document.querySelector(".meni")).display, mob: !!document.querySelector(".meni-mob").getBoundingClientRect().height }));
  await p.click(".meni-mob summary");
  const linkovi = await p.evaluate(() => [...document.querySelectorAll(".meni-mob__panel a")].filter(a => a.getBoundingClientRect().height >= 40).map(a => a.getAttribute("href")));
  zapisi("mobilni-meni", "desktop meni skriven, „Meni“ otvara sve stranice, rani pristup i Prijavu (cilj ≥ 40 px), bez Razvoja",
    pre.meni === "none" && pre.mob && ["/kako-radi", "/funkcionalnosti", "/za-advokate", "/bezbednost", "/beta", "/app"].every(x => linkovi.includes(x)) && !linkovi.includes("/razvoj"), linkovi.join(","));
  await p.click('.meni-mob__panel a[href="/funkcionalnosti"]');
  zapisi("mobilni-meni", "link iz menija otvara stranicu", await p.evaluate(() => location.pathname === "/funkcionalnosti"));
  await ctx.close();
}

// ── Pokret: reduced motion = mirna pozadina, inače V2 potpis animira ─────────
for (const [rm, ocekivano] of [["reduce", false], ["no-preference", true]]) {
  const { ctx } = await kontekst({ viewport: { width: 1440, height: 900 }, reducedMotion: rm });
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  await p.waitForTimeout(600);
  zapisi("pokret", `prefers-reduced-motion: ${rm} → pozadina ${ocekivano ? "animira" : "mirna"}`, await p.evaluate(() => window.__vxPozadina && window.__vxPozadina.animira) === ocekivano);
  await ctx.close();
}

// ── Website V3: otkrivanje odeljaka — sa pokretom se sve otkrije, bez pokreta je odmah vidljivo ──
for (const [rm, sPokretom] of [["no-preference", true], ["reduce", false]]) {
  const { ctx } = await kontekst({ viewport: { width: 1440, height: 900 }, reducedMotion: rm });
  const p = await ctx.newPage();
  await p.goto(BASE + "/");
  const pre = await p.evaluate(() => ({ pokret: document.body.classList.contains("pokret"),
    skriveno: [...document.querySelectorAll(".otkrij")].filter(e => getComputedStyle(e).opacity === "0").length, ukupno: document.querySelectorAll(".otkrij").length }));
  for (let y = 0; y < 30; y++) { await p.mouse.wheel(0, 700); await p.waitForTimeout(60); }
  await p.waitForTimeout(800);
  const posle = await p.evaluate(() => [...document.querySelectorAll(".otkrij")].filter(e => getComputedStyle(e).opacity !== "1").length);
  zapisi("pokret", `${rm}: ${sPokretom ? "odeljci skriveni pa otkriveni pri skrolovanju" : "bez klase pokret, sve odmah vidljivo"}`,
    pre.pokret === sPokretom && (sPokretom ? pre.skriveno > 0 : pre.skriveno === 0) && posle === 0, JSON.stringify({ ...pre, posle }));
  await ctx.close();
}

// ── Katalog: pretraga po tekstu ─────────────────────────────────────────────
{
  const { ctx } = await kontekst({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + "/funkcionalnosti");
  const stanje = () => p.evaluate(() => ({ vidljive: [...document.querySelectorAll(".stavka")].filter(s => !s.hidden).map(s => s.dataset.status + ":" + s.dataset.id),
    ukupno: document.querySelectorAll(".stavka").length, poruka: document.getElementById("filter-rezultat").textContent, filter: !document.getElementById("filter").hidden }));
  const a = await stanje();
  zapisi("katalog", "bez JS filter je sakriven (atribut hidden se poštuje)", await p.evaluate(() => { const f = document.getElementById("filter"); f.hidden = true; const v = f.checkVisibility(); f.hidden = false; return v === false; }));
  await p.fill("#filter-tekst", "ocr");
  const b = await stanje();
  await p.fill("#filter-tekst", "");
  const c = await stanje();
  const bezStatusa = await p.evaluate(() => !document.getElementById("filter-status") && !document.querySelector(".status, .legenda"));
  zapisi("katalog", "pretraga vidljiva sa JS; „ocr“ sužava listu, prazna vraća sve; nema statusnih oznaka ni filtera po statusu",
    a.filter && b.vidljive.length >= 1 && b.vidljive.length < a.ukupno && /Prikazano/.test(b.poruka) && c.vidljive.length === a.ukupno && bezStatusa,
    `${b.vidljive.join(",")} | ${b.poruka} | ${c.vidljive.length}/${a.ukupno}`);
  await ctx.close();
}

// ── Beta prijava: uspeh, greška servera, greška validacije, prekid veze, prazna forma ──
async function beta(odgovor, popuni = true) {
  const { ctx } = await kontekst({ viewport: { width: 390, height: 844 } });
  let poslato = null;
  if (odgovor) await ctx.route("**/waitlist/prijava", async r => { poslato = JSON.parse(r.request().postData()); if (odgovor === "prekid") return r.abort("connectionreset"); return r.fulfill(odgovor); });
  const p = await ctx.newPage();
  const greske = [];
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(BASE + "/beta");
  if (popuni) { await p.fill("#beta-ime", "Petar Primer"); await p.fill("#beta-email", "petar@primer.rs"); await p.fill("#beta-firma", "AK Primer"); }
  await p.click("#beta-posalji");
  await p.waitForFunction(() => !document.getElementById("beta-ishod").hidden || document.querySelector('[aria-invalid="true"]'), null, { timeout: 8000 }).catch(() => {});
  const r = await p.evaluate(() => ({ ishod: document.getElementById("beta-ishod").hidden ? "" : document.getElementById("beta-ishod").innerText,
    klasa: document.getElementById("beta-ishod").className, uloga: document.getElementById("beta-ishod").getAttribute("role"),
    fokus: document.activeElement.id, nevazeca: [...document.querySelectorAll('[aria-invalid="true"]')].map(e => e.id),
    poruke: [...document.querySelectorAll(".polje__greska")].filter(e => !e.hidden).map(e => e.textContent), dugme: !document.getElementById("beta-posalji").checkVisibility() }));
  await p.screenshot({ path: join(OUT, `beta-${typeof odgovor === "object" && odgovor ? odgovor.status : odgovor || (popuni ? "stvarni-backend" : "prazno")}.png`), fullPage: false });
  await ctx.close();
  return { ...r, poslato, greske };
}
{
  const u = await beta({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, poruka: "Vaš nalog je već aktivan. Prijavite se!" }) });
  zapisi("beta", "uspeh (200, ok:true): evidentirano za adresu, bez obećanja mejla, bez otkrivanja stanja naloga, fokus na ishodu",
    /evidentirana za adresu petar@primer\.rs/.test(u.ishod) && /ne šalje e-poštom/.test(u.ishod) && !/aktivan/.test(u.ishod) && u.uloga === "status" && u.fokus === "beta-ishod" && u.dugme
    && u.poslato && u.poslato.ime === "Petar Primer" && u.poslato.firma === "AK Primer", u.ishod);
  const s = await beta({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Internal Server Error" }) });
  zapisi("beta", "greška servera (500): „Server nije potvrdio prijavu“ (ishod upisa nije tvrđen), role=alert, bez uspeha", /nije potvrdio prijavu/.test(s.ishod) && !/nije sačuvana/.test(s.ishod) && s.uloga === "alert" && !/evidentirana/.test(s.ishod) && !s.dugme, s.ishod);
  const v = await beta({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }] }) });
  zapisi("beta", "greška validacije (422): polje e-pošte označeno, poruka o proveri podataka", /proverite unete podatke/.test(v.ishod) && v.nevazeca.includes("beta-email"), v.ishod);
  const k = await beta("prekid");
  zapisi("beta", "prekid veze: ishod nepoznat, može bezbedno ponovo", /nije poznato da li je prijava sačuvana/.test(k.ishod) && /bezbedno poslati ponovo/.test(k.ishod), k.ishod);
  const prazno = await beta(null, false);
  zapisi("beta", "prazna forma: ništa se ne šalje, obe greške uz polja, fokus na prvom", prazno.nevazeca.join() === "beta-ime,beta-email" && prazno.fokus === "beta-ime" && prazno.poruke.length === 2, JSON.stringify(prazno));
  const stvarno = await beta(null, true);
  zapisi("beta", "stvaran api.py bez dostupne baze: forma prikazuje grešku, nikad uspeh", /nije potvrdio|nije poznato/.test(stvarno.ishod) && !/evidentirana/.test(stvarno.ishod), stvarno.ishod);
}

// ── Pre-auth ulaz (/app-legacy, kuda V2 /app šalje neprijavljenog korisnika) ──
for (const tema of ["dark", "light"]) {
  for (const [ek, w, h] of [["390", 390, 844], ["1440", 1440, 900]]) {
    const { ctx } = await kontekst({ viewport: { width: w, height: h } });
    if (tema === "light") await ctx.addInitScript(() => { try { localStorage.setItem("vx_theme", "light"); localStorage.setItem("theme", "light"); } catch (e) {} });
    const p = await ctx.newPage();
    const greske = [];
    p.on("pageerror", e => greske.push(String(e)));
    const odg = await p.goto(BASE + "/app-legacy?posle=app");
    const ima = await p.evaluate(() => !!document.getElementById("vx-landing"));
    if (!ima) {
      zapisi(`pre-auth@${tema}-${ek}`, "/app-legacy servira legacy dokument sa #vx-landing", false,
        `${odg && odg.status()} ${p.url()} ${(await p.content()).slice(0, 300).replace(/\s+/g, " ")}`);
      await ctx.close(); continue;
    }
    if (tema === "light") await p.evaluate(() => document.body.classList.add("light-theme"));
    await p.waitForFunction(() => getComputedStyle(document.getElementById("vx-landing")).display !== "none", null, { timeout: 10000 }).catch(() => {});
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(200);
    const r = await p.evaluate(() => {
      const l = document.getElementById("vx-landing");
      const pozadina = (e) => { for (let x = e; x; x = x.parentElement) { const c = getComputedStyle(x).backgroundColor, a = c.startsWith("rgba") ? parseFloat(c.split(",")[3]) : 1; if (a >= 0.95) return c; } return "rgb(255,255,255)"; };
      const tekst = [...l.querySelectorAll("*")].filter(e => e.getClientRects().length && [...e.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim()));
      return { vidljiv: getComputedStyle(l).display !== "none", tekst: l.innerText, preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth, sirina: document.documentElement.scrollWidth + "/" + document.documentElement.clientWidth + " " + [...document.body.querySelectorAll("*")].filter(e => e.getClientRects().length && e.getBoundingClientRect().right > document.documentElement.clientWidth + 1).slice(0, 4).map(e => e.tagName + "#" + e.id + "." + e.className).join(","),
        h1: getComputedStyle(l.querySelector("h1")).fontFamily, beta: !!l.querySelector('a[href="/beta"]'),
        boje: tekst.map(e => ({ t: e.textContent.trim().slice(0, 20), c: getComputedStyle(e).color, bg: pozadina(e) })),
        najmanji: Math.min(...tekst.map(e => parseFloat(getComputedStyle(e).fontSize))) };
    });
    const g = `pre-auth@${tema}-${ek}`;
    const los = r.boje.filter(b => kontrast(b.c, b.bg) < 4.5);
    zapisi(g, "ulaz vidljiv, V2 tipografija, link na /beta, bez preliva", r.vidljiv && r.h1.includes("Source Serif 4") && r.beta && !r.preliv, JSON.stringify({ v: r.vidljiv, h1: r.h1, b: r.beta, p: r.preliv, s: r.sirina }));
    zapisi(g, "bez zastarelih tvrdnji (847 zakona, 10 sekundi, AES-256, podsetnici, ograničen broj mesta, besplatno, Pravo na dohvat ruke)",
      !/847|10 sekundi|AES|obaveštenja 7|ograničen broj|besplatno|dohvat ruke|Operativni Sistem/i.test(r.tekst), r.tekst.slice(0, 120));
    zapisi(g, "tekst ≥ 4,5:1 i ≥ 12 px", los.length === 0 && r.najmanji >= 12, los.slice(0, 2).map(b => b.t + " " + kontrast(b.c, b.bg).toFixed(2)).join(" | ") + ` min ${r.najmanji}`);
    if (ek === "1440" || tema === "dark") await p.screenshot({ path: join(OUT, `pre-auth-${tema}-${ek}.png`) });
    if (tema === "dark" && ek === "1440") {
      await p.click(".vxp-akcije button");
      const modal = await p.evaluate(() => ({ otvoren: document.getElementById("auth-modal").classList.contains("open"), naslov: document.getElementById("auth-modal-title").innerText, pod: document.getElementById("auth-modal-sub").innerText }));
      zapisi(g, "„Prijavite se“ otvara postojeći modal prijave; početni tekst modala odgovara prijavi", modal.otvoren && modal.naslov === "Dobrodošli." && modal.pod === "Prijavite se na vaš nalog.", JSON.stringify(modal));
      await p.screenshot({ path: join(OUT, `pre-auth-modal-1440.png`) });
    }
    const plutajuci = () => p.evaluate(() => [...document.querySelectorAll("body *")].filter(e => !e.closest("#vx-landing") && e.id !== "cv" && !e.closest("#auth-modal")
      && ["fixed", "sticky"].includes(getComputedStyle(e).position) && e.checkVisibility({ opacityProperty: true, visibilityProperty: true })
      && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().bottom > 0).map(e => e.id || e.className));
    const pre = await plutajuci();
    zapisi(g, "pre prijave nema legacy plutajućih kontrola (glas, povratne informacije, mobilna navigacija, kursor, linija obaveštenja)", pre.length === 0, pre.join(","));
    if (tema === "dark" && ek === "1440") {
      await p.evaluate(() => { document.getElementById("vx-landing").style.display = "none"; });
      const posle = await plutajuci();
      zapisi(g, "kada je ulaz sakriven (prijavljen korisnik), kontrole se vraćaju nepromenjene", posle.includes("vx-voice-fab") && posle.includes("feedback-fab"), posle.join(","));
    }
    zapisi(g, "nijedna greška stranice", greske.length === 0, greske.slice(0, 2).join(" | "));
    await ctx.close();
  }
}

// ── Pravne stranice, preusmerenja, sitemap ──────────────────────────────────
for (const put of ["/privacy", "/terms", "/security", "/bezbednosni-list", "/dpa", "/ai-disclosure", "/status"]) {
  zapisi("pravne", `${put} odgovara 200`, (await dohvati(put)).status === 200);
}
const POVUCENE = { "/sposobnosti": "/funkcionalnosti", "/platforma": "/kako-radi", "/kontakt": "/beta", "/web3": "/", "/vizija": "/", "/tehnologija": "/", "/razvoj": "/funkcionalnosti" };
for (const [put, cilj] of Object.entries(POVUCENE)) {
  const r = await dohvati(put);
  zapisi("preusmerenja", `${put} → 301 ${cilj}, bez starog sadržaja`, r.status === 301 && r.loc === cilj && !/<html/i.test(r.telo), `${r.status} ${r.loc}`);
}
{
  const sm = await dohvati("/sitemap.xml");
  const loc = [...sm.telo.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => new URL(m[1]).pathname);
  zapisi("seo", "sitemap: sve javne stranice, nijedno preusmerenje", STRANICE.every(s => loc.includes(s)) && !Object.keys(POVUCENE).some(s => loc.includes(s)), loc.join(","));
  const app = await dohvati("/app");
  zapisi("aplikacija", "/app i dalje odgovara 200 (prekidači isključeni → klasična aplikacija)", app.status === 200 && /auth-modal/.test(app.telo));
}

await browser.close();
py.kill();
await rm(dir, { recursive: true, force: true });
console.log(`\n${ukupno - pada}/${ukupno} PASS   (snimci: shots/site/)`);
process.exit(pada ? 1 : 0);
