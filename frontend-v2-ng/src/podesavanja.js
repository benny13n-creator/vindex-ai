/* Vindex V2 NG — B10: lična podešavanja email podsetnika.
 * Postojeći backend ostaje jedini izvor istine; nema novih rokova ili slanja bez klika.
 * Sesija iz VxSesija, HTTP samo preko VxApi; nema identiteta korisnika u zahtevu.
 */
(function (root) {
  "use strict";

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, redniBroj = 0, citanje = null, zauzeto = false, profil = null;

    function poruka(id, tekst, stanje) {
      var n = $(id);
      n.hidden = !tekst;
      n.textContent = tekst || "";
      if (stanje) n.dataset.stanje = stanje; else delete n.dataset.stanje;
    }

    function osveziKontrole() {
      var dostupno = !!profil && !zauzeto;
      ["pn-dan-7", "pn-dan-3", "pn-dan-1", "pn-nedeljni"].forEach(function (id) {
        $(id).disabled = !dostupno || !profil.smtp_ok;
      });
      $("pn-sacuvaj").disabled = !dostupno || !profil.smtp_ok || !profil.email;
      $("pn-test").hidden = !profil || !profil.aktivan;
      $("pn-test").disabled = !dostupno || !profil.smtp_ok || !profil.email;
      $("pn-deaktiviraj").hidden = !profil || !profil.aktivan;
      $("pn-deaktiviraj").disabled = !dostupno;
    }

    function ocisti() {
      redniBroj++;
      if (citanje) citanje.abort();
      citanje = null;
      profil = null;
      zauzeto = false;
      $("pn-adresa").textContent = "—";
      $("pn-aktivno").textContent = "";
      ["pn-dan-7", "pn-dan-3", "pn-dan-1", "pn-nedeljni"].forEach(function (id) { $(id).checked = false; });
      poruka("pn-stanje", "", "");
      poruka("pn-poruka", "", "");
      osveziKontrole();
    }

    function validanProfil(p) {
      return p && typeof p.aktivan === "boolean" && typeof p.smtp_ok === "boolean"
        && (p.email === null || typeof p.email === "string")
        && ["dan_7", "dan_3", "dan_1"].every(function (k) { return typeof p[k] === "boolean"; });
    }

    function greskaCitanja(g) {
      if (g && g.kod === "AUTH_REQUIRED") return "Prijava je istekla. Prijavite se ponovo.";
      if (g && g.kod === "FORBIDDEN") return "Nemate pristup podešavanjima ovog naloga.";
      return "Podešavanja nisu učitana. Ništa nije uključeno niti promenjeno.";
    }

    async function ucitaj(porukaPosle) {
      var moj = ++redniBroj;
      if (citanje) citanje.abort();
      citanje = new AbortController();
      profil = null;
      poruka("pn-poruka", "", "");
      poruka("pn-stanje", "Učitavanje email podešavanja…", "ucitavanje");
      osveziKontrole();
      var r = await api.get("/email-notif/profil", {
        token: sesija.token(), signal: citanje.signal, oblik: validanProfil
      });
      if (moj !== redniBroj) return;
      citanje = null;
      if (!r.ok) {
        poruka("pn-stanje", greskaCitanja(r.greska), "greska");
        osveziKontrole();
        return;
      }
      profil = r.podaci;
      $("pn-adresa").textContent = profil.email || "Email adresa nije dostupna";
      $("pn-aktivno").textContent = profil.aktivan ? "Podsetnici su uključeni." : "Podsetnici su isključeni.";
      $("pn-dan-7").checked = profil.dan_7;
      $("pn-dan-3").checked = profil.dan_3;
      $("pn-dan-1").checked = profil.dan_1;
      $("pn-nedeljni").checked = profil.nedeljni !== false;
      poruka("pn-stanje", !profil.smtp_ok ? "Email server nije konfigurisan. Aktivacija nije dostupna." :
        !profil.email ? "Nalog nema potvrđenu adresu za prijem podsetnika." : "", !profil.smtp_ok || !profil.email ? "greska" : "");
      if (porukaPosle) poruka("pn-poruka", porukaPosle, "uspeh");
      osveziKontrole();
    }

    function greskaPisanja(r, radnja) {
      if (r.greska && (r.greska.ishodNepoznat || r.greska.kod === "OUTCOME_UNKNOWN")) {
        return "Ishod nije poznat. Proverite trenutno stanje pre ponovnog pokušaja.";
      }
      if (r.greska && r.greska.kod === "AUTH_REQUIRED") return "Prijava je istekla. Prijavite se ponovo.";
      return radnja + " nije potvrđena (HTTP " + (r.status || "mreža") + ").";
    }

    async function izvrsi(putanja, telo, metod, uspeh) {
      if (zauzeto || !profil) return;
      var moj = redniBroj;
      zauzeto = true;
      poruka("pn-stanje", "", "");
      poruka("pn-poruka", "Zahtev je u toku…", "ucitavanje");
      osveziKontrole();
      var r = await api.send(putanja, { metod: metod || "POST", telo: telo, token: sesija.token() });
      if (moj !== redniBroj) return;
      zauzeto = false;
      if (!r.ok) {
        poruka("pn-poruka", greskaPisanja(r, "Radnja"), "greska");
        osveziKontrole();
        return;
      }
      if (!r.podaci || r.podaci.ok !== true) {
        poruka("pn-poruka", "Server je prihvatio zahtev, ali potvrda nije čitljiva. Proverite stanje pre ponavljanja.", "greska");
        osveziKontrole();
        return;
      }
      if (putanja === "/email-notif/test") {
        var istaAdresa = r.podaci.poslato_na === profil.email;
        poruka("pn-poruka", istaAdresa
          ? "Server je prihvatio testno slanje na prikazanu adresu. Proverite prijem u inboxu i Spam folderu."
          : "Server je prihvatio zahtev, ali primalac nije potvrđen. Proverite nalog pre ponavljanja.",
          istaAdresa ? "uspeh" : "greska");
        osveziKontrole();
        return;
      }
      await ucitaj(uspeh);
    }

    $("pn-sacuvaj").addEventListener("click", function () {
      if (!profil || zauzeto || !profil.smtp_ok || !profil.email) return;
      izvrsi("/email-notif/profil", {
        aktivan: true, dan_7: $("pn-dan-7").checked, dan_3: $("pn-dan-3").checked,
        dan_1: $("pn-dan-1").checked, nedeljni: $("pn-nedeljni").checked
      }, "POST", "Email podsetnici su sačuvani.");
    });
    $("pn-test").addEventListener("click", function () {
      if (!profil || !profil.aktivan || !profil.smtp_ok || !profil.email || zauzeto) return;
      izvrsi("/email-notif/test", {}, "POST", "");
    });
    $("pn-deaktiviraj").addEventListener("click", function () {
      if (!profil || !profil.aktivan || zauzeto) return;
      izvrsi("/email-notif/profil", null, "DELETE", "Email podsetnici su isključeni.");
    });

    function pokreni() {
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) {
        poruka("pn-stanje", "Prijavite se da biste podesili svoje podsetnike.", "greska");
        return;
      }
      ucitaj();
    }

    /* Promena naloga dok je pogled otvoren: stari podaci se brišu, a pogled se puni za novi nalog. */
    var otvoren = false;
    var odjavi = sesija.naPromenu(function (novo, staro) {
      if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) { ocisti(); if (otvoren) pokreni(); }
    });
    ocisti();
    return {
      otvori: function () { otvoren = true; ocisti(); pokreni(); },
      zatvori: function () { otvoren = false; ocisti(); },
      zaustavi: function () { otvoren = false; odjavi(); ocisti(); },
    };
  }

  root.VxPodesavanja = Object.freeze({ napravi: napravi });
})(window);
