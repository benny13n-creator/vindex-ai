/* Vindex V2 — prostori.
 *
 * Vindex nije skup modula nego radno okruzenje kancelarije organizovano oko
 * predmeta. Korisnik uci CETIRI mesta, ne osamdeset osam sposobnosti:
 *
 *   DANAS        sta trazi moju paznju
 *   PREDMETI     gde radim
 *   ZNANJE       sta kaze pravo
 *   KANCELARIJA  kako vodim firmu
 *   (Usklađenost — peti prostor, samo uz odgovarajuce pravo)
 *
 * PRAVILO KOJE OVAJ MODUL SPROVODI:
 * prostor koji korisnik nema NE POSTOJI u navigaciji. Nema onemogucene
 * stavke, nema „uskoro", nema sivog teksta koji obecava. Onemogucena
 * navigacija je obecanje koje proizvod ne moze da odrzi, i ucini da korisnik
 * uci mapu proizvoda umesto da radi.
 *
 * Isto pravilo vazi i za prostor koji jos NIJE izgradjen: ne prikazuje se.
 * Lista raste kako kapije prolaze — ne obrnuto.
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

/** Svi prostori iz vlasnickog modela, redom kojim se prikazuju. */
export const PROSTORI = Object.freeze([
  { kljuc: "danas",       naziv: "Danas",        putanja: "/app-v2/danas" },
  { kljuc: "predmeti",    naziv: "Predmeti",     putanja: "/app-v2/predmeti" },
  { kljuc: "znanje",      naziv: "Znanje",       putanja: "/app-v2/znanje" },
  { kljuc: "kancelarija", naziv: "Kancelarija",  putanja: "/app-v2/kancelarija" },
  { kljuc: "uskladjenost", naziv: "Usklađenost", putanja: "/app-v2/uskladjenost" },
]);

/**
 * Prostori koje ovaj nalog stvarno vidi.
 *
 * @param {Set<string>|string[]} izgradjeni  prostori koji postoje u ovoj verziji
 * @param {(kljuc:string)=>boolean} sme      pravo pristupa; podrazumevano sve
 *
 * Dva uslova su NAMERNO odvojena:
 *   „nije izgradjeno"  je stanje proizvoda i menja se sa svakom kapijom
 *   „nema pravo"       je stanje naloga i dolazi sa servera
 * Spajanje to dvoje bi znacilo da se buduce pravo ne moze razlikovati od
 * buduce funkcije — a to su dve razlicite odluke.
 */
export function vidljiviProstori(izgradjeni, sme = () => true) {
  const skup = izgradjeni instanceof Set ? izgradjeni : new Set(izgradjeni || []);
  return PROSTORI.filter(p => skup.has(p.kljuc) && sme(p.kljuc));
}

export function prostorZaPutanju(putanja, vidljivi) {
  const p = String(putanja || "").replace(/\/+$/, "");
  return (vidljivi || []).find(x => x.putanja === p) || null;
}
