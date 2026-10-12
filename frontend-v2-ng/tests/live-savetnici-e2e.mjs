// Vindex V2 NG — VCR002 T07: savetnik za predmet u sva tri PROVERENA načina rada kroz STVARAN V2 /app nad PRAVIM
// api.app (routers/multi_agent.py + shared/idempotency.py). Pokretanje: `node tests/live-savetnici-e2e.mjs`.
// Server: tests/osb003_solo_server.py sa VX_AGENTI=1 (zamenjen SAMO poziv modela). Proverava UI I server:
//   A) jedan savetnik — odgovor, provera citata, 1 naplata
//   B) tri pogleda istovremeno — 3 odeljka sa sopstvenom proverom, jedna naplata od 3 jedinice (po isporučenom odgovoru)
//   C) od istraživanja do nacrta — 3 koraka; korak 2 i 3 dobijaju prethodni izlaz UNUTAR granice poverenja;
//      završni odgovor nosi SVOJU proveru; „radni materijal“
//   D) trajna idempotencija: svaki pokretač je jedan COMPLETED red u v2_mutation_idempotency; reload ne pokreće ništa

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4527, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_AGENTI: "1" };
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
p.on("response", s => { const u = new URL(s.url()); if (u.pathname.startsWith("/api/") && s.status() >= 500) api500.push(`${s.status()} ${u.pathname}`); });
const cekaj = (fn, arg, ms = 20000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const ekran = () => p.evaluate(() => ({
  naslov: document.getElementById("ag-odgovor-naslov").textContent,
  vrh: [...document.querySelectorAll("#ag-citati > li")].map(x => x.dataset.kljuc + ":" + x.textContent),
  blokovi: [...document.querySelectorAll("#ag-tekst .ag-rez")].map(s => ({ agent: s.dataset.agent, stanje: s.dataset.stanje,
    citati: [...s.querySelectorAll(".warns > .warn")].map(w => w.dataset.kljuc) })),
  tekst: document.getElementById("ag-tekst").innerText,
  kontekst: document.getElementById("ag-kontekst").hidden ? null : document.getElementById("ag-kontekst").textContent,
  stanje: document.getElementById("ag-stanje").hidden ? null : document.getElementById("ag-stanje").textContent,
}));
async function pokreni(nacin, agent) {
  await p.selectOption("#ag-nacin", nacin);
  if (agent) await p.selectOption("#ag-agent", agent);
  await p.fill("#ag-zadatak", "Analiziraj zakonitost otkaza i pripremi tužbu radi poništaja rešenja.");
  await p.click("#ag-posalji");
  return cekaj(() => !document.getElementById("ag-odgovor").hidden || (!document.getElementById("ag-stanje").hidden && document.getElementById("ag-stanje").dataset.stanje !== "ucitavanje"), null, 30000);
}

// predmet (ručno)
await p.goto(BASE + "/app#/predmeti/nov");
await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
await p.fill("#nov-naziv", "Marković protiv Gradnja Invest — otkaz");
await p.click("#nov-posalji");
zapisi("priprema", "predmet otvoren", await cekaj(() => /#\/predmeti\/[^/]+/.test(location.hash) && !/nov$/.test(location.hash)));
const hashPredmet = await p.evaluate(() => location.hash.replace(/\/[a-z-]+$/, ""));
await obradi();
await p.goto(BASE + "/app" + hashPredmet + "/pitanje");
await p.click("#tab-pitanje").catch(() => {});
zapisi("priprema", "Savetnik za ovaj predmet je dostupan", await cekaj(() => !document.getElementById("ag-posalji").disabled && document.querySelectorAll("#ag-agent option").length === 6));
const s0 = await stanje();

// A) jedan savetnik
await pokreni("pojedinacno", "research");
let e = await ekran();
let s = await stanje();
zapisi("A", "odgovor jednog savetnika sa proverom citata i kontekstom predmeta", /Pravno istraživanje/.test(e.naslov) && e.vrh.length === 1 && /uz podatke i dokumente ovog predmeta/.test(e.kontekst || ""), JSON.stringify(e.vrh));
zapisi("A", "server: jedan poziv modela, jedna naplata", s.pozivi_modela.filter(x => x.startsWith("agent:")).length === 1 && s.naplaceno_jedinica - s0.naplaceno_jedinica === 1, JSON.stringify([s.pozivi_modela, s.naplaceno_jedinica]));
zapisi("A", "trajna idempotencija: /api/agents/run COMPLETED", s.idempotencija.filter(x => x === "/api/agents/run:COMPLETED").length === 1, JSON.stringify(s.idempotencija));
const sA = s;

// B) tri pogleda istovremeno
await pokreni("paralelno");
e = await ekran(); s = await stanje();
zapisi("B", "tri odeljka, svaki sa sopstvenom proverom citata", e.blokovi.length === 3 && e.blokovi.every(b => b.stanje === "USPEH" && b.citati.length === 1)
  && e.blokovi.map(b => b.agent).join() === "research,litigation,intake", JSON.stringify(e.blokovi));
zapisi("B", "izmišljen član 999 je označen kao nepotvrđen kod parnične strategije", e.blokovi[1].citati[0] === "citati-neprovereni", JSON.stringify(e.blokovi[1]));
zapisi("B", "server: 3 paralelna poziva, jedna naplata od 3 jedinice (po isporučenom odgovoru)",
  s.pozivi_modela.filter(x => x.startsWith("para:")).length === 3 && s.naplaceno_jedinica - sA.naplaceno_jedinica === 3 && s.naplate - sA.naplate === 1, JSON.stringify([s.pozivi_modela.slice(-3), s.naplaceno_jedinica - sA.naplaceno_jedinica]));
const sB = s;

// C) niz je ISKLJUČEN (VCR002 RC FIX 2): pad radnika posle plaćenog koraka ostavlja plaćen rad nigde zabeležen
const o = await p.evaluate(() => [...document.querySelectorAll("#ag-nacin option")].map(x => [x.value, x.disabled]));
zapisi("C", "niz se ne nudi nad pravim katalogom savetnika; ostala dva načina da", JSON.stringify(o) === JSON.stringify([["pojedinacno", false], ["paralelno", false], ["niz", true]]), JSON.stringify(o));
await p.evaluate(() => { const n = document.getElementById("ag-nacin"); n.value = "niz"; n.dispatchEvent(new Event("change")); });
await p.fill("#ag-zadatak", "Analiziraj zakonitost otkaza i pripremi tužbu radi poništaja rešenja.");
await p.click("#ag-posalji");
await cekaj(() => !document.getElementById("ag-stanje").hidden);
e = await ekran(); s = await stanje();
zapisi("C", "nasilno izabran niz: server nije pozvan — nijedan poziv modela, nijedna naplata, nijedan zapis idempotencije",
  s.pozivi_modela.length === sB.pozivi_modela.length && s.naplaceno_jedinica === sB.naplaceno_jedinica && !s.idempotencija.some(x => x.startsWith("/api/agents/pipeline")),
  JSON.stringify([s.pozivi_modela.length - sB.pozivi_modela.length, s.naplaceno_jedinica - sB.naplaceno_jedinica]));

// D) trajnost i reload
zapisi("D", "svaki pokretač je tačno jedan COMPLETED zapis idempotencije", JSON.stringify(s.idempotencija) === JSON.stringify(["/api/agents/run-parallel:COMPLETED", "/api/agents/run:COMPLETED"]), JSON.stringify(s.idempotencija));
const preReload = s.pozivi_modela.length;
await p.reload();
await p.click("#tab-pitanje").catch(() => {});
await cekaj(() => !document.getElementById("ag-posalji").disabled);
s = await stanje();
zapisi("D", "reload ne pokreće savetnike ponovo (bez poziva modela i naplate)", s.pozivi_modela.length === preReload, String(s.pozivi_modela.length - preReload));
zapisi("D", "svi upisi pripadaju prijavljenom korisniku", JSON.stringify(s.vlasnici) === '["uid-A"]', JSON.stringify(s.vlasnici));
zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0 && s.spoljni_pokusaji === 0);
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 2), api500.slice(0, 3)]));

await browser.close(); srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} ${pada ? "FAIL" : "PASS"}`);
process.exit(pada ? 1 : 0);
