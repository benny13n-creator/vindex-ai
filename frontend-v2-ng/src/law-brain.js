/* Vindex V2 NG — LAW BRAIN: iskustvo kancelarije (NS008).
 *
 * Ugovori (routers/law_brain.py) — čitanje BEZ modela i BEZ kredita:
 *   GET /api/law-brain/znanje → {iskustvo{state, grupe[{tip, relevantnih, sa_ljudskim_ishodom, po_ishodu, recenice,
 *        mali_uzorak}]}, verifikovani_radovi{state, stavke[]}, potvrdjene_lekcije{state, stavke[], kandidata},
 *        memorija_kancelarije{state, stavke[], veze[]}, napomena, data_quality}
 *   Stavka = Law Brain item: {id, trust_class, validity, title, excerpt, source_ref, attrs, state, predmet_id}.
 * Predmet → Analiza (Task 14): vidi `predmet()` ispod.
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


  /* ── Predmet → Analiza → Iskustvo kancelarije ──
   *   GET  /api/law-brain/predmeti/{id}          → sekcije similar_cases, verified_artifacts, confirmed_lessons,
   *        relevant_human_memory, descriptive_outcomes, data_quality (bez modela i kredita; tuđ = 404).
   *   POST /api/law-brain/predmeti/{id}/sinteza  → SAMO na izričit klik; {stanje, tvrdnje[{tekst, vrsta, source_refs}],
   *        odbaceno, napomena}. NEMA_OSNOVA = model nije pozvan; 503 = analiza nije izvršena (kredit nije potrošen).
   */
  var VRSTA_TVRDNJE = { iskustvo: "Iskustvo kancelarije", ishod: "Ishod uneo advokat", overen_rad: "Overen rad",
    neproverena_beleska: "Beleška — nije proverena" };
  function predmet(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); }, A = alati(d);
    var sesija = o.sesija, api = o.api, trenutni = null, gen = 0, kontroler = null, genS = 0, kS = null, salje = false;
    var LISTE = ["lbp-slicni", "lbp-radovi", "lbp-lekcije", "lbp-ishodi", "lbp-memorija", "lbp-sinteza"];

    function stanje(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zivi(moja) { return moja === gen && !!trenutni && sesija.stanje().korisnik === trenutni.korisnik; }
    function ocistiPrikaz() {
      LISTE.forEach(function (id) { $(id).replaceChildren(); });
      ["lbp-stanje", "lbp-sl-stanje", "lbp-sl-napomena", "lbp-rad-stanje", "lbp-lek-stanje", "lbp-is-stanje", "lbp-mem-stanje", "lbp-sinteza-stanje"]
        .forEach(function (id) { stanje(id, null); });
      $("lbp-sadrzaj").hidden = true; $("lbp-prazno").hidden = true;
      $("lbp-analiziraj").disabled = false; $("lbp-analiziraj").textContent = "Analiziraj iskustvo kancelarije";
    }
    function ocisti() {
      gen++; genS++; salje = false;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      if (kS) { kS.abort(); kS = null; }
      trenutni = null; ocistiPrikaz();
    }
    function sekcija(s, idStanja, prazno) {
      if (!s || s.state === "DEGRADED") { stanje(idStanja, "greska", NEDOSTUPNO); return false; }
      if (s.state === "EMPTY") { stanje(idStanja, "prazno", prazno); return false; }
      stanje(idStanja, null); return true;
    }

    async function ucitaj() {
      if (!trenutni) return;
      var moja = ++gen, id = trenutni.id;
      if (kontroler) kontroler.abort();
      kontroler = new AbortController();
      ocistiPrikaz();
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("lbp-stanje", "greska", "Niste prijavljeni. Iskustvo kancelarije se ne prikazuje."); return; }
      stanje("lbp-stanje", "ucitavanje", "Učitavanje iskustva kancelarije…");
      var r = await api.get("/api/law-brain/predmeti/" + encodeURIComponent(id), { token: sesija.token(), signal: kontroler.signal,
        oblik: function (x) { return x && x.similar_cases && x.verified_artifacts && x.confirmed_lessons && x.descriptive_outcomes && x.data_quality; } });
      if (!zivi(moja) || trenutni.id !== id) return;
      kontroler = null;
      if (!r.ok) {
        if (r.greska && r.greska.kod === "ABORTED") return;
        stanje("lbp-stanje", "greska", r.greska && (r.greska.kod === "NOT_FOUND" || r.greska.kod === "FORBIDDEN") ? "Predmet nije dostupan."
          : GRESKA[r.greska && r.greska.kod] || "Iskustvo kancelarije nije učitano zbog greške na serveru. Ovo ne znači da ga nema.");
        return;
      }
      stanje("lbp-stanje", null);
      prikazi(r.podaci);
    }

    function prikazi(k) {
      var ima = false;
      if (sekcija(k.similar_cases, "lbp-sl-stanje", "Nema ranijih završenih predmeta sličnih ovom među predmetima koje možete da vidite.")) {
        niz(k.similar_cases.stavke).forEach(function (s) {
          var is = s.ishod || {};
          ima = true;
          $("lbp-slicni").append(A.stavka({ trust_class: "SOURCE_CASE_FACT" }, tekst(s.naziv) || "Raniji predmet", [tekst(s.zasto),
            is.status === "RECORDED" ? "Ishod (uneo advokat): " + tekst(is.ishod) : is.status === "OUTCOME_UNKNOWN" ? "Ishod nije zabeležen." : "",
            s.sopstveni === false ? "Delegiran vam predmet kolege." : ""]));
        });
        stanje("lbp-sl-napomena", "info", tekst(k.similar_cases.napomena));
      }
      if (sekcija(k.verified_artifacts, "lbp-rad-stanje", "Nema overenih radova za ovaj ni slične predmete.")) {
        niz(k.verified_artifacts.stavke).forEach(function (a) { ima = true; $("lbp-radovi").append(A.stavka(a, tekst(a.title) || "Nacrt", [tekst(a.excerpt)])); });
      }
      if (sekcija(k.confirmed_lessons, "lbp-lek-stanje", "Nema potvrđenih lekcija za ovu vrstu predmeta.")) {
        niz(k.confirmed_lessons.stavke).forEach(function (x) { ima = true; $("lbp-lekcije").append(A.stavka(x, tekst(x.excerpt), [])); });
      }
      var dsc = k.descriptive_outcomes;
      if (sekcija(dsc, "lbp-is-stanje", "Slični predmeti nemaju ljudski zabeležen ishod — nema šta da se opiše.")) {
        niz(dsc.recenice).forEach(function (rec) { $("lbp-ishodi").append(A.stavka({ trust_class: "HUMAN_CONFIRMED_OUTCOME" }, rec, [])); });
        if (dsc.mali_uzorak) $("lbp-ishodi").append(A.el("p", "field__help", "Mali uzorak — opis prošlih predmeta, ne pravilo i ne predviđanje."));
      }
      var mem = k.relevant_human_memory;
      if (sekcija(mem, "lbp-mem-stanje", mem && mem.kancelarija === false ? "Niste član kancelarije." : "Nema beleški kancelarije za ovaj predmet.")) {
        niz(mem.stavke).forEach(function (b) { $("lbp-memorija").append(A.stavka(b, tekst(b.excerpt), [tekst(b.title)])); });
        niz(mem.veze).forEach(function (v) { $("lbp-memorija").append(A.stavka(v, tekst(v.excerpt), [])); });
      }
      $("lbp-prazno").hidden = ima;
      $("lbp-sadrzaj").hidden = false;
    }

    async function analiziraj() {
      if (!trenutni || salje) return;
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("lbp-sinteza-stanje", "greska", "Niste prijavljeni. Analiza nije pokrenuta."); return; }
      var moja = ++genS, id = trenutni.id, korisnik = trenutni.korisnik;
      salje = true; kS = new AbortController();
      $("lbp-analiziraj").disabled = true; $("lbp-analiziraj").textContent = "Analiza u toku…";
      $("lbp-sinteza").replaceChildren();
      stanje("lbp-sinteza-stanje", "ucitavanje", "Analiza iskustva kancelarije…");
      var r = await api.send("/api/law-brain/predmeti/" + encodeURIComponent(id) + "/sinteza", { token: sesija.token(), signal: kS.signal,
        oblik: function (x) { return x && typeof x.stanje === "string" && Array.isArray(x.tvrdnje); } });
      if (moja !== genS || !trenutni || trenutni.id !== id || sesija.stanje().korisnik !== korisnik) return;
      kS = null; salje = false;
      $("lbp-analiziraj").disabled = false; $("lbp-analiziraj").textContent = "Analiziraj iskustvo kancelarije";
      if (!r.ok) {
        var g = r.greska || {};
        if (g.kod === "ABORTED" && !g.ishodNepoznat) return;
        /* 503 ove rute = model nije izvršen i kredit NIJE potrošen (routers/law_brain.py); ostali 5xx/prekid = ishod nepoznat. */
        stanje("lbp-sinteza-stanje", "greska", g.ishodNepoznat && r.status !== 503 ? "Ishod analize nije poznat. Ne pokrećite je ponovo dok ne osvežite stranicu."
          : g.kod === "FORBIDDEN" ? "Analiza iskustva nije dostupna za vaš nalog."
          : g.kod === "RATE_LIMITED" ? "Previše zahteva. Pokušajte ponovo malo kasnije."
          : "Analiza nije izvršena. Kredit nije potrošen.");
        return;
      }
      var x = r.podaci;
      if (x.stanje === "NEMA_OSNOVA") { stanje("lbp-sinteza-stanje", "prazno", tekst(x.poruka) || "Nema proverenog iskustva — analiza nije pokrenuta."); return; }
      if (!x.tvrdnje.length) { stanje("lbp-sinteza-stanje", "prazno", "Nijedna tvrdnja analize nije prošla proveru izvora — ništa se ne prikazuje."); return; }
      stanje("lbp-sinteza-stanje", "info", tekst(x.napomena) + (x.odbaceno ? " Odbačeno tvrdnji bez izvora: " + x.odbaceno + "." : ""));
      x.tvrdnje.forEach(function (t) {
        var li = A.el("li", "an-item"), red = A.el("div", "an-item__head");
        var oz = A.el("span", "prov", VRSTA_TVRDNJE[t.vrsta] || "Analiza (AI)"); oz.dataset.poreklo = "AI_ANALYSIS";
        red.append(A.el("span", "an-item__text", tekst(t.tekst)), oz);
        li.append(red, A.el("span", "an-item__meta", "AI sinteza · izvori: " + niz(t.refs).join(", ")));
        li.dataset.vrsta = t.vrsta || "";
        $("lbp-sinteza").append(li);
      });
    }

    function postavi(p, aktivan) {
      if (trenutni && trenutni.id === p.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: p.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() { if (!trenutni || trenutni.ucitano) return; trenutni.ucitano = true; ucitaj(); }

    $("lbp-analiziraj").addEventListener("click", analiziraj);
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });
    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxLawBrain = Object.freeze({ znanje: znanje, predmet: predmet, KLASA: KLASA });
})(window);
