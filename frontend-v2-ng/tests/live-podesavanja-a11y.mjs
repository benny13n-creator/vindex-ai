// P2.3 Pristupačnost V2 Podešavanja (svaki odeljak × tamna/svetla): kontrast vidljivog teksta prema stvarnoj
// pozadini (WCAG 1.4.3: 4.5:1, veliki tekst 3:1; neaktivne kontrole izuzete), oznake polja i imena kontrola,
// vidljiv fokus za tastaturu, redosled Tab-a kroz kontrole odeljka, uvećanje 200% bez vodoravnog pomeranja.
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { kombinuj, napraviPredmete, predmetiRuta } from "./fixtures/predmeti-api.mjs";
import { podesavanjaRuta, podesavanjaMock, KORISNICI, sesija, KLJUC } from "./fixtures/podesavanja-api.mjs";

let pada = 0;
function proveri(naziv, uslov, detalj = "") { console.log((uslov ? "PASS" : "FAIL") + "  " + naziv + (uslov || !detalj ? "" : "  → " + detalj)); if (!uslov) pada++; }
const SEKCIJE = (process.env.PN_SEKCIJE || "nalog,izgled,obavestenja,kancelarija,finansije,privatnost,pomoc").split(",");
const s = podesavanjaMock();
s.profilEmail[KORISNICI.B.token] = { aktivan: true, dan_7: true, dan_3: false, dan_1: true, nedeljni: true };
const f = await pokreniFixture(kombinuj(predmetiRuta(Object.fromEntries(Object.values(KORISNICI).map(k => [k.token, { id: k.id, predmeti: napraviPredmete(k.id, 1) }]))), podesavanjaRuta(s)));
const browser = await chromium.launch();

const MERA = () => {
  const lum = (c) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const rgb = (s) => { const m = s.match(/[\d.]+/g); return m ? m.map(Number) : null; };
  const L = ([r, g, b]) => 0.2126 * lum(r) + 0.7152 * lum(g) + 0.0722 * lum(b);
  const pozadina = (e) => {
    const slojevi = [];
    for (let n = e; n; n = n.parentElement) {
      const c = rgb(getComputedStyle(n).backgroundColor);
      if (c && (c.length < 4 || c[3] > 0)) { slojevi.push(c); if (c.length < 4 || c[3] >= 1) break; }
    }
    let osnova = [255, 255, 255];
    for (const c of slojevi.reverse()) { const a = c.length > 3 ? c[3] : 1; osnova = osnova.map((v, i) => c[i] * a + v * (1 - a)); }
    return osnova;
  };
  const koren = document.querySelector("#podesavanja-pogled");
  const losi = [];
  const hodaj = document.createTreeWalker(koren, NodeFilter.SHOW_TEXT);
  while (hodaj.nextNode()) {
    const t = hodaj.currentNode, e = t.parentElement;
    if (!t.nodeValue.trim() || !e || e.closest("[hidden]") || !e.getClientRects().length) continue;
    if (e.closest("button:disabled, input:disabled, select:disabled, option")) continue;
    const cs = getComputedStyle(e);
    if (cs.visibility === "hidden" || cs.display === "none") continue;
    const boja = rgb(cs.color), a = boja.length > 3 ? boja[3] : 1, bg = pozadina(e);
    const fg = boja.slice(0, 3).map((v, i) => v * a + bg[i] * (1 - a));
    const l1 = L(fg), l2 = L(bg), odnos = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const px = parseFloat(cs.fontSize), veliki = px >= 24 || (px >= 18.66 && Number(cs.fontWeight) >= 700);
    if (odnos < (veliki ? 3 : 4.5)) losi.push(t.nodeValue.trim().slice(0, 30) + " (" + odnos.toFixed(2) + ")");
  }
  // Oznake i imena
  const bezImena = [];
  koren.querySelectorAll("input, select, textarea, button, a[href]").forEach(n => {
    if (n.closest("[hidden]") || !n.getClientRects().length) return;
    const ime = (n.labels && n.labels.length ? [...n.labels].map(l => l.textContent).join(" ") : "") || n.getAttribute("aria-label") || (n.tagName === "BUTTON" || n.tagName === "A" ? n.textContent : "");
    if (!ime.trim()) bezImena.push(n.id || n.outerHTML.slice(0, 50));
  });
  return { losi, bezImena };
};

