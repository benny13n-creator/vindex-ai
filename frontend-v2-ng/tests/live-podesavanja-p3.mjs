// Settings Master Sprint P3: Integracije — samo tačno stanje; nijedna integracija se ne prikazuje kao da radi
// bez dokaza, nema kontrola, tehničkih putanja, ključeva ni zahteva ka spoljnim servisima.
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { kombinuj, napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { podesavanjaRuta, podesavanjaMock, KORISNICI, sesija, KLJUC } from "./fixtures/podesavanja-api.mjs";

let pada = 0;
function proveri(naziv, uslov) { console.log((uslov ? "PASS" : "FAIL") + "  " + naziv); if (!uslov) pada++; }
const s = podesavanjaMock();
const f = await pokreniFixture(kombinuj(predmetiRuta(Object.fromEntries(Object.values(KORISNICI).map(k => [k.token, { id: k.id, predmeti: napraviPredmete(k.id, 1) }]))), podesavanjaRuta(s)));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await ctx.addInitScript(([k, v]) => localStorage.setItem(k, v), [KLJUC, sesija(KORISNICI.A)]);
const zahtevi = [], spolja = [], greske = [];
await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname !== "127.0.0.1") { spolja.push(u.href); return r.abort(); } zahtevi.push(u.pathname); return r.continue(); });
const page = await ctx.newPage();
page.on("pageerror", e => greske.push(String(e)));
await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/integracije");
await page.waitForFunction(() => !document.getElementById("pn-integracije").hidden);
const meta = (id) => page.locator('#pn-integr-lista [data-integracija="' + id + '"] .people__meta').innerText();
proveri("Integracije: SEF dostupan samo za podešavanje, slanje faktura jasno nedostupno", /Dostupno za podešavanje/.test(await meta("sef")) && /nije dostupno/.test(await meta("sef")));
proveri("Integracije: email podsetnici upućuju na Obaveštenja", /Dostupno/.test(await meta("email")));
for (const id of ["kalendar", "clio", "webhook", "sms"]) proveri("Integracije: " + id + " jasno označen kao nedostupan", /^Nije dostupno/.test(await meta(id)));
const tekst = await page.locator("#pn-integracije").innerText();
proveri("Integracije: bez tehničkih putanja, ključeva i tokena", !/\/v1\/|\/api\/|webhook\/|vndx_|X-Vindex|secret|token/i.test(tekst));
proveri("Integracije: nema nijedne kontrole (dugme/polje)", (await page.locator("#pn-integracije button, #pn-integracije input, #pn-integracije select").count()) === 0);
const pre = zahtevi.length;
await page.locator('#pn-integr-lista [data-integracija="sef"] a').click();
await page.waitForFunction(() => !document.getElementById("pn-finansije").hidden);
proveri("Integracije: link vodi u odeljak Finansije i plan", new URL(page.url()).hash === "#/podesavanja/finansije");
await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/integracije");
await page.waitForFunction(() => !document.getElementById("pn-integracije").hidden);
proveri("Integracije: otvaranje odeljka ne poziva integracione rute", !zahtevi.some(p => /\/api\/integrations|\/api\/webhooks|\/v1\/|\/api-kljucevi|\/sms\/|\/api\/whatsapp/.test(p)));
proveri("Integracije: nijedan zahtev van loopback-a, nema grešaka skripte", spolja.length === 0 && greske.length === 0);
await ctx.close();
await browser.close();
await f.zatvori();
if (pada) { console.error("P3: " + pada + " neuspešnih"); process.exit(1); }
console.log("P3 Integracije: svi scenariji prošli.");
