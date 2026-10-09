// Vindex V2 NG — NS005 Task 11: Danas (obaveze), odluka o predloženom roku, kalendar 30 dana.
// Pokretanje: `node tests/live-danas.mjs` (fixture na 127.0.0.1; ništa spolja).
// Backend (samo sopstveni rokovi, tuđ rok 404 bez upisa, odluka ne menja/ne briše hronologiju,
// poslednja odluka važi, neuspeo upis 503, pad izvora kalendara se kaže) dokazuje STVARNA ruta:
// tests/test_ns005_t11_rokovi_danas.py.

import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { rokoviRuta } from "./fixtures/pisanje-api.mjs";

const KLJUC = "sb-czsxymueizfqrbbgqqob-auth-token";
const TA = "vx-da-A-NE-U-LOG-64", TB = "vx-da-B-NE-U-LOG-19";
let pada = 0, ukupno = 0;
const izlaz = [];
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  const l = `${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`;
  izlaz.push(l); console.log(l);
}
const ses = (id, t, za = 3600) => JSON.stringify({ access_token: t, refresh_token: "r", expires_at: Math.floor(Date.now() / 1000) + za, user: { id } });
const cekaj = (p, fn, arg, ms = 8000) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
const D = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const SPOLJNO = /email|sms|viber|whatsapp|push|notif|posalji|ics/i;

