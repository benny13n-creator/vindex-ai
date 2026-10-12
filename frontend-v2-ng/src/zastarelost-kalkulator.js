/* Vindex V2 NG — kalkulator zastarelosti (VCR001 T07).
 *
 * Ugovor (routers/zastarelost.py, deterministički — bez modela, bez podataka predmeta):
 *   GET  /zastarelost/tipovi    → {tipovi:[{kljuc, naziv, osnov, opis}]}   (zatvoren spisak; nudi se SAMO on)
 *   POST /zastarelost/kalkulisi {tip, datum_pocetka: YYYY-MM-DD} → {zakonski_osnov, rok_opis, datum_zastarelosti,
 *        dana_preostalo, isteklo, napomena}; nepoznat tip ili neispravan datum → 422.
 * Rezultat je orijentacioni: prekid i zastoj zastarelosti se NE računaju — to se izričito kaže uz svaki rezultat.
 * Ništa se ne upisuje u predmet.
 */
(function (root) {
  "use strict";

  function tekst(v) { return String(v == null ? "" : v).trim(); }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api;
    var tipovi = null, gen = 0, salje = false, aktivan = false;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function poruka(st, t) { var n = $("zs-poruka"); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zakljucaj(da) { salje = da; $("zs-izracunaj").disabled = da || !tipovi; }
    function ocistiRezultat() { $("zs-rezultat").hidden = true; $("zs-rezultat-lista").replaceChildren(); }

    async function ucitajTipove() {
      if (tipovi) { zakljucaj(salje); return; }
      var moja = ++gen;
      var r = await api.get("/zastarelost/tipovi", { token: sesija.token(), oblik: function (x) { return Array.isArray(x.tipovi); } });
      if (moja !== gen) return;
      if (!r.ok) { poruka("greska", "Spisak vrsta potraživanja nije učitan. Kalkulator trenutno nije dostupan."); return; }
      var lista = r.podaci.tipovi.filter(function (t) { return t && tekst(t.kljuc) && tekst(t.naziv); });
      if (!lista.length) { poruka("greska", "Spisak vrsta potraživanja je prazan."); return; }
      tipovi = lista;
      var s = $("zs-tip"); s.replaceChildren();
      lista.forEach(function (t) { var op = el("option", null, tekst(t.naziv)); op.value = tekst(t.kljuc); s.append(op); });
      opis(); zakljucaj(false);
    }
    function opis() {
      var t = (tipovi || []).filter(function (x) { return x.kljuc === $("zs-tip").value; })[0];
      $("zs-tip-pomoc").textContent = t ? [tekst(t.osnov), tekst(t.opis)].filter(Boolean).join(" — ") : "";
    }

    async function izracunaj() {
      if (salje || !tipovi) return;
      var tip = $("zs-tip").value, datum = $("zs-datum").value;
      if (!tipovi.some(function (t) { return t.kljuc === tip; })) { poruka("greska", "Izaberite vrstu potraživanja sa spiska."); return; }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(datum)) { poruka("greska", "Unesite datum od kog rok teče."); $("zs-datum").focus(); return; }
      var moja = ++gen;
      zakljucaj(true); ocistiRezultat(); poruka("ucitavanje", "Računanje…");
      var r = await api.send("/zastarelost/kalkulisi", { telo: { tip: tip, datum_pocetka: datum }, token: sesija.token(),
        oblik: function (x) { return typeof x.datum_zastarelosti === "string" && typeof x.isteklo === "boolean"; } });
      if (moja !== gen) return;
      zakljucaj(false);
      if (!(r.ok && r.podaci)) {
        var g = r.greska || {};
        poruka("greska", g.kod === "VALIDATION_ERROR" ? "Server nije prihvatio vrstu ili datum." : "Rok nije izračunat. Pokušajte ponovo.");
        return;
      }
      var x = r.podaci, ul = $("zs-rezultat-lista");
      poruka(null);
      var glavno = x.isteklo ? "Zastarelost je NASTUPILA " + tekst(x.datum_zastarelosti) + "." : "Zastarelost nastupa " + tekst(x.datum_zastarelosti) + " (za " + x.dana_preostalo + " dan(a)).";
      var li = el("li", x.isteklo ? "warn" : "an-item"); li.append(el("span", "an-item__text", glavno)); ul.append(li);
      [["Rok", x.rok_opis], ["Zakonski osnov", x.zakonski_osnov], ["Rok teče od", x.datum_pocetka], ["Napomena", x.napomena]].forEach(function (p) {
        if (tekst(p[1])) { var s = el("li", "an-item"); s.append(el("span", "an-item__text", p[0] + ": " + tekst(p[1]))); ul.append(s); }
      });
      $("zs-rezultat").hidden = false;
    }

    function aktiviraj() { if (aktivan) return; aktivan = true; ucitajTipove(); }
    function ocisti() { gen++; aktivan = false; poruka(null); ocistiRezultat(); zakljucaj(false); }

    $("zs-forma").addEventListener("submit", function (e) { e.preventDefault(); izracunaj(); });
    $("zs-tip").addEventListener("change", opis);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { tipovi = null; ocisti(); } });
    return { aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxZastarelostKalkulator = Object.freeze({ napravi: napravi });
})(window);
