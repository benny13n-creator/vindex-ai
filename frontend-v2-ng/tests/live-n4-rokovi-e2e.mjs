// Vindex V2 NG — N4 ROKOVI: ispravka AI predloga roka (pogrešno pročitan datum) i kalkulator rokova sa pomeranjem
// poslednjeg dana sa neradnog dana — stvaran V2 /app u Chromium-u nad PRAVIM api.app (tests/osb003_solo_server.py +
// sintetičko seme). Lanac odluka (audit_immutable) je stvaran kod nad bazom u memoriji. Ništa ne izlazi van 127.0.0.1.
// Pokretanje: `node tests/live-n4-rokovi-e2e.mjs`.
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4534, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const iso = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
const zaDana = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };
const STARO = "2026-01-01T08:00:00+00:00";
const PA = "33333333-aaaa-4aaa-8aaa-000000000001", PB = "44444444-bbbb-4bbb-8bbb-000000000001";
const rok = (id, pid, uid, datum, dogadjaj) => ({ id, predmet_id: pid, user_id: uid, dogadjaj, datum: datum, datum_iso: datum, vaznost: "važan",
  akter: "Smart Intake (AI)", izvor: "AI_AUTONOMOUS", vrsta: "rok", dokument_id: "dok-resenje", dokument_naziv: "Resenje o otkazu.pdf", created_at: STARO });
const SEME = {
  predmeti: [{ id: PA, user_id: "uid-A", naziv: "Zlatić protiv Zlatna Linija", status: "aktivan", created_at: STARO },
             { id: PB, user_id: "uid-B", naziv: "TAJNI B", status: "aktivan", created_at: STARO }],
  predmet_hronologija: [rok("rok-los", PA, "uid-A", zaDana(10), "Rok za tužbu radi poništaja otkaza"),
                        rok("rok-drugi", PA, "uid-A", zaDana(20), "Rok za odgovor"),
                        rok("rok-b", PB, "uid-B", zaDana(10), "TAJNI rok B")],
};
const dir = await mkdtemp(join(tmpdir(), "vx-n4-"));
await writeFile(join(dir, "seme.json"), JSON.stringify(SEME));
const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", VX_OSB003_SEME: join(dir, "seme.json") };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, opt = {}) => new Promise(r => {
  const q = http.request(BASE + p, { method: opt.method || "GET", headers: opt.headers || {} }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); });
  q.on("error", () => r({ s: 0, b: "" })); if (opt.telo) q.write(opt.telo); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app sa sintetičkim semenom", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const kao = (tok) => (p, metod = "GET", telo) => zahtev(p, { method: metod, headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json" }, telo: telo && JSON.stringify(telo) });
const kaoA = kao("tok-A"), kaoB = kao("tok-B");
const json = (r) => { try { return JSON.parse(r.b); } catch { return null; } };
const kandidati = async () => (json(await kaoA(`/api/rokovi/kandidati?od=${zaDana(-90)}&dana=60`)) || { rokovi: [] }).rokovi;

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", timezoneId: "Europe/Belgrade" });
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
const cekaj = (fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);
async function danas() {
  await p.goto(BASE + "/app#/predmeti");
  await p.goto(BASE + "/app#/danas");
  await cekaj(() => document.querySelectorAll("#da-predlozi li").length > 0 || /Nema predloženih/.test(document.body.innerText));
}
const sr = (isoD) => isoD.slice(8, 10) + "." + isoD.slice(5, 7) + "." + isoD.slice(0, 4) + ".";

// ══ K1–K2 ispravka predloga u Danas ═════════════════════════════════════════════════════════════════════════════
await danas();
const red = () => p.evaluate(() => [...document.querySelectorAll("#da-predlozi li")].map(x => x.innerText.replace(/\s+/g, " ")));
zapisi("K1", "predlog sa pogrešnim datumom je predlog (ne obaveza) i nudi „Ispravi datum“", (await red()).some(x => /Rok za tužbu/.test(x) && /Ispravi datum/.test(x))
  && !(await p.evaluate(() => document.getElementById("da-obaveze").innerText)).includes("Rok za tužbu"), JSON.stringify(await red()));
