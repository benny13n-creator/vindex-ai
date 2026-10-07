/* Vindex V2 NG — aktivni predmeti iz postojećeg `GET /api/predmeti` (samo čitanje).
 *
 * Ugovor (api.py `lista_predmeta`, main 5fd4db65):
 *   • korisnik se određuje ISKLJUČIVO iz tokena; server filtrira `user_id`
 *   • `limit` 1..500 (podrazumevano 200), `offset` ≥ 0, `status`, `q` (samo naziv)
 *   • odgovor `{ predmeti, ukupno, limit, offset }`; `ukupno` je `count="exact"`
 *   • predmeti u brisanju (tombstone) se izbacuju POSLE brojanja, pa strana može
 *     imati manje redova od `limit` iako ima još strana
 *
 * Zato se stranice pomeraju za `limit` koji je server prijavio (ne za broj
 * primljenih redova), a kraj je `offset >= ukupno`. Broj strana je ograničen.
 * Ako se `ukupno` promeni između strana ili se `id` ponovi, rezultat se ODBACUJE
 * kao greška: tihi duplikat ili izgubljen predmet su gori od jasne greške.
 *
 * Polja se mapiraju samo iz onoga što odgovor STVARNO sadrži. Tabela `predmeti`
 * nema `sud` ni `klijent` (produkciona sonda 2026-08-21 i migracije) — ta polja
 * ostaju prazna, nikad izmišljena. `view=summary` se ne koristi jer ne sadrži
 * stranke (`tuzilac`, `tuzeni`), po kojima se pretražuje.
 */
(function (root) {
  "use strict";

  var STRANA = 500;           // najveći `limit` koji server prihvata
  var NAJVISE_STRANA = 200;   // tvrda granica petlje (100 000 predmeta)

  function oblikStrane(d) {
    return Array.isArray(d.predmeti) && Number.isInteger(d.ukupno) && d.ukupno >= 0 &&
      Number.isInteger(d.limit) && d.limit > 0 && Number.isInteger(d.offset) && d.offset >= 0;
  }

  function tekst(v) { return typeof v === "string" ? v.trim() : ""; }

  function datumIso(r) {
    var v = tekst(r.updated_at) || tekst(r.created_at);
    return /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : "";
  }

  /* Jedan red API-ja → red registra. Vraća null ako red nema id ili naziv. */
  function mapiraj(r) {
    if (!r || typeof r !== "object") return null;
    var id = typeof r.id === "string" || typeof r.id === "number" ? String(r.id) : "";
    var naziv = tekst(r.naziv);
    if (!id || !naziv) return null;
    var stranke = [tekst(r.tuzilac), tekst(r.tuzeni)].filter(Boolean);
    return {
      id: id,
      naziv: naziv,
      broj: tekst(r.broj_predmeta),
      stranke: stranke,
      klijent: "",            // ne postoji u odgovoru
      sud: "",                // ne postoji u odgovoru
      vrsta: "",
      stanje: tekst(r.status) || "aktivan",
      izmenjeno: datumIso(r),
    };
  }

  function neispravno(poruka) { return { ok: false, greska: { kod: "INVALID_RESPONSE", poruka: poruka } }; }

  async function ucitaj(token, signal) {
    var predmeti = [];
    var videni = Object.create(null);
    var ukupno = null;
    var offset = 0;

    for (var strana = 0; strana < NAJVISE_STRANA; strana++) {
      var r = await root.VxApi.get("/api/predmeti", {
        token: token, signal: signal, oblik: oblikStrane,
        parametri: { status: "aktivan", limit: STRANA, offset: offset },
      });
      if (!r.ok) return r;
      var d = r.podaci;
      if (d.offset !== offset) return neispravno("Server je vratio drugu stranu od tražene.");
      if (ukupno === null) ukupno = d.ukupno;
      else if (d.ukupno !== ukupno) {
        return { ok: false, greska: { kod: "INCONSISTENT", poruka: "Lista predmeta se promenila tokom učitavanja." } };
      }
      for (var i = 0; i < d.predmeti.length; i++) {
        var p = mapiraj(d.predmeti[i]);
        if (!p) return neispravno("Predmet bez oznake ili naziva.");
        if (videni[p.id]) {
          return { ok: false, greska: { kod: "INCONSISTENT", poruka: "Isti predmet se pojavio na dve strane." } };
        }
        videni[p.id] = 1;
        predmeti.push(p);
      }
      offset += d.limit;
      if (offset >= ukupno) return { ok: true, predmeti: predmeti, ukupno: ukupno };
      if (signal && signal.aborted) return { ok: false, greska: { kod: "ABORTED" } };
    }
    return { ok: false, greska: { kod: "INCONSISTENT", poruka: "Previše strana — učitavanje je prekinuto." } };
  }

  /* Izvor postoji samo u LIVE režimu. Ako je izvor već postavljen (šav koji
   * koriste testovi životnog ciklusa sesije), ne prepisuje se. */
  if (!root.VxRuntime || root.VxRuntime.rezim !== root.VxRuntime.LIVE) return;
  if (root.VxLiveIzvor) return;
  root.VxLiveIzvor = Object.freeze({ ucitaj: ucitaj, mapiraj: mapiraj });
})(window);
