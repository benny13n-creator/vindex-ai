/* Pod veličine teksta — merenje na STVARNO ISCRTANOM DOM-u.
   Ne čita CSS fajl kao dokaz: veličina je `getComputedStyle(el).fontSize`, tj. ono
   što je pobedilo u kaskadi. Deklaracija koju neko drugo pravilo pregazi ili koja
   ne pogađa nijedan prikazan element ovde se NE vidi — i ne treba da se vidi.
   Pobedničko pravilo (`poreklo`) je samo dijagnostika za popravku. */
window.__vxFont = (function () {

  /* Zaključani ekran (Pregled dana, `.kc-sphere`): isti opseg kao CSS_ZAKLJUCANO u
     tests/test_faza1_izvor_pod.py — `#tab-h`, `.kc-*`, `.vx2-*`. */
  function zakljucan(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.id === 'tab-h') return true;
      var k = (typeof n.className === 'string') ? n.className : '';
      if (/(^|\s)(kc-|vx2-)/.test(k)) return true;
    }
    return false;
  }

  function vidljiv(el) {
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false;
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (parseFloat(getComputedStyle(n).opacity) === 0) return false;
    }
    var r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;          /* sr-only / skupljeno */
    if (r.right + window.scrollX <= 0 || r.bottom + window.scrollY <= 0) return false;  /* van ekrana */
    if (cs.clip === 'rect(0px, 0px, 0px, 0px)' || /inset\(50%\)/.test(cs.clipPath || '')) return false;
    return true;
  }

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
    while (n && n.nodeType === 1 && dubina < 4) {
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

  /* Dijagnostika: koja deklaracija font-size pogađa element (inline ili poslednje
     poklapajuće pravilo, `!important` ispred ostalih). Nije dokaz veličine. */
  var _pravila = null;
  function pravila() {
    if (_pravila) return _pravila;
    _pravila = [];
    for (var i = 0; i < document.styleSheets.length; i++) {
      var ss = document.styleSheets[i], r;
      try { r = ss.cssRules; } catch (e) { continue; }
      var izvor = ss.href ? ss.href.split('/').pop().split('?')[0] : 'index.html <style>';
      (function hodaj(lista) {
        for (var j = 0; j < lista.length; j++) {
          var pr = lista[j];
          if (pr.cssRules && pr.type !== 1) {
            if (pr.media && !window.matchMedia(pr.media.mediaText).matches) continue;
            hodaj(pr.cssRules); continue;
          }
          if (pr.type !== 1 || !pr.style) continue;
          var v = pr.style.getPropertyValue('font-size');
          if (!v) continue;
          _pravila.push({ sel: pr.selectorText, v: v.trim(), vazno: pr.style.getPropertyPriority('font-size') === 'important', izvor: izvor });
        }
      })(r || []);
    }
    return _pravila;
  }

  function poreklo(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.style && n.style.fontSize) return { el: n === el ? 'sam' : 'predak ' + putanja(n).split(' > ').pop(), sel: '[style]', v: n.style.fontSize, izvor: 'inline (vindex.js/index.html)' };
      var sve = pravila(), poslednje = null, vazno = null;
      for (var i = 0; i < sve.length; i++) {
        var pr = sve[i], ok = false;
        try { ok = n.matches(pr.sel); } catch (e) {}
        if (!ok) continue;
        if (pr.vazno) vazno = pr; else poslednje = pr;
      }
      var w = vazno || poslednje;
      if (w) return { el: n === el ? 'sam' : 'predak ' + putanja(n).split(' > ').pop(), sel: w.sel, v: w.v, izvor: w.izvor, vazno: w.vazno };
    }
    return null;
  }

  /* Svi vidljivi tekstualni čvorovi; `ispod` = efektivni font-size < prag. */
  function skeniraj(kontekst, prag) {
    var izmereno = 0, ispod = [];
    var svi = document.querySelectorAll('body *');
    for (var i = 0; i < svi.length; i++) {
      var el = svi[i], tag = el.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'OPTION' ||
          tag === 'svg' || tag === 'SVG' || el.closest('svg') || el.closest('#vx-probe-host')) continue;
      var tekst = sopstveniTekst(el);
      var jePolje = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT');
      if (tag === 'INPUT' && /^(checkbox|radio|range|color|file|hidden|image)$/i.test(el.type || '')) continue;
      var poljeTekst = jePolje ? (el.value || el.getAttribute('placeholder') || '') : '';
      if (tag === 'SELECT' && el.selectedOptions && el.selectedOptions[0]) poljeTekst = el.selectedOptions[0].textContent;
      if (!/[\p{L}\p{N}]/u.test(tekst || poljeTekst)) continue;   /* samo znak/ikonica nije tekst */
      if (!vidljiv(el) || zakljucan(el)) continue;
      izmereno++;
      var px = parseFloat(getComputedStyle(el).fontSize);
      if (px < prag) {
        var r = el.getBoundingClientRect();
        ispod.push({ kontekst: kontekst, putanja: putanja(el), tekst: (tekst || poljeTekst).trim().slice(0, 50), px: px,
                     w: Math.round(r.width), h: Math.round(r.height), poreklo: poreklo(el) });
      }
    }
    return { izmereno: izmereno, ispod: ispod };
  }

  return { skeniraj: skeniraj, vidljiv: vidljiv, zakljucan: zakljucan };
})();
