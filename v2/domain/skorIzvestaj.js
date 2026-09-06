/* Vindex V2 — strukturirani skor-izvestaji (AML/KYC, MiCA readiness, ZDI
 * license risk, Documentation Health), domenski sloj.
 *
 * OTKRIVENI KVAR (Z017.2 execution queue, G3/G4/G5 klasifikacija): ove 4
 * backend funkcije (`web3_compliance.py`: aml_kyc_auditor_sync,
 * mica_readiness_score_sync, zdi_license_checker_sync,
 * documentation_health_score_sync) NIKAD nisu vracale `{rezultat}` -- vracaju
 * `{audit_data|health_data|license_data|score_data, objasnjenje}`. Komentar
 * u backend kodu (SS "Operation Singular Intelligence") kaze da su
 * PROJEKTOVANE za legacy `static/vindex.js`-ovo sopstveno bespoke
 * iscrtavanje. V2-ov generican `uNalaz()` (domain/uskladjenost.js) trazi
 * `rezultat` -- ne postoji za ove 4, pa je prikaz UVEK bio
 * "odgovor nije stigao u ocekivanom obliku" za SVAKI /web3/aml-audit poziv.
 * Ovaj modul je stvarna popravka: strukturiran prikaz, ne text-only fallback.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/** Kategorije dolaze kao objekat {kljuc: {skor,max,status,komentar}} --
 * pretvara se u niz radi stabilnog redosleda iscrtavanja. */
function uKategorije(sirov) {
  const k = sirov || {};
  return Object.keys(k).map(kljuc => {
    const v = k[kljuc] || {};
    return {
      kljuc,
      // Naziv kategorije se NE prevodi izmisljeno -- sirov kljuc (npr.
      // "kyc_procedure") postaje "Kyc procedure" (razmaci, prvo veliko
      // slovo). Nepouzdan prevod bi bio gori od doslovnog kljuca.
      naziv: kljuc.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()),
      skor: Number.isFinite(v.skor) ? v.skor : null,
      max: Number.isFinite(v.max) ? v.max : null,
      status: tekst(v.status),
      komentar: tekst(v.komentar),
    };
  });
}

/**
 * `ukupniKljuc`/`nivoKljuc` se razlikuju po backend funkciji:
 *   aml:    ukupna_uskladenost / uskladenost_nivo
 *   mica:   ukupni_skor / skor_nivo
 *   health: ukupni_skor / skor_nivo
 *   license: nema skor/nivo u istom obliku -- v. uLicencu ispod
 */
export function uSkorIzvestaj(sirov, { ukupniKljuc, nivoKljuc, kljucPodataka }) {
  const o = sirov || {};
  const podaci = (kljucPodataka && o[kljucPodataka]) || {};
  return {
    ukupno: Number.isFinite(podaci[ukupniKljuc]) ? podaci[ukupniKljuc] : null,
    nivo: tekst(podaci[nivoKljuc]),
    kategorije: uKategorije(podaci.kategorije),
    kriticniNedostaci: Array.isArray(podaci.kriticni_nedostaci) ? podaci.kriticni_nedostaci.map(tekst).filter(Boolean) : [],
    preporuke: Array.isArray(podaci.preporuke) ? podaci.preporuke.map(tekst).filter(Boolean) : [],
    objasnjenje: tekst(o.objasnjenje),
  };
}

/** ZDI License Checker ima drugaciji oblik od preostale 3 (nema kategorije/
 * skor) -- posebna funkcija, ne prisiljava se u isti kalup. */
export function uLicencu(sirov) {
  const o = sirov || {};
  const l = o.license_data || {};
  return {
    dozvolaPotrebna: l.dozvola_potrebna === true,
    nadlezniOrgan: tekst(l.nadlezni_organ),
    rizikNivo: tekst(l.rizik_nivo),
    tipDozvole: tekst(l.tip_dozvole),
    pravniOsnov: Array.isArray(l.pravni_osnov) ? l.pravni_osnov.map(tekst).filter(Boolean) : [],
    obavezneMere: Array.isArray(l.obavezne_mere) ? l.obavezne_mere.map(tekst).filter(Boolean) : [],
    kaznePriKrsenju: tekst(l.kazne_pri_krsenju || l["kazne_pri_kršenju"]),
    objasnjenje: tekst(o.objasnjenje),
  };
}
