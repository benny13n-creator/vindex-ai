// Vindex V2 NG — Task 4: aktivni predmeti iz postojećeg GET /api/predmeti.
// Pokretanje: `node tests/live-matters.mjs` (sam podiže fixture).
//
// Fixture verno ponavlja ugovor api.py (tests/fixtures/predmeti-api.mjs).
// Tokeni i predmeti su izmišljeni; ništa ne ide van 127.0.0.1.

import { chromium } from "playwright";
import http from "node:http";
import { readFile } from "node:fs/promises";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TOKEN = "vx-matters-token-NE-U-LOG-44dd";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const sesija = (id) => JSON.stringify({ access_token: TOKEN, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id, email: id + "@primer.test" } });

const browser = await chromium.launch();

async function scenario(predmeti, { kuke = {}, korisnik = "k1" } = {}) {
  const f = await pokreniFixture(predmetiRuta({ [TOKEN]: { id: korisnik, predmeti } }, kuke));
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.addInitScript(([k, v]) => { localStorage.setItem(k, v); }, [KLJUC, sesija(korisnik)]);
  const p = await ctx.newPage();
  const greske = [];
  let bajtova = 0;
  p.on("pageerror", e => greske.push(String(e)));
  p.on("response", async (r) => { if (new URL(r.url()).pathname === "/api/predmeti") { try { bajtova += (await r.body()).length; } catch {} } });
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live`);
  await p.waitForFunction(() => {
    const e = document.getElementById("empty");
    return !e.hidden ? e.dataset.stanje !== "ucitavanje" : document.querySelectorAll("#rows tr").length > 0;
  }, null, { timeout: 15000 }).catch(() => {});
  await p.waitForTimeout(100);
  return { f, ctx, p, greske, bajtova: () => bajtova };
}
const ekran = (p) => p.evaluate(() => ({
  ids: Array.from(document.querySelectorAll("#rows tr")).map(tr => tr.dataset.id),
  broj: document.getElementById("count").textContent,
  stanje: document.getElementById("empty").hidden ? "registar" : (document.getElementById("empty").dataset.stanje || "prazno"),
  naslov: document.getElementById("empty-title").textContent,
  tekstPraznog: document.getElementById("empty-text").textContent,
  pretragaIskljucena: document.getElementById("pretraga").disabled,
}));
async function zatvori(s) { await s.ctx.close(); await s.f.zatvori(); }

// ── 0 / 1 / 12 / 240 ─────────────────────────────────────────────────────
for (const [n, ocekivanBroj] of [[0, "0 predmeta"], [1, "1 predmet"], [12, "12 predmeta"], [240, "240 predmeta"]]) {
  const s = await scenario(napraviPredmete("k1", n));
  const e = await ekran(s.p);
  if (n === 0) {
    zapisi(`n=${n}`, "uspešno pročitano, ukupno 0 → „Nema aktivnih predmeta“", e.stanje === "prazno" && e.naslov === "Nema aktivnih predmeta", `${e.stanje} / ${e.naslov}`);
  } else {
    zapisi(`n=${n}`, `prikazano svih ${n}`, e.ids.length === n, `${e.ids.length}`);
  }
  zapisi(`n=${n}`, `broj „${ocekivanBroj}“ iz API ukupno`, e.broj === ocekivanBroj, e.broj);
  const z = s.f.zahtevi;
  zapisi(`n=${n}`, "tačno jedan zahtev (limit 500 pokriva sve)", z.length === 1, `${z.length}`);
  zapisi(`n=${n}`, "bez JS grešaka", s.greske.length === 0, s.greske.join(" | "));
  if (n === 240) console.log(`INFO  [n=240] veličina odgovora (pun select, sa case_dna): ${s.bajtova()} B ≈ ${(s.bajtova() / 1024).toFixed(0)} KiB, ${(s.bajtova() / 240 / 1024).toFixed(1)} KiB po predmetu`);
  await zatvori(s);
}

// ── 1037 aktivnih + neaktivni + u brisanju → 3 strane ───────────────────
{
  const UKUPNO_AKT = 1037;
  const aktivni = napraviPredmete("k1", UKUPNO_AKT, { u_brisanju: i => i % 150 === 7 });
  const neaktivni = napraviPredmete("k1x", 60, { status: i => (i % 2 ? "zatvoren" : "arhiviran") }).map(p => ({ ...p, user_id: "k1" }));
  const tudji = napraviPredmete("tudji", 30);
  const s = await scenario([...aktivni, ...neaktivni, ...tudji]);
  const e = await ekran(s.p);
  const uBrisanju = aktivni.filter(p => p.brisanje_zapoceto).map(p => p.id);
  const ocekivani = new Set(aktivni.filter(p => !p.brisanje_zapoceto).map(p => p.id));
  const z = s.f.zahtevi;
  zapisi("1037", "tri zahteva: offset 0, 500, 1000", z.length === 3 && z.map(x => x.parametri.offset).join(",") === "0,500,1000", z.map(x => x.parametri.offset).join(","));
  zapisi("1037", "svaki zahtev: status=aktivan, limit=500, GET, Bearer", z.every(x => x.parametri.status === "aktivan" && x.parametri.limit === "500" && x.metod === "GET" && x.auth === `Bearer ${TOKEN}`));
  // NS002 Task 4 (founder): lista koristi `view=summary`; nikad user_id ni q.
  zapisi("1037", "svaki zahtev: view=summary, bez user_id i bez q", z.every(x => x.parametri.view === "summary" && !("user_id" in x.parametri) && !("q" in x.parametri)), JSON.stringify(z[0].parametri));
  zapisi("1037", "nema duplikata", new Set(e.ids).size === e.ids.length);
  zapisi("1037", `svih ${ocekivani.size} aktivnih (bez ${uBrisanju.length} u brisanju) prikazano, nijedan izgubljen`, e.ids.length === ocekivani.size && e.ids.every(id => ocekivani.has(id)), `${e.ids.length}`);
  zapisi("1037", "nijedan neaktivan ni tuđ predmet", e.ids.every(id => id.startsWith("k1-")));
  zapisi("1037", "nijedan predmet u brisanju", !e.ids.some(id => uBrisanju.includes(id)));
  // NS002 Task 4 (founder): prikazani broj = stvarno učitani jedinstveni predmeti,
  // ne `ukupno` servera (koje broji i predmete u brisanju).
  zapisi("1037", `prikazani broj = stvarno prikazani predmeti (${ocekivani.size}), ne server ukupno 1037`, e.broj === `${ocekivani.size} predmeta` && e.ids.length === ocekivani.size, e.broj);
  await zatvori(s);
}

// ── NS002 Task 4: ukupno servera 12, jedan u brisanju → prikaz 11 ───────
{
  const s = await scenario(napraviPredmete("k1", 12, { u_brisanju: i => i === 3 }));
  const e = await ekran(s.p);
  const z = s.f.zahtevi;
  zapisi("brisanje", "server ukupno 12, jedan u brisanju: prikazano 11 redova i „11 predmeta“", e.ids.length === 11 && e.broj === "11 predmeta", `${e.ids.length} / ${e.broj}`);
  zapisi("brisanje", "jedan zahtev, bez beskonačne petlje", z.length === 1, `${z.length}`);
  await s.p.fill("#pretraga", "broj 7");
  const p = await ekran(s.p);
  zapisi("brisanje", "broj pri pretrazi je u odnosu na stvarnih 11 („1 od 11 predmeta“)", p.broj === "1 od 11 predmeta", p.broj);
  await zatvori(s);
}

// ── NS002 Task 4: LIVE ne obećava sud ────────────────────────────────────
{
  const s = await scenario(napraviPredmete("k1", 3));
  const r = await s.p.evaluate(() => ({
    zaglavlje: document.querySelector('.cases th[data-kljuc="broj"] .sort').textContent,
    ph: document.getElementById("pretraga").placeholder,
    sudova: document.querySelectorAll("#rows .ref__court").length,
  }));
  zapisi("sud", "LIVE zaglavlje kolone je „Broj predmeta“", r.zaglavlje === "Broj predmeta", r.zaglavlje);
  zapisi("sud", "LIVE pretraga ne pominje sud", !/sud/i.test(r.ph), r.ph);
  zapisi("sud", "LIVE ne prikazuje polje suda ni zamenski „—“ za sud", r.sudova === 0, `${r.sudova}`);
  await zatvori(s);
}
{
  const f = await pokreniFixture(async () => false);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${f.port}/`);
  const zag = await p.evaluate(() => document.querySelector('.cases th[data-kljuc="broj"] .sort').textContent);
  zapisi("sud", "DEMO zadržava „Broj i sud“", zag === "Broj i sud", zag);
  await ctx.close(); await f.zatvori();
}

