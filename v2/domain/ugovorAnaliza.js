/* Vindex V2 — Pravna analiza pametnog ugovora (G5/F12), domenski sloj.
 *
 * OTKRIVENI KVAR (Z017.2): backend (`routers/web3.py::post_analiziraj_ugovor`)
 * ocekuje `{solidity_source}`, V2-ov generican obrazac za USKLADJENOST je
 * slao `{tekst}` za SVIH 5 analiza bez izuzetka -- svaki pokusaj ove
 * konkretne analize je vracao 422 pre nego sto bi handler uopste bio
 * pozvan. Popravka: poseban `poljeTela` po analizi (v. ANALIZE), ne
 * univerzalno "tekst" polje.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function nizTeksta(v) {
  return Array.isArray(v) ? v.map(tekst).filter(Boolean) : [];
}

export function uUgovorAnalizu(sirov) {
  const o = sirov || {};
  const a = o.analysis_result || {};
  const rizici = Array.isArray(a.pravni_rizici) ? a.pravni_rizici.map(r => ({
    rizik: tekst(r && r.rizik),
    ozbiljnost: tekst(r && r.ozbiljnost),
    obrazlozenje: tekst(r && r.obrazlozenje),
  })).filter(r => r.rizik) : [];

  const amlKyc = a.aml_kyc || {};

  return {
    nazivUgovora: tekst(o.contract_name),
    solidityVerzija: tekst(o.solidity_version),
    jeProxy: o.is_proxy_detected === true,
    rizici,
    amlNivoRizika: tekst(amlKyc.nivo_rizika),
    amlObrazlozenje: tekst(amlKyc.obrazlozenje),
    klasifikacijaTokena: Array.isArray(a.klasifikacija_tokena) ? a.klasifikacija_tokena.map(k => ({
      kategorija: tekst(k && k.kategorija),
      status: tekst(k && k.status),
      faktoriZa: nizTeksta(k && k.faktori_za),
      faktoriProtiv: nizTeksta(k && k.faktori_protiv),
    })).filter(k => k.kategorija) : [],
  };
}
