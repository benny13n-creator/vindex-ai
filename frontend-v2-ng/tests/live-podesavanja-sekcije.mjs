// P1.1 Podešavanja: ljuska odeljaka (kartice na širokom ekranu, izbor na telefonu, adresa po odeljku).
// Izolovano: statika + mock API na 127.0.0.1; nijedan zahtev ne ide van loopback-a.
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { kombinuj, napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { podesavanjaRuta, podesavanjaMock, KORISNICI, sesija, KLJUC } from "./fixtures/podesavanja-api.mjs";

let pada = 0;
function proveri(naziv, uslov) { console.log((uslov ? "PASS" : "FAIL") + "  " + naziv); if (!uslov) pada++; }

const OCEKIVANE = (process.env.PN_SEKCIJE || "nalog,obavestenja,kancelarija,finansije,privatnost,pomoc").split(",");
const NAZIVI = { nalog: "Moj nalog", izgled: "Izgled i rad", obavestenja: "Obaveštenja", kancelarija: "Kancelarija",
  finansije: "Finansije i plan", integracije: "Integracije", privatnost: "Privatnost i podaci", pomoc: "Pomoć i informacije" };

const stanje = podesavanjaMock();
const f = await pokreniFixture(kombinuj(predmetiRuta({
  [KORISNICI.A.token]: { id: KORISNICI.A.id, predmeti: napraviPredmete(KORISNICI.A.id, 1) },
  [KORISNICI.B.token]: { id: KORISNICI.B.id, predmeti: napraviPredmete(KORISNICI.B.id, 1) },
}), podesavanjaRuta(stanje)));
const browser = await chromium.launch();
const spolja = [];

async function kontekst(sirina, visina) {
  const ctx = await browser.newContext({ viewport: { width: sirina, height: visina } });
  await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, sesija(KORISNICI.A)]);
  await ctx.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") { spolja.push(url.href); return route.abort(); }
    return route.continue();
  });
  return ctx;
}
const baza = "http://127.0.0.1:" + f.port + "/?rezim=live";

// Široki ekran
let ctx = await kontekst(1400, 900);
let page = await ctx.newPage();
const greske = [];
page.on("pageerror", e => greske.push(String(e)));
await page.goto(baza + "#/podesavanja");
await page.waitForSelector("#pn-sekcije .tabs__item");
const kartice = await page.locator("#pn-sekcije .tabs__item").evaluateAll(a => a.map(x => [x.dataset.sekcija, x.textContent, x.getAttribute("href")]));
proveri("Kartice su tačno odeljci sa stvarnom funkcijom, kanonskim redom: " + kartice.map(k => k[0]).join(","),
  JSON.stringify(kartice.map(k => k[0])) === JSON.stringify(OCEKIVANE)
  && kartice.every(k => k[1] === NAZIVI[k[0]] && k[2] === "#/podesavanja/" + k[0]));
proveri("#/podesavanja otvara prvi odeljak", await page.locator("#pn-" + OCEKIVANE[0]).isVisible()
  && await page.locator('#pn-sekcije [aria-current="page"]').getAttribute("data-sekcija") === OCEKIVANE[0]);
proveri("Samo jedan odeljak je vidljiv", (await page.locator("[data-pn-sekcija]:visible").count()) === 1);
proveri("Izbor za telefon je sakriven na širokom ekranu", await page.locator(".pn-izbor").isHidden());
for (const id of OCEKIVANE) {
  await page.locator('#pn-sekcije [data-sekcija="' + id + '"]').click();
  await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, id);
  proveri("Klik na „" + NAZIVI[id] + "“ menja adresu i prikazuje samo taj odeljak", new URL(page.url()).hash === "#/podesavanja/" + id
    && (await page.locator("[data-pn-sekcija]:visible").count()) === 1
    && await page.locator('#pn-sekcije [aria-current="page"]').getAttribute("data-sekcija") === id);
}
await page.goto(baza + "#/podesavanja/nepostojeci");
await page.waitForFunction(() => location.hash !== "#/podesavanja/nepostojeci");
proveri("Nepoznat odeljak se zamenjuje prvim (bez praznog ekrana)", new URL(page.url()).hash === "#/podesavanja/" + OCEKIVANE[0]
  && await page.locator("#pn-" + OCEKIVANE[0]).isVisible());
const zadnji = OCEKIVANE[OCEKIVANE.length - 1];
await page.goto(baza + "#/podesavanja/" + zadnji);
await page.reload();
await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, zadnji);
proveri("Posle osvežavanja ostaje izabrani odeljak", await page.locator('#pn-sekcije [aria-current="page"]').getAttribute("data-sekcija") === zadnji);
await page.goBack();
proveri("Glavna navigacija: Podešavanja ostaju aktivna stavka", await page.locator('.sidenav__item[href="#/podesavanja"]').getAttribute("aria-current") === "page"
  || !(new URL(page.url()).hash.startsWith("#/podesavanja")));
// Tastatura: kartice su linkovi u tab redu, Enter otvara odeljak.
await page.goto(baza + "#/podesavanja/" + OCEKIVANE[0]);
await page.locator('#pn-sekcije [data-sekcija="' + OCEKIVANE[1] + '"]').focus();
await page.keyboard.press("Enter");
await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, OCEKIVANE[1]);
proveri("Tastatura: fokus na kartici + Enter otvara odeljak", new URL(page.url()).hash === "#/podesavanja/" + OCEKIVANE[1]);
proveri("Fokus na kartici je vidljiv", await page.locator('#pn-sekcije [data-sekcija="' + OCEKIVANE[1] + '"]').evaluate(a => {
  a.focus(); const s = getComputedStyle(a); return s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0; }));
await ctx.close();

// Telefon
ctx = await kontekst(375, 812);
page = await ctx.newPage();
page.on("pageerror", e => greske.push(String(e)));
await page.goto(baza + "#/podesavanja");
await page.waitForSelector("#pn-sekcija-izbor option", { state: "attached" });
proveri("Telefon: kartice skrivene, izbor odeljka vidljiv", await page.locator("#pn-sekcije").isHidden() && await page.locator("#pn-sekcija-izbor").isVisible());
proveri("Telefon: izbor nudi iste odeljke", JSON.stringify(await page.locator("#pn-sekcija-izbor option").evaluateAll(o => o.map(x => x.value))) === JSON.stringify(OCEKIVANE));
await page.locator("#pn-sekcija-izbor").selectOption(zadnji);
await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, zadnji);
proveri("Telefon: izbor menja odeljak i adresu", new URL(page.url()).hash === "#/podesavanja/" + zadnji);
proveri("Telefon: nema vodoravnog pomeranja stranice", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
await ctx.close();

proveri("Nema grešaka skripte", greske.length === 0);
proveri("Nijedan zahtev nije otišao van loopback-a", spolja.length === 0);
await browser.close();
await f.zatvori();
if (pada) { console.error("P1.1: " + pada + " neuspešnih provera"); process.exit(1); }
console.log("P1.1 Podešavanja odeljci: svi scenariji prošli.");
