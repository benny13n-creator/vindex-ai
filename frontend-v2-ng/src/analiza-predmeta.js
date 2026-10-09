/* Vindex V2 NG — ANALIZA predmeta: profesionalni Genome, dokazi, protivrečnosti, rizici i spremnost (NS006, Task 10).
 *
 * Ugovori (routers/case_dna.py) — SAMO čitanje, bez modela i bez upisa (otvaranje ne troši kredit):
 *   GET /api/predmeti/{id}/genome-v2          → ugovor pg-1: metapodaci, identitet, cinjenice, stranke, pravna_pitanja,
 *        hronologija, strategija, nedostaje, metrike, nesigurnost, dokazi (graf), kontradikcije, spremnost.
 *        Svaka stavka nosi `poreklo` (SOURCE_FACT | HUMAN_CONFIRMED | DETERMINISTIC_DERIVATION | AI_ANALYSIS | UNKNOWN).
 *        Sekcija čiji izvor nije pročitan ima `stanje: DEGRADED` — prikazuje se kao nedostupna, NIKAD kao prazna.
 *   GET /api/predmeti/{id}/genome-v2/promene  → {stanje, trenutna_verzija, prethodna_verzija, nastala, promene[{oznaka, opis}],
 *        analiticke[], nepoznato[]} — deterministička razlika verzija; procene modela odvojeno.
 * Tuđ i nepostojeći predmet → isti 404. Pravni osnovi iz analize nisu potvrđeno pravo i tako se i prikazuju.
 * Nijedan broj se ne naziva verovatnoćom ishoda.
 */