// ── NS002 Task 4: veličina odgovora, pun vs summary (240 predmeta) ──────
{
  const f = await pokreniFixture(predmetiRuta({ [TOKEN]: { id: "k1", predmeti: napraviPredmete("k1", 240) } }));
  const dohvati = (upit) => new Promise((res) => http.get({ host: "127.0.0.1", port: f.port, path: "/api/predmeti?" + upit, headers: { Authorization: `Bearer ${TOKEN}` } },
    (r) => { const d = []; r.on("data", c => d.push(c)); r.on("end", () => res(Buffer.concat(d))); }));
  const pun = await dohvati("status=aktivan&limit=500&offset=0");
  const sum = await dohvati("view=summary&status=aktivan&limit=500&offset=0");
  const sj = JSON.parse(sum.toString("utf8"));
  const smanjenje = (1 - sum.length / pun.length) * 100;
  console.log(`INFO  [payload] 240 predmeta: pun ${pun.length} B, summary ${sum.length} B, smanjenje ${smanjenje.toFixed(1)}%`);
  zapisi("payload", "summary ne sadrži case_dna", !sum.toString("utf8").includes("case_dna") && sj.predmeti.every(x => !("case_dna" in x)));
  zapisi("payload", "summary je materijalno manji od punog odgovora", sum.length * 2 < pun.length, `${smanjenje.toFixed(1)}%`);
  zapisi("payload", "summary nosi polja koja lista prikazuje i pretražuje", sj.predmeti.every(x => ["id", "naziv", "status", "broj_predmeta", "tuzilac", "tuzeni", "updated_at"].every(k => k in x)));
  await f.zatvori();
}

