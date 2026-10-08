/* Vindex V2 NG — potpisna pozadina (prenos originalnog Vindex efekta).
 *
 * IZVOR: legal-agent `static/vindex.js`, blok `/* CANVAS *\/`, funkcija
 * `drawBg` (identična na lokalnom main i origin/main; uvedena u 605b7604).
 *
 * Preneto DOSLOVNO: 60 tačaka, raspodela brzina/veličina/faza, redosled
 * pozivanja slučajnih brojeva, mreža na 80 px, prozirnosti, prag linija
 * 160 px, debljine, boje po temi i redosled crtanja (tačka i se pomera pa
 * crta, linije idu ka tačkama j > i koje u tom frejmu još nisu pomerene).
 *
 * Odobrene izmene (Phase B):
 *   D1  uklonjen radijalni sjaj koji prati kursor (i slušalac `mousemove`)
 *   —   tema iz `html[data-theme]` umesto `body.light-theme`
 *   —   kretanje po vremenu: 1 jedinica = 1 frejm originala pri 60 Hz
 *   —   DPR + ograničenje rezolucije platna
 *   —   prefers-reduced-motion: jedan nepomičan frejm
 *   —   pauza dok je stranica skrivena, nastavak bez vremenskog skoka
 *   —   zatvoren modul sa `destroy()` umesto globalnih promenljivih
 *   —   opciono seme (`window.VX_BG_SEED`) samo za testove; bez njega
 *       koristi se Math.random kao u originalu
 */
