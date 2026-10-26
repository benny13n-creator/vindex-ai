// Snimci V2 Podešavanja: svaki odeljak × tamna/svetla × desktop/telefon, nad mockom ugovora (127.0.0.1).
// Izlaz: PN_SNIMCI_DIR (podrazumevano ./snimci-podesavanja). Proverava i vodoravno pomeranje i greške skripte.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { kombinuj, napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { podesavanjaRuta, podesavanjaMock, KORISNICI, sesija, KLJUC } from "./fixtures/podesavanja-api.mjs";

const DIR = process.env.PN_SNIMCI_DIR || "snimci-podesavanja";
mkdirSync(DIR, { recursive: true });
const SEKCIJE = (process.env.PN_SEKCIJE || "nalog,izgled,obavestenja,kancelarija,finansije,privatnost,pomoc").split(",");
const s = podesavanjaMock();
s.sef[KORISNICI.B.token] = { seller_pib: "123456789", seller_naziv: "Advokatska kancelarija Test", seller_adresa: "Ulica 1", seller_mesto: "Beograd", api_key: "XXXXXXXXXXXXWXYZ" };
s.profilEmail[KORISNICI.B.token] = { aktivan: true, dan_7: true, dan_3: false, dan_1: true, nedeljni: true };
const f = await pokreniFixture(kombinuj(predmetiRuta(Object.fromEntries(Object.values(KORISNICI).map(k => [k.token, { id: k.id, predmeti: napraviPredmete(k.id, 1) }]))), podesavanjaRuta(s)));
const browser = await chromium.launch();
let pada = 0;
for (const tema of ["dark", "light"]) for (const [ime, w, h] of [["desktop", 1400, 900], ["telefon", 375, 812]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem(k, v); localStorage.setItem("vx-ng-tema", t); }, [KLJUC, sesija(KORISNICI.B), tema]);
  await ctx.route("**/*", r => new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort());
  const page = await ctx.newPage(), greske = [];
  page.on("pageerror", e => greske.push(String(e)));
  for (const sek of SEKCIJE) {
    await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/" + sek);
    await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, sek);
    await page.waitForTimeout(500);
    const tema2 = await page.evaluate(() => document.documentElement.dataset.theme);
    const preliv = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    await page.screenshot({ path: `${DIR}/${sek}-${tema}-${ime}.png`, fullPage: true });
    const ok = tema2 === tema && !preliv;
    if (!ok) pada++;
    console.log((ok ? "PASS" : "FAIL") + `  ${sek} ${tema} ${ime} (tema=${tema2}, vodoravni preliv=${preliv})`);
  }
  if (greske.length) { pada++; console.log("FAIL  greške skripte: " + greske.join(" | ")); }
  await ctx.close();
}
await browser.close();
await f.zatvori();
if (pada) { console.error(pada + " neuspešnih"); process.exit(1); }
console.log("Snimci Podešavanja: svi prošli.");
