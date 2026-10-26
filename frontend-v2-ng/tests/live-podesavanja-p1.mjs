// Settings Master Sprint P1: odeljci Podešavanja nad mockom STVARNIH ugovora (tests/fixtures/podesavanja-api.mjs).
// Prijavljen/neprijavljen, negativna autorizacija, promena naloga, odjava u toku, spor server, dupli klik,
// greška upisa. Sve na 127.0.0.1; nijedan stvaran email, SMS, faktura ni brisanje.
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { kombinuj, napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { podesavanjaRuta, podesavanjaMock, KORISNICI, sesija, KLJUC } from "./fixtures/podesavanja-api.mjs";

let pada = 0;
function proveri(naziv, uslov) { console.log((uslov ? "PASS" : "FAIL") + "  " + naziv); if (!uslov) pada++; }
const SAMO = process.env.PN_SAMO ? process.env.PN_SAMO.split(",") : null;
const deo = (ime) => !SAMO || SAMO.includes(ime);

const s = podesavanjaMock();
const f = await pokreniFixture(kombinuj(predmetiRuta(Object.fromEntries(Object.values(KORISNICI).map(k => [k.token, { id: k.id, predmeti: napraviPredmete(k.id, 1) }]))),
  podesavanjaRuta(s)));
const browser = await chromium.launch();
const spolja = [], greske = [];
const LIVE = "http://127.0.0.1:" + f.port + "/?rezim=live", PRIMARNI = "http://127.0.0.1:" + f.port + "/app";

async function otvori(korisnik, adresa, { sirina = 1400, visina = 900 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: sirina, height: visina } });
  if (korisnik) await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, sesija(korisnik)]);
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname !== "127.0.0.1") { spolja.push(u.href); return r.abort(); } return r.continue(); });
  const page = await ctx.newPage();
  page.on("pageerror", e => greske.push(String(e)));
  await page.goto(adresa);
  return { ctx, page };
}
const tekst = (page, sel) => page.locator(sel).innerText();
const odZahteva = (n) => s.zahtevi.slice(n);
async function promeniNalog(page, k) {
  await page.evaluate(([kl, v]) => { localStorage.setItem(kl, v); window.dispatchEvent(new Event("focus")); }, [KLJUC, sesija(k)]);
}