(function () {
  "use strict";

  /* ── Konstante originala ─────────────────────────────────────────────── */
  var BROJ_TACAKA = 60;
  var KORAK_MREZE = 80;
  var PRAG_LINIJE = 160;
  var BOJA = { dark: "0,212,255", light: "0,153,187" };
  var MREZA_A = { dark: 0.048, light: 0.04 };
  var LINIJA_A = { dark: 0.18, light: 0.09 };
  var FAZA_PO_FREJMU = 0.007;

  /* ── Prilagođavanja ──────────────────────────────────────────────────── */
  var FREJM_MS = 1000 / 60;            // jedinica brzine originala
  var MAX_KORAK_MS = 100;              // duži razmak (zastoj) se ne nadoknađuje skokom
  var MAX_DPR = 2;
  var MAX_PIKSELA = 1440 * 900 * 4;    // 5,18 Mpx: 1440×900 pri DPR 2, veće površine se skaliraju

  function mulberry32(seme) {
    var a = seme >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /**
   * @param {HTMLCanvasElement} platno
   * @param {{seed?: number, rucno?: boolean}} [opcije]
   *   rucno: bez petlje i bez slušalaca (za testove i poređenje sa originalom)
   */
  function mount(platno, opcije) {
    opcije = opcije || {};
    var ctx = platno.getContext("2d");
    var rnd = typeof opcije.seed === "number" ? mulberry32(opcije.seed) : Math.random;
    var smanjeno = window.matchMedia("(prefers-reduced-motion: reduce)");

    platno.style.pointerEvents = "none";
    platno.setAttribute("aria-hidden", "true");
    platno.tabIndex = -1;

    var W = 0, H = 0, dpr = 1;
    var rafId = 0, poslednje = null, unisten = false;
    var odjave = [];
    var stat = { frames: 0, animira: false, crtanjeMs: [], dpr: 1, platnoPx: [0, 0] };

    function slusaj(cilj, tip, fn) {
      cilj.addEventListener(tip, fn);
      odjave.push(function () { cilj.removeEventListener(tip, fn); });
    }

    function tema() { return document.documentElement.dataset.theme === "light" ? "light" : "dark"; }

    function velicina() {
      W = window.innerWidth; H = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      if (W * H * dpr * dpr > MAX_PIKSELA) dpr = Math.max(1, Math.sqrt(MAX_PIKSELA / (W * H)));
      platno.width = Math.round(W * dpr);
      platno.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      stat.dpr = dpr; stat.platnoPx = [platno.width, platno.height];
    }

    velicina();

    /* Isti redosled poziva kao u originalu: x, y, vx, vy, t, r. */
    var pts = [];
    for (var i = 0; i < BROJ_TACAKA; i++) {
      pts.push({ x: rnd() * W, y: rnd() * H, vx: (rnd() - 0.5) * 0.18, vy: (rnd() - 0.5) * 0.18, t: rnd() * Math.PI * 2, r: rnd() * 0.8 + 0.25 });
    }

    /* Jedan frejm originala; `k` = koliko frejmova od 60 Hz je proteklo. */
    function frejm(k) {
      var t0 = performance.now();
      var isL = tema() === "light";
      var rgb = BOJA[isL ? "light" : "dark"];
      var x, y, j;
      ctx.clearRect(0, 0, W, H);

      ctx.strokeStyle = "rgba(" + rgb + "," + MREZA_A[isL ? "light" : "dark"] + ")";
      ctx.lineWidth = 1;
      for (x = 0; x < W; x += KORAK_MREZE) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
      for (y = 0; y < H; y += KORAK_MREZE) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

      /* D1: ovde je u originalu bio radijalni sjaj oko kursora — uklonjen. */

      for (var n = 0; n < pts.length; n++) {
        var p = pts[n];
        p.x += p.vx * k; p.y += p.vy * k; p.t += FAZA_PO_FREJMU * k;
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0; if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
        var rawA = 0.4 + 0.4 * Math.sin(p.t);
        var a = isL ? Math.max(0.12, Math.min(0.22, rawA * 0.28)) : Math.max(0.35, Math.min(0.75, rawA * 0.75));
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r + 0.5, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(" + rgb + "," + a + ")"; ctx.fill();
        for (j = n + 1; j < pts.length; j++) {
          var q = pts[j], d = Math.hypot(p.x - q.x, p.y - q.y);
          if (d < PRAG_LINIJE) {
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y);
            ctx.strokeStyle = "rgba(" + rgb + "," + (LINIJA_A[isL ? "light" : "dark"] * (1 - d / PRAG_LINIJE)) + ")";
            ctx.lineWidth = 0.7; ctx.stroke();
          }
        }
      }
      stat.frames++;
      var ms = performance.now() - t0;
      if (stat.crtanjeMs.length < 2000) stat.crtanjeMs.push(ms);
    }

    function petlja(sad) {
      if (unisten) return;
      rafId = requestAnimationFrame(petlja);
      /* Prvi frejm posle (ponovnog) pokretanja ne pomera ništa: nema skoka. */
      var dt = poslednje === null ? 0 : Math.min(sad - poslednje, MAX_KORAK_MS);
      poslednje = sad;
      frejm(dt / FREJM_MS);
    }

    function zaustavi() { cancelAnimationFrame(rafId); rafId = 0; poslednje = null; stat.animira = false; }

    function pokreni() {
      if (unisten) return;
      zaustavi();
      if (smanjeno.matches) { frejm(0); return; }   // statična tekstura
      if (document.hidden) return;                   // nastavlja se na visibilitychange
      stat.animira = true;
      rafId = requestAnimationFrame(petlja);
    }

    /* DPR se menja i bez promene veličine prozora (prevlačenje na drugi ekran). */
    var dprUpit = null;
    function pratiDpr() {
      if (dprUpit) dprUpit.removeEventListener("change", naDpr);
      dprUpit = window.matchMedia("(resolution: " + (window.devicePixelRatio || 1) + "dppx)");
      dprUpit.addEventListener("change", naDpr);
    }
    function naDpr() { velicina(); pratiDpr(); if (!stat.animira) frejm(0); }
    function naVelicinu() { velicina(); if (!stat.animira) frejm(0); }

    var posmatrac = null;
    if (!opcije.rucno) {
      slusaj(window, "resize", naVelicinu);
      slusaj(document, "visibilitychange", pokreni);
      slusaj(smanjeno, "change", pokreni);
      pratiDpr();
      odjave.push(function () { if (dprUpit) dprUpit.removeEventListener("change", naDpr); dprUpit = null; });
      /* Statična slika mora pratiti promenu teme; animirana je čita svaki frejm. */
      posmatrac = new MutationObserver(function () { if (!stat.animira) frejm(0); });
      posmatrac.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      odjave.push(function () { posmatrac.disconnect(); });
      pokreni();
    }

    return {
      stat: stat,
      /* Test/poređenje: jedan frejm sa zadatim brojem 60 Hz koraka. */
      frejm: frejm,
      /* Test: napreduj stanje za `ms` u koracima od `korakMs` bez crtanja petlje. */
      napreduj: function (ms, korakMs) { var n = Math.round(ms / korakMs); for (var s = 0; s < n; s++) frejm(korakMs / FREJM_MS); },
      tacke: function () { return pts.map(function (p) { return { x: p.x, y: p.y, t: p.t }; }); },
      destroy: function () {
        if (unisten) return;
        unisten = true;
        zaustavi();
        odjave.forEach(function (f) { f(); });
        odjave = [];
        ctx.clearRect(0, 0, W, H);
      },
    };
  }

  window.VindexSignatureBackground = { mount: mount };

  var platno = document.getElementById("pozadina");
  if (platno && platno.getContext) {
    var seme = typeof window.VX_BG_SEED === "number" ? window.VX_BG_SEED : undefined;
    var inst = mount(platno, { seed: seme });
    /* Kompatibilno sa postojećim proverama (frames, animira) + pristup instanci. */
    window.__vxPozadina = inst.stat;
    window.__vxPozadinaInstanca = inst;
  }
})();
