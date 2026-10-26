/* Vindex V2 NG — Podešavanja › Privatnost i podaci (P1.3) i Pomoć i informacije.
 *
 * Ugovori (vlasnik iz tokena; semantika servera se NE menja):
 *   GET    /api/export/complete → application/zip (routers/data_export.py): 8 tabela, bez originalnih fajlova;
 *          503 ako server ne može da dokaže zapis u nepromenljiv dnevnik — tada nema fajla.
 *   DELETE /api/gdpr/account    → {ok, poruka, napomena} (routers/gdpr.py): anonimizacija profila, gašenje
 *          email podsetnika; predmeti/klijenti/dokumenti ostaju; founder 403; ponavljanje ne menja ništa dodatno.
 *   GET    /api/me              → email za proveru potvrde (potvrda je samo zaštita od greške, NE autorizacija —
 *          autorizacija je token na serveru).
 * Ništa se ne briše bez upisane email adrese naloga i klika.
 */
(function (root) {
  "use strict";

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, gen = 0, kontrola = null, otvoren = false, email = null, zauzeto = false, obrisano = false;

    function poruka(id, st, t) { var n = $(id); n.hidden = !st; n.textContent = t || ""; if (st) n.dataset.stanje = st; else delete n.dataset.stanje; }
    function osvezi() {
      var spreman = !!email && !zauzeto && !obrisano;
      $("pn-izvoz").disabled = !email || zauzeto;
      $("pn-brisanje-potvrda").disabled = !spreman;
      $("pn-brisanje").disabled = !spreman || $("pn-brisanje-potvrda").value.trim().toLowerCase() !== email.toLowerCase();
    }
    function ocisti() {
      gen++; if (kontrola) kontrola.abort(); kontrola = null;
      email = null; zauzeto = false; obrisano = false;
      $("pn-brisanje-potvrda").value = "";
      ["pn-priv-stanje", "pn-izvoz-poruka", "pn-brisanje-poruka"].forEach(function (id) { poruka(id, null); });
      osvezi();
    }
    async function ucitaj() {
      var moj = ++gen; if (kontrola) kontrola.abort(); kontrola = new AbortController();
      poruka("pn-priv-stanje", "ucitavanje", "Učitavanje naloga…");
      var r = await api.get("/api/me", { token: sesija.token(), signal: kontrola.signal, oblik: function (x) { return typeof x.email === "string" && !!x.email; } });
      if (moj !== gen) return;
      kontrola = null;
      if (!r.ok) {
        if (r.greska.kod === "ABORTED") return;
        poruka("pn-priv-stanje", "greska", r.greska.kod === "AUTH_REQUIRED" ? "Prijava je istekla. Prijavite se ponovo." : "Nalog nije učitan. Izvoz i brisanje nisu dostupni.");
        return;
      }
      email = r.podaci.email;
      poruka("pn-priv-stanje", null);
      osvezi();
    }

    $("pn-izvoz").addEventListener("click", async function () {
      if (!email || zauzeto) return;
      var moj = gen;
      zauzeto = true; osvezi();
      poruka("pn-izvoz-poruka", "ucitavanje", "Priprema izvoza… Ovo može potrajati.");
      var r = await api.preuzmi("/api/export/complete", { metod: "GET", token: sesija.token(), tip: "application/zip" });
      if (moj !== gen) return;
      zauzeto = false; osvezi();
      if (!r.ok) {
        poruka("pn-izvoz-poruka", "greska", r.greska.kod === "AUTH_REQUIRED" ? "Prijava je istekla. Izvoz nije preuzet."
          : r.greska.kod === "SERVER_ERROR" ? "Izvoz nije napravljen: server nije mogao da pročita sve podatke ili da zabeleži izvoz. Fajl nije preuzet."
          : "Izvoz nije preuzet (" + r.greska.kod + ").");
        return;
      }
      var url = URL.createObjectURL(r.blob), a = d.createElement("a");
      a.href = url; a.download = r.ime || "vindex-izvoz.zip"; d.body.append(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
      poruka("pn-izvoz-poruka", "uspeh", "Fajl „" + (r.ime || "vindex-izvoz.zip") + "“ je preuzet.");
    });

    $("pn-brisanje-potvrda").addEventListener("input", osvezi);
    $("pn-brisanje").addEventListener("click", async function () {
      if (!email || zauzeto || obrisano || $("pn-brisanje-potvrda").value.trim().toLowerCase() !== email.toLowerCase()) return;
      var moj = gen;
      zauzeto = true; osvezi();
      poruka("pn-brisanje-poruka", "ucitavanje", "Zahtev je u toku…");
      var r = await api.send("/api/gdpr/account", { metod: "DELETE", token: sesija.token(), oblik: function (x) { return x.ok === true && typeof x.poruka === "string"; } });
      if (moj !== gen) return;
      zauzeto = false;
      if (r.ok && r.podaci) {
        obrisano = true;
        poruka("pn-brisanje-poruka", "uspeh", r.podaci.poruka + (typeof r.podaci.napomena === "string" ? " " + r.podaci.napomena : "") + " Prijava na nalog i dalje radi; odjavite se kada završite.");
      } else if (r.ok) {
        poruka("pn-brisanje-poruka", "nepoznato", "Server je prihvatio zahtev, ali potvrda nije čitljiva. Ponovljeni zahtev ne menja već anonimizovan nalog.");
      } else if (r.greska.ishodNepoznat) {
        poruka("pn-brisanje-poruka", "nepoznato", "Server nije potvrdio ishod. Pokušajte ponovo kasnije; ponovljeni zahtev ne menja već anonimizovan nalog.");
      } else {
        poruka("pn-brisanje-poruka", "greska", r.greska.kod === "FORBIDDEN" ? "Ovaj nalog se ne može obrisati kroz aplikaciju. Ništa nije promenjeno."
          : r.greska.kod === "RATE_LIMITED" ? "Previše zahteva. Ništa nije promenjeno; pokušajte za minut."
          : r.greska.kod === "AUTH_REQUIRED" ? "Prijava je istekla. Ništa nije promenjeno."
          : "Zahtev je odbijen (" + r.greska.kod + "). Ništa nije promenjeno.");
      }
      osvezi();
    });

    function pokreni() {
      if (sesija.stanje().stanje !== sesija.STANJA.PRIJAVLJEN) { poruka("pn-priv-stanje", "greska", "Prijavite se da biste upravljali svojim podacima."); return; }
      ucitaj();
    }
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

  /* Pomoć i informacije: samo statični linkovi ka postojećim javnim stranicama. */
  function pomoc() { return { otvori: function () {}, zatvori: function () {}, zaustavi: function () {} }; }

  root.VxPodesavanjaSekcije = root.VxPodesavanjaSekcije || {};
  root.VxPodesavanjaSekcije.privatnost = napravi;
  root.VxPodesavanjaSekcije.pomoc = pomoc;
  /* P3 Integracije: statičan, tačan pregled stanja (nijedna integracija nema kompletan lanac postoji → ovlašćeno →
     podešeno → testirano; inventar: docs/v2-execution/SETTINGS_MASTER_SPRINT_STATE.md). Bez zahteva i kontrola. */
  root.VxPodesavanjaSekcije.integracije = pomoc;
})(window);
