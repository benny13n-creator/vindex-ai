/* Vindex V2 NG — životni ciklus jednog predmeta i njegovog dokumenta (samo čitanje).
 *
 * Isti ugovor kao src/live.js, za predmet:
 *   • svaka promena sesije, predmeta ili zatvaranje ODMAH briše podatke iz
 *     memorije i sa ekrana, otkazuje zahtev u letu i tek onda učitava novo;
 *   • odgovor koji je zakasnio (drugi predmet, druga sesija) se BACA;
 *   • sesija se ponovo čita pre primene rezultata;
 *   • dokument ima sopstvenu generaciju: promena predmeta ili dokumenta
 *     poništava tekst prethodnog dokumenta pre nego što stigne novi.
 *
 * prikazi(v) dobija: {vrsta:"predmet-stanje", stanje, greska?} |
 *   {vrsta:"predmet", predmet, dokumenti, klijenti} |
 *   {vrsta:"dokument-stanje", dokId, stanje, greska?} | {vrsta:"dokument", dokId, tekst, dostupan}
 */
(function (root) {
  "use strict";

  var S = root.VxSesija ? root.VxSesija.STANJA : null;

  function napravi(opcije) {
    var sesija = opcije.sesija, izvor = opcije.izvor, prikazi = opcije.prikazi;
    var predmetId = null, podaci = null, kontroler = null, generacija = 0;
    var dokId = null, dokKontroler = null, dokGeneracija = 0;

    function ponistiDokument() {
      dokGeneracija++;
      if (dokKontroler) { dokKontroler.abort(); dokKontroler = null; }
      dokId = null;
    }
    function ponisti() {
      generacija++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      podaci = null;
      ponistiDokument();
    }

    function bezSesije(s) {
      if (!S) return "greska-sesije";
      if (s.stanje === S.UCITAVANJE) return "ucitavanje";
      if (s.stanje === S.NEPRIJAVLJEN) return "bez-prijave";
      if (s.stanje === S.ISTEKLA) return "istekla";
      if (s.stanje === S.GRESKA) return "greska-sesije";
      return null;
    }

    async function ucitaj() {
      if (predmetId === null) return;
      var s = sesija.stanje(), bez = bezSesije(s);
      if (bez) { prikazi({ vrsta: "predmet-stanje", stanje: bez }); return; }
      var moja = ++generacija, id = predmetId;
      if (kontroler) kontroler.abort();
      kontroler = new AbortController();
      var signal = kontroler.signal, korisnik = s.korisnik;
      prikazi({ vrsta: "predmet-stanje", stanje: "ucitavanje" });
      var r;
      try { r = await izvor.ucitajPredmet(id, sesija.token(), signal); }
      catch (e) { r = { ok: false, greska: { kod: "INVALID_RESPONSE" } }; }
      if (moja !== generacija || signal.aborted) return;
      sesija.proveri();
      if (moja !== generacija) return;
      kontroler = null;
      if (!r || !r.ok) {
        var g = (r && r.greska) || { kod: "INVALID_RESPONSE" };
        if (g.kod === "ABORTED") return;
        podaci = null;
        prikazi({ vrsta: "predmet-stanje", stanje: "greska", greska: g });
        return;
      }
      podaci = { korisnik: korisnik, id: id, predmet: r.predmet, dokumenti: r.dokumenti, klijenti: r.klijenti };
      prikazi({ vrsta: "predmet", predmet: r.predmet, dokumenti: r.dokumenti, klijenti: r.klijenti });
    }

    function otvori(id) {
      if (id === predmetId && (podaci || kontroler)) return;   // isti predmet je već tu ili se učitava
      ponisti();
      predmetId = id;
      prikazi({ vrsta: "predmet-ocisti" });
      ucitaj();
    }

    function zatvori() {
      ponisti();
      predmetId = null;
      prikazi({ vrsta: "predmet-ocisti" });
    }

    async function otvoriDokument(id) {
      if (!podaci || !podaci.dokumenti.some(function (d) { return d.id === id; })) return;
      ponistiDokument();
      dokId = id;
      var moja = ++dokGeneracija, mojPredmet = generacija;
      dokKontroler = new AbortController();
      var signal = dokKontroler.signal;
      prikazi({ vrsta: "dokument-stanje", dokId: id, stanje: "ucitavanje" });
      var r;
      try { r = await izvor.ucitajTekst(podaci.id, id, sesija.token(), signal); }
      catch (e) { r = { ok: false, greska: { kod: "INVALID_RESPONSE" } }; }
      if (moja !== dokGeneracija || mojPredmet !== generacija || signal.aborted) return;
      sesija.proveri();
      if (moja !== dokGeneracija || mojPredmet !== generacija) return;
      dokKontroler = null;
      if (!r || !r.ok) {
        var g = (r && r.greska) || { kod: "INVALID_RESPONSE" };
        if (g.kod === "ABORTED") return;
        prikazi({ vrsta: "dokument-stanje", dokId: id, stanje: "greska", greska: g });
        return;
      }
      prikazi({ vrsta: "dokument", dokId: id, tekst: r.tekst, dostupan: r.dostupan });
    }

    function naPromenuSesije(novo, staro) {
      var isti = S && novo.stanje === S.PRIJAVLJEN && staro.stanje === S.PRIJAVLJEN && novo.korisnik === staro.korisnik;
      if (isti || predmetId === null) { if (!isti) ponisti(); return; }
      ponisti();
      prikazi({ vrsta: "predmet-ocisti" });
      var bez = bezSesije(novo);
      if (bez) prikazi({ vrsta: "predmet-stanje", stanje: bez });
      else ucitaj();
    }
    var odjavi = sesija.naPromenu(naPromenuSesije);

    return {
      otvori: otvori,
      zatvori: zatvori,
      otvoriDokument: otvoriDokument,
      zatvoriDokument: function () { ponistiDokument(); prikazi({ vrsta: "dokument-ocisti" }); },
      podaci: function () { return podaci; },
      zaustavi: function () { odjavi(); ponisti(); },
    };
  }

  root.VxDetalj = Object.freeze({ napravi: napravi });
})(window);
