// Semantički ugovor ekrana pri stvarnom zumu pregledača (NS002B).
//
// Ono što korisnik pri zumu 200% STVARNO dobija: raspored, režim navigacije i
// panela, preliv, geometriju redova, ograničenje naziva na 2 reda, fokus bez
// pomeranja, tipografski pod i izračunate stilove ključnih elemenata. Ovo se
// poredi HEAD protiv foundation-a i blokira; snimak ekrana je samo dokaz.

/** Ugovor stranice u trenutnom stanju (bez interakcije). */
export function ugovor(p) {
  return p.evaluate(() => {
    const r = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
    const vidljiv = (e) => !!e && !e.closest("[hidden]") && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
    const KLJUCNI = [".topbar", ".wordmark", ".sheet__title", ".sheet__count", "#pretraga", ".cases th .sort", ".case__name", ".case__meta", ".ref__no", ".ref__court",
      ".state", "time.date", ".sidenav__label", ".panel__title", ".att__title", ".demo-badge", "#panel-toggle", "#nav-toggle", "#theme-toggle"];
    const stilovi = {};
    for (const s of KLJUCNI) {
      const e = document.querySelector(s);
      if (!e) { stilovi[s] = null; continue; }
      const c = getComputedStyle(e);
      stilovi[s] = {
        vidljiv: vidljiv(e),
        font: c.fontFamily, size: c.fontSize, weight: c.fontWeight, lh: c.lineHeight, color: c.color, bg: c.backgroundColor,
        border: [c.borderTopWidth, c.borderRightWidth, c.borderBottomWidth, c.borderLeftWidth].join(" "),
        transform: c.transform, opacity: c.opacity, clamp: c.webkitLineClamp,
      };
    }
    // Tipografski pod: najmanja izračunata veličina vidljivog teksta.
    let minFont = Infinity, minEl = "";
    const hodaj = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (hodaj.nextNode()) {
      const t = hodaj.currentNode; if (!t.textContent.trim()) continue;
      const e = t.parentElement; if (!vidljiv(e)) continue;
      const px = parseFloat(getComputedStyle(e).fontSize);
      if (px < minFont) { minFont = px; minEl = e.tagName.toLowerCase() + (e.className ? "." + String(e.className).split(" ")[0] : ""); }
    }
    const nazivi = [...document.querySelectorAll(".case__name")];
    return {
      dpr: devicePixelRatio, inner: [innerWidth, innerHeight],
      preliv: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      sirine: [document.documentElement.scrollWidth, document.documentElement.clientWidth],
      skrol: [Math.round(scrollX), Math.round(scrollY)],
      nav: getComputedStyle(document.getElementById("nav")).position === "fixed" ? "fioka" : "kolona",
      panel: getComputedStyle(document.getElementById("panel")).position === "fixed" ? "fioka" : "kolona",
      okviri: { glavni: r(document.getElementById("glavni")), registar: r(document.getElementById("registry")), topbar: r(document.querySelector(".topbar")) },
      redovi: [...document.querySelectorAll("#rows tr")].map(t => Math.round(t.getBoundingClientRect().height)),
      najviseRedovaNaziva: Math.max(0, ...nazivi.map(a => Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight)))),
      minFont: [minFont, minEl],
      stilovi,
    };
  });
}

/** Fokus tastature na prvi naziv ne sme da promeni visinu nijednog reda. */
export async function fokusBezPomeranja(p) {
  const visine = () => p.evaluate(() => [...document.querySelectorAll("#rows tr")].map(t => Math.round(t.getBoundingClientRect().height)));
  const pre = await visine();
  await p.focus('th[data-kljuc="izmenjeno"] .sort');
  await p.keyboard.press("Tab");
  const naNazivu = await p.evaluate(() => !!document.activeElement && document.activeElement.classList.contains("case__name"));
  const posle = await visine();
  const linija = await p.evaluate(() => { const a = document.activeElement; return a && a.classList.contains("case__name") ? Math.round(a.getBoundingClientRect().height / parseFloat(getComputedStyle(a).lineHeight)) : -1; });
  await p.evaluate(() => document.activeElement && document.activeElement.blur());
  return { naNazivu, isto: JSON.stringify(pre) === JSON.stringify(posle), linijaFokusiranog: linija };
}

/** Razlike između dva ugovora (prazno = identični). */
export function razlikeUgovora(a, b, put = "") {
  if (JSON.stringify(a) === JSON.stringify(b)) return [];
  if (a && b && typeof a === "object" && typeof b === "object" && !Array.isArray(a)) {
    return [...new Set([...Object.keys(a), ...Object.keys(b)])].flatMap(k => razlikeUgovora(a[k], b[k], put ? put + "." + k : k));
  }
  return [`${put}: ${JSON.stringify(a)} ≠ ${JSON.stringify(b)}`];
}
