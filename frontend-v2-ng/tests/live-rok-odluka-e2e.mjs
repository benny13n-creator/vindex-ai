// Vindex V2 NG — Night Sprint II / A2: od izjavljenog roka do zabeležene ljudske odluke kroz STVARAN primarni V2 /app
// (VINDEX_V2_NG_PRIMARY_ENABLED) nad PRAVIM api.app: GET /api/rokovi/kandidati, POST /api/rokovi/{id}/potvrdi|odbij,
// audit_immutable lanac (stvaran log_action, baza u memoriji), POST /api/kalendar/ics kao spoljni izvršivi izlaz.
// Pokretanje: `node tests/live-rok-odluka-e2e.mjs` (server: tests/ns2_rok_odluka_server.py; ništa ne izlazi van 127.0.0.1).
// Snimci: VX_SNIMCI=<dir>. Svaki korak se proverava i u UI-ju i u lancu odluka (GET /__ns2/stanje).

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = Number(process.env.VX_PORT || 4531), BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
const SNIMCI = process.env.VX_SNIMCI || "";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const D = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const DT = (n) => { const [y, m, d] = D(n).split("-"); return `${d}.${m}.${y}.`; };
const BACKEND_TERMINI = /HUMAN_DIRECT|AI_ASSISTED|AI_AUTONOMOUS|DETERMINISTIC|LEGACY_UNKNOWN|UNCONFIRMED|CONFIRMED|REJECTED|UNKNOWN|audit|stanje_odluke|vrsta|undefined|null\b|\[object/;

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/ns2_rok_odluka_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (metod, p, { token, telo } = {}) => new Promise(r => {
  const h = { Accept: "application/json" };
  if (token) h.Authorization = "Bearer " + token;
  const b = telo === undefined ? null : Buffer.from(JSON.stringify(telo));
  if (b) { h["Content-Type"] = "application/json"; h["Content-Length"] = b.length; }
  const q = http.request(BASE + p, { method: metod, headers: h }, s => { let x = ""; s.setEncoding("utf8"); s.on("data", c => x += c); s.on("end", () => r({ s: s.statusCode, b: x })); });
  q.on("error", () => r({ s: 0, b: "" })); if (b) q.write(b); q.end();
});
const json = (x) => { try { return JSON.parse(x.b); } catch { return null; } };
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("GET", "/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app, primarni V2 /app odgovara", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const stanje = async () => json(await zahtev("GET", "/__ns2/stanje"));
const kvar = (tabela, radnja, ukljucen) => zahtev("POST", "/__ns2/kvar", { telo: { tabela, radnja, ukljucen } });
const odlukeZa = (st, id) => st.odluke.filter(o => o.rok === id).map(o => o.akcija);
const kandidati = async (token) => { const r = await zahtev("GET", `/api/rokovi/kandidati?od=${D(-90)}&dana=30`, { token }); return { s: r.s, j: json(r) }; };
const ics = async () => { const r = await zahtev("POST", `/api/kalendar/ics?od=${D(-1)}&do=${D(60)}`, { token: "tok-A" }); return { s: r.s, t: r.b.replace(/\r\n[ \t]/g, "") }; };
const vevent = (t) => (t.match(/BEGIN:VEVENT/g) || []).length;

// ── 1. Advokat stvara rokove (stvarne rute) ───────────────────────────────────────────────────────────────────────
const pA = json(await zahtev("POST", "/api/predmeti", { token: "tok-A", telo: { naziv: "Petrović protiv Gradnja Invest", tip: "Radni spor" } }));
const pB = json(await zahtev("POST", "/api/predmeti", { token: "tok-B", telo: { naziv: "TAJNI predmet B" } }));
const pC = json(await zahtev("POST", "/api/predmeti", { token: "tok-C", telo: { naziv: "Predmet C" } }));
const PA = pA && (pA.id || (pA.predmet && pA.predmet.id)), PB = pB && (pB.id || (pB.predmet && pB.predmet.id)), PC = pC && (pC.id || (pC.predmet && pC.predmet.id));
zapisi("1.stvaranje", "predmeti su stvoreni stvarnom rutom (A, B, C)", !!(PA && PB && PC), JSON.stringify(pA).slice(0, 120));
const lanac = json(await zahtev("POST", "/api/rokovi/lanac", { token: "tok-A", telo: { tip_dogadjaja: "dostava_resenja", datum_pocetka: D(-3), predmet_id: PA } }));
zapisi("1.stvaranje", "advokat izričito upisuje ZPP rok (POST /api/rokovi/lanac → sačuvano u predmet)", lanac && lanac.sacuvano_u_predmet === true, JSON.stringify(lanac && lanac.lanac).slice(0, 120));
// Redovi kakve proizvodi A1 (eksplicitni pisac stavlja vrsta="rok") i zatečen pisac bez `vrsta`.
const R = {};
const umetni = async (kljuc, red) => { R[kljuc] = json(await zahtev("POST", "/__ns2/umetni", { telo: { predmet_id: PA, user_id: "uid-A", vaznost: "visok", akter: "Advokat", ...red, datum: red.datum_iso } })).id; };
await umetni("A1", { dogadjaj: "Rok za dopunu tužbe", datum_iso: D(5), izvor: "HUMAN_DIRECT", vrsta: "rok" });
await umetni("NULL", { dogadjaj: "Rok za odgovor na podnesak bez oznake", datum_iso: D(6), izvor: "HUMAN_DIRECT" });
await umetni("KOL", { dogadjaj: "Rok za predlog za izvršenje", datum_iso: D(7), izvor: "AI_ASSISTED", vrsta: "rok", stanje: "potvrdjen" });
await umetni("BEZIZV", { dogadjaj: "Rok za uplatu takse", datum_iso: D(8), vrsta: "rok" });
await umetni("BEZDAT", { dogadjaj: "Rok bez datuma", datum_iso: null, vrsta: "rok", izvor: "HUMAN_DIRECT" });
const adv = [["DUP", "Rok za izjašnjenje o veštačenju", 9], ["TO", "Rok za dostavu dokaza", 10], ["AUD", "Rok za plaćanje predujma", 11],
  ["UNK", "Rok za predlog svedoka", 13], ["CONC", "Rok za odgovor na reviziju", 14], ["DBL", "Rok za uređenje tužbe", 15], ["PR", "Rok za protivtužbu", 16], ["MOB", "Rok za podnesak sudu", 17]];
for (const [k, t, n] of adv) await umetni(k, { dogadjaj: t, datum_iso: D(n), izvor: "HUMAN_DIRECT", vrsta: "rok" });
R.B = json(await zahtev("POST", "/__ns2/umetni", { telo: { predmet_id: PB, user_id: "uid-B", dogadjaj: "TAJNI rok B", datum_iso: D(4), datum: D(4), vaznost: "visok", vrsta: "rok", izvor: "HUMAN_DIRECT" } })).id;
R.C = json(await zahtev("POST", "/__ns2/umetni", { telo: { predmet_id: PC, user_id: "uid-C", dogadjaj: "Rok za žalbu C", datum_iso: D(4), datum: D(4), vaznost: "visok", vrsta: "rok", izvor: "HUMAN_DIRECT" } })).id;

// ── 2. Upisano ─────────────────────────────────────────────────────────────────────────────────────────────────────
let st = await stanje();
const lanacRed = st.hronologija.find(h => h.predmet_id === PA && h.izvor === "DETERMINISTIC");
R.LANAC = lanacRed && lanacRed.id;
zapisi("2.upis", "ZPP rok je upisan kao izjavljen rok (vrsta=rok, izvor=DETERMINISTIC) u predmet A", !!lanacRed && lanacRed.vrsta === "rok" && lanacRed.korisnik === "uid-A" && lanacRed.datum_iso === D(12), JSON.stringify(lanacRed));
zapisi("2.upis", "nijedna odluka ne postoji pre ljudske radnje (ni za HUMAN_DIRECT, DETERMINISTIC, AI_ASSISTED, `stanje=potvrdjen`)", st.odluke.length === 0, JSON.stringify(st.odluke));
let k0 = await kandidati("tok-A");
const ids0 = new Map((k0.j && k0.j.rokovi || []).map(x => [x.id, x]));
zapisi("2.upis", "kandidati: svi izjavljeni rokovi su UNCONFIRMED, i onaj sa kolonom `stanje=potvrdjen`", k0.s === 200 && ["A1", "KOL", "BEZIZV", "LANAC"].every(k => ids0.get(R[k]) && ids0.get(R[k]).stanje_odluke === "UNCONFIRMED"));
zapisi("2.upis", "red bez datuma ne dolazi kroz kandidate (opseg po datum_iso) — dokumentovano ograničenje", !ids0.has(R.BEZDAT));
zapisi("2.upis", "red bez `vrsta` JESTE u kandidatima (sirov), ali bez oznake roka", ids0.has(R.NULL) && !ids0.get(R.NULL).vrsta);
let x0 = await ics();
zapisi("8.izvrsivo", "pre ijedne odluke .ics nema nijedan rok (404, ništa za izvoz)", x0.s === 404, String(x0.s));

// ── 3/4. Vidljivo u V2 pregledu ───────────────────────────────────────────────────────────────────────────────────
const browser = await chromium.launch();
const spoljni = [], greskeJS = [];
async function sesija(token, korisnik, { w = 1440, h = 900 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  await ctx.route("**/*", r => {
    const u = new URL(r.request().url());
    if (u.hostname !== "127.0.0.1") { spoljni.push(u.href); return r.abort(); }
    if (u.pathname === "/static/vindex.js") return r.fulfill({ status: 200, contentType: "text/javascript", body: "/* legacy blokiran */" });
    return r.continue();
  });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } },
    [KLJUC, JSON.stringify({ access_token: token, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: korisnik } })]);
  const p = await ctx.newPage();
  p.setDefaultTimeout(10000);
  p.on("pageerror", e => greskeJS.push(String(e)));
  const odluke = [], citanja = [];
  p.on("request", q => { const u = new URL(q.url()); if (/^\/api\/rokovi\/[^/]+\/(potvrdi|odbij)$/.test(u.pathname)) odluke.push(u.pathname); if (u.pathname === "/api/rokovi/kandidati") citanja.push(u.pathname); });
  await p.goto(BASE + "/app#/danas");
  return { ctx, p, odluke, citanja };
}
const cekaj = (p, fn, arg, ms = 12000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const ucitano = (p) => cekaj(p, () => { const n = document.getElementById("da-stanje"); const pog = document.getElementById("danas-pogled");
  return pog && !pog.hidden && n.dataset.stanje !== "ucitavanje" && (n.hidden || n.dataset.stanje) && (!document.getElementById("da-predlozi-stanje").hidden || document.querySelector("#da-predlozi .review") || n.dataset.stanje === "greska"); });
const red = (p, id) => p.evaluate((id) => { const li = document.querySelector(`#da-predlozi .review[data-rok="${id}"]`); return li ? li.innerText : null; }, id);
const ekran = (p) => p.evaluate(() => {
  const st = (id) => { const e = document.getElementById(id); return e && !e.hidden ? e.dataset.stanje + ":" + e.textContent : null; };
  return { predlozi: [...document.querySelectorAll("#da-predlozi .review")].map(li => li.dataset.rok), obaveze: document.getElementById("da-obaveze").innerText,
    kalendar: document.getElementById("da-kalendar").innerText, poruka: st("da-poruka"), stanje: st("da-stanje"), napomena: st("da-napomena"), pogled: document.getElementById("danas-pogled").innerText };
});
const posleOdluke = async (s, pre) => { await cekaj(s.p, () => !document.getElementById("da-poruka").hidden);
  for (let i = 0; i < 60 && s.citanja.length <= pre; i++) await s.p.waitForTimeout(100); await ucitano(s.p); await s.p.waitForTimeout(150); };

const s1 = await sesija("tok-A", "uid-A");
zapisi("3.vidljivo", "/app#/danas (primarni V2) se učitao", await ucitano(s1.p));
let e = await ekran(s1.p);
const tA1 = await red(s1.p, R.A1);
zapisi("3.vidljivo", "rok iz A1 pisca je predlog za odluku", e.predlozi.includes(R.A1), e.predlozi.length + " predloga");
zapisi("4.prikaz", "predlog nosi stvaran datum, opis, predmet i poreklo „uneto ručno“ + „čeka vašu odluku“",
  !!tA1 && tA1.includes("Rok za dopunu tužbe") && tA1.includes(DT(5)) && tA1.includes("Petrović protiv Gradnja Invest") && tA1.includes("uneto ručno") && tA1.includes("čeka vašu odluku"), (tA1 || "").replace(/\n/g, " | "));
const tL = await red(s1.p, R.LANAC);
zapisi("4.prikaz", "ZPP rok: „izračunato iz kataloga rokova“, datum " + DT(12), !!tL && tL.includes("izračunato iz kataloga rokova") && tL.includes(DT(12)), (tL || "").replace(/\n/g, " | "));
const tK = await red(s1.p, R.KOL), tBI = await red(s1.p, R.BEZIZV);
zapisi("4.prikaz", "AI_ASSISTED: „uneto uz pomoć AI“; bez porekla: „poreklo nije zabeleženo“", !!tK && tK.includes("uneto uz pomoć AI") && !!tBI && tBI.includes("poreklo nije zabeleženo"));
zapisi("invarijanta", "kolona `stanje=potvrdjen` bez odluke NIJE obaveza ni u kalendaru — ostaje predlog", e.predlozi.includes(R.KOL) && !e.obaveze.includes("Rok za predlog za izvršenje") && !e.kalendar.includes("Rok za predlog za izvršenje"));
zapisi("invarijanta", "HUMAN_DIRECT / DETERMINISTIC rok bez odluke nije obaveza ni u kalendaru", !e.obaveze.includes("Rok za dopunu tužbe") && !e.kalendar.includes("Rok za dopunu tužbe") && !e.kalendar.includes("Rok za žalbu na rešenje"));
zapisi("vrsta", "red bez `vrsta` se ne prikazuje, a napomena ga prebrojava (A1 zatvara izvor ovog slučaja)", !e.pogled.includes("bez oznake") && /^prazno:1 zapis hronologije nema oznaku da je rok/.test(e.napomena || ""), e.napomena);
zapisi("izolacija", "ništa od korisnika B ni C", !/TAJNI|žalbu C/.test(e.pogled));
zapisi("jezik", "nema pozadinskih termina u pregledu", !BACKEND_TERMINI.test(e.pogled), (e.pogled.match(BACKEND_TERMINI) || [""])[0]);
zapisi("invarijanta", "samo učitavanje ne upisuje odluku", (await stanje()).odluke.length === 0 && s1.odluke.length === 0);
if (SNIMCI) await s1.p.screenshot({ path: join(SNIMCI, "a2-danas-desktop.png"), fullPage: true });
if (SNIMCI) await s1.p.locator("#da-predlozi").screenshot({ path: join(SNIMCI, "a2-predlozi-desktop.png") });

// ── 5. Tastatura: Tab do „Potvrdi“ za TAJ rok, Enter ──────────────────────────────────────────────────────────────
async function tabDo(p, id, dugme) {
  await p.evaluate(() => { document.activeElement && document.activeElement.blur && document.activeElement.blur(); window.scrollTo(0, 0); document.body.focus(); });
  for (let i = 0; i < 250; i++) {
    await p.keyboard.press("Tab");
    const ok = await p.evaluate(([id, d]) => { const a = document.activeElement; return !!a && a.tagName === "BUTTON" && a.textContent === d && !!a.closest(`.review[data-rok="${id}"]`); }, [id, dugme]);
    if (ok) return true;
  }
  return false;
}
let pre = s1.citanja.length;
zapisi("5.tastatura", "Tab stiže do „Potvrdi“ tačno tog roka", await tabDo(s1.p, R.A1, "Potvrdi"));
await s1.p.keyboard.press("Enter");
await posleOdluke(s1, pre);
e = await ekran(s1.p); st = await stanje();
zapisi("5.odluka", "Enter na „Potvrdi“ → tačno jedan zapis rok_potvrdjen za TAJ rok, od tog korisnika", JSON.stringify(odlukeZa(st, R.A1)) === '["rok_potvrdjen"]' && st.odluke.every(o => o.korisnik === "uid-A") && st.odluke.length === 1, JSON.stringify(st.odluke));
zapisi("6.trajno", "kandidati (autoritativno) → CONFIRMED", (await kandidati("tok-A")).j.rokovi.find(x => x.id === R.A1).stanje_odluke === "CONFIRMED");
zapisi("5.odluka", "poruka: potvrđen, uz „ne znači da je sistem proverio“", /^uspeh:Rok „Rok za dopunu tužbe“ je potvrđen/.test(e.poruka || "") && /ne znači da je sistem proverio/.test(e.poruka), e.poruka);
zapisi("7.osvezavanje", "UI je ponovo pročitao kandidate; rok više nije predlog, sada je obaveza i u kalendaru", s1.citanja.length > pre && !e.predlozi.includes(R.A1) && e.obaveze.includes("Rok za dopunu tužbe") && e.kalendar.includes("Rok za dopunu tužbe"));
pre = s1.citanja.length;
zapisi("5.tastatura", "Tab stiže do „Odbij“ ZPP roka", await tabDo(s1.p, R.LANAC, "Odbij"));
await s1.p.keyboard.press("Enter");
await posleOdluke(s1, pre);
e = await ekran(s1.p); st = await stanje();
zapisi("5.odluka", "Enter na „Odbij“ → rok_odbijen za TAJ rok", JSON.stringify(odlukeZa(st, R.LANAC)) === '["rok_odbijen"]' && st.odluke.length === 2);
zapisi("5.odluka", "poruka: odbijen, ne briše se", /^uspeh:Rok „Rok: Rok za žalbu na rešenje.*je odbijen\. Ne briše se/.test(e.poruka || ""), e.poruka);
zapisi("9.istorija", "odbijen rok NIJE obrisan iz hronologije", st.hronologija.some(h => h.id === R.LANAC));
zapisi("7.osvezavanje", "odbijen rok nije ni predlog ni obaveza", !e.predlozi.includes(R.LANAC) && !e.obaveze.includes("žalbu na rešenje") && !e.kalendar.includes("žalbu na rešenje"));

// ── 8. Samo potvrđen rok postaje spoljno izvršiv (.ics) ──────────────────────────────────────────────────────────
let x1 = await ics();
zapisi("8.izvrsivo", ".ics: tačno jedan događaj — potvrđeni rok; bez odbijenog, predloga i neizjavljenog", x1.s === 200 && vevent(x1.t) === 1 && x1.t.includes("Rok za dopunu tužbe") && !/žalbu na rešenje|predlog za izvršenje|bez oznake|uplatu takse/.test(x1.t), `${x1.s} ${vevent(x1.t)}`);

// ── 9. Odbijen ostaje u internoj istoriji predmeta (V2 #/predmeti/<id>/rad) ─────────────────────────────────────
await s1.p.goto(BASE + `/app#/predmeti/${encodeURIComponent(PA)}/rad`);
const hronOk = await cekaj(s1.p, () => document.querySelectorAll("#hron-lista .chrono__item").length > 0);
const hron = await s1.p.evaluate(() => [...document.querySelectorAll("#hron-lista .chrono__item")].map(li => li.innerText.replace(/\n/g, " | ")));
const hr = (t) => hron.find(x => x.includes(t)) || "";
zapisi("9.istorija", "hronologija predmeta: odbijen rok je i dalje tu, označen „rok — odbijen“", hronOk && /rok — odbijen/.test(hr("žalbu na rešenje")), hr("žalbu na rešenje"));
zapisi("9.istorija", "potvrđen „rok — potvrđen“, nepotvrđen (i sa kolonom potvrdjen) „rok — čeka vašu odluku“", /rok — potvrđen/.test(hr("dopunu tužbe")) && /rok — čeka vašu odluku/.test(hr("predlog za izvršenje")));
zapisi("9.istorija", "red bez `vrsta` nema oznaku odluke (nije rok)", !!hr("bez oznake") && !/rok —/.test(hr("bez oznake")));
zapisi("jezik", "hronologija bez pozadinskih termina", !BACKEND_TERMINI.test(hron.join(" ")), (hron.join(" ").match(BACKEND_TERMINI) || [""])[0]);
if (SNIMCI) await s1.p.screenshot({ path: join(SNIMCI, "a2-hronologija-desktop.png"), fullPage: true });
await s1.p.goto(BASE + "/app#/danas"); await ucitano(s1.p);

// ── Adversarijalno ────────────────────────────────────────────────────────────────────────────────────────────────
// Dupli klik
{
  pre = s1.citanja.length;
  await s1.p.evaluate((id) => { const b = document.querySelector(`#da-predlozi .review[data-rok="${id}"] button`); b.click(); b.click(); b.click(); }, R.DUP);
  await posleOdluke(s1, pre);
  st = await stanje();
  zapisi("dupli-klik", "trostruki klik → jedan zahtev i jedan zapis u lancu", s1.odluke.filter(x => x.includes(R.DUP)).length === 1 && odlukeZa(st, R.DUP).length === 1);
}
// Prekid posle odluke na serveru (zahtev stigne, odgovor ne)
{
  await s1.p.route(`**/api/rokovi/${R.TO}/potvrdi`, async (r) => { await r.fetch(); await r.abort("timedout"); });
  pre = s1.citanja.length;
  await s1.p.click(`#da-predlozi .review[data-rok="${R.TO}"] button:first-of-type`);
  await posleOdluke(s1, pre);
  e = await ekran(s1.p); st = await stanje();
  zapisi("prekid", "UI kaže „ishod nije poznat“ (ne uspeh, ne „nije zabeleženo“)", /^nepoznato:Ishod odluke za rok „Rok za dostavu dokaza“ nije poznat/.test(e.poruka || "") && !/“ je potvrđen:|nije zabeleženo/.test(e.poruka), e.poruka);
  zapisi("prekid", "UI ponovo čita stanje: rok je (na serveru) potvrđen → obaveza, više nije predlog", s1.citanja.length > pre && !e.predlozi.includes(R.TO) && e.kalendar.includes("Rok za dostavu dokaza"));
  zapisi("prekid", "nema ponovnog slanja: jedan zahtev, jedan zapis", s1.odluke.filter(x => x.includes(R.TO)).length === 1 && odlukeZa(st, R.TO).length === 1);
  await s1.p.unroute(`**/api/rokovi/${R.TO}/potvrdi`);
}
// Audit lanac nedostupan za upis
{
  await kvar("audit_immutable", "insert", true);
  pre = s1.citanja.length;
  await s1.p.click(`#da-predlozi .review[data-rok="${R.AUD}"] button:first-of-type`);
  await posleOdluke(s1, pre);
  e = await ekran(s1.p); st = await stanje();
  await kvar("audit_immutable", "insert", false);
  zapisi("audit-pad", "neuspeo upis u lanac: bez uspeha, „ishod nije poznat“", /^nepoznato:/.test(e.poruka || "") && !/“ je potvrđen:/.test(e.pogled), e.poruka);
  zapisi("audit-pad", "nijedan zapis; posle ponovnog čitanja rok i dalje čeka odluku", odlukeZa(st, R.AUD).length === 0 && e.predlozi.includes(R.AUD));
}
// Upis uspeo, ali lanac nije pročitan posle upisa → server vraća UNKNOWN
{
  await kvar("audit_immutable", "select", true);
  pre = s1.citanja.length;
  await s1.p.click(`#da-predlozi .review[data-rok="${R.UNK}"] button:first-of-type`);
  await posleOdluke(s1, pre);
  e = await ekran(s1.p); st = await stanje();
  await kvar("audit_immutable", "select", false);
  zapisi("nepoznato-stanje", "odgovor UNKNOWN → „odluka primljena, stanje nije potvrđeno čitanjem“, ne „je potvrđen“", /^nepoznato:Vaša odluka za rok „Rok za predlog svedoka“ je primljena, ali trenutno stanje roka nije potvrđeno/.test(e.poruka || "") && !/“ je potvrđen:/.test(e.poruka), e.poruka);
  zapisi("nepoznato-stanje", "ponovno čitanje palo → pregled izričito kaže da nije učitan (ne prazan)", /greska|nepotpuno/.test(e.stanje || "") && !/Nema predloženih/.test(e.pogled), e.stanje);
  zapisi("nepoznato-stanje", "zapis u lancu postoji tačno jednom", JSON.stringify(odlukeZa(st, R.UNK)) === '["rok_potvrdjen"]');
  await s1.p.reload(); await ucitano(s1.p);
}
// Nepostojeći id, tuđ rok, neizjavljen red — UI dobija stvaran odgovor servera
{
  await s1.p.route("**/api/rokovi/kandidati?*", async (r) => {
    const o = await r.fetch(); const j = await o.json();
    const sablon = j.rokovi.find(x => x.id === R.DUP) || j.rokovi[0];
    j.rokovi.push({ ...sablon, id: "r-ne-postoji", dogadjaj: "Lažni rok", stanje_odluke: "UNCONFIRMED", datum_iso: D(18) },
      { ...sablon, id: R.B, dogadjaj: "Tuđi rok", stanje_odluke: "UNCONFIRMED", datum_iso: D(18) },
      { ...sablon, id: R.NULL, dogadjaj: "Neizjavljen red", vrsta: "rok", stanje_odluke: "UNCONFIRMED", datum_iso: D(18) },
      { ...sablon, id: "r-los-datum", dogadjaj: "Rok sa lošim datumom", stanje_odluke: "UNCONFIRMED", datum_iso: "nije-datum" });
    await r.fulfill({ response: o, json: j });
  });
  await s1.p.reload(); await ucitano(s1.p);
  const pokusaj = async (id) => { await s1.p.click(`#da-predlozi .review[data-rok="${id}"] button:first-of-type`);
    await cekaj(s1.p, (id) => { const li = document.querySelector(`#da-predlozi .review[data-rok="${id}"]`); return li && !li.querySelector("button").disabled && !li.querySelector("[role=status]").hidden && li.querySelector("[role=status]").textContent !== "Beleži se…"; }, id);
    return (await red(s1.p, id)) || ""; };
  const t404 = await pokusaj("r-ne-postoji"), tB = await pokusaj(R.B), t409 = await pokusaj(R.NULL);
  e = await ekran(s1.p); st = await stanje();
  zapisi("nevazeci-id", "nepostojeći id → „Rok nije dostupan. Ništa nije zabeleženo.“", /Rok nije dostupan\. Ništa nije zabeleženo/.test(t404), t404.replace(/\n/g, " | "));
  zapisi("tudji-rok", "tuđ rok → isti odgovor kao nepostojeći (404), bez curenja", /Rok nije dostupan\. Ništa nije zabeleženo/.test(tB) && !/TAJNI/.test(e.pogled));
  zapisi("neizjavljen", "red bez `vrsta` (podmetnut kao rok) → server 409: „nije označen kao rok … Ništa nije zabeleženo“", /nije označen kao rok.*Ništa nije zabeleženo/.test(t409), t409.replace(/\n/g, " | "));
  zapisi("neizjavljen", "nijedan od tri pokušaja nije upisan u lanac", odlukeZa(st, "r-ne-postoji").length === 0 && odlukeZa(st, R.B).length === 0 && odlukeZa(st, R.NULL).length === 0 && !e.poruka);
  zapisi("datum", "predlog bez ispravnog datuma se ne prikazuje, ali se KAŽE", !e.predlozi.includes("r-los-datum") && /1 predloženi rok nema ispravan datum/.test(e.napomena || ""), e.napomena);
  await s1.p.unroute("**/api/rokovi/kandidati?*");
  await s1.p.reload(); await ucitano(s1.p);
  const r1 = await zahtev("POST", `/api/rokovi/${R.B}/potvrdi`, { token: "tok-A", telo: {} }), r2 = await zahtev("POST", "/api/rokovi/..%2F..%2Fx/potvrdi", { token: "tok-A", telo: {} });
  zapisi("tudji-rok", "API: tuđ rok 404 bez teksta tuđeg roka; neispravan id nije 2xx", r1.s === 404 && !/TAJNI/.test(r1.b) && (r2.s >= 400 && r2.s < 500));
}
// Zastarele sesije istog advokata: konkurentne odluke, dupla potvrda, potvrda posle odbijanja.
// Svaka zastarela sesija je zasebna: posle SVOJE odluke sesija ponovo čita stanje, pa više nije zastarela.
{
  const tri = [R.CONC, R.DBL, R.PR];
  const zs = [];
  for (let i = 0; i < 3; i++) { const z = await sesija("tok-A", "uid-A"); await ucitano(z.p); zs.push(z); }
  zapisi("sesije", "tri druge sesije vide iste predloge", (await Promise.all(zs.map(z => ekran(z.p)))).every(x => tri.every(id => x.predlozi.includes(id))));
  // s1: potvrđuje CONC i DBL, odbija PR
  for (const [id, dug] of [[R.CONC, 1], [R.DBL, 1], [R.PR, 2]]) { pre = s1.citanja.length; await s1.p.click(`#da-predlozi .review[data-rok="${id}"] button:nth-of-type(${dug})`); await posleOdluke(s1, pre); }
  e = await ekran(zs[0].p);
  zapisi("zastarelo", "zastarela sesija i dalje prikazuje već odlučene predloge (do ponovnog čitanja)", tri.every(id => e.predlozi.includes(id)));
  // zastarele: Odbij CONC (konkurentno, posle potvrde), Potvrdi DBL (dupla potvrda), Potvrdi PR (potvrda posle odbijanja)
  const rez = {};
  for (const [z, id, dug] of [[zs[0], R.CONC, 2], [zs[1], R.DBL, 1], [zs[2], R.PR, 1]]) {
    pre = z.citanja.length; await z.p.click(`#da-predlozi .review[data-rok="${id}"] button:nth-of-type(${dug})`); await posleOdluke(z, pre);
    const ek = await ekran(z.p); rez[id] = { poruka: ek.poruka, predlog: ek.predlozi.includes(id), zahteva: z.odluke.length };
  }
  st = await stanje();
  const kk = new Map((await kandidati("tok-A")).j.rokovi.map(x => [x.id, x.stanje_odluke]));
  zapisi("konkurentno", "potvrda (s1) pa odbijanje (zastarela): poslednja odluka važi → REJECTED; oba zapisa u lancu", JSON.stringify(odlukeZa(st, R.CONC)) === '["rok_potvrdjen","rok_odbijen"]' && kk.get(R.CONC) === "REJECTED");
  zapisi("konkurentno", "poruka zastarele sesije odgovara stanju koje je server pročitao (odbijen)", /^uspeh:.*je odbijen/.test(rez[R.CONC].poruka || ""), rez[R.CONC].poruka);
  zapisi("dupla-potvrda", "dupla potvrda: dva zapisa u lancu (append-only), stanje CONFIRMED, jedan zahtev iz UI-ja", JSON.stringify(odlukeZa(st, R.DBL)) === '["rok_potvrdjen","rok_potvrdjen"]' && kk.get(R.DBL) === "CONFIRMED" && /^uspeh:.*“ je potvrđen:/.test(rez[R.DBL].poruka || "") && rez[R.DBL].zahteva === 1);
  zapisi("posle-odbijanja", "postojeći ugovor: potvrda posle odbijanja (zastarela sesija) VRAĆA izvršivost — poslednja odluka važi", JSON.stringify(odlukeZa(st, R.PR)) === '["rok_odbijen","rok_potvrdjen"]' && kk.get(R.PR) === "CONFIRMED");
  zapisi("zastarelo", "posle svoje odluke svaka zastarela sesija je ponovo pročitala stanje (rok više nije predlog)", tri.every(id => rez[id].predlog === false));
  await s1.p.reload(); await ucitano(s1.p); e = await ekran(s1.p);
  zapisi("zastarelo", "s1 posle osvežavanja: odbijen CONC nije obaveza; DBL i PR jesu", !e.kalendar.includes("Rok za odgovor na reviziju") && e.kalendar.includes("Rok za uređenje tužbe") && e.kalendar.includes("Rok za protivtužbu"));
  for (const z of zs) await z.ctx.close();
}
// Telefon (390 px): pregled i odluka dodirom
{
  const m = await sesija("tok-A", "uid-A", { w: 390, h: 844 });
  await ucitano(m.p);
  const mere = await m.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("telefon", "390 px: bez horizontalnog skrola", mere.sw <= mere.vw, `${mere.sw}/${mere.vw}`);
  const vid = await m.p.evaluate((id) => { const b = document.querySelector(`#da-predlozi .review[data-rok="${id}"] button`); const r = b.getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth && r.left >= 0; }, R.MOB);
  zapisi("telefon", "„Potvrdi“ je ceo u ekranu", vid);
  if (SNIMCI) await m.p.screenshot({ path: join(SNIMCI, "a2-danas-mobile.png"), fullPage: true });
  if (SNIMCI) await m.p.locator("#da-predlozi").screenshot({ path: join(SNIMCI, "a2-predlozi-mobile.png") });
  pre = m.citanja.length;
  await m.p.locator(`#da-predlozi .review[data-rok="${R.MOB}"] button`).first().tap().catch(() => m.p.click(`#da-predlozi .review[data-rok="${R.MOB}"] button:first-of-type`));
  await posleOdluke(m, pre);
  e = await ekran(m.p); st = await stanje();
  zapisi("telefon", "odluka sa telefona upisana i prikazana", JSON.stringify(odlukeZa(st, R.MOB)) === '["rok_potvrdjen"]' && /^uspeh:.*je potvrđen/.test(e.poruka || ""));
  if (SNIMCI) { await m.p.locator("#da-poruka").scrollIntoViewIfNeeded(); await m.p.screenshot({ path: join(SNIMCI, "a2-danas-mobile-posle-potvrde.png") }); }
  await m.ctx.close();
}
// Istekla sesija (401 na odluci)
{
  const c = await sesija("tok-C", "uid-C");
  await ucitano(c.p);
  zapisi("sesija", "korisnik C vidi svoj rok", (await ekran(c.p)).predlozi.includes(R.C));
  await zahtev("POST", "/__ns2/opozovi", { telo: { token: "tok-C" } });
  await c.p.click(`#da-predlozi .review[data-rok="${R.C}"] button:first-of-type`);
  await cekaj(c.p, (id) => { const li = document.querySelector(`#da-predlozi .review[data-rok="${id}"]`); return li && !li.querySelector("button").disabled && li.querySelector("[role=status]").textContent !== "Beleži se…"; }, R.C);
  const t = (await red(c.p, R.C)) || ""; e = await ekran(c.p); st = await stanje();
  zapisi("sesija", "401 → „Prijava više nije važeća. Ništa nije zabeleženo.“, bez uspeha i bez upisa", /Prijava više nije važeća\. Ništa nije zabeleženo/.test(t) && !e.poruka && odlukeZa(st, R.C).length === 0, t.replace(/\n/g, " | "));
  await c.ctx.close();
}

// ── Završno: nijedna nedozvoljena odluka; .ics bez duplikata ─────────────────────────────────────────────────────
st = await stanje();
const dozvoljeni = new Set([R.A1, R.LANAC, R.DUP, R.TO, R.UNK, R.CONC, R.DBL, R.PR, R.MOB]);
zapisi("invarijanta", "svaki zapis u lancu odgovara izričitom kliku; ništa za KOL, BEZIZV, NULL, AUD, B, C", st.odluke.every(o => dozvoljeni.has(o.rok)) && [R.KOL, R.BEZIZV, R.NULL, R.AUD, R.B, R.C].every(id => odlukeZa(st, id).length === 0), JSON.stringify(st.odluke.map(o => o.akcija[4] + ":" + Object.keys(R).find(k => R[k] === o.rok))));
const x2 = await ics();
const potvrdjeni = ["Rok za dopunu tužbe", "Rok za izjašnjenje o veštačenju", "Rok za dostavu dokaza", "Rok za predlog svedoka", "Rok za uređenje tužbe", "Rok za protivtužbu", "Rok za podnesak sudu"];
const broj = (t) => x2.t.split("\r\n").filter(l => l.startsWith("SUMMARY:") && l.includes(t)).length;
zapisi("8.izvrsivo", ".ics: svaki potvrđen rok tačno jednom (i posle duple potvrde i prekida)", x2.s === 200 && vevent(x2.t) === potvrdjeni.length && potvrdjeni.every(t => broj(t) >= 1) && broj("Rok za uređenje tužbe") === 1 && broj("Rok za dostavu dokaza") === 1, `${vevent(x2.t)} događaja; ` + potvrdjeni.map(t => broj(t)).join(","));
zapisi("8.izvrsivo", ".ics: bez odbijenih, predloga, neizjavljenih i tuđih", !/žalbu na rešenje|odgovor na reviziju|predlog za izvršenje|uplatu takse|plaćanje predujma|bez oznake|TAJNI|žalbu C/.test(x2.t));
await s1.ctx.close();
await browser.close();
zapisi("izolacija", "nijedan zahtev pregledača van 127.0.0.1", spoljni.length === 0, spoljni.slice(0, 2).join());
zapisi("izolacija", "server: 0 pokušaja spoljne veze", st.spoljni_pokusaji === 0);
zapisi("konzola", "bez JS grešaka stranice", greskeJS.length === 0, greskeJS.join(" | ").slice(0, 200));
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