for (const tema of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript(([k, v, t]) => { localStorage.setItem(k, v); localStorage.setItem("vx-ng-tema", t); }, [KLJUC, sesija(KORISNICI.B), tema]);
  await ctx.route("**/*", r => new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort());
  const page = await ctx.newPage();
  for (const sek of SEKCIJE) {
    await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/" + sek);
    await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, sek);
    await page.waitForTimeout(400);
    const m = await page.evaluate(MERA);
    proveri(`${tema} ${sek}: kontrast vidljivog teksta ≥ WCAG AA`, m.losi.length === 0, m.losi.join(" | "));
    proveri(`${tema} ${sek}: svako polje ima oznaku, svaka kontrola ime`, m.bezImena.length === 0, m.bezImena.join(" | "));
    // Tastatura: Tab od kartice odeljka kroz kontrole; svaki fokusirani element ima vidljiv obris.
    await page.locator('#pn-sekcije [data-sekcija="' + sek + '"]').focus();
    const bezObrisa = [], posecene = new Set();
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      const st = await page.evaluate(() => {
        const a = document.activeElement;
        if (!a || !a.closest("#podesavanja-pogled")) return null;
        const c = getComputedStyle(a);
        return { id: a.id || a.textContent.trim().slice(0, 24) || a.tagName, obris: c.outlineStyle !== "none" && parseFloat(c.outlineWidth) > 0 || c.boxShadow !== "none" };
      });
      if (!st) break;
      posecene.add(st.id);
      if (!st.obris) bezObrisa.push(st.id);
    }
    proveri(`${tema} ${sek}: fokus tastature je vidljiv na svakoj kontroli (${posecene.size} kontrola)`, bezObrisa.length === 0, bezObrisa.join(" | "));
  }
  await ctx.close();
}

// Uvećanje 200%: viewport 700×450 na 1400×900 ekranu (isti CSS raspored kao zum pregledača).
const ctx = await browser.newContext({ viewport: { width: 700, height: 450 }, deviceScaleFactor: 2 });
await ctx.addInitScript(([k, v]) => localStorage.setItem(k, v), [KLJUC, sesija(KORISNICI.B)]);
await ctx.route("**/*", r => new URL(r.request().url()).hostname === "127.0.0.1" ? r.continue() : r.abort());
const page = await ctx.newPage();
for (const sek of SEKCIJE) {
  await page.goto("http://127.0.0.1:" + f.port + "/app#/podesavanja/" + sek);
  await page.waitForFunction(i => !document.getElementById("pn-" + i).hidden, sek);
  await page.waitForTimeout(300);
  const preliv = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  const sitno = await page.evaluate(() => { let min = 99; const h = document.createTreeWalker(document.querySelector("#podesavanja-pogled"), NodeFilter.SHOW_TEXT);
    while (h.nextNode()) { const e = h.currentNode.parentElement; if (h.currentNode.nodeValue.trim() && e && !e.closest("[hidden]") && e.getClientRects().length) min = Math.min(min, parseFloat(getComputedStyle(e).fontSize)); } return min; });
  proveri(`zum 200% ${sek}: bez vodoravnog pomeranja, najmanji tekst ${sitno}px ≥ 12px`, preliv <= 0 && sitno >= 12, "preliv " + preliv + "px");
}
await ctx.close();
await browser.close();
await f.zatvori();
if (pada) { console.error("P2.3: " + pada + " neuspešnih"); process.exit(1); }
console.log("P2.3 pristupačnost Podešavanja: svi scenariji prošli.");
