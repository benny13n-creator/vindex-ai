// Vindex V2 NG — N2 ČAROBNJAK PRIJEMA: slučajevi koje N1 zlatni tok ne meri — dva klijenta istog imena, isti klijent sa
// dva legitimna predmeta (i istim nazivom), istovremeni zahtevi, zaobiđena kapija u interfejsu, prekinut unos i tuđ klijent.
// Stvaran V2 /app u Chromium-u nad PRAVIM api.app koji upisuje (tests/osb003_solo_server.py); simulirani su samo modeli,
// embedding/Pinecone i prijava. Ništa ne izlazi van 127.0.0.1. Pokretanje: `node tests/live-n2-carobnjak-e2e.mjs`.
//
// Sintetički podaci: „Marko Marković“ (dve osobe istog imena kod advokata A, treća kod advokata B).
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import http from "node:http";

const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4532, BASE = `http://127.0.0.1:${PORT}`;
const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const PY = process.env.VX_PYTHON || "python";
let pada = 0, ukupno = 0;
const zapisi = (g, n, ok, d = "") => { ukupno++; if (!ok) pada++; console.log(`${ok ? "PASS" : "FAIL"}  [${g}] ${n}${d ? " — " + d : ""}`); };
const nalaz = (g, n, d) => console.log(`INFO  [${g}] ${n} — ${d}`);

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
for (const k of ["SUPABASE_DB_URL", "DATABASE_URL"]) delete env[k];
const srv = spawn(PY, ["tests/osb003_solo_server.py", String(PORT)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
let srvIzlaz = ""; srv.stdout.on("data", d => srvIzlaz += d); srv.stderr.on("data", d => srvIzlaz += d);
const zahtev = (p, opt = {}) => new Promise(r => {
  const q = http.request(BASE + p, { method: opt.method || "GET", headers: opt.headers || {} }, s => { let b = ""; s.on("data", c => b += c); s.on("end", () => r({ s: s.statusCode, b })); });
  q.on("error", () => r({ s: 0, b: "" })); if (opt.telo) q.write(opt.telo); q.end();
});
let spreman = false;
for (let i = 0; i < 300 && !spreman; i++) { spreman = (await zahtev("/app")).s === 200; if (!spreman) await new Promise(r => setTimeout(r, 300)); }
zapisi("server", "pravi api.app nad bazom koja upisuje", spreman, spreman ? "" : srvIzlaz.slice(-600));
if (!spreman) { srv.kill(); process.exit(1); }
const zlatni = async () => JSON.parse((await zahtev("/__osb003/zlatni")).b);
const kao = (tok) => (p, metod = "GET", telo) => zahtev(p, { method: metod, headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json" }, telo: telo && JSON.stringify(telo) });
const kaoA = kao("tok-A"), kaoB = kao("tok-B");
const json = (r) => { try { return JSON.parse(r.b); } catch { return null; } };
const pauza = (ms) => new Promise(r => setTimeout(r, ms));

// ── Seme kroz STVARNE rute: dva „Marko Marković“ kod A (razlikuju se samo po kontaktu), treći kod B ──────────────────
const k1 = json(await kaoA("/klijenti", "POST", { tip: "fizicko_lice", ime: "Marko", prezime: "Marković", email: "marko.prvi@primer.test" }));
await pauza(5600);                                         // server odbija isto ime u roku od 5 s (zaštita od duplog klika)
const k2 = json(await kaoA("/klijenti", "POST", { tip: "fizicko_lice", ime: "Marko", prezime: "Marković", telefon: "060 000 1122" }));
const kB = json(await kaoB("/klijenti", "POST", { tip: "fizicko_lice", ime: "Marko", prezime: "Marković", email: "marko.b@primer.test" }));
const K1 = k1 && k1.klijent && k1.klijent.id, K2 = k2 && k2.klijent && k2.klijent.id, KB = kB && kB.klijent && kB.klijent.id;
zapisi("seme", "tri sintetička klijenta istog imena (dva kod A, jedan kod B)", !!(K1 && K2 && KB && K1 !== K2), JSON.stringify([K1, K2, KB]));

const browser = await chromium.launch();
const spoljni = [], greskeJS = [], api500 = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
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
const cekaj = (fn, arg, ms = 15000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const tekstEl = (id) => p.evaluate((i) => (document.getElementById(i) || {}).textContent || "", id);

async function naNovPredmet() {
  await p.goto(BASE + "/app#/");
  await p.goto(BASE + "/app#/predmeti/nov");
  await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
}
async function predlogIzOpisa(opis) {
  await p.click("#nov-rezim-opis");
  await p.fill("#npo-opis", opis);
  await p.click("#npo-predlozi");
  return cekaj(() => !document.getElementById("npo-predlog").hidden);
}
const stavkeKartoteke = () => p.evaluate(() => [...document.querySelectorAll("#npo-klijenti .pick__item")].map(b => b.innerText.replace(/\s+/g, " ").trim()));
async function pretraziKartoteku(q) {
  await p.fill("#npo-klijent-pretraga", q);
  await cekaj(() => document.querySelectorAll("#npo-klijenti .pick__item").length > 0, null, 6000);
  return stavkeKartoteke();
}
/* Provera sukoba; ako ishod traži izričitu potvrdu advokata, advokat je daje (to je dozvoljen tok). Vraća naslov ishoda. */
async function coiIPotvrda() {
  await p.click("#npo-proveri");
  await cekaj(() => !document.getElementById("npo-coi").hidden);
  if (!(await p.evaluate(() => document.getElementById("npo-coi-potvrda-red").hidden))) await p.check("#npo-coi-potvrda");
  return tekstEl("npo-coi-naslov");
}
async function otvoriICekaj() {
  await p.click("#npo-otvori");
  const ok = await cekaj(() => /#\/predmeti\/[^/]+$/.test(location.hash) && !/nov$/.test(location.hash));
  return ok ? decodeURIComponent((await p.evaluate(() => location.hash)).split("/")[2]) : null;
}
const OPIS = "Klijent Marko Marković traži naknadu štete zbog saobraćajne nezgode od osiguravajućeg društva. Cilj: isplata štete.";

// ══ 1) DVA KLIJENTA ISTOG IMENA: advokat mora da vidi KOJI je koji i da predmet ode izabranom ═════════════════════════
await naNovPredmet();
zapisi("1", "predlog iz opisa stigao (model simuliran)", await predlogIzOpisa(OPIS));
const stavke = await pretraziKartoteku("Marković");
zapisi("1", "kartoteka A prikazuje oba svoja Marka, a ne Marka advokata B", stavke.length === 2 && !stavke.some(s => /marko\.b@/.test(s)), JSON.stringify(stavke));
zapisi("1", "dve osobe istog imena se razlikuju u izboru (kontakt u stavci)", stavke.length === 2 && stavke[0] !== stavke[1]
  && stavke.some(s => /060 000 1122/.test(s)) && stavke.some(s => /marko\.prvi@primer\.test/.test(s)), JSON.stringify(stavke));
await p.evaluate(() => { const b = [...document.querySelectorAll("#npo-klijenti .pick__item")].find(x => /060 000 1122/.test(x.innerText)); if (b) b.click(); });
const izbor = await tekstEl("npo-klijent-izbor");
zapisi("1", "potvrda izbora kaže KOJI Marko je izabran", /060 000 1122/.test(izbor), izbor);
await p.fill("#npo-naziv", "Marković — naknada štete");
const coi1 = await coiIPotvrda();
zapisi("1", "provera sukoba izvršena za izabranog klijenta; otvaranje dozvoljeno", await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000), coi1);
const P1 = await otvoriICekaj();
let z = await zlatni();
const klijentiA = () => z.klijenti.filter(k => k.user_id === "uid-A").length;
zapisi("1", "predmet otvoren i vezan za IZABRANOG Marka (ne za drugog), bez novog klijenta",
  !!P1 && z.veze.filter(v => v.predmet_id === P1).length === 1 && z.veze.find(v => v.predmet_id === P1).klijent_id === K2 && klijentiA() === 2, JSON.stringify([P1, z.veze, klijentiA()]));

// ══ 2) ISTI KLIJENT, DRUGI LEGITIMAN PREDMET ISTOG NAZIVA ═════════════════════════════════════════════════════════════
const odmah = await kaoA("/api/intake/kreiraj", "POST", { klijent_id: K2, naziv: "Marković — naknada štete", opis: "drugi", tip: "opsti" });
z = await zlatni();
zapisi("2", "isti naziv odmah posle otvaranja (<5 s) → 409 sa porukom, bez drugog predmeta", odmah.s === 409 && z.predmeti.filter(x => x.user_id === "uid-A").length === 1, `${odmah.s} ${odmah.b.slice(0, 120)}`);
await pauza(5600);                                         // legitiman drugi predmet: advokat ga otvara kasnije
await naNovPredmet();
await predlogIzOpisa(OPIS + " Drugi spor istog klijenta: regres.");
await pretraziKartoteku("Marković");
await p.evaluate(() => { const b = [...document.querySelectorAll("#npo-klijenti .pick__item")].find(x => /060 000 1122/.test(x.innerText)); if (b) b.click(); });
await p.fill("#npo-naziv", "Marković — naknada štete");
const coi2 = await coiIPotvrda();
const coi2Lista = await p.evaluate(() => [...document.querySelectorAll("#npo-coi-lista li")].map(x => x.textContent));
zapisi("2", "provera sukoba za POSTOJEĆEG klijenta sa aktivnim predmetom ne blokira njegov novi predmet",
  await cekaj(() => !document.getElementById("npo-otvori").disabled, null, 5000), JSON.stringify([coi2, coi2Lista, await tekstEl("npo-coi-telo")]));
const P2 = await otvoriICekaj();
z = await zlatni();
const predmetiA = z.predmeti.filter(x => x.user_id === "uid-A");
zapisi("2", "drugi legitiman predmet istog naziva JE otvoren (nije zaključan kao „možda duplikat“)", !!P2 && P2 !== P1 && predmetiA.length === 2,
  JSON.stringify([P1, P2, predmetiA.map(x => x.naziv), await tekstEl("npo-poruka")]));
zapisi("2", "oba predmeta vezana za istog klijenta, klijent nije dupliran", !!P2 && z.veze.find(v => v.predmet_id === P2)?.klijent_id === K2
  && z.veze.find(v => v.predmet_id === P1)?.klijent_id === K2 && klijentiA() === 2, JSON.stringify([z.veze, klijentiA()]));

// ══ 2b) PRAVILO SUKOBA po identitetu (ista funkcija koju koriste čarobnjak i kartica Klijenti), nad sintetičkim odgovorima
const pravilo = await p.evaluate(() => {
  const f = window.VxKlijentiPredmeta.ishod, akt = "aktivan";
  const nal = (o) => Object.assign({ sloj: "klijenti", tip_konflikta: "klijent_u_sistemu", predmet_id: "P-1", predmet_naziv: "Stari", predmet_status: akt,
    klijent_id: "K-2", uloga_klijent: true }, o);
  const s1 = (o) => Object.assign({ sloj: "predmeti", tip_konflikta: "naziv_predmeta", predmet_id: "P-3", predmet_naziv: "Marković protiv Osiguranja", predmet_status: akt,
    klijenti_predmeta: ["K-2"] }, o);
  const odg = (k, potpuna = true) => ({ status: "conflict", provera_potpuna: potpuna, konflikti: k });
  return {
    isti: f(odg([nal({})]), null, "K-2").vrsta,
    imeUNazivuSvog: f(odg([s1({})]), null, "K-2").vrsta,
    imeUNazivuTudjeg: f(odg([s1({ klijenti_predmeta: ["K-9"] })]), null, "K-2").vrsta,
    s1BezSpiska: f(odg([s1({ klijenti_predmeta: undefined })]), null, "K-2").vrsta,
    imenjak: f(odg([nal({ klijent_id: "K-1" })]), null, "K-2").vrsta,
    bezIzbora: f(odg([nal({})]), null, null).vrsta,
    protivna: f(odg([nal({ tip_konflikta: "suprotna_strana", uloga_klijent: false })]), null, "K-2").vrsta,
    ulogaNijePotvrdjena: f(odg([nal({ uloga_klijent: undefined })]), null, "K-2").vrsta,
    istiPlusImenjakIstiPredmet: f(odg([nal({}), nal({ klijent_id: "K-1" })]), null, "K-2").vrsta,
    prazanPredmet: f(odg([nal({ predmet_id: "" }), s1({ predmet_id: "", klijenti_predmeta: [""] })]), null, "K-2").vrsta,
    istiNepotpuna: f(odg([nal({})], false), null, "K-2").vrsta,
  };
});
zapisi("2b", "isti zapis klijenta (izričita uloga klijenta) i ime u nazivu SVOG predmeta → pregled uz potvrdu", pravilo.isti === "pregled" && pravilo.imeUNazivuSvog === "pregled", JSON.stringify(pravilo));
zapisi("2b", "imenjak, protivna strana, nepotvrđena uloga, tuđ predmet, nalaz bez spiska/identiteta, bez izbora → i dalje SUKOB",
  ["imenjak", "protivna", "ulogaNijePotvrdjena", "imeUNazivuTudjeg", "s1BezSpiska", "bezIzbora", "istiPlusImenjakIstiPredmet", "prazanPredmet"].every(k => pravilo[k] === "sukob"), JSON.stringify(pravilo));
zapisi("2b", "nepotpuna provera ostaje nepotpuna i kad je nalaz o istom klijentu", pravilo.istiNepotpuna === "nepotpuna", pravilo.istiNepotpuna);

// ══ 2c) promena izbora POSLE provere: ishod važi samo za klijenta za koga je provera rađena
await naNovPredmet();
await predlogIzOpisa(OPIS + " Promena izbora.");
await pretraziKartoteku("Marković");
await p.evaluate(() => { const b = [...document.querySelectorAll("#npo-klijenti .pick__item")].find(x => /060 000 1122/.test(x.innerText)); if (b) b.click(); });
await p.fill("#npo-naziv", "Promena izbora posle provere");
await coiIPotvrda();
const preIzmene = !(await p.isDisabled("#npo-otvori"));
await p.evaluate(() => { const b = [...document.querySelectorAll("#npo-klijenti .pick__item")].find(x => /marko\.prvi@/.test(x.innerText)); if (b) b.click(); });
zapisi("2c", "drugi Marko izabran posle provere → otvaranje zaključano dok se provera ne ponovi", preIzmene && await p.isDisabled("#npo-otvori"),
  JSON.stringify([preIzmene, await tekstEl("npo-klijent-izbor")]));

// ══ 2d) STVARAN SERVER: izabrani klijent je PROTIVNA STRANA u aktivnom predmetu → sukob (nalaz pregleda M1)
const kDrugi = json(await kaoA("/klijenti", "POST", { tip: "fizicko_lice", ime: "Petar", prezime: "Perić" }));
const pPetar = json(await kaoA("/api/intake/kreiraj", "POST", { klijent_id: kDrugi.klijent.id, naziv: "Perić — naknada", opis: "x", tip: "opsti" }));
const veza = await kaoA(`/api/predmeti/${pPetar.predmet_id}/confirm-links`, "POST", { klijent_ids: [K1], uloga: "protivna_stranka" });
const coiSrv = json(await kaoA("/api/conflict-check", "POST", { ime_prezime: "Marko Marković" }));
const ishodK1 = await p.evaluate(([x, kid]) => window.VxKlijentiPredmeta.ishod(x, null, kid).vrsta, [coiSrv, K1]);
zapisi("2d", "Marko (K1) kao protivna strana u aktivnom predmetu → server: suprotna_strana, V2: SUKOB za izabranog K1",
  veza.s === 200 && ishodK1 === "sukob" && coiSrv.konflikti.some(k => k.klijent_id === K1 && k.tip_konflikta === "suprotna_strana" && k.uloga_klijent === false),
  JSON.stringify([veza.s, ishodK1, coiSrv.konflikti.map(k => [k.sloj, k.tip_konflikta, k.uloga, k.uloga_klijent])]));
// m1: ime klijenta u nazivu NJEGOVOG aktivnog predmeta (stvaran sloj 1) → nov predmet istog klijenta nije blokiran
await pauza(5600);
const k3 = json(await kaoA("/klijenti", "POST", { tip: "fizicko_lice", ime: "Jelena", prezime: "Jelić", email: "jelena@primer.test" }));
await kaoA("/api/intake/kreiraj", "POST", { klijent_id: k3.klijent.id, naziv: "Jelena Jelić protiv Osiguranja", opis: "x", tip: "opsti" });
const coiJ = json(await kaoA("/api/conflict-check", "POST", { ime_prezime: "Jelena Jelić" }));
const ishodJ = await p.evaluate(([x, kid]) => window.VxKlijentiPredmeta.ishod(x, null, kid).vrsta, [coiJ, k3.klijent.id]);
const ishodJBez = await p.evaluate((x) => window.VxKlijentiPredmeta.ishod(x, null, null).vrsta, coiJ);
zapisi("2d", "ime klijentkinje u nazivu NJENOG predmeta (sloj 1) → pregled za nju, a sukob kad klijent nije izabran iz kartoteke",
  ishodJ === "pregled" && ishodJBez === "sukob", JSON.stringify([ishodJ, ishodJBez, coiJ.konflikti.map(k => [k.sloj, k.tip_konflikta, k.klijenti_predmeta])]));

// ══ 3) PREKINUT UNOS: predlog spreman, klijent izabran, stranica osvežena pre otvaranja → ništa upisano, čist početak ═══
await naNovPredmet();
await predlogIzOpisa(OPIS + " Treći, prekinut unos.");
await pretraziKartoteku("Marković");
await p.evaluate(() => { const b = document.querySelector("#npo-klijenti .pick__item"); if (b) b.click(); });
await p.fill("#npo-naziv", "Prekinut unos — ne sme da nastane");
const preReload = await zlatni();
await p.reload();
await cekaj(() => { const f = document.getElementById("nov-forma"); return f && !f.closest("[hidden]"); });
z = await zlatni();
zapisi("3", "osvežavanje usred unosa: nijedan predmet, klijent ni veza nisu upisani", z.predmeti.length === preReload.predmeti.length
  && z.klijenti.length === preReload.klijenti.length && z.veze.length === preReload.veze.length && !z.predmeti.some(x => /Prekinut unos/.test(x.naziv)), JSON.stringify(z.predmeti.map(x => x.naziv)));
await p.click("#nov-rezim-opis");
zapisi("3", "posle osvežavanja čarobnjak počinje čist (bez polovičnog predloga)", await p.evaluate(() => document.getElementById("npo-predlog").hidden && !document.getElementById("npo-opis").value));

// ══ 4) KAPIJE NA SERVERU: tuđ klijent, istovremeni zahtevi, zaobiđena provera sukoba ═════════════════════════════════
const preB = (await zlatni()).predmeti.length;
const rB = await kaoB("/api/intake/kreiraj", "POST", { klijent_id: K1, naziv: "B sa klijentom A", opis: "x", tip: "opsti" });
z = await zlatni();
zapisi("4", "B ne može da otvori predmet za klijenta advokata A (404), i ne ostaje predmet bez klijenta", rB.s === 404 && z.predmeti.length === preB
  && !z.predmeti.some(x => x.naziv === "B sa klijentom A"), `${rB.s} ${rB.b.slice(0, 100)}`);
const rBl = json(await kaoB("/klijenti?pretraga=Markovi%C4%87&limit=20"));
zapisi("4", "kartoteka B vidi samo svog Marka", !!rBl && rBl.klijenti.length === 1 && rBl.klijenti[0].id === KB, JSON.stringify(rBl && rBl.klijenti.map(k => k.id)));
for (const pid of [P1, P2]) {
  const r = await kaoB(`/api/predmeti/${pid}`);
  zapisi("4", `B ne vidi predmet A (${String(pid).slice(0, 8)})`, r.s === 404, String(r.s));
}
const preIst = (await zlatni()).predmeti.length;
const ist = await Promise.all([1, 2].map(() => kaoA("/api/intake/kreiraj", "POST", { klijent_id: K1, naziv: "Istovremeno otvaranje", opis: "x", tip: "opsti" })));
z = await zlatni();
const nastalo = z.predmeti.length - preIst;
nalaz("4", "dva ISTOVREMENA zahteva za isti naziv (dva taba / skript)", `statusi ${ist.map(r => r.s).join("/")}, nastalo predmeta: ${nastalo}`);
zapisi("4", "istovremeni zahtevi za isti naziv: TAČNO jedan predmet, drugi zahtev 409 (nijedan lažan uspeh)",
  nastalo === 1 && ist.filter(r => r.s === 200).length === 1 && ist.filter(r => r.s === 409).length === 1, `${ist.map(r => r.s)} → ${nastalo}`);
const zaobidjen = await kaoA("/api/intake/kreiraj", "POST", { klijent_id: K1, naziv: "Bez provere sukoba", opis: "x", tip: "opsti" });
nalaz("4", "otvaranje direktnim API pozivom BEZ provere sukoba (sopstveni klijent)", `status ${zaobidjen.s} — server ne zahteva proveru; kapija postoji samo u interfejsu (odluka osnivača)`);

// ══ Bezbednost testa ═════════════════════════════════════════════════════════════════════════════════════════════════
zapisi("bezbednost", "0 spoljnih veza", spoljni.length === 0, JSON.stringify(spoljni.slice(0, 3)));
zapisi("bezbednost", "bez JS grešaka i bez 5xx", greskeJS.length === 0 && api500.length === 0, JSON.stringify([greskeJS.slice(0, 3), api500.slice(0, 3)]));

await browser.close();
srv.kill();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
