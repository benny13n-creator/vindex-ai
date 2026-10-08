/* Vindex V2 NG — izmena predmeta, beleške i hronologija (NS005, CAP-005/006/007).
 *
 * Ugovori (api.py):
 *   PATCH /api/predmeti/{id}            polja: naziv, tip, opis, tuzilac, tuzeni,
 *                                       vrednost_spora (+ if_updated_at) → {ok, updated_at}
 *                                       409 = izmenjen u međuvremenu; 404 = nije dostupan
 *   POST  /api/predmeti/{id}/beleske    {sadrzaj} → {beleska}
 *   GET   /api/predmeti/{id}            beleske i hronologija dolaze uz detalj (bez novih zahteva)
 * `broj_predmeta`, `status` i `rizik` se ovde NE nude: broj server ne prima, status
 * ima svoj tok zatvaranja, rizik računa program. Brisanja nema.
 *
 * Posle uspešnog upisa predmet se PONOVO ČITA sa servera — ekran prikazuje ono
 * što je zapisano, ne ono što je poslato. Ništa se ne slika unapred.
 * Promena predmeta ili sesije poništava upis u letu i briše sve sa ekrana.
 */
(function (root) {
  "use strict";

  var POLJA = [
    { kljuc: "naziv", id: "izm-naziv" },
    { kljuc: "tip", id: "izm-tip" },
    { kljuc: "tuzilac", id: "izm-tuzilac" },
    { kljuc: "tuzeni", id: "izm-tuzeni" },
    { kljuc: "vrednost_spora", id: "izm-vrednost", broj: true },
    { kljuc: "opis", id: "izm-opis" },
  ];
  var brojFormat = new Intl.NumberFormat("sr-Latn-RS", { maximumFractionDigits: 2 });

  function brojIzTeksta(v) {
    var t = String(v || "").trim();
    if (!t) return null;
    var n = Number(t.replace(/\s/g, "").replace(/\./g, "").replace(",", "."));
    return Number.isFinite(n) && n >= 0 ? n : NaN;
  }
  function datum(iso) { var p = String(iso || "").split("-"); return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] + "." : String(iso || ""); }

  var PORUKE_ODBIJANJA = {
    AUTH_REQUIRED: "Prijava više nije važeća. Izmena nije sačuvana; prijavite se ponovo.",
    FORBIDDEN: "Server nije dozvolio izmenu. Ništa nije sačuvano.",
    NOT_FOUND: "Predmet nije dostupan. Ništa nije sačuvano.",
    BAD_REQUEST: "Server nije prihvatio podatke. Ništa nije sačuvano.",
    VALIDATION_ERROR: "Server nije prihvatio podatke. Ništa nije sačuvano.",
    RATE_LIMITED: "Previše zahteva. Ništa nije sačuvano; pokušajte ponovo malo kasnije.",
    CONFIG_ERROR: "Zahtev nije poslat. Ništa nije sačuvano.",
  };

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, osvezi = o.osvezi;
    var trenutni = null;          // {korisnik, id, predmet}
    var generacija = 0, kontroler = null, salje = false;
    var naCekanju = null;         // {korisnik, id, cilj, tekst} — poruka posle ponovnog čitanja

    function el(tag, cls, tekst) { var e = d.createElement(tag); if (cls) e.className = cls; if (tekst != null) e.textContent = tekst; return e; }
    function poruka(id, stanje, tekst) {
      var n = $(id);
      if (!stanje) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; }
      n.hidden = false; n.dataset.stanje = stanje; n.textContent = tekst;
    }
    function zakljucaj(da) {
      salje = da;
      $("izm-sacuvaj").disabled = da; $("izm-sacuvaj").textContent = da ? "Čuvanje…" : "Sačuvaj izmene";
      $("bel-dodaj").disabled = da; $("bel-dodaj").textContent = da ? "Dodavanje…" : "Dodaj belešku";
    }
    function zatvoriIzmenu() {
      $("izmena-forma").hidden = true;
      $("izmena-otvori").hidden = !trenutni;
      $("predmet-cinjenice").hidden = false;
      poruka("izm-poruka", null);
    }
    function ocisti() {
      generacija++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      trenutni = null;
      zakljucaj(false);
      $("izmena-forma").reset(); zatvoriIzmenu();
      $("izmena-otvori").hidden = true;
      poruka("pregled-poruka", null); poruka("bel-poruka", null);
      $("bel-forma").reset();
      $("bel-lista").replaceChildren(); $("bel-stanje").hidden = true; $("bel-stanje").textContent = "";
      $("hron-lista").replaceChildren(); $("hron-stanje").hidden = true; $("hron-stanje").textContent = "";
    }

    function stanjeListe(id, tekst, oznaka) { var s = $(id); s.hidden = !tekst; s.textContent = tekst || ""; if (oznaka) s.dataset.stanje = oznaka; else delete s.dataset.stanje; }

    function postavi(v) {
      ocisti();
      var s = sesija.stanje();
      trenutni = { korisnik: s.korisnik, id: v.predmet.id, predmet: v.predmet };
      $("izmena-otvori").hidden = false;
      // Beleške: null = nije učitano (nije isto što i „nema beleški").
      if (v.beleske === null || v.beleske === undefined) stanjeListe("bel-stanje", "Beleške nisu učitane uz predmet.", "greska");
      else if (!v.beleske.length) stanjeListe("bel-stanje", "Predmet još nema beleški.", "prazno");
      else v.beleske.forEach(function (b) {
        var li = el("li", "note");
        li.append(el("p", "note__text", b.tekst));
        if (b.datum) { var t = el("time", "note__meta", datum(b.datum)); t.dateTime = b.datum; li.append(t); }
        $("bel-lista").append(li);
      });
      if (v.hronologija === null || v.hronologija === undefined) stanjeListe("hron-stanje", "Hronologija nije učitana uz predmet.", "greska");
      else if (!v.hronologija.length) stanjeListe("hron-stanje", "Hronologija predmeta je prazna.", "prazno");
      else v.hronologija.forEach(function (h) {
        var li = el("li", "chrono__item");
        var t = el("time", "chrono__date", h.datum ? datum(h.datum) : "—"); if (/^\d{4}-\d{2}-\d{2}$/.test(h.datum)) t.dateTime = h.datum;
        var tekst = el("span", "chrono__text", h.dogadjaj);
        li.append(t, tekst);
        var meta = [h.akter, h.vaznost ? "važnost: " + h.vaznost : ""].filter(Boolean).join(" · ");
        if (meta) li.append(el("span", "chrono__meta", meta));
        $("hron-lista").append(li);
      });
      if (naCekanju && naCekanju.id === v.predmet.id && naCekanju.korisnik === s.korisnik) {
        poruka(naCekanju.cilj, "uspeh", naCekanju.tekst);
      }
      naCekanju = null;
    }

    function otvoriIzmenu() {
      if (!trenutni) return;
      var p = trenutni.predmet;
      $("izm-naziv").value = p.naziv; $("izm-tip").value = p.tip; $("izm-tuzilac").value = p.tuzilac; $("izm-tuzeni").value = p.tuzeni;
      $("izm-vrednost").value = p.vrednost !== null && p.vrednost !== undefined ? brojFormat.format(p.vrednost) : "";
      $("izm-opis").value = p.opis || "";
      poruka("pregled-poruka", null); poruka("izm-poruka", null);
      $("izmena-otvori").hidden = true;
      $("predmet-cinjenice").hidden = true;
      $("izmena-forma").hidden = false;
      $("izm-naziv").focus();
    }

    function izmene() {
      var p = trenutni.predmet, out = {};
      var vrednosti = { naziv: p.naziv, tip: p.tip, tuzilac: p.tuzilac, tuzeni: p.tuzeni, vrednost_spora: p.vrednost, opis: p.opis || "" };
      for (var i = 0; i < POLJA.length; i++) {
        var f = POLJA[i], v = $(f.id).value;
        if (f.broj) {
          var n = brojIzTeksta(v);
          if (Number.isNaN(n)) return { greska: "Vrednost spora mora biti broj (npr. 850.000 ili 850000,50).", polje: f.id };
          if (n !== (vrednosti.vrednost_spora === undefined ? null : vrednosti.vrednost_spora)) out.vrednost_spora = n;
        } else {
          v = v.trim();
          if (f.kljuc === "tip") v = (root.VxNovPredmet && v ? root.VxNovPredmet.tipZaSlanje(v) : v) || "";
          if (f.kljuc === "naziv" && !v) return { greska: "Naziv predmeta ne može biti prazan.", polje: f.id };
          if (v !== (vrednosti[f.kljuc] || "")) out[f.kljuc] = v;
        }
      }
      return { polja: out };
    }

    async function upis(vrsta, putanja, opcije, ciljPoruke, uspehTekst, nepoznatoTekst) {
      if (salje || !trenutni) return;
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN || s.korisnik !== trenutni.korisnik) { poruka(ciljPoruke, "greska", "Niste prijavljeni. Ništa nije sačuvano."); return; }
      var moja = ++generacija, id = trenutni.id, korisnik = trenutni.korisnik;
      kontroler = new AbortController();
      zakljucaj(true);
      poruka(ciljPoruke, "ucitavanje", vrsta === "izmena" ? "Izmene se čuvaju…" : "Beleška se dodaje…");
      opcije.token = sesija.token(); opcije.signal = kontroler.signal;
      var r = await api.send(putanja, opcije);
      if (moja !== generacija) return;                       // drugi predmet/sesija: odgovor se baca
      sesija.proveri();
      if (moja !== generacija || !trenutni || trenutni.id !== id || sesija.stanje().korisnik !== korisnik) return;
      kontroler = null;
      zakljucaj(false);
      if (r.ok) {
        naCekanju = { korisnik: korisnik, id: id, cilj: vrsta === "izmena" ? "pregled-poruka" : "bel-poruka", tekst: uspehTekst };
        osvezi();
        return;
      }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka(ciljPoruke, "nepoznato", nepoznatoTekst); return; }
      if (vrsta === "izmena" && g.kod === "CONFLICT") {
        poruka(ciljPoruke, "greska", "Predmet je u međuvremenu izmenjen na drugom mestu. Vaša izmena NIJE sačuvana. Zatvorite izmenu i otvorite je ponovo da vidite trenutne podatke.");
        return;
      }
      poruka(ciljPoruke, "greska", PORUKE_ODBIJANJA[g.kod] || "Server je odbio zahtev. Ništa nije sačuvano.");
    }

    $("izmena-otvori").addEventListener("click", otvoriIzmenu);
    $("izm-odustani").addEventListener("click", function () { if (!salje) { zatvoriIzmenu(); $("izmena-otvori").focus(); } });
    $("izmena-forma").addEventListener("submit", function (e) {
      e.preventDefault();
      if (salje || !trenutni) return;
      POLJA.forEach(function (f) { $(f.id).removeAttribute("aria-invalid"); });
      var r = izmene();
      if (r.greska) { $(r.polje).setAttribute("aria-invalid", "true"); poruka("izm-poruka", "greska", r.greska); $(r.polje).focus(); return; }
      if (!Object.keys(r.polja).length) { poruka("izm-poruka", "greska", "Nema izmena za čuvanje."); return; }
      var telo = r.polja;
      if (trenutni.predmet.azurirano) telo.if_updated_at = trenutni.predmet.azurirano;
      upis("izmena", "/api/predmeti/" + encodeURIComponent(trenutni.id), { metod: "PATCH", telo: telo }, "izm-poruka", "Izmene su sačuvane.",
        "Ishod nije poznat: veza je prekinuta ili server nije odgovorio ispravno, pa su izmene možda sačuvane. Zatvorite izmenu i proverite podatke pre nego što pokušate ponovo.");
    });
    $("bel-forma").addEventListener("submit", function (e) {
      e.preventDefault();
      if (salje || !trenutni) return;
      var t = $("bel-tekst").value.trim();
      if (!t) { $("bel-tekst").setAttribute("aria-invalid", "true"); poruka("bel-poruka", "greska", "Beleška je prazna."); $("bel-tekst").focus(); return; }
      $("bel-tekst").removeAttribute("aria-invalid");
      upis("beleska", "/api/predmeti/" + encodeURIComponent(trenutni.id) + "/beleske", { telo: { sadrzaj: t.slice(0, 8000) } }, "bel-poruka", "Beleška je dodata.",
        "Ishod nije poznat: beleška je možda dodata. Osvežite predmet i proverite pre nego što pokušate ponovo.");
    });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { naCekanju = null; ocisti(); } });

    return { postavi: postavi, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxRadPredmeta = Object.freeze({ napravi: napravi });
})(window);