// ── Mapiranje polja: samo stvarna polja ─────────────────────────────────
{
  const p = napraviPredmete("k1", 3, { broj: i => (i === 1 ? null : `P ${700 + i}/2026`), tuzeni: i => (i === 2 ? "" : `Tuženi ${i}`) });
  const s = await scenario(p);
  const redovi = await s.p.evaluate(() => Array.from(document.querySelectorAll("#rows tr")).map(tr => ({
    id: tr.dataset.id,
    naziv: tr.querySelector(".case__name").textContent,
    meta: tr.querySelector(".case__meta").textContent,
    broj: tr.querySelector(".ref__no").textContent,
    sud: tr.querySelector(".ref__court") ? tr.querySelector(".ref__court").textContent : null,
    stanje: tr.querySelector(".state").textContent,
    datum: tr.querySelector("time").textContent,
  })));
  const r0 = redovi.find(r => r.id === "k1-00000"), r1 = redovi.find(r => r.id === "k1-00001"), r2 = redovi.find(r => r.id === "k1-00002");
  zapisi("polja", "naziv iz `naziv`", r0.naziv === "Predmet k1 broj 0");
  zapisi("polja", "broj iz `broj_predmeta`", r0.broj === "P 700/2026", r0.broj);
  zapisi("polja", "bez broja → „—“, ne izmišljen broj", r1.broj === "—", r1.broj);
  zapisi("polja", "stranke iz `tuzilac`/`tuzeni`", r0.meta === "Tužilac 0·Tuženi 0", r0.meta);
  zapisi("polja", "prazna stranka se ne prikazuje", r2.meta === "Tužilac 2", r2.meta);
  zapisi("polja", "sud se NE prikazuje (ne postoji u odgovoru)", redovi.every(r => r.sud === null));
  zapisi("polja", "stanje „Aktivan“ iz `status`", redovi.every(r => r.stanje === "Aktivan"));
  zapisi("polja", "datum iz `updated_at`", r0.datum === "06.10.2026.", r0.datum);
  await zatvori(s);
}

// ── Pretraga samo nad učitanim poljima ───────────────────────────────────
{
  const s = await scenario(napraviPredmete("k1", 12));
  const ph = await s.p.locator("#pretraga").getAttribute("placeholder");
  zapisi("pretraga", "placeholder ne obećava klijenta ni sud", !/klijent|sud/i.test(ph) && /stranka/i.test(ph), ph);
  for (const [upit, ocekivano, opis] of [
    ["broj 7", 1, "naziv"], ["P 1003/2026", 1, "broj predmeta"], ["Tužilac 11", 1, "tužilac"],
    ["tuzeni 4", 1, "tuženi bez dijakritika"], ["TAJNI-OPIS", 0, "`opis` NIJE učitan u pretragu"],
    ["Činjenica", 0, "`case_dna` NIJE u pretrazi"], ["Osnovni sud", 0, "sud ne postoji"],
  ]) {
    await s.p.fill("#pretraga", upit);
    const e = await ekran(s.p);
    zapisi("pretraga", `„${upit}“ (${opis}) → ${ocekivano}`, e.ids.length === ocekivano, `${e.ids.length}`);
    if (ocekivano === 0) zapisi("pretraga", `poruka opisuje stvarna polja (${opis})`, /nazivu, broju predmeta i strankama/.test(e.tekstPraznog) && !/klijent|sudu/.test(e.tekstPraznog), e.tekstPraznog);
  }
  zapisi("pretraga", "pretraga ne šalje nove zahteve", s.f.zahtevi.length === 1, `${s.f.zahtevi.length}`);
  await zatvori(s);
}

