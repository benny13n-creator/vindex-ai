/* Vindex V2 NG — jedan predmet i njegovi dokumenti iz POSTOJEĆIH ruta (samo čitanje).
 *
 *   GET /api/predmeti/{id}                              → predmet, dokumenti, klijenti
 *   GET /api/predmeti/{id}/dokumenti/{dok}/preview      → izdvojeni tekst dokumenta
 *
 * O pristupu odlučuje SERVER (vlasnik iz tokena, postojeće delegirano čitanje).
 * Ovaj sloj dodatno ODBIJA odgovor koji nije za traženi predmet: drugi `id`
 * predmeta ili dokument tuđeg predmeta je neispravan odgovor, ne podatak.
 * Ništa se ne izmišlja: polje koje odgovor nema ostaje prazno.
 */
(function (root) {
  "use strict";

  /* ID ulazi u putanju: samo bezbedni znakovi, inače se zahtev ni ne šalje. */
  var ISPRAVAN_ID = /^[A-Za-z0-9_-]{1,64}$/;

  function tekst(v) { return typeof v === "string" ? v.trim() : ""; }
  function broj(v) { return typeof v === "number" && Number.isFinite(v) ? v : null; }
  function datumIso(v) { var s = tekst(v); return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : ""; }
  function neispravno(poruka) { return { ok: false, greska: { kod: "INVALID_RESPONSE", poruka: poruka } }; }

  function mapirajPredmet(p) {
    return {
      id: String(p.id),
      naziv: tekst(p.naziv),
      broj: tekst(p.broj_predmeta),
      status: tekst(p.status),
      tip: tekst(p.tip),
      tuzilac: tekst(p.tuzilac),
      tuzeni: tekst(p.tuzeni),
      opis: tekst(p.opis),
      /* Doslovna vrednost za optimističku proveru izmene (`if_updated_at`). */
      azurirano: typeof p.updated_at === "string" ? p.updated_at : "",
      vrednost: broj(p.vrednost_spora) !== null ? p.vrednost_spora
        : (typeof p.vrednost_spora === "string" && /^\s*\d+([.,]\d+)?\s*$/.test(p.vrednost_spora) ? Number(p.vrednost_spora.trim().replace(",", ".")) : null),
      otvoren: datumIso(p.created_at),
      izmenjeno: datumIso(p.updated_at) || datumIso(p.created_at),
    };
  }

  function mapirajDokument(d) {
    return {
      id: String(d.id),
      naziv: tekst(d.naziv_fajla),
      tip: tekst(d.tip_dokaza),
      datum: datumIso(d.created_at),
      velicinaKb: broj(d.velicina_kb),
      redniBroj: broj(d.redni_broj),
    };
  }

  /* NS005: beleške i hronologija iz ISTOG odgovora detalja. Kada polje nije
   * niz, vraća se null („nije učitano"), nikad prazna lista. */
  function mapirajBeleske(niz) {
    if (!Array.isArray(niz)) return null;
    return niz.filter(function (x) { return x && typeof x === "object" && x.id !== undefined && x.id !== null; })
      .map(function (x) { return { id: String(x.id), tekst: typeof x.sadrzaj === "string" ? x.sadrzaj : "", datum: datumIso(x.created_at), vreme: tekst(x.created_at) }; });
  }
  function mapirajHronologiju(niz) {
    if (!Array.isArray(niz)) return null;
    return niz.filter(function (x) { return x && typeof x === "object"; })
      .map(function (x) { return { dogadjaj: tekst(x.dogadjaj), datum: datumIso(x.datum_iso) || datumIso(x.datum) || tekst(x.datum), vaznost: tekst(x.vaznost), akter: tekst(x.akter) }; })
      .filter(function (x) { return x.dogadjaj; });
  }

  function mapirajKlijenta(k) {
    var ime = [tekst(k.ime), tekst(k.prezime)].filter(Boolean).join(" ");
    return { naziv: ime || tekst(k.firma), firma: ime ? tekst(k.firma) : "", uloga: tekst(k.uloga) };
  }

  async function ucitajPredmet(id, token, signal) {
    if (typeof id !== "string" || !ISPRAVAN_ID.test(id)) {
      return { ok: false, greska: { kod: "NOT_FOUND", poruka: "Neispravan identifikator predmeta." } };
    }
    var r = await root.VxApi.get("/api/predmeti/" + id, { token: token, signal: signal });
    if (!r.ok) return r;
    var d = r.podaci;
    if (!d.predmet || typeof d.predmet !== "object" || Array.isArray(d.predmet)) return neispravno("Odgovor nema predmet.");
    /* Odgovor mora biti za TRAŽENI predmet. */
    if (String(d.predmet.id) !== id) return neispravno("Odgovor se odnosi na drugi predmet.");
    if (d.predmet.brisanje_zapoceto) return { ok: false, greska: { kod: "NOT_FOUND", poruka: "Predmet nije dostupan." } };
    if (!Array.isArray(d.dokumenti) || !Array.isArray(d.klijenti_linked)) return neispravno("Odgovor nema očekivani oblik.");
    var dokumenti = [];
    for (var i = 0; i < d.dokumenti.length; i++) {
      var x = d.dokumenti[i];
      if (!x || typeof x !== "object" || x.id === undefined || x.id === null) return neispravno("Dokument bez identifikatora.");
      /* Dokument koji ne pripada ovom predmetu se ne prikazuje — ceo odgovor je sumnjiv. */
      if (x.predmet_id !== undefined && x.predmet_id !== null && String(x.predmet_id) !== id) return neispravno("Dokument ne pripada predmetu.");
      dokumenti.push(mapirajDokument(x));
    }
    var klijenti = d.klijenti_linked.filter(function (k) { return k && typeof k === "object"; }).map(mapirajKlijenta).filter(function (k) { return k.naziv; });
    return { ok: true, predmet: mapirajPredmet(d.predmet), dokumenti: dokumenti, klijenti: klijenti,
             beleske: mapirajBeleske(d.beleske), hronologija: mapirajHronologiju(d.hronologija) };
  }

  async function ucitajTekst(predmetId, dokId, token, signal) {
    if (!ISPRAVAN_ID.test(String(predmetId)) || !ISPRAVAN_ID.test(String(dokId))) {
      return { ok: false, greska: { kod: "NOT_FOUND", poruka: "Neispravan identifikator dokumenta." } };
    }
    var r = await root.VxApi.get("/api/predmeti/" + predmetId + "/dokumenti/" + dokId + "/preview", { token: token, signal: signal });
    if (!r.ok) return r;
    var d = r.podaci;
    if (typeof d.tekst !== "string" || typeof d.dostupan !== "boolean") return neispravno("Odgovor nema očekivani oblik.");
    return { ok: true, tekst: d.tekst, dostupan: d.dostupan && d.tekst.trim() !== "" };
  }

  root.VxPredmetIzvor = Object.freeze({ ucitajPredmet: ucitajPredmet, ucitajTekst: ucitajTekst, ISPRAVAN_ID: ISPRAVAN_ID });
})(window);
