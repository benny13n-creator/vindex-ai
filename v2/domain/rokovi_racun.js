/* Vindex V2 — racunanje rokova: zastarelost i procesni rokovi (B26).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * OVO NIJE AI ODGOVOR I NE SME DA IZGLEDA KAO AI ODGOVOR
 *
 * Backend racuna oba roka deterministicki, iz zakona: zastarelost po ZOO/ZR,
 * procesni rokovi po ZPP/ZKP/ZR/ZIO/ZUP, uz srpske praznike i radne dane.
 * Svaki odgovor NOSI zakonski osnov (`zakonski_osnov`, odnosno naziv roka sa
 * clanom). Zato ovaj ekran sme da prikaze zakljucak — ali samo dok osnov
 * postoji.
 *
 * ZAKLJUCAK BEZ OSNOVA SE NE PRIKAZUJE. Ako odgovor stigne bez zakonskog
 * osnova, to nije „rok bez fusnote" nego racun cije poreklo ne mozemo da
 * pokazemo advokatu koji ce se na njega pozvati pred sudom. `uZastarelost`
 * tada vraca `upotrebljiv: false`.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * „ISTEKLO" JE NALAZ, NE STIL. Zastarelo potrazivanje i propusten procesni
 * rok su najteze vesti koje ovaj ekran moze da saopsti. Nose sopstveno
 * stanje (`ISHOD.ISTEKLO`), da ih prikaz ne bi izjednacio sa „ostalo je jos
 * malo vremena".
 *
 * ODSUTAN BROJ DANA NIJE NULA. `dana_preostalo` koje nije stiglo znaci „ne
 * znam koliko je ostalo", a ne „istice danas".
 */

export const ISHOD = Object.freeze({
  U_TOKU: "u_toku",
  BLIZU: "blizu",
  ISTEKLO: "isteklo",
  NEPOZNATO: "nepoznato",
});

/** Prag na kome rok prestaje da bude „ima vremena". */
export const DANA_HITNO = 30;

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

/**
 * Datum u srpskom obliku. Backend salje zastarelost vec kao „01.05.2030", a
 * procesni rok kao ISO „2026-09-22" — advokat ne sme da vidi dva oblika
 * datuma na istom ekranu, jer bi ih citao kao dve razlicite vrste podatka.
 * Nepoznat oblik se NE prepravlja: prikazuje se onakav kakav je stigao.
 */
export function datumSrpski(v) {
  const s = tekst(v);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : s;
}

function ceoBroj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function oceni(dana, isteklo, prag) {
  // `isteklo === true` je izricita izjava backenda i pobedjuje racunicu.
  if (isteklo === true) return ISHOD.ISTEKLO;
  if (dana === null) return ISHOD.NEPOZNATO;
  if (dana < 0) return ISHOD.ISTEKLO;
  return dana <= prag ? ISHOD.BLIZU : ISHOD.U_TOKU;
}

/* ── Zastarelost potrazivanja ───────────────────────────────────────────── */
export function uZastarelost(sirov) {
  const o = sirov || {};
  const osnov = tekst(o.zakonski_osnov);
  const dana = ceoBroj(o.dana_preostalo);
  return {
    // Bez zakonskog osnova zakljucak se NE prikazuje: advokat se pred sudom
    // poziva na clan, ne na nas racun.
    upotrebljiv: !!osnov && !!tekst(o.datum_zastarelosti),
    vrsta: tekst(o.tip_potrazivanja),
    osnov,
    rokOpis: tekst(o.rok_opis),
    odDatuma: datumSrpski(o.datum_pocetka),
    doDatuma: datumSrpski(o.datum_zastarelosti),
    doDatumaIso: tekst(o.datum_zastarelosti_iso),
    dana,
    danaPoznato: dana !== null,
    ishod: oceni(dana, o.isteklo, 180),
    napomena: tekst(o.napomena),
  };
}

/* ── Procesni rok ───────────────────────────────────────────────────────── */
export function uProcesniRok(sirov) {
  const o = sirov || {};
  const naziv = tekst(o.naziv);
  const dana = ceoBroj(o.dani_do_isteka);
  return {
    // Naziv procesnog roka NOSI clan zakona („Žalba … (ZPP čl. 368)"), pa je
    // on ovde ono sto je `zakonski_osnov` kod zastarelosti.
    upotrebljiv: !!naziv && !!tekst(o.datum_isteka),
    naziv,
    odDatuma: datumSrpski(o.datum_pocetka),
    doDatuma: datumSrpski(o.datum_isteka),
    dana,
    danaPoznato: dana !== null,
    ishod: oceni(dana, o.isteklo, DANA_HITNO),
    napomena: tekst(o.napomena),
  };
}

/**
 * `new Date("2026-02-31")` NIJE NaN — JavaScript prevrce datum na 3. mart.
 * Provera kroz `getTime()` bi zato propustila nepostojeci datum do servera,
 * koji vraca 422; advokat bi dobio tehnicku poruku umesto recenice koja kaze
 * sta da ispravi. Zato se komponente porede posle parsiranja.
 */
function datumPostoji(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return false;
  const g = Number(m[1]), mes = Number(m[2]), dan = Number(m[3]);
  const d = new Date(g, mes - 1, dan);
  return d.getFullYear() === g && d.getMonth() === mes - 1 && d.getDate() === dan;
}

/* ── Ulazna provera ─────────────────────────────────────────────────────── */
/**
 * Vraca sta nedostaje, na jeziku advokata. Poziv se ne salje dok ovo nije
 * prazno — server bi vratio 422, a advokat bi dobio tehnicku poruku umesto
 * recenice koja kaze sta da uradi.
 */
export function nedostaciRacuna({ tip, datum } = {}) {
  const g = [];
  if (!tekst(tip)) g.push("Izaberite vrstu roka.");
  const d = tekst(datum);
  if (!d) g.push("Unesite datum od koga rok teče.");
  else if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) g.push("Datum mora biti u obliku GGGG-MM-DD.");
  else if (!datumPostoji(d)) g.push("Datum ne postoji.");
  return g;
}

/** Tipovi stizu sa servera; ovde se samo cisti oblik za prikaz. */
export function uTipoveZastarelosti(sirov) {
  const niz = sirov && Array.isArray(sirov.tipovi) ? sirov.tipovi : [];
  return niz
    .map(t => ({
      kljuc: tekst(t && t.kljuc),
      naziv: tekst(t && t.naziv),
      osnov: tekst(t && t.osnov),
      opis: tekst(t && t.opis),
    }))
    .filter(t => t.kljuc && t.naziv);
}

export function uTipoveProcesnih(sirov) {
  const niz = sirov && Array.isArray(sirov.tipovi) ? sirov.tipovi : [];
  return niz
    .map(t => ({
      kljuc: tekst(t && t.kod),
      naziv: tekst(t && t.naziv),
      dana: ceoBroj(t && t.dani),
      // „radni" i „kalendarski" nisu isto i razlika menja datum — pise se.
      racunanje: tekst(t && t.tip) === "radni" ? "radnih dana" : "kalendarskih dana",
      opis: tekst(t && t.napomena),
    }))
    .map(t => Object.assign(t, {
      // Napomena sa servera cesto vec pocinje istim brojem dana („15 radnih
      // dana od dostavljanja presude"). Ponoviti to ispred nje daje
      // „15 radnih dana · 15 radnih dana od dostavljanja presude".
      ponavlja: t.dana !== null && t.opis.startsWith(String(t.dana) + " "),
    }))
    .filter(t => t.kljuc && t.naziv);
}