// ── Zlonameran HTML u podacima se prikazuje kao TEKST ───────────────────
{
  const NAZIV = '<img src=x onerror="window.__xss=1">Predmet<script>window.__xss=2</script>';
  const STRANKA = '<b onmouseover="window.__xss=3">Zli</b>';
  const s = await scenario(napraviPredmete("k1", 2, { naziv: i => (i === 0 ? NAZIV : "Običan"), tuzilac: () => STRANKA }));
  const r = await s.p.evaluate(() => ({
    elemenata: document.querySelectorAll("#rows img, #rows script, #rows b").length,
    xss: window.__xss,
    naziv: document.querySelector('#rows tr[data-id="k1-00000"] .case__name').textContent,
    meta: document.querySelector('#rows tr[data-id="k1-00000"] .case__meta').textContent,
  }));
  zapisi("xss", "nijedan <img>/<script>/<b> nije napravljen u registru", r.elemenata === 0, `${r.elemenata}`);
  zapisi("xss", "nijedan injektovan kod nije izvršen", r.xss === undefined, String(r.xss));
  zapisi("xss", "naziv je prikazan doslovno kao tekst", r.naziv === NAZIV);
  zapisi("xss", "stranka je prikazana doslovno kao tekst", r.meta.includes(STRANKA));
  await zatvori(s);
}
{
  const izvori = await Promise.all(["src/app.js", "src/predmeti.js", "src/live.js", "src/api.js", "src/session.js"].map(f => readFile(new URL("../" + f, import.meta.url), "utf8")));
  const opasno = izvori.flatMap((t, i) => (t.match(/innerHTML|outerHTML\s*=|insertAdjacentHTML|document\.write/g) || []).map(m => i + ":" + m));
  zapisi("xss", "nijedan innerHTML/outerHTML=/insertAdjacentHTML/document.write u LIVE kodu", opasno.length === 0, opasno.join(","));
}

// ── Nedosledne strane → greška, nikad delimična lista ───────────────────
{
  const s = await scenario(napraviPredmete("k1", 1037), { kuke: { izmeniOdgovor: (t, off) => (off === 500 ? { ...t, ukupno: t.ukupno + 1 } : t) } });
  const e = await ekran(s.p);
  zapisi("nedosledno", "ukupno se promenilo između strana → greška, 0 redova", /^greska-/.test(e.stanje) && e.ids.length === 0, `${e.stanje} ${e.ids.length}`);
  await zatvori(s);
}
{
  const s = await scenario(napraviPredmete("k1", 1037), { kuke: { izmeniOdgovor: (t, off) => (off === 500 ? { ...t, predmeti: [t.predmeti[0], ...t.predmeti.slice(1)].map((p, i) => (i === 0 ? { ...p, id: "k1-00000" } : p)) } : t) } });
  const e = await ekran(s.p);
  zapisi("nedosledno", "isti id na dve strane → greška, 0 redova", /^greska-/.test(e.stanje) && e.ids.length === 0, `${e.stanje} ${e.ids.length}`);
  await zatvori(s);
}
{
  const s = await scenario(napraviPredmete("k1", 5), { kuke: { izmeniOdgovor: (t) => ({ predmeti: t.predmeti }) } });
  const e = await ekran(s.p);
  zapisi("oblik", "odgovor bez `ukupno` → greška, ne prazna lista", /^greska-/.test(e.stanje) && e.ids.length === 0, `${e.stanje}`);
  await zatvori(s);
}
{
  const s = await scenario(napraviPredmete("k1", 5), { kuke: { izmeniOdgovor: (t) => ({ ...t, predmeti: t.predmeti.map((p, i) => (i === 2 ? { ...p, naziv: "" } : p)) }) } });
  const e = await ekran(s.p);
  zapisi("oblik", "predmet bez naziva → greška, ne tiho preskakanje", /^greska-/.test(e.stanje) && e.ids.length === 0, `${e.stanje}`);
  await zatvori(s);
}
{
  const s = await scenario(napraviPredmete("k1", 1037), { kuke: { preStrane: (off) => (off === 1000 ? { status: 500 } : null) } });
  const e = await ekran(s.p);
  zapisi("greska-usred", "500 na trećoj strani → greška, ne 1000 predmeta kao „sve“", /^greska-/.test(e.stanje) && e.ids.length === 0, `${e.stanje} ${e.ids.length}`);
  await zatvori(s);
}

await browser.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
