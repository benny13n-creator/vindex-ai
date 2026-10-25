// B10 V2: izolovani Chromium test prikaza i opt-in email podsetnika.
// Svi zahtevi idu na 127.0.0.1 ili su mockovani. Nema stvarnih emailova.
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const A = "B10-test-token-A", B = "B10-test-token-B";
const adrese = { [A]: "b10-a@example.test", [B]: "b10-b@example.test" };
const profili = {};
const zahtevi = [];
let pokvarenoCitanje = false, testSlanja = 0, pada = 0;
function proveri(naziv, uslov) {
  console.log((uslov ? "PASS" : "FAIL") + "  " + naziv);
  if (!uslov) pada++;
}
const sesija = (id, token) => JSON.stringify({
  access_token: token, expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id }
});
const prof = (t) => Object.assign({
  aktivan: false, dan_7: true, dan_3: true, dan_1: true,
  nedeljni: true, smtp_ok: true, email: adrese[t]
}, profili[t] || {});
const browser = await chromium.launch();
const f = await pokreniFixture(predmetiRuta({
  [A]: { id: "korisnik-A", predmeti: napraviPredmete("korisnik-A", 1) },
  [B]: { id: "korisnik-B", predmeti: napraviPredmete("korisnik-B", 1) }
}));
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await ctx.addInitScript(([k, v]) => { if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); localStorage.setItem(k, v); } }, [KLJUC, sesija("korisnik-A", A)]);
const spolja = [];
await ctx.route("**/*", async route => {
  const req = route.request(), url = new URL(req.url());
  if (url.hostname !== "127.0.0.1") { spolja.push(req.url()); return route.abort(); }
  if (url.pathname !== "/email-notif/profil" && url.pathname !== "/email-notif/test") return route.continue();
  const t = (req.headers().authorization || "").replace(/^Bearer /, "");
  zahtevi.push({ path: url.pathname, method: req.method(), token: t, body: req.postData() });
  const odgovori = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (!adrese[t]) return odgovori(401, { detail: "Unauthorized" });
  if (req.method() === "GET" && url.pathname === "/email-notif/profil") {
    return pokvarenoCitanje ? odgovori(503, { detail: "temporary" }) : odgovori(200, prof(t));
  }
  if (req.method() === "POST" && url.pathname === "/email-notif/profil") {
    const body = JSON.parse(req.postData() || "{}");
    profili[t] = Object.assign({}, body);
    return odgovori(200, { ok: true, aktivan: body.aktivan });
  }
  if (req.method() === "DELETE" && url.pathname === "/email-notif/profil") {
    delete profili[t];
    return odgovori(200, { ok: true });
  }
  if (req.method() === "POST" && url.pathname === "/email-notif/test") {
    testSlanja++;
    return odgovori(200, { ok: true, poslato_na: adrese[t] });
  }
  return odgovori(405, { detail: "not allowed" });
});
const page = await ctx.newPage(), greske = [];
page.on("pageerror", e => greske.push(String(e)));
await page.goto("http://127.0.0.1:" + f.port + "/?rezim=live#/podesavanja");
await page.waitForFunction(() => document.getElementById("pn-adresa").textContent.includes("b10-a@example.test"));
proveri("V2 Podešavanja su vidljiva u istoj navigaciji", !await page.locator("#podesavanja-nav").evaluate(el => el.hidden)
  && await page.locator("#podesavanja-pogled").isVisible()
  && await page.locator("#podesavanja-nav a").getAttribute("aria-current") === "page");
proveri("Samo email adresa vlasnika A se prikazuje", (await page.locator("#pn-adresa").innerText()) === adrese[A]);
proveri("Test email ne ide automatski pri otvaranju", testSlanja === 0
  && zahtevi.filter(z => z.method === "POST").length === 0);
