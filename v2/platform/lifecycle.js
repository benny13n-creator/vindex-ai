/* Vindex V2 — zivotni ciklus ekrana.
 *
 * Svaki montiran ekran dobija `ciklus` i kroz njega registruje SVE sto posle
 * mora da nestane: slusace, tajmere, AbortController-e, observere. Bez ovoga
 * ponovno montiranje ostavlja sirocad — a to se ne vidi dok aplikacija ne
 * pocne dvaput da zove isti endpoint.
 *
 * Nije event bus i nije store. Samo lista stvari koje treba pozvati unazad.
 */

export function napraviCiklus() {
  const zadaci = [];
  let ugasen = false;

  return {
    get ugasen() { return ugasen; },

    /** Slusac koji se sam skida pri gasenju. */
    slusaj(cilj, dogadjaj, rukovalac, opcije) {
      if (ugasen) return;
      cilj.addEventListener(dogadjaj, rukovalac, opcije);
      zadaci.push(() => cilj.removeEventListener(dogadjaj, rukovalac, opcije));
    },

    /** Tajmer koji se sam ponistava pri gasenju. */
    odlozi(fn, ms) {
      if (ugasen) return 0;
      const id = window.setTimeout(fn, ms);
      zadaci.push(() => window.clearTimeout(id));
      return id;
    },

    /** AbortController koji se sam prekida pri gasenju. */
    prekidac() {
      const c = new AbortController();
      zadaci.push(() => c.abort());
      return c;
    },

    dodaj(fn) { if (!ugasen) zadaci.push(fn); },

    ugasi() {
      if (ugasen) return;
      ugasen = true;
      while (zadaci.length) {
        const fn = zadaci.pop();
        try { fn(); } catch (e) { /* ciscenje ne sme da obori gasenje */ }
      }
    },
  };
}