// ═══ P1.2 Moj nalog ═════════════════════════════════════════════════════════
if (deo("nalog")) {
  let n = s.zahtevi.length;
  let { ctx, page } = await otvori(KORISNICI.A, LIVE + "#/podesavanja/nalog");
  await page.waitForFunction(() => document.getElementById("pn-nalog-email").textContent.includes("@"));
  proveri("Nalog: email vlasnika iz /api/me", (await tekst(page, "#pn-nalog-email")) === KORISNICI.A.email);
  proveri("Nalog: aktivni plan i rok iz /api/plan/status", (await tekst(page, "#pn-nalog-plan")) === "Solo — važi do 31.01.2027.");
  proveri("Nalog: zahtevi nose samo token A i samo čitaju", odZahteva(n).length >= 2 && odZahteva(n).every(z => z.token === KORISNICI.A.token && z.metod === "GET"));
  proveri("Nalog: nema izmišljenog polja za ime ni lozinku u V2", (await page.locator("#pn-nalog input").count()) === 0);
  proveri("Nalog: promena lozinke upućuje na postojeći postupak", await page.locator('#pn-nalog a[href="/app-legacy"]').count() === 1);
  proveri("Nalog: van primarnog prikaza nema lažnog dugmeta za odjavu", await page.locator("#pn-nalog-odjava").isHidden());
  n = s.zahtevi.length;
  const odmah = await page.evaluate(([kl, v]) => { localStorage.setItem(kl, v); window.dispatchEvent(new Event("focus"));
    return document.getElementById("pn-nalog").innerText; }, [KLJUC, sesija(KORISNICI.B)]);
  await page.waitForFunction(e => document.getElementById("pn-nalog-email").textContent === e, KORISNICI.B.email);
  proveri("Nalog: promena A→B odmah briše podatke A i puni za B", !odmah.includes(KORISNICI.A.email) && !(await tekst(page, "#pn-nalog")).includes(KORISNICI.A.email)
    && odZahteva(n).every(z => z.token === KORISNICI.B.token) && (await tekst(page, "#pn-nalog-plan")) === "Kancelarija");
  await page.evaluate(kl => { localStorage.removeItem(kl); window.dispatchEvent(new Event("focus")); }, KLJUC);
  await page.waitForFunction(() => document.getElementById("pn-nalog-stanje").textContent.includes("Prijavite se"));
  proveri("Nalog: odjava dok je ekran otvoren uklanja podatke", !(await tekst(page, "#pn-nalog")).includes("@example.test"));
  await ctx.close();

  ({ ctx, page } = await otvori(null, LIVE + "#/podesavanja/nalog"));
  await page.waitForFunction(() => document.getElementById("pn-nalog-stanje").textContent.includes("Prijavite se"));
  proveri("Nalog: neprijavljen korisnik ne šalje zahtev i ne vidi podatke", await page.locator("#pn-nalog-podaci").isHidden()
    && !s.zahtevi.some(z => z.token === null && z.putanja === "/api/me"));
  await ctx.close();

  ({ ctx, page } = await otvori({ ...KORISNICI.A, token: "PN-nevazeci" }, LIVE + "#/podesavanja/nalog"));
  await page.waitForFunction(() => document.getElementById("pn-nalog-stanje").textContent.includes("istekla"));
  proveri("Nalog: nevažeći token → 401 → poruka o prijavi, bez podataka", await page.locator("#pn-nalog-podaci").isHidden());
  await ctx.close();

  s.pada["GET /api/plan/status"] = 503;
  ({ ctx, page } = await otvori(KORISNICI.A, LIVE + "#/podesavanja/nalog"));
  await page.waitForFunction(() => document.getElementById("pn-nalog-plan").textContent.length > 0);
  proveri("Nalog: pad plana se ne prikazuje kao plan", (await tekst(page, "#pn-nalog-plan")) === "Plan trenutno nije učitan.");
  delete s.pada["GET /api/plan/status"];
  await ctx.close();

  s.kasnjenje = 1500;
  ({ ctx, page } = await otvori(KORISNICI.A, LIVE + "#/podesavanja/nalog"));
  await page.waitForTimeout(300);
  proveri("Nalog: spor server → stanje učitavanja, bez starih podataka", (await tekst(page, "#pn-nalog-stanje")).includes("Učitavanje") && await page.locator("#pn-nalog-podaci").isHidden());
  s.kasnjenje = 0;
  await ctx.close();

  ({ ctx, page } = await otvori(KORISNICI.A, PRIMARNI + "#/podesavanja/nalog"));
  await page.waitForFunction(() => document.getElementById("pn-nalog-email").textContent.includes("@"));
  proveri("Nalog (primarni /app): odjava ide postojećim tokom", await page.locator("#pn-nalog-odjava").isVisible()
    && await page.locator("#pn-nalog-odjava").getAttribute("href") === "/app-legacy?odjava=1");
  await ctx.close();
}