const browser = await chromium.launch();
const konzola = [], sviSpoljni = [], sviZahtevi = [];
async function scenario(kuke = {}, { token = TA, korisnik = "kA", w = 1440, h = 900, pripremi } = {}) {
  const A = napraviPredmete("kA", 2), B = napraviPredmete("kB", 1);
  const KOR = {
    [TA]: { id: "kA", predmeti: A, rokovi: [
      { id: "r-pot", predmet_id: A[0].id, dogadjaj: "⚠️ Rok za odgovor na tužbu", datum_iso: D(2), vrsta: "rok", izvor: "covek", odluka: "CONFIRMED" },
      { id: "r-kand", predmet_id: A[0].id, dogadjaj: "Rok za žalbu", datum_iso: D(3), vrsta: "rok", izvor: "ai" },
      { id: "r-old", predmet_id: A[1].id, dogadjaj: "Propušten rok za dopunu", datum_iso: D(-4), vrsta: "rok", izvor: "covek", odluka: "CONFIRMED" },
      { id: "r-odb", predmet_id: A[0].id, dogadjaj: "ODBIJEN rok", datum_iso: D(1), vrsta: "rok", odluka: "REJECTED" },
      { id: "r-izv", predmet_id: A[0].id, dogadjaj: "IZVRŠEN rok", datum_iso: D(1), vrsta: "rok", stanje: "izvrsen", odluka: "CONFIRMED" },
      { id: "r-cin", predmet_id: A[0].id, dogadjaj: "Kraj zaposlenja tužioca kod tuženog", datum_iso: D(1) },
      { id: "r-dal", predmet_id: A[1].id, dogadjaj: "Rok za izvođenje dokaza", datum_iso: D(20), vrsta: "rok", odluka: "CONFIRMED" },
      { id: "r-xss", predmet_id: A[1].id, dogadjaj: "Rok <img src=x onerror=window.__xss=1>", datum_iso: D(5), vrsta: "rok", izvor: "ai" },
    ], dogadjaji: [{ tip: "rociste", datum: D(1), vreme: "09:30", naslov: "🏛 Ročište", predmet_id: A[0].id, predmet_naziv: A[0].naziv, detalji: { id: "ro-1", sud: "Osnovni sud u Beogradu", sudnica: "sudnica 12", status: "zakazano" } },
                   { tip: "rok_dokument", datum: D(2), predmet_id: A[0].id, predmet_naziv: A[0].naziv, detalji: {} }] },
    [TB]: { id: "kB", predmeti: B, rokovi: [{ id: "r-B", predmet_id: B[0].id, dogadjaj: "TAJNI rok B", datum_iso: D(2), vrsta: "rok", odluka: "CONFIRMED" }],
            dogadjaji: [{ tip: "rociste", datum: D(1), vreme: "10:00", predmet_id: B[0].id, predmet_naziv: "TAJNI predmet B", detalji: { id: "ro-B", sud: "TAJNI sud" } }] },
  };
  if (pripremi) pripremi(KOR, A);
  const f = await pokreniFixture(kombinuj(rokoviRuta(KOR, kuke), predmetiRuta(KOR), predmetDetaljRuta(KOR, {})));
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const spoljni = [];
  await ctx.route("**/*", r => { const u = new URL(r.request().url()); if (u.hostname === "127.0.0.1") return r.continue(); spoljni.push(u.href); return r.abort(); });
  await ctx.addInitScript(() => { window.__daFetch = 0; const o = window.fetch.bind(window); window.fetch = (u, opt) => { if (/\/api\/rokovi\/[^/]+\/(potvrdi|odbij)$/.test(String(u))) window.__daFetch++; return o(u, opt); }; });
  await ctx.addInitScript(([k, v]) => {
    if (!sessionStorage.getItem("vx-init")) { sessionStorage.setItem("vx-init", "1"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }
  }, [KLJUC, token ? ses(korisnik, token) : null]);
  const p = await ctx.newPage();
  p.on("console", m => konzola.push(m.text()));
  p.on("pageerror", e => konzola.push("PAGEERROR " + e));
  await p.goto(`http://127.0.0.1:${f.port}/?rezim=live#/danas`);
  const drugi = await ctx.newPage();
  await drugi.goto(`http://127.0.0.1:${f.port}/src/tokens.css`);
  return { f, KOR, A, ctx, p, drugi, spoljni, async zatvori() { sviZahtevi.push(...f.zahtevi); sviSpoljni.push(...spoljni); await ctx.close(); await f.zatvori(); } };
}
const postavi = (s, v) => s.drugi.evaluate(([k, v]) => { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }, [KLJUC, v]);
const ucitano = (p) => cekaj(p, () => { const n = document.getElementById("da-stanje"); return !document.getElementById("danas-pogled").hidden && n.dataset.stanje !== "ucitavanje" && (n.hidden || n.dataset.stanje) && (!document.getElementById("da-predlozi-stanje").hidden || document.querySelector("#da-predlozi .review") || n.dataset.stanje === "greska"); });
const ekran = (p) => p.evaluate(() => {
  const vid = (id) => { const e = document.getElementById(id); return !!e && !e.closest("[hidden]") && e.getClientRects().length > 0; };
  const st = (id) => vid(id) ? document.getElementById(id).dataset.stanje + ":" + document.getElementById(id).textContent : null;
  const red = (li) => [...li.children].map(c => c.textContent).join("|");
  return {
    grupe: [...document.querySelectorAll("#da-obaveze .today__group")].map(g => g.querySelector("h3").textContent + "=" + [...g.querySelectorAll(".today__item")].map(red).join(" / ")),
    predlozi: [...document.querySelectorAll("#da-predlozi .review")].map(li => li.dataset.rok + "|" + li.querySelector(".review__name").textContent + "|" + li.querySelector(".review__meta").textContent),
    kalendar: [...document.querySelectorAll("#da-kalendar .today__item .today__what")].map(x => x.textContent),
    dani: [...document.querySelectorAll("#da-kalendar .today__day")].map(x => x.textContent),
    stanje: st("da-stanje"), poruka: st("da-poruka"), obStanje: st("da-obaveze-stanje"), prStanje: st("da-predlozi-stanje"), kalStanje: st("da-kalendar-stanje"), napomena: st("da-napomena"),
    nav: (document.querySelector('.sidenav__item[href="#/danas"]') || {}).getAttribute ? document.querySelector('.sidenav__item[href="#/danas"]').getAttribute("aria-current") : "nema",
    xss: window.__xss || null, ceo: document.body.innerText, pogled: document.getElementById("danas-pogled").innerText,
  };
});
const zahtevi = (s, re, metod = "POST") => s.f.zahtevi.filter(z => z.metod === metod && re.test(z.putanja));

// ── A: razvrstavanje ─────────────────────────────────────────────────────
{
  const s = await scenario();
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("A.nav", "„Danas“ je stvaran link u LIVE i aktivna stavka na #/danas", e.nav === "page");
  zapisi("A.obaveze", "grupe po prioritetu: Propušteno, Sutra, Narednih 7 dana", e.grupe.length === 3 && e.grupe[0].startsWith("Propušteno (1)=") && e.grupe[1].startsWith("Sutra (1)=") && e.grupe[2].startsWith("Narednih 7 dana (1)="), e.grupe.map(g => g.split("=")[0]).join(","));
  zapisi("A.obaveze", "predmet bez ročišta dobija naziv iz registra (ne gola reč „Predmet“)", /Propušten rok za dopunu\|Predmet kA broj 1/.test(e.grupe[0]), e.grupe[0]);
  zapisi("A.obaveze", "propušten potvrđen rok je prvi; ročište nosi sud, sudnicu i vreme", /Propušten rok za dopunu/.test(e.grupe[0]) && /u 09:30.*Ročište\|Osnovni sud u Beogradu, sudnica 12\|Predmet kA broj 0/.test(e.grupe[1]), e.grupe[1]);
  zapisi("A.obaveze", "potvrđen rok bez ukrasnog emoji-ja; predlog NIJE obaveza", /\|Rok\|Rok za odgovor na tužbu\|/.test(e.grupe[2]) && !/⚠/.test(e.grupe.join()) && !/Rok za žalbu/.test(e.grupe.join()), e.grupe[2]);
  zapisi("A.razreseno", "odbijen i izvršen rok se ne prikazuju nigde", !/ODBIJEN rok|IZVRŠEN rok/.test(e.ceo));
  zapisi("A.vrsta", "red bez izjavljene vrste nije ni obaveza ni predlog; napomena ga prebrojava", !/Kraj zaposlenja/.test(e.ceo) && /^prazno:1 zapis hronologije nema oznaku/.test(e.napomena || ""), e.napomena);
  zapisi("A.vrsta", "događaj kalendara koji nije ročište ne postaje obaveza", e.grupe.join().split("Ročište").length === 2);
  zapisi("A.predlozi", "predlozi: samo nepotvrđeni rokovi, po datumu, sa „predložio sistem“", JSON.stringify(e.predlozi.map(x => x.split("|")[0])) === '["r-kand","r-xss"]' && /predložio sistem/.test(e.predlozi[0]), e.predlozi.join(" / "));
  zapisi("A.xss", "HTML u opisu roka je tekst, ništa se ne izvršava", /<img src=x/.test(e.ceo) && e.xss === null);
  zapisi("A.kalendar", "kalendar 30 dana: samo potvrđeni rokovi i ročišta, bez propuštenih i bez predloga", JSON.stringify(e.kalendar) === JSON.stringify(["Osnovni sud u Beogradu, sudnica 12", "Rok za odgovor na tužbu", "Rok za izvođenje dokaza"]), e.kalendar.join(" / "));
  zapisi("A.kalendar", "dani su naslovljeni danom u nedelji; predlozi se prebrojavaju, ne prikazuju", e.dani.length === 3 && /^(ponedeljak|utorak|sreda|četvrtak|petak|subota|nedelja), /.test(e.dani[0]) && /Predloženi rokovi koji čekaju odluku \(2\) nisu u kalendaru/.test(e.ceo), e.dani.join(" / "));
  zapisi("A.izolacija", "ništa od korisnika B", !/TAJN/.test(e.ceo));
  zapisi("A.istina", "potpun pregled: bez upozorenja o nepotpunosti", e.stanje === null, String(e.stanje));
  zapisi("A.tvrdnje", "ekran ne tvrdi ništa o podsetnicima mejlom/SMS/Viberom", !/podsetni|mejl|e-mail|SMS|Viber|WhatsApp/i.test(e.pogled));
  const q = s.f.zahtevi.find(z => z.putanja === "/api/rokovi/kandidati");
  zapisi("A.upit", "kandidati: od = pre 90 dana, dana = 30; kalendar isti početak", q && q.parametri.od === D(-90) && q.parametri.dana === "30" && s.f.zahtevi.some(z => z.putanja === "/api/kalendar/pregled" && z.parametri.od === D(-90) && z.parametri.do === D(30)), JSON.stringify(q && q.parametri));
  await s.zatvori();
}
// ── B: odluka ────────────────────────────────────────────────────────────
{
  const tela = [];
  const s = await scenario({ upisano: (p, b) => tela.push([p, b]) });
  await ucitano(s.p);
  await s.p.click('#da-predlozi .review[data-rok="r-kand"] button:first-of-type');
  await cekaj(s.p, () => !document.getElementById("da-poruka").hidden && !document.querySelector('#da-predlozi .review[data-rok="r-kand"]'));
  let e = await ekran(s.p);
  const t = tela.find(x => x[0] === "/api/rokovi/r-kand/potvrdi");
  zapisi("B.potvrda", "POST samo za TAJ rok; telo bez user_id", !!t && !("user_id" in t[1]) && zahtevi(s, /^\/api\/rokovi\/[^/]+\/(potvrdi|odbij)$/).length === 1, JSON.stringify(t));
  zapisi("B.potvrda", "poruka: potvrđen, ali sistem NIJE proverio tačnost", /^uspeh:Rok „Rok za žalbu“ je potvrđen/.test(e.poruka || "") && /ne znači da je sistem proverio/.test(e.poruka), e.poruka);
  zapisi("B.potvrda", "posle ponovnog čitanja rok je obaveza i u kalendaru, više nije predlog", /Rok za žalbu/.test(e.grupe.join()) && e.kalendar.includes("Rok za žalbu") && !e.predlozi.some(x => x.startsWith("r-kand")));
  await s.p.click('#da-predlozi .review[data-rok="r-xss"] button:nth-of-type(2)');
  await cekaj(s.p, () => !document.querySelector('#da-predlozi .review[data-rok="r-xss"]'));
  e = await ekran(s.p);
  zapisi("B.odbijanje", "odbijanje: poruka kaže da se NE briše; rok nestaje iz predloga", /je odbijen\. Ne briše se — ostaje u hronologiji/.test(e.poruka || "") && /^prazno:Nema predloženih rokova/.test(e.prStanje || ""), e.poruka);
  zapisi("B.grupno", "nema „potvrdi sve“", !/Potvrdi sve/i.test(e.ceo));
  await s.zatvori();
}
for (const [naziv, kuka, re, ponovo] of [
  ["404", { status: 404 }, /nije dostupan\. Ništa nije zabeleženo/, false], ["429", { status: 429 }, /Previše zahteva/, false],
  ["503", { status: 503 }, /nije poznat/, true], ["prekid", { prekid: true }, /nije poznat/, true],
]) {
  const s = await scenario({ pre: (p) => p === "/api/rokovi/odluka:POST" ? kuka : null });
  await ucitano(s.p);
  const pre = zahtevi(s, /^\/api\/rokovi\/kandidati$/, "GET").length;
  await s.p.click('#da-predlozi .review[data-rok="r-kand"] button:first-of-type');
  if (ponovo) await cekaj(s.p, () => !document.getElementById("da-poruka").hidden);
  else await cekaj(s.p, () => { const li = document.querySelector('#da-predlozi .review[data-rok="r-kand"]'); return li && !li.querySelector("button").disabled; });
  await s.p.waitForTimeout(300);
  const e = await ekran(s.p);
  const redTekst = await s.p.evaluate(() => { const li = document.querySelector('#da-predlozi .review[data-rok="r-kand"]'); return li ? li.textContent : ""; });
  const tekst = ponovo ? (e.poruka || "") : redTekst;
  zapisi("C.ishod", `${naziv}: ${ponovo ? "„ishod nepoznat“ + ponovno čitanje" : "greška u redu, dugmad ponovo dostupna"}`, re.test(tekst) && (!ponovo || (e.poruka.startsWith("nepoznato:") && zahtevi(s, /^\/api\/rokovi\/kandidati$/, "GET").length > pre)) && !/je potvrđen/.test(e.ceo), tekst.slice(0, 160));
  zapisi("C.ishod", `${naziv}: aplikacija šalje jednom`, await s.p.evaluate(() => window.__daFetch) === 1);
  if (ponovo) zapisi("C.ishod", `${naziv}: nikad „nije zabeleženo“ kad ishod nije poznat`, !/nije zabeleženo/.test(e.poruka));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/rokovi/odluka:POST" ? new Promise(r => setTimeout(r, 900)) : null });
  await ucitano(s.p);
  await s.p.evaluate(() => { const b = document.querySelector('#da-predlozi .review[data-rok="r-kand"] button'); b.click(); b.click(); b.click(); });
  await cekaj(s.p, () => !document.getElementById("da-poruka").hidden);
  await s.p.waitForTimeout(200);
  zapisi("C.dupli", "višestruki klik → tačno jedna odluka", await s.p.evaluate(() => window.__daFetch) === 1 && zahtevi(s, /\/potvrdi$/).length === 1);
  await s.zatvori();
}
// ── D: istina o čitanju ─────────────────────────────────────────────────
{
  const s = await scenario({ pre: (p) => p === "/api/rokovi/kandidati:GET" ? { status: 503 } : null });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("D.istina", "kandidati 503: pregled izričito NIJE potpun; ročišta se i dalje vide", /^nepotpuno:Pregled NIJE potpun: rokovi nisu učitani/.test(e.stanje || "") && /Osnovni sud u Beogradu/.test(e.grupe.join()), e.stanje);
  zapisi("D.istina", "kandidati 503: predlozi „nije prazan spisak“ (nikad „nema predloga“)", /^greska:.*nije prazan spisak/.test(e.prStanje || "") && !/Nema predloženih/.test(e.ceo), e.prStanje);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/kalendar/pregled:GET" ? { status: 500 } : null });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("D.istina", "kalendar 500: „ročišta nisu učitana“; potvrđeni rokovi i predlozi se i dalje vide", /ročišta nisu učitana/.test(e.stanje || "") && /Rok za odgovor/.test(e.grupe.join()) && e.predlozi.length === 2 && !/Osnovni sud/.test(e.ceo), e.stanje);
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => /^\/api\/(rokovi\/kandidati|kalendar\/pregled):GET$/.test(p) ? { status: 503 } : null });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("D.istina", "oba izvora pala: „nije prazan dan“, bez lista i bez „nema obaveza“", /^greska:.*Ovo nije prazan dan/.test(e.stanje || "") && !e.grupe.length && !e.predlozi.length && !/Nema potvrđenih|Nema predloženih/.test(e.ceo), e.stanje);
  await s.zatvori();
}
{
  const s = await scenario({ kalendar: (t) => ({ ...t, dogadjaji: [], degraded_sources: ["rocista"] }), odseceno: true });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("D.istina", "degraded_sources[rocista] i odsečeni rokovi se kažu", /ročišta nisu učitana/.test(e.stanje || "") && /rokova ima više nego što je prikazano/.test(e.stanje), e.stanje);
  await s.zatvori();
}
{
  const s = await scenario({}, { pripremi: (KOR) => { KOR[TA].rokovi = []; KOR[TA].dogadjaji = []; } });
  await ucitano(s.p);
  const e = await ekran(s.p);
  zapisi("D.prazno", "stvarno prazno: mirne poruke, bez upozorenja", /^prazno:Nema potvrđenih rokova ni ročišta za narednih 7 dana/.test(e.obStanje || "") && /^prazno:Nema predloženih/.test(e.prStanje || "") && /^prazno:Nema potvrđenih rokova ni ročišta u narednih 30/.test(e.kalStanje || "") && e.stanje === null);
  await s.zatvori();
}
// ── E: sesija i zastarelo ────────────────────────────────────────────────
{
  const s = await scenario({ pre: (p, k) => p === "/api/rokovi/kandidati:GET" && k === "kA" ? new Promise(r => setTimeout(r, 1200)) : null });
  await s.p.waitForTimeout(250);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(2200);
  const e = await ekran(s.p);
  zapisi("E.sesija", "A→B usred učitavanja: zakasneli odgovor A se ne prikazuje; prikazan je B", !/Rok za odgovor|Rok za žalbu|Propušten/.test(e.ceo) && /TAJNI rok B/.test(e.ceo), e.grupe.join(" / ").slice(0, 160));
  await s.zatvori();
}
{
  const s = await scenario();
  await ucitano(s.p);
  await postavi(s, null);
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(600);
  const e = await ekran(s.p);
  zapisi("E.sesija", "odjava: obaveze, predlozi i kalendar A nestaju odmah", !e.grupe.length && !e.predlozi.length && !e.kalendar.length && !/Rok za odgovor|Rok za žalbu/.test(e.ceo));
  await s.zatvori();
}
{
  const s = await scenario({ pre: (p) => p === "/api/rokovi/odluka:POST" ? new Promise(r => setTimeout(r, 1200)) : null });
  await ucitano(s.p);
  await s.p.click('#da-predlozi .review[data-rok="r-kand"] button:first-of-type');
  await s.p.waitForTimeout(150);
  await postavi(s, ses("kB", TB));
  await s.p.evaluate(() => window.dispatchEvent(new Event("focus")));
  await s.p.waitForTimeout(1800);
  const e = await ekran(s.p);
  zapisi("E.sesija", "odluka A u letu, prelazak na B: poruka o roku A se ne prikazuje korisniku B", !/Rok za žalbu/.test(e.ceo) && e.poruka === null, String(e.poruka));
  await s.zatvori();
}
// ── F: raspored ──────────────────────────────────────────────────────────
for (const [w, h] of [[390, 844], [1024, 768]]) {
  const s = await scenario({}, { w, h });
  await ucitano(s.p);
  const m = await s.p.evaluate(() => ({ sw: document.documentElement.scrollWidth, vw: innerWidth }));
  zapisi("F.raspored", `${w}px: bez horizontalnog skrola stranice`, m.sw <= m.vw, `${m.sw}/${m.vw}`);
  if (process.env.NS005_SNIMCI) await s.p.screenshot({ path: `${process.env.NS005_SNIMCI}/ns005-danas-${w}.png` });
  await s.zatvori();
}

await browser.close();
zapisi("izolacija", "nijedan zahtev van 127.0.0.1", sviSpoljni.length === 0, sviSpoljni.slice(0, 2).join());
zapisi("izolacija", "nijedan zahtev ne nosi user_id", sviZahtevi.every(z => !/user_id/i.test(z.upit)));
zapisi("izolacija", "nijedan zahtev ka mejlu/SMS/Viber/WhatsApp/push/ICS", sviZahtevi.every(z => !SPOLJNO.test(z.putanja)));
zapisi("token", "token nikad u adresi", sviZahtevi.every(z => ![TA, TB].some(t => z.upit.includes(t))));
zapisi("token", "token nije u konzoli", ![TA, TB].some(t => konzola.join("\n").includes(t)));
zapisi("token", "token nije u izlazu testa", ![TA, TB].some(t => izlaz.join("\n").includes(t)));
zapisi("konzola", "bez grešaka stranice", !konzola.some(l => l.startsWith("PAGEERROR")), konzola.filter(l => l.startsWith("PAGEERROR")).join(" | ").slice(0, 200));
console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
