/* Vindex V2 NG — LAW BRAIN: iskustvo kancelarije (NS008).
 *
 * Ugovori (routers/law_brain.py) — čitanje BEZ modela i BEZ kredita:
 *   GET /api/law-brain/znanje → {iskustvo{state, grupe[{tip, relevantnih, sa_ljudskim_ishodom, po_ishodu, recenice,
 *        mali_uzorak}]}, verifikovani_radovi{state, stavke[]}, potvrdjene_lekcije{state, stavke[], kandidata},
 *        memorija_kancelarije{state, stavke[], veze[]}, napomena, data_quality}
 *   Stavka = Law Brain item: {id, trust_class, validity, title, excerpt, source_ref, attrs, state, predmet_id}.
 * Pravila: stanje DEGRADED = izvor nije pročitan (NIKAD „prazno"); zakon/praksa, znanje kancelarije i AI
 * analiza se vizuelno razlikuju; nema procenata ni „šansi"; filter je lokalan (ne šalje zahtev).
 */
(function (root) {
  "use strict";

  var KLASA = {
    HUMAN_CONFIRMED_OUTCOME: ["Ishod uneo advokat", "HUMAN_CONFIRMED"],
    LAWYER_VERIFIED_ARTIFACT: ["Overio advokat", "HUMAN_CONFIRMED"],
    HUMAN_MEMORY_NOTE: ["Beleška kolege — nije proverena činjenica", "HUMAN_NOTE"],
    HUMAN_CORRECTION: ["Ispravka advokata", "HUMAN_NOTE"],
    EXPLICIT_GRAPH_RELATION: ["Veza koju je upisao čovek — ne dokazuje uzrok", "HUMAN_NOTE"],
    SOURCE_CASE_FACT: ["Iz predmeta", "SOURCE_FACT"],
    AI_CANDIDATE_LESSON: ["Predlog AI — nepotvrđeno", "AI_ANALYSIS"],
    AI_WORK_PRODUCT: ["AI rad — nepotvrđeno", "AI_ANALYSIS"],
    UNKNOWN_LEGACY: ["Poreklo nepoznato", "UNKNOWN"],
  };
  var NEDOSTUPNO = "Nije dostupno — izvor nije pročitan. Ovo ne znači da podataka nema.";
  var GRESKA = {
    AUTH_REQUIRED: "Prijava više nije važeća. Iskustvo kancelarije se ne prikazuje.",
    RATE_LIMITED: "Previše zahteva. Pokušajte ponovo malo kasnije.",
    NETWORK_ERROR: "Server nije dostupan. Iskustvo kancelarije nije učitano.",
    INVALID_RESPONSE: "Odgovor servera nije ispravan. Iskustvo kancelarije se ne prikazuje.",
  };

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function niz(v) { return Array.isArray(v) ? v : []; }
  function normalizuj(s) { return tekst(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "dj"); }

  function alati(d) {
    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function oznaka(klasa) {
      var k = KLASA[klasa] || KLASA.UNKNOWN_LEGACY, s = el("span", "prov", k[0]);
      s.dataset.poreklo = k[1]; s.dataset.trust = KLASA[klasa] ? klasa : "UNKNOWN_LEGACY";
      return s;
    }
    function stavka(it, glavni, dodaci) {
      var li = el("li", "an-item"), red = el("div", "an-item__head");
      red.append(el("span", "an-item__text", glavni), oznaka(it.trust_class));
      li.append(red);
      niz(dodaci).forEach(function (x) { if (tekst(x)) li.append(el("span", "an-item__meta", x)); });
      if (it.validity === "STALE") li.append(el("span", "an-item__meta lb-zastarelo", "Možda zastarelo — proverite da li još važi."));
      li.dataset.trust = it.trust_class || "";
      return li;
    }
    return { el: el, oznaka: oznaka, stavka: stavka };
  }

  /* ── Znanje → Iskustvo kancelarije ── */
  function znanje(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); }, A = alati(d);
    var sesija = o.sesija, api = o.api, gen = 0, kontroler = null;
    var LISTE = ["lb-iskustvo", "lb-radovi", "lb-lekcije", "lb-memorija"];

    function stanje(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function ocisti() {
      gen++; if (kontroler) { kontroler.abort(); kontroler = null; }
      LISTE.forEach(function (id) { $(id).replaceChildren(); });
      ["lb-stanje", "lb-isk-stanje", "lb-rad-stanje", "lb-lek-stanje", "lb-mem-stanje"].forEach(function (id) { stanje(id, null); });
      $("lb-sadrzaj").hidden = true; $("lb-filter").value = "";
    }
    function sekcija(s, idStanja, prazno) {
      if (!s || s.state === "DEGRADED") { stanje(idStanja, "greska", NEDOSTUPNO); return false; }
      if (s.state === "EMPTY") { stanje(idStanja, "prazno", prazno); return false; }
      stanje(idStanja, null); return true;
    }

    async function ucitaj() {
      var moja = ++gen;
      if (kontroler) kontroler.abort();
      kontroler = new AbortController();
      LISTE.forEach(function (id) { $(id).replaceChildren(); });
      $("lb-sadrzaj").hidden = true;
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("lb-stanje", "greska", "Niste prijavljeni. Iskustvo kancelarije se ne prikazuje."); return; }
      var korisnik = s.korisnik;
      stanje("lb-stanje", "ucitavanje", "Učitavanje iskustva kancelarije…");
      var r = await api.get("/api/law-brain/znanje", { token: sesija.token(), signal: kontroler.signal,
        oblik: function (x) { return x && x.iskustvo && x.verifikovani_radovi && x.potvrdjene_lekcije && x.memorija_kancelarije; } });
      if (moja !== gen || sesija.stanje().korisnik !== korisnik) return;
      kontroler = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanje("lb-stanje", "greska", GRESKA[r.greska && r.greska.kod] || "Iskustvo kancelarije nije učitano zbog greške na serveru. Ovo ne znači da ga nema.");
        return;
      }
      stanje("lb-stanje", null);
      prikazi(r.podaci);
    }

    function prikazi(z) {
      var isk = z.iskustvo;
      if (sekcija(isk, "lb-isk-stanje", "Još nema završenih predmeta koje možete da vidite.")) {
        niz(isk.grupe).forEach(function (g) {
          var glavni = (tekst(g.tip) || "Vrsta nije navedena") + " — " + g.relevantnih + (g.relevantnih === 1 ? " završen predmet" : " završenih predmeta");
          var li = A.stavka({ trust_class: g.sa_ljudskim_ishodom ? "HUMAN_CONFIRMED_OUTCOME" : "SOURCE_CASE_FACT" }, glavni,
            niz(g.recenice).slice(1).concat(g.sa_ljudskim_ishodom ? [] : ["Ishod nije zabeležen ni za jedan — iskustvo bez ishoda."])
              .concat(g.sa_ljudskim_ishodom && g.mali_uzorak ? ["Mali uzorak — opis, ne pravilo."] : []));
          $("lb-iskustvo").append(li);
        });
      }
      var rad = z.verifikovani_radovi;
      if (sekcija(rad, "lb-rad-stanje", "Nema overenih radova. Nacrt postaje rad kancelarije tek kada ga advokat odobri.")) {
        niz(rad.stavke).forEach(function (a) {
          var at = a.attrs || {};
          $("lb-radovi").append(A.stavka(a, tekst(a.title) || "Nacrt",
            [tekst(a.predmet_naziv) ? "Predmet: " + tekst(a.predmet_naziv) : "", tekst(a.excerpt),
             a.state === "APPROVED_NOT_INDEXED" ? "Odobren, ali nije u pretrazi znanja (ocena kvaliteta ispod praga)." : "Odobren i dostupan pretrazi znanja.",
             at.tip ? "Vrsta: " + tekst(at.tip) : ""]));
        });
      }
      var lek = z.potvrdjene_lekcije;
      if (sekcija(lek, "lb-lek-stanje", "Nema potvrđenih lekcija.")) {
        niz(lek.stavke).forEach(function (x) { $("lb-lekcije").append(A.stavka(x, tekst(x.excerpt), [tekst(x.title)])); });
      }
      if (lek && lek.state !== "DEGRADED" && lek.kandidata) {
        var n = A.el("p", "field__help lb-kandidati", lek.kandidata + (lek.kandidata === 1 ? " predlog lekcije čeka" : " predloga lekcija čeka") + " vašu potvrdu — ne prikazuju se kao praksa kancelarije.");
        $("lb-lekcije").append(n);
      }
      var mem = z.memorija_kancelarije;
      var memPrazno = mem && mem.kancelarija === false ? "Niste član kancelarije — memorija kancelarije nije dostupna." : "Nema beleški kancelarije.";
      if (sekcija(mem, "lb-mem-stanje", memPrazno)) {
        niz(mem.stavke).forEach(function (b) {
          var at = b.attrs || {};
          $("lb-memorija").append(A.stavka(b, tekst(b.excerpt), [tekst(b.title),
            (at.sopstvena ? "Vaša beleška" : "Beleška kolege") + (at.potvrde_count ? " · potvrdilo: " + at.potvrde_count : "")]));
        });
        niz(mem.veze).forEach(function (v) { $("lb-memorija").append(A.stavka(v, tekst(v.excerpt), [])); });
      }
      $("lb-sadrzaj").hidden = false;
      filtriraj();
    }

    function filtriraj() {
      var q = normalizuj($("lb-filter").value);
      LISTE.forEach(function (id) {
        $(id).querySelectorAll(".an-item").forEach(function (li) { li.hidden = !!q && normalizuj(li.textContent).indexOf(q) === -1; });
      });
    }

    $("lb-filter").addEventListener("input", filtriraj);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });
    return { otvori: function () { ucitaj(); }, zatvori: function () {}, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxLawBrain = Object.freeze({ znanje: znanje, KLASA: KLASA });
})(window);