// ═══ P1.3 Privatnost i podaci + Pomoć ══════════════════════════════════════
if (deo("privatnost")) {
  let { ctx, page } = await otvori(KORISNICI.A, LIVE + "#/podesavanja/privatnost");
  await page.waitForFunction(() => !document.getElementById("pn-izvoz").disabled);
  proveri("Privatnost: opis izvoza navodi tačno šta izvoz sadrži i šta ne", /osam grupa/.test(await tekst(page, "#pn-privatnost")) && /Ne sadrži: originalne fajlove/.test(await tekst(page, "#pn-privatnost"))
    && !/svi (vaši )?podaci/i.test(await tekst(page, "#pn-privatnost")));
  proveri("Privatnost: linkovi ka postojećim pravnim stranicama", JSON.stringify(await page.locator("#pn-privatnost .pn-linkovi a").evaluateAll(a => a.map(x => x.getAttribute("href"))))
    === JSON.stringify(["/privacy", "/terms", "/dpa", "/security"]));
  let n = s.zahtevi.length;
  const [preuzimanje] = await Promise.all([page.waitForEvent("download"), page.locator("#pn-izvoz").dblclick()]);
  await page.waitForFunction(() => /preuzet/.test(document.getElementById("pn-izvoz-poruka").textContent));
  const izvozi = odZahteva(n).filter(z => z.putanja === "/api/export/complete");
  proveri("Privatnost: izvoz je GET sa tokenom A, dupli klik = jedan zahtev, ime iz servera", izvozi.length === 1 && izvozi[0].metod === "GET" && izvozi[0].token === KORISNICI.A.token
    && preuzimanje.suggestedFilename() === "vindex-export-2026-10-26T10-00-00.zip");
  s.pada["GET /api/export/complete"] = 503;
  await page.locator("#pn-izvoz").click();
  await page.waitForFunction(() => /nije napravljen/.test(document.getElementById("pn-izvoz-poruka").textContent));
  proveri("Privatnost: 503 izvoza (dnevnik nije dokazan) → bez fajla, jasna greška", true);
  delete s.pada["GET /api/export/complete"];

  proveri("Brisanje: dugme je onemogućeno bez potvrde", await page.locator("#pn-brisanje").isDisabled());
  await page.locator("#pn-brisanje-potvrda").fill(KORISNICI.B.email);
  proveri("Brisanje: tuđa adresa ne otključava brisanje", await page.locator("#pn-brisanje").isDisabled());
  await page.locator("#pn-brisanje-potvrda").fill(KORISNICI.A.email.toUpperCase() + " ");
  proveri("Brisanje: tačna adresa naloga (bez obzira na velika slova/razmak) otključava", await page.locator("#pn-brisanje").isEnabled());
  s.pada["DELETE /api/gdpr/account"] = 403;
  await page.locator("#pn-brisanje").click();
  await page.waitForFunction(() => /ne može obrisati/.test(document.getElementById("pn-brisanje-poruka").textContent));
  proveri("Brisanje: 403 → „ništa nije promenjeno“, bez lažnog uspeha", s.anonimizovani.length === 0 && /Ništa nije promenjeno/.test(await tekst(page, "#pn-brisanje-poruka")));
  s.pada["DELETE /api/gdpr/account"] = 502;
  await page.locator("#pn-brisanje").click();
  await page.waitForFunction(() => /nije potvrdio ishod/.test(document.getElementById("pn-brisanje-poruka").textContent));
  proveri("Brisanje: 5xx → ishod nepoznat, ne „uspeh“ ni „nije izvršeno“", true);
  delete s.pada["DELETE /api/gdpr/account"];
  n = s.zahtevi.length;
  await page.locator("#pn-brisanje").dblclick();
  await page.waitForFunction(() => /anonimizovan/.test(document.getElementById("pn-brisanje-poruka").textContent));
  proveri("Brisanje: jedan DELETE sa tokenom A, poruka i napomena servera, zatim zaključano",
    odZahteva(n).filter(z => z.putanja === "/api/gdpr/account").length === 1 && JSON.stringify(s.anonimizovani) === JSON.stringify([KORISNICI.A.id])
    && /Zakon o advokaturi/.test(await tekst(page, "#pn-brisanje-poruka")) && await page.locator("#pn-brisanje").isDisabled());
  await ctx.close();

  ({ ctx, page } = await otvori(KORISNICI.A, LIVE + "#/podesavanja/privatnost"));
  await page.waitForFunction(() => !document.getElementById("pn-izvoz").disabled);
  await page.locator("#pn-brisanje-potvrda").fill(KORISNICI.A.email);
  await promeniNalog(page, KORISNICI.B);
  await page.waitForFunction(() => document.getElementById("pn-brisanje-potvrda").value === "" && !document.getElementById("pn-izvoz").disabled);
  await page.locator("#pn-brisanje-potvrda").fill(KORISNICI.A.email);
  proveri("Brisanje: posle promene naloga potvrda se briše, a adresa A ne otključava nalog B", await page.locator("#pn-brisanje").isDisabled());
  await ctx.close();

  ({ ctx, page } = await otvori(null, LIVE + "#/podesavanja/privatnost"));
  await page.waitForFunction(() => /Prijavite se/.test(document.getElementById("pn-priv-stanje").textContent));
  proveri("Privatnost: neprijavljen → izvoz i brisanje onemogućeni", await page.locator("#pn-izvoz").isDisabled() && await page.locator("#pn-brisanje").isDisabled());
  await page.goto(LIVE + "#/podesavanja/pomoc");
  await page.waitForFunction(() => !document.getElementById("pn-pomoc").hidden);
  proveri("Pomoć: samo postojeće javne stranice", JSON.stringify(await page.locator("#pn-pomoc a").evaluateAll(a => a.map(x => x.getAttribute("href"))))
    === JSON.stringify(["/status", "/ai-disclosure", "/kako-radi", "/bezbednosni-list"]));
  await ctx.close();
  proveri("Privatnost: jedina anonimizacija je ona izričito potvrđena u testu", JSON.stringify(s.anonimizovani) === JSON.stringify([KORISNICI.A.id]));
}

proveri("P1: nema grešaka skripte", greske.length === 0);
proveri("P1: nijedan zahtev van loopback-a", spolja.length === 0);
proveri("P1: nijedan stvaran email nije poslat (mock brojač)", s.poslatiEmailovi === 0);
await browser.close();
await f.zatvori();
if (pada) { console.error("P1: " + pada + " neuspešnih provera"); process.exit(1); }
console.log("P1 Podešavanja: svi scenariji prošli.");
