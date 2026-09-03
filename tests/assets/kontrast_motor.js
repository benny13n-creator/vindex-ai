/* Faza 1 — merenje kontrasta na STVARNO ISCRTANOM DOM-u.
   Ne cita CSS fajl. Cita getComputedStyle + kompozituje alfa slojeve
   kroz stvarno lanac predaka, tacno onako kako pixel zavrsi na ekranu. */
window.__vxContrast = (function () {

  function parseColor(s) {
    if (!s) return null;
    var m = s.match(/^rgba?\(([^)]+)\)$/);
    if (!m) return null;
    var p = m[1].split(/[,\s\/]+/).filter(function (x) { return x !== ''; });
    var r = parseFloat(p[0]), g = parseFloat(p[1]), b = parseFloat(p[2]);
    var a = p.length > 3 ? parseFloat(p[3]) : 1;
    if (isNaN(r) || isNaN(g) || isNaN(b)) return null;
    return { r: r, g: g, b: b, a: isNaN(a) ? 1 : a };
  }

  /* src preko dst (oba premultiplikovana kroz sopstvenu alfu) */
  function over(src, dst) {
    var a = src.a + dst.a * (1 - src.a);
    if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
    return {
      r: (src.r * src.a + dst.r * dst.a * (1 - src.a)) / a,
      g: (src.g * src.a + dst.g * dst.a * (1 - src.a)) / a,
      b: (src.b * src.a + dst.b * dst.a * (1 - src.a)) / a,
      a: a
    };
  }

  function lum(c) {
    function ch(v) { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
  }

  function ratio(fg, bg) {
    var l1 = lum(fg), l2 = lum(bg);
    var hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  }

  /* Efektivna pozadina ispod elementa: idi UZ stablo skupljajuci slojeve,
     pa ih kompozituj odozdo nagore. Vrati i da li je bilo gradijenta. */
  function effectiveBg(el) {
    var slojevi = [];
    var gradient = null;
    var n = el;
    while (n && n.nodeType === 1) {
      var cs = getComputedStyle(n);
      var bi = cs.backgroundImage;
      if (bi && bi !== 'none' && gradient === null) gradient = bi.slice(0, 90);
      var c = parseColor(cs.backgroundColor);
      var op = parseFloat(cs.opacity);
      if (c && c.a > 0) {
        var ea = c.a * (isNaN(op) ? 1 : op);
        slojevi.push({ r: c.r, g: c.g, b: c.b, a: ea });
      }
      n = n.parentElement;
    }
    /* podloga stranice ako nista nije neprovidno */
    slojevi.push({ r: 255, g: 255, b: 255, a: 1 });
    var acc = slojevi[slojevi.length - 1];
    for (var i = slojevi.length - 2; i >= 0; i--) acc = over(slojevi[i], acc);
    return { boja: acc, gradient: gradient };
  }

  function inheritedOpacity(el) {
    var o = 1, n = el;
    while (n && n.nodeType === 1) {
      var v = parseFloat(getComputedStyle(n).opacity);
      if (!isNaN(v)) o *= v;
      n = n.parentElement;
    }
    return o;
  }

  function vidljiv(el) {
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) === 0) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    return true;
  }

  /* Direktan tekst elementa (ne racunaj tekst dece) */
  function sopstveniTekst(el) {
    var t = '';
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3) t += n.nodeValue;
    }
    return t.replace(/\s+/g, ' ').trim();
  }

  function putanja(el) {
    var d = [], n = el, dubina = 0;
    while (n && n.nodeType === 1 && dubina < 5) {
      var s = n.tagName.toLowerCase();
      if (n.id) s += '#' + n.id;
      if (n.className && typeof n.className === 'string') {
        var k = n.className.trim().split(/\s+/).slice(0, 3);
        if (k.length && k[0]) s += '.' + k.join('.');
      }
      d.unshift(s);
      n = n.parentElement; dubina++;
    }
    return d.join(' > ');
  }

  /* Specificnost selektora (a,b,c) -> broj */
  function spec(sel) {
    var s = sel.replace(/::?[a-z-]+(\([^)]*\))?/g, ' ');
    var id = (sel.match(/#[\w-]+/g) || []).length;
    var kl = (sel.match(/\.[\w-]+/g) || []).length +
             (sel.match(/\[[^\]]*\]/g) || []).length +
             (sel.match(/:(?!:)(hover|focus|active|checked|disabled|first-child|last-child|nth-[a-z-]+|not|is|where)/g) || []).length;
    var el = (s.match(/(^|[\s>+~])([a-zA-Z][\w-]*)/g) || []).length;
    return id * 10000 + kl * 100 + el;
  }

  var _pravila = null;
  function svaPravila() {
    if (_pravila) return _pravila;
    _pravila = [];
    for (var i = 0; i < document.styleSheets.length; i++) {
      var ss = document.styleSheets[i], r;
      try { r = ss.cssRules; } catch (e) { continue; }
      if (!r) continue;
      var izvor = ss.href ? ss.href.split('/').pop() : '<inline>';
      (function hodaj(lista) {
        for (var j = 0; j < lista.length; j++) {
          var pr = lista[j];
          if (pr.cssRules && pr.type !== 1) { hodaj(pr.cssRules); continue; }
          if (pr.type !== 1 || !pr.style) continue;
          var boja = pr.style.getPropertyValue('color');
          if (!boja) continue;
          _pravila.push({
            sel: pr.selectorText,
            boja: boja.trim(),
            vazno: pr.style.getPropertyPriority('color') === 'important',
            izvor: izvor,
            spec: spec(pr.selectorText || '')
          });
        }
      })(r);
    }
    return _pravila;
  }

  /* Koja deklaracija je POBEDILA za color na ovom elementu */
  function poreklo(el) {
    if (el.style && el.style.color) return { sel: '[style atribut]', boja: el.style.color, izvor: 'inline', vazno: false };
    var sve = svaPravila(), kandidati = [];
    for (var i = 0; i < sve.length; i++) {
      var pr = sve[i];
      try { if (el.matches(pr.sel)) kandidati.push({ pr: pr, red: i }); } catch (e) {}
    }
    if (!kandidati.length) return null;
    kandidati.sort(function (a, b) {
      if (a.pr.vazno !== b.pr.vazno) return a.pr.vazno ? 1 : -1;
      if (a.pr.spec !== b.pr.spec) return a.pr.spec - b.pr.spec;
      return a.red - b.red;
    });
    var w = kandidati[kandidati.length - 1].pr;
    return { sel: w.sel, boja: w.boja, izvor: w.izvor, vazno: w.vazno, broj_kandidata: kandidati.length };
  }

  function skeniraj(kontekst) {
    var out = [];
    var svi = document.querySelectorAll('body *');
    for (var i = 0; i < svi.length; i++) {
      var el = svi[i];
      if (el.closest && el.closest('#vx-probe-host')) continue;
      var tag = el.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' ||
          tag === 'CANVAS' || tag === 'SVG' || tag === 'PATH') continue;

      var tekst = sopstveniTekst(el);
      var tip = (tag === 'INPUT') ? (el.type || 'text').toLowerCase() : '';
      var NETEKST = {checkbox:1, radio:1, range:1, color:1, file:1, hidden:1, image:1};
      if (tag === 'INPUT' && NETEKST[tip]) continue;
      var jePolje = (tag === 'INPUT' || tag === 'TEXTAREA');
      var ph = jePolje ? (el.getAttribute('placeholder') || '') : '';
      var vrednost = jePolje ? (el.value || '') : '';
      if (!tekst && !ph && !vrednost) continue;
      if (!vidljiv(el)) continue;

      var cs = getComputedStyle(el);
      var fgRaw = parseColor(cs.color);
      if (!fgRaw) continue;

      var bgInfo = effectiveBg(el);
      var op = inheritedOpacity(el);
      var fg = over({ r: fgRaw.r, g: fgRaw.g, b: fgRaw.b, a: fgRaw.a * op }, bgInfo.boja);

      var fs = parseFloat(cs.fontSize);
      var fw = parseInt(cs.fontWeight, 10) || 400;
      var veliki = (fs >= 24) || (fs >= 18.66 && fw >= 700);
      var prag = veliki ? 3.0 : 4.5;

      var r = ratio(fg, bgInfo.boja);

      out.push({
        kontekst: kontekst,
        putanja: putanja(el),
        tag: tag,
        tekst: (tekst || ph).slice(0, 70),
        placeholder: !!(!tekst && ph),
        boja: cs.color,
        fg_efektivno: 'rgb(' + Math.round(fg.r) + ',' + Math.round(fg.g) + ',' + Math.round(fg.b) + ')',
        bg_efektivno: 'rgb(' + Math.round(bgInfo.boja.r) + ',' + Math.round(bgInfo.boja.g) + ',' + Math.round(bgInfo.boja.b) + ')',
        gradient: bgInfo.gradient,
        px: fs,
        weight: fw,
        veliki: veliki,
        prag: prag,
        odnos: Math.round(r * 100) / 100,
        pada: r < prag,
        poreklo: (r < prag) ? poreklo(el) : null
      });
    }
    return out;
  }

  /* ── HIJERARHIJA ─────────────────────────────────────────────────
     Za zadate selektore vrati efektivnu luminansu iscrtanog teksta.
     Poredak luminansi = vizuelna hijerarhija. Meri se na PRVOM
     vidljivom pojavljivanju; ako ga nema, sintetizuj cvor u pravom
     roditelju da se dobije stvarna kaskada. */
  function lestvica(grupe) {
    var izlaz = {};
    for (var g in grupe) {
      var redovi = [];
      for (var i = 0; i < grupe[g].length; i++) {
        var sel = grupe[g][i];
        var el = null;
        var svi = document.querySelectorAll(sel);
        for (var j = 0; j < svi.length; j++) {
          if (vidljiv(svi[j]) && sopstveniTekst(svi[j])) { el = svi[j]; break; }
        }
        if (!el) { for (var j2 = 0; j2 < svi.length; j2++) { if (vidljiv(svi[j2])) { el = svi[j2]; break; } } }
        if (!el && svi.length) el = svi[0];
        if (!el) { redovi.push({ sel: sel, nema: true }); continue; }
        var cs = getComputedStyle(el);
        var fgRaw = parseColor(cs.color);
        var bgI = effectiveBg(el);
        if (!fgRaw) { redovi.push({ sel: sel, nema: true }); continue; }
        var fg = over({ r: fgRaw.r, g: fgRaw.g, b: fgRaw.b, a: fgRaw.a * inheritedOpacity(el) }, bgI.boja);
        redovi.push({
          sel: sel,
          boja: cs.color,
          fg: 'rgb(' + Math.round(fg.r) + ',' + Math.round(fg.g) + ',' + Math.round(fg.b) + ')',
          bg: 'rgb(' + Math.round(bgI.boja.r) + ',' + Math.round(bgI.boja.g) + ',' + Math.round(bgI.boja.b) + ')',
          L: Math.round(lum(fg) * 100000) / 100000,
          odnos: Math.round(ratio(fg, bgI.boja) * 100) / 100
        });
      }
      izlaz[g] = redovi;
    }
    return izlaz;
  }

  /* Broj razlicitih iscrtanih boja teksta na vidljivim cvorovima */
  function razlicitostBoja() {
    var skup = {}, n = 0;
    var svi = document.querySelectorAll('body *');
    for (var i = 0; i < svi.length; i++) {
      var el = svi[i];
      if (!sopstveniTekst(el)) continue;
      if (!vidljiv(el)) continue;
      var cs = getComputedStyle(el);
      var fgRaw = parseColor(cs.color); if (!fgRaw) continue;
      var bgI = effectiveBg(el);
      var fg = over({ r: fgRaw.r, g: fgRaw.g, b: fgRaw.b, a: fgRaw.a * inheritedOpacity(el) }, bgI.boja);
      var k = Math.round(fg.r) + ',' + Math.round(fg.g) + ',' + Math.round(fg.b);
      if (!skup[k]) { skup[k] = 0; n++; }
      skup[k]++;
      }
    return { razlicitih: n, ukupno_cvorova: Object.keys(skup).reduce(function(a,k){return a+skup[k];},0), raspodela: skup };
  }

  return { skeniraj: skeniraj, lestvica: lestvica, razlicitostBoja: razlicitostBoja, ratio: ratio, parseColor: parseColor, over: over, lum: lum };
})();
