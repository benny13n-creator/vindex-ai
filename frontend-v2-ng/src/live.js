/* Vindex V2 NG — životni ciklus LIVE podataka.
 *
 * Povezuje tri stvari i ništa više:
 *   VxSesija (ko je prijavljen)  →  izvor podataka (window.VxLiveIzvor)  →  prikaz
 *
 * REDOSLED pri svakoj promeni sesije je obavezan:
 *   1. otkaži zahtev u letu i ODBACI podatke prethodne sesije (memorija + ekran);
 *   2. prikaži stanje nove sesije;
 *   3. tek onda, ako je sesija ispravna, učitaj podatke NOVE sesije.
 * Tako podaci korisnika A nikad nisu na ekranu dok se učitava korisnik B.
 *
 * Izvor podataka je zamenljiv (`window.VxLiveIzvor.ucitaj(token, signal)` →
 * `{ ok, predmeti, ukupno }` ili `{ ok:false, greska }`). Dok izvor ne postoji,
 * LIVE pošteno kaže da nije povezan — nikad ne prikazuje primere.
 */
(function (root) {
  "use strict";

  var S = root.VxSesija ? root.VxSesija.STANJA : null;

  function napravi(opcije) {
    var sesija = opcije.sesija;
    var prikazi = opcije.prikazi;
    var izvor = opcije.izvor || null;

    var podaci = null;          // { korisnik, predmeti, ukupno } ili null
    var kontroler = null;       // AbortController zahteva u letu
    var generacija = 0;         // raste pri svakom novom učitavanju / poništavanju

    function ponisti() {
      generacija++;
      if (kontroler) { kontroler.abort(); kontroler = null; }
      podaci = null;
    }

    function stanjeBezPodataka(s) {
      if (!S) return { vrsta: "greska-sesije" };
      if (s.stanje === S.UCITAVANJE) return { vrsta: "ucitavanje" };
      if (s.stanje === S.NEPRIJAVLJEN) return { vrsta: "bez-prijave" };
      if (s.stanje === S.ISTEKLA) return { vrsta: "istekla" };
      if (s.stanje === S.GRESKA) return { vrsta: "greska-sesije" };
      return null;
    }

    async function ucitaj() {
      var s = sesija.stanje();
      var bez = stanjeBezPodataka(s);
      if (bez) { prikazi(bez); return; }
      if (!izvor || typeof izvor.ucitaj !== "function") { prikazi({ vrsta: "nepovezano" }); return; }

      var moja = ++generacija;
      if (kontroler) kontroler.abort();
      kontroler = new AbortController();
      var signal = kontroler.signal;
      var korisnik = s.korisnik;
      prikazi({ vrsta: "ucitavanje" });

      var r;
      try { r = await izvor.ucitaj(sesija.token(), signal); }
      catch (e) { r = { ok: false, greska: { kod: "INVALID_RESPONSE", poruka: "Neočekivana greška pri učitavanju." } }; }

      /* Odgovor koji je zakasnio (nova sesija, novo učitavanje, odjava) se baca. */
      if (moja !== generacija || signal.aborted) return;
      var sad = sesija.stanje();
      if (sad.stanje !== (S && S.PRIJAVLJEN) || sad.korisnik !== korisnik) return;
      kontroler = null;

      if (!r || !r.ok) {
        var g = (r && r.greska) || { kod: "INVALID_RESPONSE" };
        if (g.kod === "ABORTED") return;
        /* 401 znači da server više ne prihvata ovu sesiju: ništa od ranije ne
         * sme ostati prikazano kao trenutno. */
        podaci = null;
        prikazi({ vrsta: "greska", greska: g });
        return;
      }
      podaci = { korisnik: korisnik, predmeti: r.predmeti, ukupno: r.ukupno };
      prikazi({ vrsta: "podaci", predmeti: podaci.predmeti, ukupno: podaci.ukupno });
    }

    function naPromenuSesije(novo, staro) {
      var istiKorisnik = novo.stanje === (S && S.PRIJAVLJEN) && staro.stanje === (S && S.PRIJAVLJEN) && novo.korisnik === staro.korisnik;
      if (istiKorisnik) return; // osvežen token istog korisnika: podaci ostaju važeći
      ponisti();
      var bez = stanjeBezPodataka(novo);
      prikazi(bez || { vrsta: "ucitavanje" });
      if (!bez) ucitaj();
    }

    var odjavi = sesija.naPromenu(naPromenuSesije);

    /* Proveri sesiju; ako to samo po sebi nije pokrenulo novo učitavanje
     * (sesija nepromenjena), poništi i učitaj jednom. Nikad dva zahteva. */
    function ponovo() {
      var pre = generacija;
      sesija.proveri();
      if (generacija === pre) { ponisti(); ucitaj(); }
    }

    return {
      pokreni: ponovo,
      osvezi: ponovo,
      podaci: function () { return podaci; },
      zaustavi: function () { odjavi(); ponisti(); },
    };
  }

  root.VxLive = Object.freeze({ napravi: napravi });
})(window);
