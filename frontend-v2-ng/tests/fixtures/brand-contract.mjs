// Ugovor kanonskog Vindex identiteta u gornjoj traci (NS003 Task 4).
//
// Jedino nameravane promene vizuelnog izgleda u odnosu na foundation 1eb20976:
//   TAMNA:  samo prostor bivšeg tekstualnog „Vindex“ (sada kanonski logo);
//   SVETLA: prostor logoa + pozadina gornje trake (#F6F7F8, founder odluka).
// Unutar tih regiona piksel-poređenje se zamenjuje OVIM semantičkim i
// geometrijskim ugovorom; van njih poređenje ostaje kakvo je bilo.

export const LOGO = {
  dark: { klasa: "wordmark__logo--tamna", fajl: "brand/Vindex_Transparent_EXACT_LOOK.svg", w: 1183, h: 309 },
  light: { klasa: "wordmark__logo--svetla", fajl: "brand/Vindex_Protected_Light_Surface.png", w: 1800, h: 500 },
};
/* Boja neprovidne margine zaštićenog lockup-a (sva 392 499 piksela margine). */
export const SVETLA_TRAKA = "rgb(246, 247, 248)";
export const KONTROLE = ["#nav-toggle", ".demo-badge", "#panel-toggle", "#theme-toggle", ".account"];

/** Stanje gornje trake i identiteta (radi i na foundation-u, gde je logo tekst). */
export function brendUgovor(p) {
  return p.evaluate((KONTROLE) => {
    const r = (e) => { const b = e.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; };
    const vidljiv = (e) => !!e && !e.closest("[hidden]") && getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility !== "hidden" && e.getClientRects().length > 0;
    const efekti = (e) => { const c = getComputedStyle(e); return { filter: c.filter, opacity: c.opacity, blend: c.mixBlendMode, transform: c.transform, senka: c.boxShadow, tekstSenka: c.textShadow,
      radius: c.borderRadius, fit: c.objectFit, clip: c.clipPath, maska: c.maskImage || c.webkitMaskImage, slika: c.backgroundImage, animacija: c.animationName }; };
    const t = document.querySelector(".topbar"), w = document.querySelector(".wordmark");
    return {
      tema: document.documentElement.dataset.theme,
      traka: { okvir: r(t), pozadina: getComputedStyle(t).backgroundColor, efekti: efekti(t), preliv: t.scrollWidth > t.clientWidth || t.scrollHeight > t.clientHeight },
      dokumentPreliv: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      viewport: innerWidth,
      telo: getComputedStyle(document.body).backgroundColor,
      kontrole: KONTROLE.map(s => { const e = document.querySelector(s); const c = getComputedStyle(e); return { s, vidljiv: vidljiv(e), okvir: vidljiv(e) ? r(e) : null, boja: c.color, pozadina: c.backgroundColor }; }),
      znak: { okvir: r(w), href: w.getAttribute("href"), ime: w.getAttribute("aria-label"), tekst: w.textContent.trim(), efekti: efekti(w) },
      slike: [...w.querySelectorAll("img")].map(i => ({ klasa: i.className, src: i.getAttribute("src"), trenutni: i.currentSrc ? new URL(i.currentSrc).pathname : "",
        alt: i.getAttribute("alt"), vidljiv: vidljiv(i), gotovo: i.complete, nw: i.naturalWidth, nh: i.naturalHeight, okvir: r(i), efekti: efekti(i) })),
    };
  }, KONTROLE);
}

const isti = (a, b, tol = 0.01) => a && b && ["x", "y", "w", "h"].every(k => Math.abs(a[k] - b[k]) <= tol);
const unutar = (a, b, tol = 0.5) => a.x >= b.x - tol && a.y >= b.y - tol && a.x + a.w <= b.x + b.w + tol && a.y + a.h <= b.y + b.h + tol;
const BEZ_EFEKATA = { filter: "none", opacity: "1", blend: "normal", transform: "none", senka: "none", radius: "0px", fit: "fill", clip: "none", maska: "none", slika: "none", animacija: "none" };

/**
 * Provere HEAD ugovora prema foundation ugovoru (`ref`) istog scenarija.
 * Vraća listu [naziv, ok, detalj]; nijedna provera ne baca izuzetak.
 */
