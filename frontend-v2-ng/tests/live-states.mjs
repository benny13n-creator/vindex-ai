// Vindex V2 NG — Task 5: pošteno stanje LIVE ekrana, bez tragova demo podataka.
// Pokretanje: `node tests/live-states.mjs` (sam podiže fixture).
//
// Za svaki ishod čitanja proverava TAČNO stanje ekrana. EMPTY („Nema aktivnih
// predmeta“) sme da se pojavi samo kada je API uspešno pročitan i ukupno == 0.
// 401/403/429/5xx/mreža/neispravan odgovor nikad ne izgledaju kao prazna
// kancelarija. LIVE ne nosi nijednu oznaku ni stavku demo podataka.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TOKEN = "vx-states-token-NE-U-LOG-55ee";
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
const sesija = () => JSON.stringify({ access_token: TOKEN, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "k1", email: "k1@primer.test" } });

const browser = await chromium.launch();

// Demo nazivi i obaveze — iz stvarnog DEMO ekrana, da bi se tražili u LIVE.
let ZABRANJENO;
{
  const f = await pokreniFixture(async () => false);
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${f.port}/`);
  ZABRANJENO = await p.evaluate(() => [...window.VX_DEMO.predmeti.map(x => x.naziv), ...window.VX_DEMO.paznja.map(x => x.naslov), "Demonstracioni podaci", "Demo nalog", "Referentni demo datum", "Demonstracioni sadržaj"]);
  await ctx.close(); await f.zatvori();
}

async function scenario(api, cekaj = true) {
  const f = await pokreniFixture(api);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await ctx.addInitScript(([k, v]) => { localStorage.setItem(k, v); }, [KLJUC, sesija()]);
  const p = await ctx.newPage();
  const greske = [];
  p.on("pageerror", e => greske.push(String(e)));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live`);
  if (cekaj) {
    await p.waitForFunction(() => {
      const e = document.getElementById("empty");
      return !e.hidden ? e.dataset.stanje !== "ucitavanje" : document.querySelectorAll("#rows tr").length > 0;
    }, null, { timeout: 15000 }).catch(() => {});
  }
  return { f, ctx, p, greske };
}
const ekran = (p) => p.evaluate(() => {
  const vid = (sel) => { const e = document.querySelector(sel); return !!e && !e.hidden && e.getClientRects().length > 0; };
  return {
    stanje: document.getElementById("empty").hidden ? "registar" : (document.getElementById("empty").dataset.stanje || ""),
    naslov: document.getElementById("empty-title").textContent,
    tekst: document.getElementById("empty-text").textContent,
    redova: document.querySelectorAll("#rows tr").length,
    broj: document.getElementById("count").textContent,
    pretragaIskljucena: document.getElementById("pretraga").disabled,
    strana: document.body.innerText,
    caption: document.querySelector(".cases caption").textContent,
    znacka: vid(".demo-badge"), nalog: vid(".account"), napomena: vid(".panel__note"),
    stavkiPanela: document.querySelectorAll("#attention li").length,
    panelNaslov: document.querySelector("#attention-empty .panel__empty-title").textContent,
    panelVidljiv: !document.getElementById("attention-empty").hidden,
  };
});
async function zatvori(s) { await s.ctx.close(); await s.f.zatvori(); }

function bezDemoa(oznaka, e) {
  const nadjeno = ZABRANJENO.filter(z => e.strana.includes(z));
  zapisi(oznaka, "nijedan demo naziv, obaveza ni oznaka u tekstu strane", nadjeno.length === 0, nadjeno.slice(0, 3).join(" | "));
  zapisi(oznaka, "značka „Demonstracioni podaci“ i „Demo nalog“ nisu vidljive", !e.znacka && !e.nalog);
  zapisi(oznaka, "napomena „Demonstracioni sadržaj“ nije vidljiva; natpis tabele bez „demonstracioni“", !e.napomena && !/demonstracion/i.test(e.caption), e.caption);
  zapisi(oznaka, "panel: nijedna stavka, neutralno „nije povezan“", e.stavkiPanela === 0 && e.panelVidljiv && /nije povezan/.test(e.panelNaslov), e.panelNaslov);
  zapisi(oznaka, "nijedna pravna tvrdnja bez izvora („Nema obaveza/rokova“, „Sve je u redu“)", !/Nema obaveza|Nema rokova|Sve je u redu|Nema stavki/.test(e.strana));
}

