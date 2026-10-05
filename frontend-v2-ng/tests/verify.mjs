// Vindex V2 NG — ponovljiva provera prototipa 001.
// Pokretanje: `node serve.mjs` u jednom terminalu, pa `node tests/verify.mjs`.
// Rezultat: shots/*.png, shots/results.json, shots/results.md
//
// Ovi testovi dokazuju PONAŠANJE i raspored. Ne dokazuju vizuelni kvalitet —
// to odlučuje founder gledajući snimke.

import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";

const BASE = process.env.VX_URL || "http://127.0.0.1:4317/";
const OUT = new URL("../shots/", import.meta.url);
await mkdir(OUT, { recursive: true });

const rezultati = [];
const greskeKonzole = [];
function zapisi(grupa, naziv, prolazi, detalj = "") {
  rezultati.push({ grupa, naziv, prolazi: !!prolazi, detalj: String(detalj) });
  console.log(`${prolazi ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}

const browser = await chromium.launch();

async function otvori({ w = 1440, h = 900, tema = "dark", nav = "puna", upit = "", motion = "reduce", dpr = 1 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr, reducedMotion: motion });
  await ctx.addInitScript(([t, n]) => {
    if (!sessionStorage.getItem("vx-test-init")) {
      localStorage.setItem("vx-ng-tema", t); localStorage.setItem("vx-ng-nav", n);
      sessionStorage.setItem("vx-test-init", "1");
    }
  }, [tema, nav]);
  const p = await ctx.newPage();
  p.on("console", m => { if (m.type() === "error") greskeKonzole.push(m.text()); });
  p.on("pageerror", e => greskeKonzole.push(String(e)));
  await p.goto(BASE + upit);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(150);
  return p;
}
const snimi = (p, ime, opts = {}) => p.screenshot({ path: new URL(ime + ".png", OUT).pathname.replace(/^\/([A-Za-z]:)/, "$1"), ...opts });

const nemaHorizontalnogSkrola = p => p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const sirina = (p, sel) => p.$eval(sel, e => Math.round(e.getBoundingClientRect().width));
const vidljiv = (p, sel) => p.$eval(sel, e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && !e.hidden && r.right > 0 && r.left < innerWidth; });
const redosled = p => p.$$eval("#rows tr", trs => trs.map(t => t.dataset.id));

// ── 1. Desktop raspored: 1440×900 i 1280×800, obe teme ──────────────────
for (const [w, h] of [[1440, 900], [1280, 800]]) {
  for (const tema of ["dark", "light"]) {
    const p = await otvori({ w, h, tema });
    const g = `desktop ${w}×${h} ${tema}`;
    zapisi(g, "tema primenjena", (await p.getAttribute("html", "data-theme")) === tema);
    zapisi(g, "navigacija, lista i panel vidljivi istovremeno",
      (await vidljiv(p, "#nav")) && (await vidljiv(p, "#glavni")) && (await vidljiv(p, "#panel")));
    const m = await sirina(p, "#glavni"), pn = await sirina(p, "#panel");
    zapisi(g, "lista je dominantna (šira od 2× panela)", m >= 2 * pn, `lista ${m}px, panel ${pn}px`);
    zapisi(g, "bez horizontalnog skrola stranice", await nemaHorizontalnogSkrola(p));
    zapisi(g, "fontovi učitani: serif + sans, latinica sa dijakriticima", await p.evaluate(() =>
      document.fonts.check('500 26px "Source Serif 4"', "Aktivni predmeti ĆčŽšĐ") &&
      document.fonts.check('400 14px "IBM Plex Sans"', "Predmet čćžšđ")));
    // Ćirilica se ne prikazuje na ekranu, pa se njen podskup učitava na zahtev i proverava da postoji.
    zapisi(g, "ćirilični podskup fontova postoji i učitava se", await p.evaluate(async () => {
      const a = await document.fonts.load('500 26px "Source Serif 4"', "Ћирилица ђжћџ");
      const b = await document.fonts.load('400 14px "IBM Plex Sans"', "Ћирилица ђжћџ");
      return a.some(x => x.status === "loaded") && b.some(x => x.status === "loaded") &&
        document.fonts.check('500 26px "Source Serif 4"', "Ћирилица") && document.fonts.check('400 14px "IBM Plex Sans"', "Ћирилица");
    }));
    await snimi(p, `01-${w}x${h}-${tema}`);
    await p.context().close();
  }
}

// ── 2. Kontrast tokena (WCAG AA, 4.5:1 za tekst) ───────────────────────
for (const tema of ["dark", "light"]) {
  const p = await otvori({ tema });
  const parovi = await p.evaluate(() => {
    const s = getComputedStyle(document.documentElement);
    const hex = v => { v = s.getPropertyValue(v).trim(); return [1, 3, 5].map(i => parseInt(v.slice(i, i + 2), 16)); };
    const lum = c => { const [r, g, b] = c.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const odnos = (a, b) => { const [x, y] = [lum(hex(a)), lum(hex(b))].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
    const out = [];
    for (const fg of ["--text-1", "--text-2", "--text-3", "--accent", "--attention", "--demo-text"])
      for (const bg of ["--bg-sheet", "--bg-panel", "--bg-shell", "--bg-hover"])
        if (s.getPropertyValue(fg).trim().startsWith("#")) out.push([fg, bg, Math.round(odnos(fg, bg) * 100) / 100]);
    return out;
  });
  const najslabiji = parovi.reduce((a, b) => (b[2] < a[2] ? b : a));
  zapisi(`kontrast ${tema}`, "svi tekstualni tokeni ≥ 4.5:1 na svim površinama", parovi.every(x => x[2] >= 4.5),
    `najniži: ${najslabiji[0]} na ${najslabiji[1]} = ${najslabiji[2]}:1`);
  await p.context().close();
}

// ── 3. Skupljanje leve navigacije ───────────────────────────────────────
{
  const p = await otvori({ w: 1440, h: 900 });
  const pre = await sirina(p, "#nav"), listaPre = await sirina(p, "#glavni");
  await p.click("#nav-collapse");
  const posle = await sirina(p, "#nav"), listaPosle = await sirina(p, "#glavni");
  zapisi("navigacija", "skupljanje sužava navigaciju", posle <= 64 && pre >= 200, `${pre}px → ${posle}px`);
  zapisi("navigacija", "oslobođen prostor ide listi", listaPosle > listaPre, `${listaPre}px → ${listaPosle}px`);
  zapisi("navigacija", "aria-expanded=false i natpis „Proširi navigaciju“",
    (await p.getAttribute("#nav-collapse", "aria-expanded")) === "false" &&
    (await p.textContent("#nav-collapse .sidenav__label")) === "Proširi navigaciju");
  zapisi("navigacija", "stavke ostaju dostupne (pristupačno ime + title)", await p.$$eval(".sidenav__item", as =>
    as.every(a => a.title && a.textContent.trim().length > 0)));
  zapisi("navigacija", "aktivna sekcija označena (aria-current=page na „Predmeti“)",
    (await p.$eval('[aria-current="page"]', a => a.textContent.trim())) === "Predmeti");
  await snimi(p, "02-1440x900-dark-nav-skupljena");
  await p.reload(); await p.waitForTimeout(100);
  zapisi("navigacija", "stanje skupljanja preživljava ponovno učitavanje", (await sirina(p, "#nav")) <= 64);
  await p.click("#nav-collapse");
  zapisi("navigacija", "ponovno proširenje", (await sirina(p, "#nav")) >= 200);
  await p.click('.sidenav__item[data-modul="Znanje"]');
  zapisi("navigacija", "neizgrađen modul prijavljuje da nije deo prototipa (ne vodi nikuda)",
    (await p.textContent("#status")).includes("nije deo ovog prototipa"));
  await p.context().close();
}

// ── 4. Dugi nazivi predmeta ─────────────────────────────────────────────
for (const [w, h] of [[1440, 900], [1280, 800]]) {
  const p = await otvori({ w, h });
  const r = await p.evaluate(() => {
    const imena = [...document.querySelectorAll(".case__name, .case__meta, .ref__court")];
    const odseceno = imena.filter(e => e.scrollWidth > e.clientWidth + 1).length;
    const reg = document.getElementById("registry");
    const najduzi = imena.filter(e => e.classList.contains("case__name")).reduce((a, b) => (b.textContent.length > a.textContent.length ? b : a));
    const lh = parseFloat(getComputedStyle(najduzi).lineHeight);
    return { odseceno, tabela: reg.scrollWidth <= reg.clientWidth, redova: Math.round(najduzi.getBoundingClientRect().height / lh), duzina: najduzi.textContent.length, title: najduzi.title === najduzi.textContent };
  });
  zapisi(`dugi nazivi ${w}`, "nijedan naziv/klijent/sud nije odsečen", r.odseceno === 0, `odsečenih: ${r.odseceno}`);
  zapisi(`dugi nazivi ${w}`, "tabela ne izlazi iz radne površine", r.tabela);
  // Refinement 01: lista prikazuje najviše 2 reda; ceo naziv ostaje u DOM-u i u title (vidi tests/refinement.mjs).
  zapisi(`dugi nazivi ${w}`, "najduži naziv: 2 reda u listi, ceo tekst u DOM-u i title", r.redova === 2 && r.title, `${r.duzina} znakova u ${r.redova} reda`);
  await p.context().close();
}

// ── 5. Pretraga, prazna lista, prazna pretraga ─────────────────────────
{
  const p = await otvori({ upit: "?predmeti=prazno" });
  zapisi("prazna lista", "poruka „Nema aktivnih predmeta“", (await vidljiv(p, "#empty")) && (await p.textContent("#empty-title")) === "Nema aktivnih predmeta");
  zapisi("prazna lista", "brojač „0 predmeta“", (await p.textContent("#count")) === "0 predmeta");
  zapisi("prazna lista", "pretraga onemogućena kad nema šta da se traži", await p.$eval("#pretraga", e => e.disabled));
  zapisi("prazna lista", "nema dugmeta „Obriši pretragu“ (nema pretrage)", !(await vidljiv(p, "#empty-clear")));
  zapisi("prazna lista", "svaki element sa atributom hidden je zaista skriven", await p.evaluate(() =>
    [...document.querySelectorAll("[hidden]")].every(e => getComputedStyle(e).display === "none")));
  await snimi(p, "03-prazna-lista-dark");
  await p.context().close();
}
{
  const p = await otvori();
  await p.fill("#pretraga", "djordjevic");
  zapisi("pretraga", "„djordjevic“ pronalazi „Đorđević“ (bez dijakritika)", (await p.$$("#rows tr")).length === 1);
  await p.fill("#pretraga", "sapcu");
  zapisi("pretraga", "„sapcu“ pronalazi „Šapcu“", (await p.$$("#rows tr")).length === 1);
  await p.fill("#pretraga", "radni spor");
  const n = (await p.$$("#rows tr")).length;
  zapisi("pretraga", "više reči = sve reči moraju postojati", n === 2, `${n} rezultata, brojač: ${await p.textContent("#count")}`);
  await p.fill("#pretraga", "nepostojeci pojam");
  zapisi("pretraga", "nema rezultata: poruka + dugme „Obriši pretragu“",
    (await vidljiv(p, "#empty")) && (await vidljiv(p, "#empty-clear")));
  await snimi(p, "04-pretraga-bez-rezultata-dark");
  await p.click("#empty-clear");
  zapisi("pretraga", "brisanje vraća celu listu i fokus u pretragu",
    (await p.$$("#rows tr")).length === 12 && (await p.evaluate(() => document.activeElement.id)) === "pretraga");
  await p.context().close();
}

// ── 6. Veliki broj predmeta + determinističko sortiranje ───────────────
{
  const p = await otvori({ upit: "?predmeti=veliko" });
  zapisi("velika lista", "240 redova, brojač „240 predmeta“",
    (await p.$$("#rows tr")).length === 240 && (await p.textContent("#count")) === "240 predmeta");
  zapisi("velika lista", "podrazumevano: Izmenjeno, opadajuće",
    (await p.getAttribute('th[data-kljuc="izmenjeno"]', "aria-sort")) === "descending");
  const podaci = await p.evaluate(() => window.VX_DEMO.predmeti.map(x => ({ id: x.id, naziv: x.naziv, broj: x.broj, izmenjeno: x.izmenjeno })));
  const kol = new Intl.Collator("sr-Latn", { sensitivity: "base", numeric: true });
  const ocekivano = (k, smer) => podaci.slice().sort((a, b) => {
    let r = k === "izmenjeno" ? (a[k] < b[k] ? -1 : a[k] > b[k] ? 1 : 0) : kol.compare(a[k], b[k]);
    if (smer === "desc") r = -r;
    return r || kol.compare(a.broj, b.broj) || (a.id < b.id ? -1 : 1);
  }).map(x => x.id);
  zapisi("velika lista", "redosled = nezavisno izračunat (Izmenjeno ↓)", JSON.stringify(await redosled(p)) === JSON.stringify(ocekivano("izmenjeno", "desc")));
  await p.click('th[data-kljuc="naziv"] .sort');
  const prvi = await redosled(p);
  zapisi("velika lista", "Predmet A→Š po srpskom kolatoru", JSON.stringify(prvi) === JSON.stringify(ocekivano("naziv", "asc")));
  await p.click('th[data-kljuc="naziv"] .sort');
  zapisi("velika lista", "drugi klik obrće smer", JSON.stringify(await redosled(p)) === JSON.stringify(ocekivano("naziv", "desc")));
  await p.reload(); await p.click('th[data-kljuc="naziv"] .sort');
  zapisi("velika lista", "isti klikovi posle ponovnog učitavanja daju identičan redosled", JSON.stringify(await redosled(p)) === JSON.stringify(prvi));
  await p.click('th[data-kljuc="broj"] .sort');
  zapisi("velika lista", "Broj predmeta: numeričko poređenje (P 99 pre P 100)", JSON.stringify(await redosled(p)) === JSON.stringify(ocekivano("broj", "asc")));
  zapisi("velika lista", "zaglavlje tabele ostaje vidljivo pri skrolu", await p.evaluate(async () => {
    document.getElementById("glavni").scrollTop = 3000; await new Promise(r => setTimeout(r, 50));
    const th = document.querySelector(".cases thead th").getBoundingClientRect();
    return th.top >= document.getElementById("glavni").getBoundingClientRect().top - 1 && th.top < 200;
  }));
  await p.evaluate(() => { document.getElementById("glavni").scrollTop = 0; });
  await p.click('th[data-kljuc="izmenjeno"] .sort'); await p.click('th[data-kljuc="izmenjeno"] .sort');
  await snimi(p, "05-velika-lista-1440-dark");
  await p.context().close();
}

// ── 7. Panel „Zahteva pažnju“ ───────────────────────────────────────────
{
  const p = await otvori();
  const n = (await p.$$("#attention li")).length;
  zapisi("panel", "ograničen broj stavki (≤ 5)", n > 0 && n <= 5, `${n} stavki`);
  zapisi("panel", "jasno označeno kao demonstracioni sadržaj", (await p.textContent(".panel__note")).includes("Demonstracioni sadržaj"));
  zapisi("panel", "stavke sortirane po datumu", await p.$$eval("#attention time", t => t.every((x, i, a) => !i || a[i - 1].dateTime <= x.dateTime)));
  await p.context().close();
  const q = await otvori({ upit: "?paznja=prazno" });
  zapisi("panel prazan", "poruka praznog stanja", (await vidljiv(q, "#attention-empty")) && !(await q.$eval("#attention", e => !e.hidden)));
  await snimi(q, "06-panel-prazan-1440-dark");
  await q.context().close();
}

// ── 8. Promena teme ne poništava stanje ────────────────────────────────
{
  const p = await otvori({ w: 1440, h: 900 });
  await p.fill("#pretraga", "spor");
  await p.click('th[data-kljuc="broj"] .sort'); await p.click('th[data-kljuc="broj"] .sort');
  await p.click("#nav-collapse");
  const pre = { upit: await p.inputValue("#pretraga"), red: await redosled(p), sort: await p.getAttribute('th[data-kljuc="broj"]', "aria-sort"), nav: await p.getAttribute("html", "data-nav") };
  await p.click("#theme-toggle");
  const posle = { upit: await p.inputValue("#pretraga"), red: await redosled(p), sort: await p.getAttribute('th[data-kljuc="broj"]', "aria-sort"), nav: await p.getAttribute("html", "data-nav") };
  zapisi("tema", "tema promenjena u svetlu", (await p.getAttribute("html", "data-theme")) === "light");
  zapisi("tema", "pretraga, sortiranje, redosled i skupljena navigacija sačuvani", JSON.stringify(pre) === JSON.stringify(posle), `upit=„${posle.upit}“, sort=${posle.sort}, nav=${posle.nav}, redova=${posle.red.length}`);
  await snimi(p, "07-tema-stanje-sacuvano-light");
  await p.reload();
  zapisi("tema", "izbor teme preživljava ponovno učitavanje", (await p.getAttribute("html", "data-theme")) === "light");
  await p.context().close();
}

// ── 9. Tastatura ────────────────────────────────────────────────────────
{
  const p = await otvori();
  await p.keyboard.press("Tab");
  zapisi("tastatura", "prvi Tab: link „Preskoči na listu predmeta“ je vidljiv",
    (await p.evaluate(() => document.activeElement.className)) === "skip" && (await p.$eval(".skip", e => e.getBoundingClientRect().top >= 0)));
  await p.keyboard.press("Enter");
  zapisi("tastatura", "Enter na preskoku vodi u listu", (await p.evaluate(() => document.activeElement.id)) === "glavni");
  await p.evaluate(() => document.activeElement.blur());
  const posete = [];
  let bezObrisa = [];
  for (let i = 0; i < 40; i++) {
    await p.keyboard.press("Tab");
    const d = await p.evaluate(() => {
      const e = document.activeElement; const s = getComputedStyle(e);
      return { opis: e.id || e.className || e.tagName, tekst: (e.textContent || e.placeholder || "").trim().slice(0, 30), obris: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2 };
    });
    if (d.opis === "BODY") continue;              // Tab je izašao iz stranice (kraj ciklusa) — nije element
    posete.push(d);
    if (!d.obris) bezObrisa.push(d.opis);
  }
  const ima = f => posete.some(f);
  zapisi("tastatura", "Tab dostiže: navigaciju, skupljanje, temu, pretragu, sortiranje, predmete, panel",
    ima(d => d.opis.includes("sidenav__item")) && ima(d => d.opis === "nav-collapse") && ima(d => d.opis === "theme-toggle") &&
    ima(d => d.opis === "pretraga") && ima(d => d.opis === "sort") && ima(d => d.opis === "case__name"));
  zapisi("tastatura", "svaki fokusirani element ima vidljiv obris fokusa (≥ 2px)", bezObrisa.length === 0, bezObrisa.length ? `bez obrisa: ${[...new Set(bezObrisa)].join(", ")}` : `${posete.length} koraka`);
  await p.focus("#theme-toggle"); await p.keyboard.press("Enter");
  zapisi("tastatura", "tema se menja tastaturom (Enter)", (await p.getAttribute("html", "data-theme")) === "light");
  await p.focus('th[data-kljuc="naziv"] .sort'); await p.keyboard.press("Space");
  zapisi("tastatura", "sortiranje tastaturom (Space)", (await p.getAttribute('th[data-kljuc="naziv"]', "aria-sort")) === "ascending");
  await p.focus("body"); await p.evaluate(() => document.activeElement.blur()); await p.keyboard.press("/");
  zapisi("tastatura", "„/“ fokusira pretragu", (await p.evaluate(() => document.activeElement.id)) === "pretraga");
  await p.keyboard.type("ugovor"); await p.keyboard.press("Escape");
  zapisi("tastatura", "Escape briše pretragu", (await p.inputValue("#pretraga")) === "" && (await p.$$("#rows tr")).length === 12);
  await p.context().close();
}

// ── 10. Uvećanje 200% i uži ekrani ─────────────────────────────────────
// 200% zoom na 1440×900 i 1280×800 = CSS viewport 720×450 i 640×400 pri DPR 2.
for (const [w, h, ime] of [[720, 450, "1440x900"], [640, 400, "1280x800"]]) {
  const p = await otvori({ w, h, dpr: 2 });
  const g = `zoom 200% (${ime})`;
  zapisi(g, "bez horizontalnog skrola stranice", await nemaHorizontalnogSkrola(p));
  zapisi(g, "lista zauzima celu širinu sadržaja", (await sirina(p, "#glavni")) >= w - 2);
  zapisi(g, "naslov i pretraga ostaju čitljivi (≥ 13px)", await p.evaluate(() =>
    [...document.querySelectorAll("body *")].filter(e => e.offsetParent && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
      .every(e => parseFloat(getComputedStyle(e).fontSize) >= 13)));
  await snimi(p, `08-zoom200-${ime}-lista`);
  await p.click("#nav-toggle");
  await p.waitForTimeout(260);
  zapisi(g, "navigacija se otvara kao fioka i fokus ulazi u nju",
    (await vidljiv(p, "#nav")) && (await p.evaluate(() => document.getElementById("nav").contains(document.activeElement))));
  zapisi(g, "dok je fioka otvorena, ostatak je inert", await p.$eval("#glavni", e => e.inert));
  await snimi(p, `08-zoom200-${ime}-navigacija`);
  await p.keyboard.press("Escape"); await p.waitForTimeout(260);
  zapisi(g, "Escape zatvara fioku i vraća fokus na dugme", (await p.evaluate(() => document.activeElement.id)) === "nav-toggle" && !(await vidljiv(p, "#nav")));
  await p.click("#panel-toggle"); await p.waitForTimeout(260);
  zapisi(g, "panel „Zahteva pažnju“ dostupan kao fioka", await vidljiv(p, "#panel"));
  await snimi(p, `08-zoom200-${ime}-panel`);
  await p.keyboard.press("Escape");
  await p.context().close();
}
{
  // Fioka i sa uključenim animacijama (bez reduced-motion): fokus mora ući u nju.
  const p = await otvori({ w: 720, h: 450, dpr: 2, motion: "no-preference" });
  await p.click("#nav-toggle"); await p.waitForTimeout(300);
  zapisi("fioka sa animacijom", "navigacija otvorena, fokus unutra",
    (await vidljiv(p, "#nav")) && (await p.evaluate(() => document.getElementById("nav").contains(document.activeElement))));
  await p.click("#scrim", { position: { x: 600, y: 300 } }); await p.waitForTimeout(300);
  zapisi("fioka sa animacijom", "klik van fioke je zatvara", !(await vidljiv(p, "#nav")));
  await p.context().close();
}
{
  // Srednja širina: panel ne sme da sabija listu.
  const p = await otvori({ w: 1100, h: 800 });
  zapisi("1100×800", "panel nije u toku stranice; lista dobija prostor", !(await vidljiv(p, "#panel")) && (await sirina(p, "#glavni")) >= 1100 - 232 - 2);
  zapisi("1100×800", "dugme „Zahteva pažnju“ sa brojem stavki", (await vidljiv(p, "#panel-toggle")) && (await p.textContent("#panel-toggle-count")) === "5");
  await snimi(p, "09-1100x800-dark");
  await p.context().close();
}

// ── 11. Pozadinska animacija i reduced-motion ──────────────────────────
async function pikseli(p) { return p.$eval("#pozadina", c => c.toDataURL()); }
{
  const p = await otvori({ motion: "reduce" });
  const f1 = await p.evaluate(() => window.__vxPozadina.frames), a = await pikseli(p);
  await p.waitForTimeout(1500);
  const f2 = await p.evaluate(() => window.__vxPozadina.frames), b = await pikseli(p);
  zapisi("reduced-motion", "petlja animacije ne radi", (await p.evaluate(() => window.__vxPozadina.animira)) === false && f1 === f2, `sličica: ${f1} → ${f2}`);
  zapisi("reduced-motion", "pozadina je nepomična (pikseli identični posle 1.5 s)", a === b);
  zapisi("reduced-motion", "tekstura i dalje postoji (statična slika, nije prazno)", await p.$eval("#pozadina", c => {
    const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n > 100;
  }));
  await p.context().close();
}
{
  const p = await otvori({ motion: "no-preference" });
  const a = await pikseli(p); const f1 = await p.evaluate(() => window.__vxPozadina.frames);
  await p.waitForTimeout(2000);
  const b = await pikseli(p); const f2 = await p.evaluate(() => window.__vxPozadina.frames);
  zapisi("animacija", "bez reduced-motion: animira u ritmu ekrana (headless ≈ 60 Hz)", f2 - f1 >= 60 && f2 - f1 <= 260, `${f2 - f1} sličica za 2 s`);
  zapisi("animacija", "slika se menja (sporo treperenje)", a !== b);
  zapisi("animacija", "radna površina i panel su neprozirni (tekstura samo u ljusci)", await p.evaluate(() =>
    ["glavni", "panel"].every(id => { const c = getComputedStyle(document.getElementById(id)).backgroundColor; return c.startsWith("rgb(") || /, 1\)$/.test(c); })));
  await p.context().close();
}

zapisi("konzola", "bez grešaka u konzoli tokom svih provera", greskeKonzole.length === 0, greskeKonzole.slice(0, 3).join(" | "));

await browser.close();

const prolazi = rezultati.filter(r => r.prolazi).length;
await writeFile(new URL("results.json", OUT), JSON.stringify({ base: BASE, prolazi, ukupno: rezultati.length, rezultati }, null, 2));
const md = [`# Rezultati provere — prototip 001`, ``, `**${prolazi}/${rezultati.length} prolazi.** Ovo dokazuje ponašanje i raspored, ne vizuelni kvalitet.`, ``,
  `| Grupa | Provera | Ishod | Detalj |`, `|---|---|---|---|`,
  ...rezultati.map(r => `| ${r.grupa} | ${r.naziv} | ${r.prolazi ? "PASS" : "**FAIL**"} | ${r.detalj.replace(/\|/g, "/")} |`)].join("\n");
await writeFile(new URL("results.md", OUT), md);
console.log(`\n${prolazi}/${rezultati.length} prolazi`);
process.exit(prolazi === rezultati.length ? 0 : 1);
