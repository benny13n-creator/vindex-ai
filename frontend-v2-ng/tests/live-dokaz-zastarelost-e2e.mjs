// Vindex V2 NG — VCR001 T07: ručni unos tvrdnje (Analiza) i kalkulator zastarelosti (Rad) kroz STVARAN V2 /app nad
// PRAVIM api.app koji upisuje. Pokretanje: `node tests/live-dokaz-zastarelost-e2e.mjs`.
// Server: tests/osb003_solo_server.py (prave rute, worker, dispečer, Case Evolution; baza u memoriji). Proverava UI I bazu.
//   1) advokat dodaje tvrdnju u Analizi → red u predmet_dokazi, događaj obrađen, Analiza je prikazuje, reload je zadržava
//   2) kalkulator zastarelosti: zatvoren spisak sa servera, izračun, napomena o prekidu/zastoju, ništa se ne upisuje

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4526, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

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
p.on("response", s => { const u = new URL(s.url()); if ((u.pathname.startsWith("/api/") || u.pathname.startsWith("/zastarelost/")) && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const txt = (id) => p.evaluate((i) => (document.getElementById(i) || {}).innerText || "", id);

// predmet (ručno)
await p.goto(BASE + "/app#/predmeti/nov");
await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
await p.fill("#nov-naziv", "Marković protiv Gradnja Invest — otkaz");
await p.click("#nov-posalji");
zapisi("priprema", "predmet otvoren", await cekaj(() => /#\/predmeti\/[^/]+/.test(location.hash) && !/nov$/.test(location.hash)));
const hashPredmet = await p.evaluate(() => location.hash.replace(/\/[a-z-]+$/, ""));
await obradi();
const s0 = await stanje();

// 1) tvrdnja
await p.goto(BASE + "/app" + hashPredmet + "/analiza");
await p.click("#tab-analiza").catch(() => {});
zapisi("1", "Analiza: obrazac „Dodaj tvrdnju“ dostupan", await cekaj(() => !document.getElementById("du-posalji").disabled && !document.getElementById("du-forma").closest("[hidden]"), null, 20000));
await p.fill("#du-tvrdnja", "kratk");
await p.fill("#du-tvrdnja", "x");
await p.click("#du-posalji");
zapisi("1", "prekratka tvrdnja se ne šalje", /bar 5 znakova/.test(await txt("du-poruka")) && (await stanje()).tvrdnje === s0.tvrdnje);
await p.fill("#du-tvrdnja", "Zaposleni je primio rešenje o otkazu 17.03.2025. godine.");
await p.fill("#du-napomena", "Potvrđeno potpisom na dostavnici.");
await p.click("#du-posalji");
zapisi("1", "potvrda upisa", await cekaj(() => /Tvrdnja je upisana/.test(document.getElementById("du-poruka").textContent)), await txt("du-poruka"));
const ob = await obradi();
const s1 = await stanje();
zapisi("1", "red u predmet_dokazi, događaj obrađen bez greške", s1.tvrdnje === s0.tvrdnje + 1 && s1.nedispecovano === 0 && ob.greske === 0, JSON.stringify([s0.tvrdnje, s1.tvrdnje, s1.nedispecovano, ob.greske]));
zapisi("1", "Analiza je ponovo pročitana i prikazuje tvrdnju", await cekaj(() => /primio rešenje o otkazu 17\.03\.2025/.test(document.getElementById("an-dokazi").innerText), null, 15000), (await txt("an-dokazi")).slice(0, 160));
zapisi("1", "obrazac je očišćen posle upisa", (await p.inputValue("#du-tvrdnja")) === "");
await p.reload();
await p.click("#tab-analiza").catch(() => {});
zapisi("1", "posle reload-a tvrdnja ostaje", await cekaj(() => /primio rešenje o otkazu 17\.03\.2025/.test(document.getElementById("an-dokazi").innerText), null, 15000));

// 2) zastarelost
await p.goto(BASE + "/app" + hashPredmet + "/rad");
await p.click("#tab-rad").catch(() => {});
zapisi("2", "Rad: spisak vrsta potraživanja sa servera", await cekaj(() => document.querySelectorAll("#zs-tip option").length >= 10 && !document.getElementById("zs-izracunaj").disabled, null, 15000),
  String(await p.evaluate(() => document.querySelectorAll("#zs-tip option").length)));
await p.selectOption("#zs-tip", "naknada_stete");
zapisi("2", "uz vrstu je prikazan zakonski osnov", /ZOO|Zakon o obligacionim/i.test(await txt("zs-tip-pomoc")), await txt("zs-tip-pomoc"));
await p.click("#zs-izracunaj");
zapisi("2", "bez datuma se ne računa", /Unesite datum/.test(await txt("zs-poruka")));
const pre = await stanje();
await p.fill("#zs-datum", "2025-03-17");
await p.click("#zs-izracunaj");
zapisi("2", "rezultat: datum zastarelosti i osnov", await cekaj(() => !document.getElementById("zs-rezultat").hidden && /Zastarelost (nastupa|je NASTUPILA)/.test(document.getElementById("zs-rezultat-lista").innerText)
  && /Zakonski osnov/.test(document.getElementById("zs-rezultat-lista").innerText)), (await txt("zs-rezultat-lista")).slice(0, 200));
zapisi("2", "napomena o subjektivnom/objektivnom roku je prikazana", /objektivni rok/i.test(await txt("zs-rezultat-lista")));
const posle = await stanje();
zapisi("2", "kalkulator ništa ne upisuje", JSON.stringify([pre.tvrdnje, pre.hronologija, pre.akcije_otvorene]) === JSON.stringify([posle.tvrdnje, posle.hronologija, posle.akcije_otvorene]));

// 3) zadaci (Rad) — dodat zadatak je i na Radnoj listi, „Završeno“ ga zatvara
await p.goto(BASE + "/app" + hashPredmet + "/rad");
await p.click("#tab-rad").catch(() => {});
zapisi("3", "Rad: zadaci učitani (prazno)", await cekaj(() => /nema zadataka/.test(document.getElementById("zd-stanje").textContent), null, 15000), await txt("zd-stanje"));
await p.fill("#zd-naziv", "Pribaviti dostavnicu od poslodavca");
await p.fill("#zd-rok", "2026-10-20");
await p.selectOption("#zd-prioritet", "visoko");
await p.click("#zd-dodaj");
zapisi("3", "zadatak dodat i prikazan u predmetu", await cekaj(() => /Pribaviti dostavnicu/.test(document.getElementById("zd-lista").innerText) && /rok 20\.10\.2026/.test(document.getElementById("zd-lista").innerText)),
  (await txt("zd-lista")).slice(0, 160) + " | " + (await txt("zd-poruka")));
await p.goto(BASE + "/app#/danas");
zapisi("3", "zadatak je na Radnoj listi (dodeljen prijavljenom korisniku)", await cekaj(() => /Pribaviti dostavnicu/.test(document.body.innerText), null, 15000));
await p.goto(BASE + "/app" + hashPredmet + "/rad");
await p.click("#tab-rad").catch(() => {});
await cekaj(() => /Pribaviti dostavnicu/.test(document.getElementById("zd-lista").innerText), null, 15000);
await p.click('#zd-lista button[aria-label^="Označi kao završen"]');
zapisi("3", "„Završeno“: status završen, bez dugmeta", await cekaj(() => /završen/.test(document.getElementById("zd-lista").innerText) && !document.querySelector("#zd-lista button")), (await txt("zd-lista")).slice(0, 160) + " | " + (await txt("zd-poruka")));
await p.reload();
await p.click("#tab-rad").catch(() => {});
zapisi("3", "posle reload-a zadatak ostaje završen", await cekaj(() => /završen/.test(document.getElementById("zd-lista").innerText), null, 15000));

const kraj = await stanje();
zapisi("bezbednost", "svi upisi pripadaju prijavljenom korisniku", JSON.stringify(kraj.vlasnici) === '["uid-A"]', JSON.stringify(kraj.vlasnici));
zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0 && kraj.spoljni_pokusaji === 0);
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 2), api500.slice(0, 3)]));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} ${pada ? "FAIL" : "PASS"}`);
process.exit(pada ? 1 : 0);
