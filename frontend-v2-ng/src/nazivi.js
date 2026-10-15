/* Vindex V2 NG — srpski nazivi za oznake koje server šalje kao identifikatore (QA-03).
 *
 * Samo prikaz: server, baza i API i dalje nose iste vrednosti; ovde se ništa ne menja i ništa ne upisuje.
 *
 *   vrstaDokumenta(kod)  `predmet_dokumenti.tip_dokaza` i Smart Intake `document_type`. Dva rečnika žive u bazi:
 *                        engleski (shared/intake_classify.py::DOCUMENT_TYPES) i srpski (routers/evidence.py,
 *                        routers/dokument.py) — postojeći zapisi nose oba.
 *   poljePodatka(kod)    Smart Intake `entity_type` (shared/intake_extract.py::ENTITY_TYPES).
 *   akter(naziv)         `predmet_hronologija.akter`. Prevode se SAMO interni nazivi procesa, uz zadržano poreklo
 *                        (AI / šablon / sistem); svaka druga vrednost je ime osobe, suda ili firme i ostaje doslovno.
 *
 * Nepoznata oznaka se NE prevodi nagađanjem: prikazuje se kao nepoznata, sa doslovnom oznakom.
 */
(function (root) {
  "use strict";

  var VRSTE = {
    // shared/intake_classify.py::DOCUMENT_TYPES
    lawsuit: "Tužba", response: "Odgovor na tužbu", appeal: "Žalba", judgment: "Presuda", contract: "Ugovor",
    invoice: "Faktura", power_of_attorney: "Punomoćje", evidence: "Dokaz", email: "Elektronska poruka",
    court_decision: "Sudska odluka", enforcement: "Izvršenje", legal_opinion: "Pravno mišljenje", other: "Ostalo",
    // raniji prikaz prijema (prijem-predmeta.js) — zadržano
    complaint: "Tužba", decision: "Rešenje", summons: "Poziv suda", notice: "Obaveštenje", unknown: "Nije prepoznato",
    // routers/evidence.py (klasifikacija dokaza)
    sudska_odluka: "Sudska odluka", podnesak: "Podnesak", ugovor: "Ugovor", dopis: "Dopis",
    medicinska_dokumentacija: "Medicinska dokumentacija", finansijska_dokumentacija: "Finansijska dokumentacija",
    javna_isprava: "Javna isprava", vestacki_nalaz: "Veštački nalaz", ostalo: "Ostalo",
    // routers/dokument.py
    presuda: "Presuda", resenje: "Rešenje", zapisnik: "Zapisnik", izvestaj: "Izveštaj", priznanica: "Priznanica",
    punomocje: "Punomoćje"
  };

  var POLJA = {
    // shared/intake_extract.py::ENTITY_TYPES
    case_number: "Broj predmeta", judge: "Sudija", plaintiff: "Tužilac", defendant: "Tuženi", court: "Sud",
    deadline: "Rok", amount: "Iznos", law_cited: "Navedeni propis",
    // raniji prikaz prijema — zadržano
    date: "Datum", contract_party: "Ugovorna strana", claim_basis: "Osnov zahteva"
  };

  /* Doslovni potpisi iz backend-a (`"akter": "..."`). Poreklo ostaje vidljivo: AI predlog, šablon ili sistem. */
  var AKTERI = {
    "Pipeline (AI)": "AI predlog iz opisa predmeta",
    "Smart Intake": "AI predlog iz otpremljenog dokumenta",
    "Genome (AI)": "AI analiza dokumenata predmeta",
    // api.py (confirm-links) i routers/intake.py: klik „Potvrdi veze“ / „Kreiraj predmet“ NIJE potvrda roka — naziv
    // zato ne sme da kaže „potvrdio“; stanje odluke prikazuje se zasebno („čeka vašu odluku“).
    "Auto-detect (AI)": "AI prepoznavanje iz dokumenta",
    "Copilot (AI)": "AI asistent, na zahtev advokata",
    "Intake Wizard (AI)": "Uneto pri prijemu predmeta (AI predlog)",
    // routers/intake.py: sadržaj je statički katalog šablona, ne model (oznaka „(AI)“ je istorijski netačna)
    "Template (AI)": "Šablon predmeta",
    "Intake Wizard — šablon": "Šablon predmeta",
    "Case Evolution Engine": "Sistem — praćenje predmeta",
    "Learning Engine": "Sistem — zatvaranje predmeta"
  };

  function tekst(v) { return String(v == null ? "" : v).trim(); }
  function ima(mapa, k) { return Object.prototype.hasOwnProperty.call(mapa, k); }

  /** "" kad oznake nema; nepoznata oznaka se prikazuje kao nepoznata, nikad kao pravni pojam. */
  function vrstaDokumenta(kod) {
    var k = tekst(kod);
    if (!k) return "";
    return ima(VRSTE, k) ? VRSTE[k] : "Nepoznata vrsta dokumenta (oznaka „" + k.slice(0, 60) + "“)";
  }

  function poljePodatka(kod) {
    var k = tekst(kod);
    if (!k) return "Nepoznato polje";
    return ima(POLJA, k) ? POLJA[k] : "Nepoznato polje (oznaka „" + k.slice(0, 60) + "“)";
  }

  function akter(naziv) {
    var k = tekst(naziv);
    return ima(AKTERI, k) ? AKTERI[k] : k;
  }

  root.VxNazivi = Object.freeze({ vrstaDokumenta: vrstaDokumenta, poljePodatka: poljePodatka, akter: akter });
})(window);