await p.evaluate(() => { const li = [...document.querySelectorAll("#da-predlozi li")].find(x => /Rok za tužbu/.test(x.innerText)); [...li.querySelectorAll("button")].find(b => b.textContent === "Ispravi datum").click(); });
const TACAN = zaDana(12);
await p.evaluate((d) => { const li = [...document.querySelectorAll("#da-predlozi li")].find(x => /Rok za tužbu/.test(x.innerText)); const u = li.querySelector('input[type="date"]'); u.value = d; [...li.querySelectorAll("button")].find(b => b.textContent === "Sačuvaj tačan datum").click(); }, TACAN);
await cekaj(() => /je upisan sa datumom koji ste uneli/.test(document.getElementById("da-poruka").textContent));
const poruka = await tekstEl("da-poruka");
zapisi("K2", "poruka kaže da je rok upisan sa datumom advokata i potvrđen, a predlog odbijen", /upisan sa datumom koji ste uneli/.test(poruka) && /odbijen/.test(poruka), poruka);
let k = await kandidati();
const nov = k.find(x => x.dogadjaj === "Rok za tužbu radi poništaja otkaza" && x.datum_iso === TACAN);
const star = k.find(x => x.id === "rok-los");
zapisi("K2", "baza: NOV rok (tačan datum) CONFIRMED, poreklo HUMAN_DIRECT, isti dokument; STARI predlog REJECTED (ostaje u hronologiji)",
  !!nov && nov.stanje_odluke === "CONFIRMED" && nov.izvor === "HUMAN_DIRECT" && (nov.dokument_naziv === "Resenje o otkazu.pdf" || nov.dokument_id === "dok-resenje")
  && !!star && star.stanje_odluke === "REJECTED", JSON.stringify([nov, star && star.stanje_odluke]));
await danas();
const obaveze = await p.evaluate(() => document.getElementById("da-kalendar").innerText.replace(/\s+/g, " "));   // +12 dana = kalendar (30 dana)
zapisi("K2", "Danas: potvrđen rok sa TAČNIM datumom je u kalendaru, predlog sa pogrešnim nestao", obaveze.includes("Rok za tužbu") && obaveze.includes(sr(TACAN).slice(0, 6))
  && !(await red()).some(x => /Rok za tužbu/.test(x)), obaveze.slice(0, 300));

// ══ K3 granice ═══════════════════════════════════════════════════════════════════════════════════════════════════
const b404 = await kaoB(`/api/rokovi/rok-drugi/ispravi`, "POST", { datum_iso: zaDana(15) });
const potvrdjen409 = await kaoA(`/api/rokovi/${nov.id}/ispravi`, "POST", { datum_iso: zaDana(15) });
const los422 = await kaoA(`/api/rokovi/rok-drugi/ispravi`, "POST", { datum_iso: "2027-02-30" });
zapisi("K3", "B ne ispravlja rok A (404); potvrđen rok se ne „ispravlja“ (409); nemoguć datum 422", b404.s === 404 && potvrdjen409.s === 409 && los422.s === 422,
  JSON.stringify([b404.s, potvrdjen409.s, los422.s]));
const pre = (await kandidati()).length;
const ist = await Promise.all([1, 2].map(() => kaoA(`/api/rokovi/rok-drugi/ispravi`, "POST", { datum_iso: zaDana(21) })));
const posle = await kandidati();
zapisi("K3", "dve istovremene ispravke istog predloga → TAČNO jedan nov rok", ist.filter(r => r.s === 200).length === 1 && posle.length === pre + 1
  && posle.filter(x => x.datum_iso === zaDana(21)).length === 1, JSON.stringify([ist.map(r => r.s), pre, posle.length]));
const bK = json(await kaoB(`/api/rokovi/kandidati?od=${zaDana(-90)}&dana=60`));
zapisi("K3", "B vidi samo svoj rok", !!bK && bK.rokovi.length === 1 && bK.rokovi[0].id === "rok-b", JSON.stringify(bK && bK.rokovi.map(r => r.id)));

// ══ K4 kalkulator: poslednji dan na subotu → ponedeljak, uz pravilo i izvor ════════════════════════════════════
await p.goto(BASE + "/app#/predmeti");
await p.goto(BASE + `/app#/predmeti/${PA}/rad`);
await cekaj(() => document.querySelectorAll("#zs-tip option").length > 5);
const tipovi = await p.evaluate(() => [...document.querySelectorAll("#zs-tip option")].map(o => o.value));
zapisi("K4", "kalkulator ne nudi neproverljive/pogrešne stavke (ček, menica, potrošačka, nasledna)", !tipovi.some(t => ["cek", "menjacki", "potroskac", "nasledna_potrazivanja", "poreski"].includes(t)), JSON.stringify(tipovi));
await p.selectOption("#zs-tip", "zalba_parnicna");
await p.fill("#zs-datum", "2026-10-30");
await p.click("#zs-izracunaj");
await cekaj(() => !document.getElementById("zs-rezultat").hidden);
const rez = await p.evaluate(() => document.getElementById("zs-rezultat-lista").innerText.replace(/\s+/g, " "));
zapisi("K4", "žalba (ZPP čl. 367): 15 dana od 30.10. = subota 14.11. → rok ističe 16.11.2026., uz pravilo ZPP čl. 103 i izvor neradnih dana",
  /Rok ističe 16\.11\.2026/.test(rez) && /14\.11\.2026 pada u subotu/.test(rez) && /ZPP čl\. 103/.test(rez) && /ZPP čl\. 367/.test(rez) && /nije u lokalnoj bazi/.test(rez), rez);

zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 3), api500.slice(0, 3)]));
await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