export function proveriBrend(u, ref) {
  const out = [];
  const z = (naziv, ok, detalj = "") => out.push([naziv, !!ok, detalj]);
  const tema = u.tema === "light" ? "light" : "dark";
  const ocek = LOGO[tema];
  const vidljive = u.slike.filter(s => s.vidljiv);
  const logo = vidljive[0];
  z(`tema ${tema}: vidljiv je tačno jedan logo, odobren za ovu temu (${ocek.fajl.split("/")[1]})`,
    vidljive.length === 1 && logo.klasa.includes(ocek.klasa) && logo.src === ocek.fajl && logo.trenutni.endsWith("/" + ocek.fajl), vidljive.map(s => s.src).join(","));
  if (!logo) return out;
  z("logo je učitan sa izvornim dimenzijama asseta", logo.gotovo && logo.nw === ocek.w && logo.nh === ocek.h, `${logo.nw}x${logo.nh}`);
  const ocekSirina = logo.okvir.h * ocek.w / ocek.h;
  z("razmera sačuvana: širina = visina × izvorna razmera (±0,5 px)", Math.abs(logo.okvir.w - ocekSirina) <= 0.5, `${logo.okvir.w.toFixed(2)} vs ${ocekSirina.toFixed(2)}`);
  const losi = Object.entries(BEZ_EFEKATA).filter(([k, v]) => logo.efekti[k] !== v && !(k === "maska" && !logo.efekti[k]));
  z("logo bez filtera, providnosti, blend-a, transformacije, senke, zaobljenja, isecanja, maske, pozadine i animacije", losi.length === 0, losi.map(([k]) => `${k}=${logo.efekti[k]}`).join(" "));
  const nadZnakom = ["filter", "opacity", "transform", "tekstSenka", "senka", "slika", "blend"].filter(k => u.znak.efekti[k] !== ({ opacity: "1", blend: "normal", slika: "none" }[k] || "none"));
  const nadTrakom = ["filter", "opacity", "transform", "senka", "slika", "blend"].filter(k => u.traka.efekti[k] !== ({ opacity: "1", blend: "normal", slika: "none" }[k] || "none"));
  z("link i traka ne dodaju efekat logou (filter/sjaj/gradijent/transformacija)", nadZnakom.length === 0 && nadTrakom.length === 0, [...nadZnakom, ...nadTrakom].join(","));
  z("logo je ceo unutar linka i gornje trake (nije isečen)", unutar(logo.okvir, u.znak.okvir) && unutar(logo.okvir, u.traka.okvir) && logo.okvir.x >= 0 && logo.okvir.x + logo.okvir.w <= u.viewport,
    JSON.stringify(logo.okvir));
  z("gornja traka i dokument bez preliva", !u.traka.preliv && !u.dokumentPreliv);
  z("link: isto odredište i isto pristupačno ime kao foundation", u.znak.href === ref.znak.href && u.znak.ime === ref.znak.ime && u.znak.ime === "Vindex — Aktivni predmeti", `${u.znak.href} „${u.znak.ime}“`);
  z("čitač ekrana ne dobija dupli „Vindex“ (logo alt=\"\", bez teksta u linku)", u.slike.every(s => s.alt === "") && u.znak.tekst === "", JSON.stringify(u.znak.tekst));
  z("gornja traka: okvir identičan foundation-u (visina, širina, položaj)", isti(u.traka.okvir, ref.traka.okvir), `${JSON.stringify(u.traka.okvir)} vs ${JSON.stringify(ref.traka.okvir)}`);
  const pomereni = u.kontrole.filter((k, i) => k.vidljiv !== ref.kontrole[i].vidljiv || (k.vidljiv && !isti(k.okvir, ref.kontrole[i].okvir)));
  z("kontrole (navigacija, značka, pažnja, tema, nalog): iste vidljivosti i okviri kao foundation", pomereni.length === 0, pomereni.map(k => k.s).join(","));
  const pozadina = tema === "light" ? SVETLA_TRAKA : ref.traka.pozadina;
  z(`pozadina gornje trake: ${tema === "light" ? "#F6F7F8 (founder odluka)" : "nepromenjena prema foundation-u"}`, u.traka.pozadina === pozadina, u.traka.pozadina);
  return out;
}

const rgb = (s) => (s.match(/[\d.]+/g) || []).map(Number);
const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
export const kontrast = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
const providna = (s) => /rgba\([^)]*,\s*0\)$/.test(s) || s === "transparent";
/** Kontrast svake vidljive kontrole naspram površine na kojoj stoji. */
export function kontrastiKontrola(u) {
  const traka = providna(u.traka.pozadina) ? u.telo : u.traka.pozadina;
  // Poluprovidna pozadina kontrole se slaže preko površine trake (alpha).
  const preko = (gore, dole) => { const g = rgb(gore), d = rgb(dole), a = g.length > 3 ? g[3] : 1; return `rgb(${[0, 1, 2].map(i => g[i] * a + d[i] * (1 - a)).join(", ")})`; };
  return u.kontrole.filter(k => k.vidljiv).map(k => ({ s: k.s, odnos: kontrast(preko(k.boja, preko(k.pozadina, traka)), preko(k.pozadina, traka)) }));
}
/** Čitljivost: tekst ≥ 4,5:1, ikonica (#nav-toggle) ≥ 3:1, i nikad slabije od foundation-a. */
export function proveriKontrast(u, ref) {
  const a = kontrastiKontrola(u), b = kontrastiKontrola(ref);
  const losi = a.filter(k => k.odnos < (k.s === "#nav-toggle" ? 3 : 4.5) || k.odnos + 0.01 < ((b.find(x => x.s === k.s) || {}).odnos || 0));
  return [["kontrole na traci ostaju čitljive (tekst ≥ 4,5:1, ikonica ≥ 3:1, ne slabije od foundation-a)", losi.length === 0 && a.length > 0,
    a.map(k => `${k.s} ${k.odnos.toFixed(2)}`).join(" ")]];
}

/** Prostor u kome je promena nameravana (CSS px; za masku piksel-poređenja). */
export function nameravaniRegion(u, ref) {
  const unija = (a, b) => { const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y); return { x, y, w: Math.max(a.x + a.w, b.x + b.w) - x, h: Math.max(a.y + a.h, b.y + b.h) - y }; };
  return u.tema === "light" ? unija(u.traka.okvir, ref.traka.okvir) : unija(u.znak.okvir, ref.znak.okvir);
}