// ── Greške: svaka svoje stanje, nijedna „prazna kancelarija“ ────────────
const GRESKE = [
  ["401", "greska-prijava", /Prijava više nije važeća/, { status: 401, telo: { detail: "Invalid token" } }],
  ["403", "greska-pristup", /Nemate pristup/, { status: 403 }],
  ["404", "greska-servis", /nije pronađen/, { status: 404 }],
  ["429", "greska-ogranicenje", /Previše zahteva/, { status: 429 }],
  ["500", "greska-server", /ne odgovara/, { status: 500 }],
  ["503", "greska-server", /ne odgovara/, { status: 503 }],
];
for (const [ime, stanjeUI, naslovRe, odgovor] of GRESKE) {
  const s = await scenario(predmetiRuta({ [TOKEN]: { id: "k1", predmeti: napraviPredmete("k1", 12) } }, { preStrane: () => odgovor }));
  const e = await ekran(s.p);
  zapisi(ime, `stanje „${stanjeUI}“`, e.stanje === stanjeUI, e.stanje);
  zapisi(ime, "naslov opisuje grešku", naslovRe.test(e.naslov), e.naslov);
  zapisi(ime, "NIJE „Nema aktivnih predmeta“ i nema redova", e.redova === 0 && !/Nema aktivnih/.test(e.naslov + e.tekst));
  zapisi(ime, "broj se ne prikazuje (nije „0 predmeta“)", e.broj === "", JSON.stringify(e.broj));
  zapisi(ime, "pretraga isključena", e.pretragaIskljucena);
  bezDemoa(ime, e);
  await zatvori(s);
}
// 429 sa Retry-After: tekst kaže koliko čekati.
{
  const s = await scenario(async (req, url, res) => {
    if (url.pathname !== "/api/predmeti") return false;
    res.writeHead(429, { "Content-Type": "application/json", "Retry-After": "30" }); res.end('{"error":"Rate limit"}'); return true;
  });
  const e = await ekran(s.p);
  zapisi("429+Retry-After", "tekst navodi čekanje od 30 s", e.stanje === "greska-ogranicenje" && /30 s/.test(e.tekst), e.tekst);
  await zatvori(s);
}
// Mreža i neispravan odgovor.
for (const [ime, stanjeUI, api] of [
  ["mreza", "greska-mreza", async (req, url) => { if (url.pathname !== "/api/predmeti") return false; req.socket.destroy(); return true; }],
  ["los-json", "greska-odgovor", async (req, url, res) => { if (url.pathname !== "/api/predmeti") return false; res.writeHead(200, { "Content-Type": "application/json" }); res.end("{nije"); return true; }],
  ["los-oblik", "greska-odgovor", async (req, url, res) => { if (url.pathname !== "/api/predmeti") return false; res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"predmeti":"x"}'); return true; }],
]) {
  const s = await scenario(api);
  const e = await ekran(s.p);
  zapisi(ime, `stanje „${stanjeUI}“, nije prazna lista`, e.stanje === stanjeUI && e.redova === 0 && !/Nema aktivnih/.test(e.naslov), `${e.stanje} / ${e.naslov}`);
  bezDemoa(ime, e);
  await zatvori(s);
}

// ── LOADING: vidljivo dok server ne odgovori ─────────────────────────────
{
  let pusti; const kapija = new Promise(r => { pusti = r; });
  const s = await scenario(predmetiRuta({ [TOKEN]: { id: "k1", predmeti: napraviPredmete("k1", 12) } }, { preStrane: () => kapija }), false);
  await s.p.waitForFunction(() => window.VxSesija && document.getElementById("empty").dataset.stanje === "ucitavanje", null, { timeout: 5000 }).catch(() => {});
  const e = await ekran(s.p);
  zapisi("ucitavanje", "dok čeka: stanje „ucitavanje“", e.stanje === "ucitavanje", e.stanje);
  zapisi("ucitavanje", "dok čeka: nije „Nema aktivnih predmeta“, nema broja", !/Nema aktivnih/.test(e.naslov) && e.broj === "", e.naslov);
  bezDemoa("ucitavanje", e);
  pusti();
  await s.p.waitForFunction(() => document.querySelectorAll("#rows tr").length === 12, null, { timeout: 5000 }).catch(() => {});
  const posle = await ekran(s.p);
  zapisi("ucitavanje", "posle odgovora: registar sa 12 predmeta", posle.stanje === "registar" && posle.redova === 12 && posle.broj === "12 predmeta", `${posle.stanje} ${posle.redova}`);
  bezDemoa("uspeh", posle);
  await zatvori(s);
}

// ── EMPTY samo kada je ukupno == 0 posle uspešnog čitanja ────────────────
{
  const s = await scenario(predmetiRuta({ [TOKEN]: { id: "k1", predmeti: [] } }));
  const e = await ekran(s.p);
  zapisi("prazno", "uspešno čitanje + ukupno 0 → „Nema aktivnih predmeta“, stanje „prazno“", e.stanje === "prazno" && e.naslov === "Nema aktivnih predmeta" && e.broj === "0 predmeta", `${e.stanje} / ${e.naslov} / ${e.broj}`);
  bezDemoa("prazno", e);
  await zatvori(s);
}

// ── DEMO zadržava sve demo oznake i obaveze ─────────────────────────────
{
  const f = await pokreniFixture(async () => false);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${f.port}/`);
  const e = await ekran(p);
  zapisi("demo", "DEMO: značka, „Demo nalog“, napomena i 5 obaveza ostaju", e.znacka && e.nalog && e.napomena && e.stavkiPanela === 5, `${e.znacka} ${e.nalog} ${e.napomena} ${e.stavkiPanela}`);
  await ctx.close(); await f.zatvori();
}

await browser.close();
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