proveri("Neaktivan profil ne pokazuje dugme za test", await page.locator("#pn-test").isHidden());
await page.locator("#pn-dan-7").uncheck();
await page.locator("#pn-dan-3").uncheck();
await page.locator("#pn-nedeljni").uncheck();
await page.locator("#pn-sacuvaj").click();
await page.waitForFunction(() => document.getElementById("pn-aktivno").textContent.includes("uključeni"));
const s = zahtevi.find(x => x.method === "POST" && x.path === "/email-notif/profil");
proveri("Aktivacija nosi prijavljeni token i SAMO podešavanja", s && s.token === A && JSON.stringify(JSON.parse(s.body))
  === JSON.stringify({ aktivan: true, dan_7: false, dan_3: false, dan_1: true, nedeljni: false }));
proveri("Po uspešnoj aktivaciji se vidi proba", await page.locator("#pn-test").isVisible());
proveri("Aktivacija nije automatsko slanje emaila", testSlanja === 0);
await page.locator("#pn-test").click();
await page.waitForFunction(() => document.getElementById("pn-poruka").textContent.includes("inboxu"));
proveri("Test ide samo eksplicitnim klikom jednom nalogu A", testSlanja === 1
  && zahtevi.filter(x => x.path === "/email-notif/test").every(x => x.token === A));
proveri("UI ne tvrdi da je inbox isporučen", /Proverite prijem/.test(await page.locator("#pn-poruka").innerText()));
await page.locator("#pn-deaktiviraj").click();
await page.waitForFunction(() => document.getElementById("pn-aktivno").textContent.includes("isključeni"));
proveri("Isključivanje je ciljani DELETE iste korisničke putanje", zahtevi.some(x => x.path === "/email-notif/profil" && x.method === "DELETE" && x.token === A)
  && await page.locator("#pn-test").isHidden());
const neDozvoli = await page.evaluate(() => window.VxApi.send("/api/predmeti", { token: "test", metod: "DELETE" }));
proveri("DELETE za ostale API rute je i dalje lokalno zabranjen", neDozvoli.ok === false && neDozvoli.greska.kod === "CONFIG_ERROR");

// Promena naloga dok je pogled otvoren: isti dokument (goto na isti URL sa hešom NE učitava stranicu ponovo).
const pre = zahtevi.length;
const odmah = await page.evaluate(([k, v]) => { localStorage.setItem(k, v); window.dispatchEvent(new Event("focus"));
  return document.getElementById("podesavanja-pogled").innerText; }, [KLJUC, sesija("korisnik-B", B)]);
await page.waitForFunction(() => document.getElementById("pn-adresa").textContent.includes("b10-b@example.test"));
proveri("Promena naloga A→B u otvorenom pogledu: adresa A odmah nestaje, pogled se puni za B", !odmah.includes(adrese[A])
  && (await page.locator("#pn-adresa").innerText()) === adrese[B]
  && zahtevi.slice(pre).length > 0 && zahtevi.slice(pre).every(x => x.token === B));
await page.reload();
await page.waitForFunction(() => document.getElementById("pn-adresa").textContent.includes("b10-b@example.test"));
proveri("Posle ponovnog učitavanja nalog B ne vidi adresu A", (await page.locator("#pn-adresa").innerText()) === adrese[B]
  && !(await page.locator("#podesavanja-pogled").innerText()).includes(adrese[A]));

pokvarenoCitanje = true;
await page.goto("http://127.0.0.1:" + f.port + "/?rezim=live#/predmeti/nov");
await page.goto("http://127.0.0.1:" + f.port + "/?rezim=live#/podesavanja");
await page.waitForFunction(() => document.getElementById("pn-stanje").textContent.includes("nisu učitana"));
proveri("GET 503: nema lažnog praznog stanja i nema aktivacije", await page.locator("#pn-sacuvaj").isDisabled()
  && await page.locator("#pn-test").isHidden());
proveri("Nema korisničkog tokena u UI i nema grešaka skripte", greske.length === 0
  && !(await page.locator("body").innerText()).includes(A));
proveri("Nijedan zahtev nije otišao van loopback fixture-a", spolja.length === 0);
await ctx.close();
await browser.close();
await f.zatvori();
if (pada) { console.error("B10 V2: " + pada + " neuspešnih provera"); process.exit(1); }
console.log("B10 V2: svi izolovani scenariji prošli.");
