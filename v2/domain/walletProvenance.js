/* Vindex V2 — Wallet Provenance (G7), domenski sloj.
 *
 * Za razliku od G1-G6/G9 (GPT nad tekstom), ovo je DETERMINISTICKI izvor:
 * stvarni podaci sa Etherscan API-ja (on-chain transakcije, OFAC SDN
 * poklapanja), NIJE GPT interpretacija. Zato ovo NE dobija istu OGRADU kao
 * ostale analize -- nalaz "adresa JESTE na OFAC listi" je provera protiv
 * ucitane liste, ne model-ova pretpostavka. Backend (routers/wallet_
 * provenance.py) vec ima disciplinovane, iskrene napomene o obimu (1-hop,
 * samo Ethereum) -- ovaj sloj ih prenosi, ne izmislja dodatne.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function uNalazStavku(sirov) {
  const n = sirov || {};
  return {
    tip: tekst(n.tip),
    poverenje: tekst(n.confidence),
    opis: tekst(n.opis),
  };
}

export function uWalletProvenance(sirov) {
  const o = sirov || {};
  const nal = o.nalazi || {};
  const cov = o.coverage || {};
  return {
    adresa: tekst(o.adresa),
    ogranicenja: Array.isArray(o.ogranicenja_analize) ? o.ogranicenja_analize.map(tekst).filter(Boolean) : [],
    pokrivenost: {
      lanac: tekst(cov.lanac),
      izvor: tekst(cov.izvor),
      ethTransakcija: Number.isFinite(cov.analizirano_eth_transakcija) ? cov.analizirano_eth_transakcija : null,
      limitDostignut: cov.limit_dostignut === true,
    },
    sankcioni: Array.isArray(nal.sankcioni) ? nal.sankcioni.map(uNalazStavku) : [],
    analiticki: Array.isArray(nal.analiticki) ? nal.analiticki.map(uNalazStavku) : [],
    nedostatakPodataka: Array.isArray(nal.nedostatak_podataka) ? nal.nedostatak_podataka.map(uNalazStavku) : [],
    // `null` (polje odsutno/nepoznato) razlicito od `false` (aktivno provereno,
    // nema poklapanja) -- isti zakon kao svuda: odsustvo podatka != negativan nalaz.
    sankcionisan: typeof o.novcanik_sankcionisan === "boolean" ? o.novcanik_sankcionisan : null,
    balansEth: Number.isFinite(o.balans_eth) ? o.balans_eth : null,
    starostDana: Number.isFinite(o.starost_dana) ? o.starost_dana : null,
    napomena: tekst(o.napomena),
  };
}

const ETH_ADRESA_RE = /^0x[a-fA-F0-9]{40}$/;

export function validnaEthAdresa(v) {
  return ETH_ADRESA_RE.test(tekst(v));
}
