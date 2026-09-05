/* Vindex V2 — tipizirane greske.
 *
 * Zasto tip a ne HTTP broj: ekran treba da razlikuje "niste prijavljeni" od
 * "nemate pravo na ovu funkciju" od "mreza je pala". To su tri razlicita
 * ishoda za korisnika, a dva od njih dele status 4xx. Broj ostaje dostupan
 * za dijagnostiku, ali odluku donosi VRSTA.
 */

export const VRSTA = Object.freeze({
  NEPRIJAVLJEN: "neprijavljen",   // 401 — sesija ne postoji ili je istekla
  ZABRANJENO:   "zabranjeno",     // 403 — nalog nema pravo na ovu funkciju
  NEISPRAVAN:   "neispravan",     // 400/422 — zahtev nije ispravan
  NEMA:         "nema",           // 404
  SERVER:       "server",         // 5xx
  MREZA:        "mreza",          // zahtev nikad nije stigao do servera
  PREKINUT:     "prekinut",       // AbortController — nije greska, nego otkazivanje
});

export class HttpGreska extends Error {
  constructor(vrsta, status, poruka) {
    super(poruka || vrsta);
    this.name = "HttpGreska";
    this.vrsta = vrsta;
    this.status = status || 0;
  }
}

export function jePrekid(e) {
  return (e && e.vrsta === VRSTA.PREKINUT) || (e && e.name === "AbortError");
}

/** Poruka za korisnika. Srpski, precizno, bez stack trace-a, bez sirovog JSON-a,
 *  bez naziva dozvole i bez "nesto je poslo naopako". */
export function porukaZaKorisnika(e) {
  const v = e && e.vrsta;
  if (v === VRSTA.MREZA)      return "Nema veze sa serverom. Proverite internet vezu i pokušajte ponovo.";
  if (v === VRSTA.SERVER)     return "Server trenutno ne odgovara. Pokušajte ponovo za koji trenutak.";
  if (v === VRSTA.ZABRANJENO) return "Ovaj nalog nema pristup ovom delu Vindexa.";
  if (v === VRSTA.NEMA)       return "Traženo nije pronađeno.";
  if (v === VRSTA.NEISPRAVAN) return "Zahtev nije mogao biti obrađen u ovom obliku.";
  return "Podaci trenutno nisu dostupni.";
}