(function (root) {
  "use strict";

  var POREKLO = {
    SOURCE_FACT: "Iz dokumenta", HUMAN_CONFIRMED: "Uneo advokat", DETERMINISTIC_DERIVATION: "Izračunato",
    AI_ANALYSIS: "Analiza (AI)", UNKNOWN: "Poreklo nepoznato",
  };
  var RELACIJA = { cinjenica_cinjenica: "činjenica — činjenica", cinjenica_norma: "činjenica — pravna norma" };
  var TEZINA = { kriticna: "kritična", vazna: "važna", manja: "manja" };
  var STANJE_K = { AKTIVNA: "aktivna", ZA_PREGLED: "traži vaš pregled", VISE_SE_NE_OPAZA: "više se ne opaža",
    RAZRESENA: "razrešena", ZAMENJENA: "zamenjena", NEPOTVRDJENA_TVRDNJAMA: "navodi je analiza; nije vezana za tvrdnje" };
  var POTPORA = { LOCIRANA_U_DOKUMENTU: "pronađeno u dokumentu", DOKUMENT_BEZ_LOKACIJE: "vezano za dokument, mesto nije pronađeno",
    BEZ_POTPORE: "bez dokumenta" };
  var SPREMNOST = { READY: "Spremno — nema otvorenih radnji", PARTIALLY_READY: "Delimično spremno", BLOCKED: "Blokirano",
    CRITICAL_GAP: "Kritičan nedostatak", UNKNOWN: "Nije moguće proceniti" };
  var KOMPLETNOST = { COMPLETE: "kompletna", PARTIAL: "delimična", DEGRADED: "delimično dostupna", UNKNOWN: "nije izračunata" };
  var STRATEGIJA = { primarni_cilj: "Primarni cilj", rezervni_plan: "Rezervni plan", scenario: "Scenario", strategija_osnova: "Strateški pravac",
    zakljucak: "Zaključak analize", argumenti_za: "U korist klijenta", argumenti_protiv: "Protiv klijenta", najslabija_tacka: "Najslabija tačka" };
  var GRESKA = {
    NOT_FOUND: "Predmet nije dostupan.", FORBIDDEN: "Predmet nije dostupan.",
    AUTH_REQUIRED: "Prijava više nije važeća. Analiza se ne prikazuje.",
    RATE_LIMITED: "Previše zahteva. Pokušajte ponovo malo kasnije.",
    NETWORK_ERROR: "Server nije dostupan. Analiza nije učitana.",
    INVALID_RESPONSE: "Odgovor servera nije ispravan. Analiza se ne prikazuje.",
  };

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function datum(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(tekst(iso)); return m ? m[3] + "." + m[2] + "." + m[1] + "." : ""; }
  function niz(v) { return Array.isArray(v) ? v : []; }

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, otvoriDokument = o.otvoriDokument || function () {};
    var trenutni = null, gen = 0, kontroler = null;

    function el(tag, cls, t) { var e = d.createElement(tag); if (cls) e.className = cls; if (t != null) e.textContent = t; return e; }
    function stanje(id, st, t) { var n = $(id); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function poreklo(p) { var s = el("span", "prov", POREKLO[p] || POREKLO.UNKNOWN); s.dataset.poreklo = POREKLO[p] ? p : "UNKNOWN"; return s; }
    function zivi(moja) { return moja === gen && !!trenutni && sesija.stanje().korisnik === trenutni.korisnik; }

    var KONTEJNERI = ["an-verzija", "an-promene", "an-analiticke", "an-sustina", "an-stranke", "an-cinjenice", "an-pitanja", "an-osnovi",
      "an-datumi", "an-nedostaje", "an-strategija", "an-nesigurnost", "an-dokazi-sazetak", "an-dokazi", "an-dokumenti",
      "an-kontr-aktivne", "an-kontr-pregled", "an-kontr-zatvorene", "an-spremnost", "an-metrike"];
    function ocistiPrikaz() {
      KONTEJNERI.forEach(function (id) { $(id).replaceChildren(); });
      ["an-promene-stanje", "an-genome-stanje", "an-dokazi-stanje", "an-kontr-stanje", "an-spremnost-stanje"].forEach(function (id) { stanje(id, null); });
      $("an-analiticke-blok").hidden = true; $("an-zatvorene-blok").hidden = true; $("an-metrike-blok").hidden = true;
      $("an-sadrzaj").hidden = true;
    }
    function ocisti() {
      gen++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      trenutni = null;
      ocistiPrikaz();
      stanje("an-stanje", null);
    }

    async function ucitaj() {
      if (!trenutni) return;
      var moja = ++gen, id = trenutni.id;
      if (kontroler) kontroler.abort();
      kontroler = new AbortController();
      ocistiPrikaz();
      var s = sesija.stanje();
      if (s.stanje !== sesija.STANJA.PRIJAVLJEN) { stanje("an-stanje", "greska", "Niste prijavljeni. Analiza se ne prikazuje."); return; }
      stanje("an-stanje", "ucitavanje", "Učitavanje analize predmeta…");
      var put = "/api/predmeti/" + encodeURIComponent(id) + "/genome-v2";
      var rez = await Promise.all([
        api.get(put, { token: sesija.token(), signal: kontroler.signal, oblik: function (x) { return x && x.metapodaci && x.dokazi && x.kontradikcije && x.spremnost; } }),
        api.get(put + "/promene", { token: sesija.token(), signal: kontroler.signal, oblik: function (x) { return x && typeof x.stanje === "string" && Array.isArray(x.promene); } }),
      ]);
      if (!zivi(moja) || trenutni.id !== id) return;
      kontroler = null;
      var g = rez[0], p = rez[1];
      if (!g.ok) {
        if (g.greska && g.greska.kod === "ABORTED") return;
        stanje("an-stanje", "greska", GRESKA[g.greska && g.greska.kod] || "Analiza nije učitana zbog greške na serveru. Ovo ne znači da analize nema.");
        return;
      }
      stanje("an-stanje", null);
      prikazi(g.podaci, p.ok ? p.podaci : null, p.ok ? null : p.greska);
    }

    /* ── crtanje ── */
    function stavkaListe(glavni, porekloKod, dodaci) {
      var li = el("li", "an-item");
      var red = el("div", "an-item__head");
      red.append(el("span", "an-item__text", glavni));
      if (porekloKod) red.append(poreklo(porekloKod));
      li.append(red);
      (dodaci || []).forEach(function (x) { if (x) li.append(x); });
      return li;
    }
    function meta(t) { return t ? el("p", "an-item__meta", t) : null; }
    function dugmeIzvora(dokId, naziv, lok) {
      if (!dokId) return null;
      var b = el("button", "text-btn an-src", "Izvor: " + (naziv || "dokument") + (lok && lok.strana_procena ? " · približno str. " + lok.strana_procena : ""));
      b.type = "button";
      b.addEventListener("click", function () { otvoriDokument(dokId); });
      return b;
    }
    function sekcijaStanje(id, sek, prazno) {
      if (!sek || sek.stanje === "DEGRADED") { stanje(id, "greska", "Nije dostupno — izvor podataka trenutno nije pročitan. Ovo ne znači da podataka nema."); return true; }
      if (sek.stanje === "UNKNOWN") { stanje(id, "nepoznato", "Analiza predmeta još nije izračunata."); return true; }
      if (sek.stanje === "INVALID") { stanje(id, "nepoznato", "Deo analize nije u ispravnom obliku i nije prikazan."); return true; }
      if (sek.stanje === "EMPTY" && prazno) { stanje(id, "prazno", prazno); return true; }
      return false;
    }

    function prikazi(g, pr, prGreska) {
      var m = g.metapodaci || {};
      var dokNaziv = {};
      niz(g.dokazi && g.dokazi.dokumenti).forEach(function (x) { dokNaziv[x.id] = x.naziv; });

      /* Verzija + šta se promenilo */
      var v = $("an-verzija");
      v.textContent = m.genome_verzija ? "Analiza v" + m.genome_verzija + (m.osvezeno ? " · osvežena " + datum(m.osvezeno) : "") +
        " · kompletnost: " + (KOMPLETNOST[m.kompletnost] || "nepoznata") : "Analiza još nije izračunata";
      if (!pr) stanje("an-promene-stanje", "greska", "Promene nisu učitane" + (prGreska && prGreska.kod === "NETWORK_ERROR" ? " — server nije dostupan." : "."));
      else if (pr.stanje === "PRVA_VERZIJA") stanje("an-promene-stanje", "prazno", "Ovo je prva verzija analize — nema sa čim da se uporedi.");
      else if (pr.stanje === "DEGRADED") stanje("an-promene-stanje", "greska", "Istorija verzija trenutno nije dostupna.");
      else if (pr.stanje === "UNKNOWN") stanje("an-promene-stanje", "nepoznato", niz(pr.nepoznato).map(function (x) { return tekst(x.razlog); }).join(" ") || "Promene nisu poznate.");
      else {
        if (!pr.promene.length) stanje("an-promene-stanje", "prazno", "Nema strukturnih promena od prethodne verzije (v" + pr.prethodna_verzija + ").");
        pr.promene.forEach(function (x) {
          var li = el("li", "an-change"); li.dataset.oznaka = tekst(x.oznaka);
          li.append(el("span", "an-change__mark", tekst(x.oznaka)), el("span", null, tekst(x.opis)));
          $("an-promene").append(li);
        });
        niz(pr.nepoznato).forEach(function (x) { $("an-promene").append(stavkaListe("Nije poznato: " + tekst(x.razlog), null)); });
        if (niz(pr.analiticke).length) {
          $("an-analiticke-blok").hidden = false;
          pr.analiticke.forEach(function (x) { $("an-analiticke").append(stavkaListe(tekst(x.opis), "AI_ANALYSIS")); });
        }
      }

      /* GENOME */
      if (!sekcijaStanje("an-genome-stanje", g.pravna_pitanja, null)) stanje("an-genome-stanje", null);
      var id = g.identitet || {};
      if (id.pravni_identitet && id.pravni_identitet.vrednost) $("an-sustina").append(stavkaListe(id.pravni_identitet.vrednost, id.pravni_identitet.poreklo));
      niz(g.pravna_pitanja && g.pravna_pitanja.stavke).forEach(function (s) {
        if (s.vrsta === "sustina_spora") $("an-sustina").append(stavkaListe(s.vrednost, s.poreklo, [meta(s.naslov)]));
      });
      niz(g.stranke && g.stranke.stavke).forEach(function (s) {
        $("an-stranke").append(stavkaListe(s.vrednost, s.poreklo, [meta(s.uloga ? s.uloga.replace(/_/g, " ") : "uloga nije navedena")]));
      });
      var pouzdane = niz(g.cinjenice && g.cinjenice.stavke).filter(function (s) { return s.poreklo === "SOURCE_FACT" || s.poreklo === "HUMAN_CONFIRMED"; });
      pouzdane.slice(0, 12).forEach(function (s) {
        $("an-cinjenice").append(stavkaListe(s.vrednost, s.poreklo, [dugmeIzvora(s.dokument_id, dokNaziv[s.dokument_id], s.lokacija)]));
      });
      if (!pouzdane.length) $("an-cinjenice").append(el("li", "list-state", g.cinjenice && g.cinjenice.stanje === "DEGRADED"
        ? "Tvrdnje nisu pročitane." : "Nema tvrdnji iz dokumenata ni tvrdnji koje je uneo advokat."));
      niz(g.pravna_pitanja && g.pravna_pitanja.stavke).forEach(function (s) {
        if (s.vrsta !== "sustina_spora") $("an-pitanja").append(stavkaListe(s.vrednost, s.poreklo, [meta(s.naslov)]));
      });
      niz(g.pravna_pitanja && g.pravna_pitanja.pravni_osnovi_neprovereni).forEach(function (s) {
        var sig = [];
        if (!s.naziv_zakona_prepoznat) sig.push("naziv propisa nije prepoznat");
        if (!s.broj_clana_moguc) sig.push("broj člana je van uobičajenog opsega");
        $("an-osnovi").append(stavkaListe(s.vrednost, s.poreklo, [meta("Predlog analize — nije potvrđeno u izvorima prava" + (sig.length ? " · " + sig.join(" · ") : ""))]));
      });
      niz(g.hronologija && g.hronologija.stavke).forEach(function (s) {
        $("an-datumi").append(stavkaListe((s.datum ? datum(s.datum) + " — " : "Datum nije ispravan — ") + s.vrednost, s.poreklo));
      });
      niz(g.nedostaje && g.nedostaje.stavke).forEach(function (s) { $("an-nedostaje").append(stavkaListe(s.vrednost, s.poreklo, [meta(s.opis)])); });
      niz(g.strategija && g.strategija.stavke).forEach(function (s) {
        var t = s.vrsta === "scenario" && s.vrednost ? tekst(s.vrednost.uslov) + " → " + tekst(s.vrednost.odgovor) : tekst(s.vrednost);
        $("an-strategija").append(stavkaListe(t, s.poreklo, [meta(STRATEGIJA[s.vrsta] || ""),
          s.lokacija && s.lokacija.dokument_id ? dugmeIzvora(s.lokacija.dokument_id, dokNaziv[s.lokacija.dokument_id], null) : null]));
      });
      niz(g.nesigurnost).forEach(function (n) { $("an-nesigurnost").append(stavkaListe(tekst(n.opis) + (n.kolicina ? " (" + n.kolicina + ")" : ""), null)); });

      /* DOKAZI */
      var dz = g.dokazi || {};
      if (!sekcijaStanje("an-dokazi-stanje", dz, "Predmet još nema tvrdnji.")) {
        var sz = dz.sazetak || {};
        $("an-dokazi-sazetak").textContent = sz.tvrdnji + " tvrdnji · " + sz.locirano + " pronađeno u dokumentu · " + sz.bez_potpore + " bez dokumenta · " +
          sz.procenjene_snage + " sa procenom snage" + (sz.u_protivrecnosti === null ? " · protivrečnosti nepoznate" : " · " + sz.u_protivrecnosti + " u protivrečnosti");
        niz(dz.tvrdnje).forEach(function (t) {
          var info = [POTPORA[t.potpora] || "", t.pravni_element ? "element: " + t.pravni_element : "pravni element nije naveden",
            t.snaga_procenjena ? "snaga: " + t.snaga : "snaga nije procenjena",
            t.protivrecnosti === null ? "protivrečnost nepoznata" : (t.protivrecnosti.length ? "u protivrečnosti" : "")].filter(Boolean).join(" · ");
          var li = stavkaListe(t.vrednost, t.poreklo, [meta(info), dugmeIzvora(t.dokument_id, dokNaziv[t.dokument_id], t.lokacija)]);
          li.dataset.tvrdnja = t.id;
          $("an-dokazi").append(li);
        });
      }
      niz(dz.dokumenti).forEach(function (x) {
        var k = x.klasifikacija || {};
        var opis = k.stanje === "NEUSPESNA" ? "klasifikacija nije uspela" : k.stanje === "NIJE_KLASIFIKOVAN" ? "nije klasifikovan" : tekst(k.tip).replace(/_/g, " ");
        var li = stavkaListe(x.naziv || "Dokument", null, [meta(opis + " · tvrdnji: " + x.broj_tvrdnji), dugmeIzvora(x.id, x.naziv, null)]);
        li.dataset.klasifikacija = tekst(k.stanje);
        $("an-dokumenti").append(li);
      });

      /* PROTIVREČNOSTI */
      var k = g.kontradikcije || {};
      function kontr(x) {
        var info = [x.relacija ? RELACIJA[x.relacija] : "", x.tezina ? "težina: " + TEZINA[x.tezina] : "", STANJE_K[x.stanje] || ""].filter(Boolean).join(" · ");
        var dodaci = [meta(info)];
        if (x.opis) dodaci.push(meta(x.opis));
        var ul = el("ul", "an-sub");
        niz(x.ucesnici).forEach(function (u) {
          ul.append(stavkaListe(u.tvrdnja || "Tvrdnja nije dostupna", u.poreklo, [dugmeIzvora(u.dokument_id, dokNaziv[u.dokument_id], u.lokacija)]));
        });
        if (ul.childNodes.length) dodaci.push(ul);
        if (niz(x.bez_izvora).length) dodaci.push(meta("Bez dokumenta: " + x.bez_izvora.length + " učesnik(a) — izvor nije poznat i ne pogađa se."));
        var li = stavkaListe(x.sporna_tacka || "Sporna tačka", x.poreklo, dodaci);
        li.dataset.kontradikcija = x.id; li.dataset.stanje = x.stanje;
        return li;
      }
      if (!sekcijaStanje("an-kontr-stanje", k, "Nema aktivnih protivrečnosti.")) {
        if (!niz(k.aktivne).length) stanje("an-kontr-stanje", "prazno", "Nema aktivnih protivrečnosti.");
        niz(k.aktivne).forEach(function (x) { $("an-kontr-aktivne").append(kontr(x)); });
        niz(k.za_pregled).forEach(function (x) { $("an-kontr-pregled").append(kontr(x)); });
        if (niz(k.zatvorene).length) { $("an-zatvorene-blok").hidden = false; k.zatvorene.forEach(function (x) { $("an-kontr-zatvorene").append(kontr(x)); }); }
      }

      /* RIZICI I SPREMNOST */
      var sp = g.spremnost || {};
      niz(sp.dimenzije).forEach(function (x) {
        var dt = el("dt", null, x.naziv), dd = el("dd", "an-dim");
        dd.dataset.dim = x.kljuc; dd.dataset.stanje = x.stanje;
        dd.append(el("span", "an-dim__value", x.stanje !== "OK" ? "Nije dostupno — izvor nije pročitan" : vrednostDimenzije(x)));
        dd.append(el("span", "an-item__meta", x.znacenje));
        niz(x.faktori).forEach(function (f) { dd.append(el("span", "an-item__meta", "· " + f)); });
        $("an-spremnost").append(dt, dd);
      });
      if (sp.stanje === "DEGRADED") stanje("an-spremnost-stanje", "greska", "Deo pokazatelja nije dostupan jer izvor nije pročitan.");
      if (niz(g.metrike).length) {
        $("an-metrike-blok").hidden = false;
        g.metrike.forEach(function (x) {
          $("an-metrike").append(stavkaListe(tekst(x.kljuc) + ": " + tekst(x.vrednost), x.klasa === "deterministic" ? "DETERMINISTIC_DERIVATION" : "AI_ANALYSIS",
            [meta(x.znacenje + " — " + x.napomena)]));
        });
      }
      $("an-sadrzaj").hidden = false;
    }

    function vrednostDimenzije(x) {
      var v = x.vrednost;
      switch (x.kljuc) {
        case "pokrivenost_procene": return v.procenjeno + " od " + v.ukupno + " tvrdnji ima procenu dokaza";
        case "nedostajuci_tipovi": return v.length ? v.map(function (t) { return tekst(t).replace(/_/g, " "); }).join(", ") : "nijedan";
        case "rocista": return v.u_narednih_30_dana + " u narednih 30 dana · " + v.u_narednih_7_dana + " u narednih 7 dana · " + v.propustena + " propušteno";
        case "procesni_rizik": return tekst(v) + " (pravilo, nije procena ishoda)";
        case "kontradikcije": return v.aktivnih + " aktivnih (" + v.kriticnih + " kritičnih) · " + v.za_pregled + " traži pregled";
        case "operativna_spremnost": return SPREMNOST[v] || tekst(v);
        default: return tekst(typeof v === "object" ? JSON.stringify(v) : v);
      }
    }

    function postavi(predmet, aktivan) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) { if (aktivan) aktiviraj(); return; }
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik, ucitano: false };
      if (aktivan) aktiviraj();
    }
    function aktiviraj() {
      if (!trenutni || trenutni.ucitano) return;
      trenutni.ucitano = true;
      ucitaj();
    }

    d.querySelectorAll("[data-an-skok]").forEach(function (b) {
      b.addEventListener("click", function () { var h = $(b.dataset.anSkok); if (h) { h.scrollIntoView({ block: "start" }); h.focus({ preventScroll: true }); } });
    });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });

    return { postavi: postavi, aktiviraj: aktiviraj, ocisti: ocisti, osvezi: function () { if (trenutni) { trenutni.ucitano = true; ucitaj(); } },
             zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxAnalizaPredmeta = Object.freeze({ napravi: napravi });
})(window);
