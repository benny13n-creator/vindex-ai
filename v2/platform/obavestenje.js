/* Vindex V2 — jednokratna poruka izmedju dva ekrana.
 *
 * Postoji zbog tacno jednog problema: radnja se zavrsi na jednom ekranu, a
 * njen ishod je vazan na sledecem. Predmet je otvoren ali dopuna nije
 * sacuvana; spis je otpremljen ali analiza nije pokrenuta. Ekran koji odlazi
 * ne sme da drzi korisnika samo da bi mu to rekao, a ekran koji dolazi ne sme
 * da precuti.
 *
 * NIJE opsti sistem obavestenja: nema reda cekanja, nema istorije, nema
 * automatskog gasenja. Jedna poruka, procita se jednom i nestaje. Sve preko
 * toga bi postalo kanal kojim se korisniku saopstava ono sto ekran nije
 * uspeo da pokaze — a to je uvek los znak.
 */

let poruka = null;

/**
 * @param {string} tekst
 * @param {"uspeh"|"upozorenje"|"greska"} vrsta
 */
export function ostavi(tekst, vrsta = "upozorenje") {
  const t = String(tekst || "").trim();
  poruka = t ? { tekst: t, vrsta } : null;
}

/** Vraca poruku i BRISE je — druga scena je nikad ne vidi. */
export function preuzmi() {
  const p = poruka;
  poruka = null;
  return p;
}

/** Iscrtava preuzetu poruku, ako je ima. Vraca element ili null. */
export function elementPoruke() {
  const p = preuzmi();
  if (!p) return null;
  const e = document.createElement("div");
  e.className = "v2-obavestenje v2-obavestenje--" + p.vrsta;
  e.setAttribute("role", p.vrsta === "greska" ? "alert" : "status");
  e.textContent = p.tekst;
  return e;
}
