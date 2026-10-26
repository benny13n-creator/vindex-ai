// Settings Master Sprint P2: Izgled i rad — tema u Podešavanjima je ISTA postavka kao prekidač u gornjoj traci.
// Nema mrežnih zahteva pri promeni teme; tema je postavka uređaja (ne podatak naloga).
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { kombinuj, napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { podesavanjaRuta, podesavanjaMock, KORISNICI, sesija, KLJUC } from "./fixtures/podesavanja-api.mjs";

let pada = 0;
function proveri(naziv, uslov) { console.log((uslov ? "PASS" : "FAIL") + "  " + naziv); if (!uslov) pada++; }
const s = podesavanjaMock();
const f = await pokreniFixture(kombinuj(predmetiRuta(Object.fromEntries(Object.values(KORISNICI).map(k => [k.token, { id: k.id, predmeti: napraviPredmete(k.id, 1) }]))), podesavanjaRuta(s)));
const browser = await chromium.launch();
const greske = [];
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); localStorage.removeItem("vx-ng-tema"); } }, [KLJUC, sesija(KORISNICI.A)]);
await ctx.route("**/*", r => new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort());
const page = await ctx.newPage();
page.on("pageerror", e => greske.push(String(e)));
const stanje = () => page.evaluate(() => ({ tema: document.documentElement.dataset.theme, dark: document.getElementById("pn-tema-dark").checked,
  light: document.getElementById("pn-tema-light").checked, gore: document.getElementById("theme-toggle-label").textContent, sacuvano: localStorage.getItem("vx-ng-tema") }));

await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/izgled");
await page.waitForFunction(() => !document.getElementById("pn-izgled").hidden);
let x = await stanje();
proveri("Izgled: podrazumevana tamna tema prikazana i u Podešavanjima i gore", x.tema === "dark" && x.dark && !x.light && x.gore === "Svetla tema");
const zahteviPre = s.zahtevi.length;
await page.locator("#pn-tema-light").check();
x = await stanje();
proveri("Izgled: izbor „Svetla“ menja temu, prekidač gore i sačuvanu vrednost", x.tema === "light" && x.light && !x.dark && x.gore === "Tamna tema" && x.sacuvano === "light");
await page.locator("#theme-toggle").click();
x = await stanje();
proveri("Izgled: prekidač gore odmah menja izbor u Podešavanjima (bez desinhronizacije)", x.tema === "dark" && x.dark && !x.light && x.sacuvano === "dark");
await page.locator("#pn-tema-dark").focus();
await page.keyboard.press("ArrowRight");
x = await stanje();
proveri("Izgled: tastatura (strelica u grupi) menja temu", x.tema === "light" && x.light);
proveri("Izgled: promena teme ne šalje nijedan zahtev", s.zahtevi.length === zahteviPre);
await page.reload();
await page.waitForFunction(() => !document.getElementById("pn-izgled").hidden);
x = await stanje();
proveri("Izgled: posle osvežavanja tema i izbor ostaju usklađeni", x.tema === "light" && x.light && x.gore === "Tamna tema");
await page.goto("http://127.0.0.1:" + f.port + "/app#/predmeti");
await page.locator("#theme-toggle").click();
await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/izgled");
await page.waitForFunction(() => !document.getElementById("pn-izgled").hidden);
x = await stanje();
proveri("Izgled: promena gore dok Podešavanja nisu otvorena — pri otvaranju izbor je tačan", x.tema === "dark" && x.dark && !x.light);
await page.evaluate(([kl, v]) => { localStorage.setItem(kl, v); window.dispatchEvent(new Event("focus")); }, [KLJUC, sesija(KORISNICI.B)]);
await page.waitForTimeout(300);
x = await stanje();
proveri("Izgled: tema je postavka uređaja — promena naloga ne menja temu i ne nosi lične podatke", x.tema === "dark" && x.dark);
proveri("Izgled: paleta nije menjana (samo postojeće teme dark/light)", await page.evaluate(() => ["dark", "light"].includes(document.documentElement.dataset.theme)));
proveri("P2: nema grešaka skripte", greske.length === 0);
await ctx.close();
await browser.close();
await f.zatvori();
if (pada) { console.error("P2: " + pada + " neuspešnih"); process.exit(1); }
console.log("P2 Izgled i rad: svi scenariji prošli.");
