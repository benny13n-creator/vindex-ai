/* Vindex V2 NG — ručni unos tvrdnje (dokaza) u predmet (VCR001 T07).
 *
 * Ugovor (routers/evidence.py::add_dokaz, shared/evidence_write.upisi_dokaz):
 *   POST /api/evidence/predmeti/{id}/dokaz {tvrdnja, napomena?} → {ok, id, snaga, snaga_izvor, dogadjaj}
 *   `snaga` se NE šalje: odsustvo polja daje `podrazumevano`, a ne lažnu „procenu advokata“ (TASK 003A).
 *   Predmet mora biti pozivaočev (404). Upis emituje NEW_EVIDENCE_REGISTERED → Case Evolution (`dogadjaj`).
 * `predmet_dokazi` je izvor istine predmeta (ne Genome): posle upisa se Analiza ponovo čita.
 */
(function (root) {
  "use strict";

  function napravi(o) {
    var d = root.document, $ = function (id) { return d.getElementById(id); };
    var sesija = o.sesija, api = o.api, posle = o.posle || function () {};
    var trenutni = null, salje = false, gen = 0;

    function poruka(st, t) { var n = $("du-poruka"); if (!st) { n.hidden = true; n.textContent = ""; delete n.dataset.stanje; return; } n.hidden = false; n.dataset.stanje = st; n.textContent = t; }
    function zakljucaj(da) { salje = da; $("du-posalji").disabled = da || !trenutni; $("du-posalji").textContent = da ? "Upisivanje…" : "Dodaj tvrdnju"; }
    function ocisti() { gen++; trenutni = null; $("du-forma").reset(); poruka(null); zakljucaj(false); }

    async function posalji() {
      if (salje || !trenutni) return;
      var tvrdnja = $("du-tvrdnja").value.trim(), napomena = $("du-napomena").value.trim();
      if (tvrdnja.length < 5) { poruka("greska", "Tvrdnja mora imati bar 5 znakova."); $("du-tvrdnja").focus(); return; }
      var telo = { tvrdnja: tvrdnja.slice(0, 2000) };
      if (napomena) telo.napomena = napomena.slice(0, 1000);
      var moja = ++gen, id = trenutni.id;
      zakljucaj(true); poruka("ucitavanje", "Upisivanje tvrdnje…");
      var r = await api.send("/api/evidence/predmeti/" + encodeURIComponent(id) + "/dokaz", { telo: telo, token: sesija.token(),
        oblik: function (x) { return x.ok === true; } });
      if (moja !== gen || !trenutni || trenutni.id !== id) return;
      zakljucaj(false);
      if (r.ok && r.podaci) {
        $("du-forma").reset();
        poruka("uspeh", r.podaci.dogadjaj === "NIJE_ZAKAZAN"
          ? "Tvrdnja je upisana. Radnje predmeta će se osvežiti pri sledećoj promeni (obaveštenje nije zakazano)."
          : "Tvrdnja je upisana u predmet.");
        posle(id);
        return;
      }
      if (r.ok) { poruka("nepoznato", "Tvrdnja je verovatno upisana, ali odgovor nije mogao da se pročita. Osvežite Analizu pre ponovnog unosa."); posle(id); return; }
      var g = r.greska || {};
      if (g.ishodNepoznat) { poruka("nepoznato", "Ishod nije poznat: veza je prekinuta. Osvežite Analizu pre ponovnog unosa, da tvrdnja ne bude upisana dvaput."); return; }
      poruka("greska", {
        NOT_FOUND: "Predmet nije dostupan. Ništa nije upisano.",
        VALIDATION_ERROR: "Server nije prihvatio tvrdnju. Ništa nije upisano.",
        FORBIDDEN: "Unos dokaza nije dostupan za vaš nalog. Ništa nije upisano.",
        RATE_LIMITED: "Previše unosa u kratkom roku. Pokušajte ponovo malo kasnije.",
        AUTH_REQUIRED: "Prijava više nije važeća. Ništa nije upisano.",
      }[g.kod] || "Server je odbio unos. Ništa nije upisano.");
    }

    function postavi(predmet) {
      if (trenutni && trenutni.id === predmet.id && trenutni.korisnik === sesija.stanje().korisnik) return;
      ocisti();
      trenutni = { id: predmet.id, korisnik: sesija.stanje().korisnik };
      zakljucaj(false);
    }

    $("du-forma").addEventListener("submit", function (e) { e.preventDefault(); posalji(); });
    var odjavi = sesija.naPromenu(function (novo, staro) { if (novo.korisnik !== staro.korisnik || novo.stanje !== staro.stanje) ocisti(); });
    return { postavi: postavi, ocisti: ocisti, zaustavi: function () { odjavi(); ocisti(); } };
  }

  root.VxDokazUnos = Object.freeze({ napravi: napravi });
})(window);
