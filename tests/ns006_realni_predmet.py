"""NS006 — realističan (izmišljen) srpski predmet za testove živog predmeta i UI.

Radni spor: zaposleni Marko Petrović protiv poslodavca „Gradnja Invest" DOO Beograd —
nezakonit otkaz i neisplaćena zarada. Svi podaci su izmišljeni.

  D1 Rešenje o otkazu (tekst; klasifikovano „dopis")       — rešenje kaže: uručeno 17.03.2025.
  D2 Dostavnica (tekst; klasifikovano „dopis")              — dostavnica kaže: uručeno 25.03.2025.
  D3 Platni listići (klasifikacija PALA; ne sme izgledati kao „ostalo")
  Tvrdnje:  T1 iz D1 (pronađena u tekstu)  · T2 iz D2 (pronađena) · T3 advokat (bez dokumenta)
            T4 model iz D3 (NIJE pronađena) · T5 stara, poreklo nepoznato
  V2 kontradikcija K1 „datum uručenja rešenja o otkazu" = T1 ↔ T2 (kritična)
  Ročište za 6 dana; Genome v4 (trenutni) i v3 (istorija, okidač događaj E-V4).
"""
from __future__ import annotations

from datetime import date, timedelta

PA = "5a5a5a5a-0000-4000-8000-0000000000a1"
PB = "5b5b5b5b-0000-4000-8000-0000000000b1"
D1, D2, D3 = ("d1d1d1d1-0000-4000-8000-0000000000d1", "d2d2d2d2-0000-4000-8000-0000000000d2",
              "d3d3d3d3-0000-4000-8000-0000000000d3")
T1, T2, T3, T4, T5 = ("c1c1c1c1-0000-4000-8000-0000000000c1", "c2c2c2c2-0000-4000-8000-0000000000c2",
                      "c3c3c3c3-0000-4000-8000-0000000000c3", "c4c4c4c4-0000-4000-8000-0000000000c4",
                      "c5c5c5c5-0000-4000-8000-0000000000c5")
K1, I1 = "ffff0001-0000-4000-8000-000000000001", "eeee0001-0000-4000-8000-000000000001"
DOGADJAJ_V4 = "e4e4e4e4-0000-4000-8000-0000000000e4"
ROCISTE = "aaaa0001-0000-4000-8000-000000000001"

TEKST_D1 = ("GRADNJA INVEST DOO BEOGRAD\nREŠENJE O OTKAZU UGOVORA O RADU\n"
            "Zaposlenom Marku Petroviću radni odnos prestaje dana 15.03.2025. godine zbog povrede radne obaveze. "
            "Rešenje je uručeno zaposlenom 17.03.2025. godine.")
TEKST_D2 = "POŠTA SRBIJE — DOSTAVNICA\nPošiljka je uručena primaocu Marku Petroviću dana 25.03.2025. godine."


def _genome(verzija: int, sa_k1: bool, dokumenata: int, cinjenica: int) -> dict:
    g = {
        "verzija": verzija,
        "pravna_teorija": {
            "pravni_identitet": "Radni spor — nezakonit otkaz i neisplaćena zarada — Petrović protiv Gradnja Invest DOO",
            "sustina_spora": "Da li je rešenje o otkazu zakonito uručeno i da li je zarada isplaćena u celosti.",
            "osnov_odgovornosti": "Nezakonit prestanak radnog odnosa i neisplaćena zarada.",
            "relevantni_zakoni": ["Zakon o radu čl. 185", "Zakon o radu čl. 9999"],
        },
        "stranke": [{"uloga": "tuzilac", "ime": "Marko Petrović"}, {"uloga": "tuzeni", "ime": "Gradnja Invest DOO Beograd"}],
        "datumi_kljucni": [{"opis": "Prestanak radnog odnosa", "datum": "2025-03-15", "znacaj": "kriticno"},
                           {"opis": "Uručenje rešenja", "datum": "17. mart 2025.", "znacaj": "kriticno"}],
        "rokovi_kriticni": [{"naziv": "Rok za tužbu radi poništaja rešenja", "datum": "2025-05-24", "status": "aktivan",
                             "lokacija": "DOK-01", "dokument_id": D1}],
        "kontradikcije": [],
        "najslabija_tacka": {"rizik": "Datum uručenja rešenja je sporan", "kriticnost": 72, "lokacija": "DOK-02", "preporuka": "Pribaviti povratnicu."},
        "strategija": {"primarni_cilj": "Poništaj rešenja o otkazu i isplata zarade",
                       "scenariji": [{"uslov": "Ako sud prihvati raniji datum uručenja", "odgovor": "Dokazivati lično neuručenje svedocima."}]},
        "nedostaje": [{"dokument": "Ugovor o radu", "hitnost": "kriticno", "opis": "Potreban za visinu zarade."}],
        "snaga_predmeta_procent": 61 if sa_k1 else 58,
        "heatmap": {"dokazi": 55, "rokovi": 70},
        "_analiza_osnov": {"dokumenata": dokumenata, "cinjenica": cinjenica, "pravnih_elemenata": 2},
        "_genome_docs_count": dokumenata, "_genome_docs_preskoceno": 0, "_dokumenti_bez_teksta": [],
        "_verifikacija": {"odluka": "approve_with_warning", "hard_flags": [], "soft_flags": [{}]},
    }
    if sa_k1:
        g["kontradikcije"] = [{"issue_label": "datum uručenja rešenja o otkazu", "claim_refs": ["CLAIM-001", "CLAIM-002"],
                               "claim_ids": sorted([T1, T2]), "relation_type": "cinjenica_cinjenica",
                               "opis": "Rešenje navodi 17.03.2025, dostavnica 25.03.2025.", "tezina": "kriticna",
                               "lokacija_1": "DOK-01", "lokacija_2": "DOK-02", "dokument_id_1": D1, "dokument_id_2": D2}]
        g["rokovi_kriticni"].append({"naziv": "Rok za žalbu", "datum": "2025-06-10", "status": "aktivan", "lokacija": "DOK-02",
                                     "dokument_id": D2})
    return g


def tabele(danas: date | None = None) -> dict:
    danas = danas or date.today()
    v3 = _genome(3, False, 2, 3)
    v4 = _genome(4, True, 3, 5)
    return {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv Gradnja Invest DOO", "tip": "radno", "status": "aktivan",
             "tuzilac": "Marko Petrović", "tuzeni": "Gradnja Invest DOO Beograd", "case_dna": v4},
            {"id": PB, "user_id": "uid-B", "naziv": "Jovanović protiv Opštine", "tip": "upravno", "status": "aktivan",
             "tuzilac": "Ana Jovanović", "tuzeni": "Opština", "case_dna": {}},
        ],
        "predmet_dokumenti": [
            {"id": D1, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "Rešenje o otkazu.pdf", "redni_broj": 1,
             "tip_dokaza": "dopis", "status": "obradjen", "klasifikovan_at": "2026-10-01T09:00:00+00:00", "ai_tags": "{}",
             "tekst_sadrzaj": TEKST_D1},
            {"id": D2, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "Dostavnica.pdf", "redni_broj": 2,
             "tip_dokaza": "dopis", "status": "obradjen", "klasifikovan_at": "2026-10-02T09:00:00+00:00", "ai_tags": "{}",
             "tekst_sadrzaj": TEKST_D2},
            {"id": D3, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "Platni listići 2024.pdf", "redni_broj": 3,
             "tip_dokaza": "ostalo", "status": "obradjen", "klasifikovan_at": "2026-10-03T09:00:00+00:00",
             "ai_tags": '{"_klasifikacija_greska": true}', "tekst_sadrzaj": "Zarada mart 2024..."},
        ],
        "predmet_dokazi": [
            {"id": T1, "predmet_id": PA, "user_id": "uid-A", "dokument_id": D1, "kategorija": "cinjenica",
             "tvrdnja": "Rešenje je uručeno zaposlenom 17.03.2025. godine.", "pravni_element": "uručenje",
             "nacin_pronalaska": "egzaktan", "start_offset": 180, "end_offset": 230, "stranica": 1,
             "izvor_snage": "dc005", "snaga": "jaka", "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
            {"id": T2, "predmet_id": PA, "user_id": "uid-A", "dokument_id": D2, "kategorija": "dokaz",
             "tvrdnja": "Pošiljka je uručena primaocu Marku Petroviću dana 25.03.2025. godine.", "pravni_element": "uručenje",
             "nacin_pronalaska": "egzaktan", "start_offset": 32, "end_offset": 100, "stranica": 1,
             "izvor_snage": "dc005", "snaga": "jaka", "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
            {"id": T3, "predmet_id": PA, "user_id": "uid-A", "dokument_id": None, "kategorija": "cinjenica",
             "tvrdnja": "Klijent tvrdi da rešenje o otkazu nije primio lično.", "pravni_element": "uručenje",
             "izvor_snage": "podrazumevano", "snaga": "srednja", "izvor_tvrdnje": "covek", "deleted_at": None},
            {"id": T4, "predmet_id": PA, "user_id": "uid-A", "dokument_id": D3, "kategorija": "dokaz",
             "tvrdnja": "Neisplaćena zarada iznosi 480.000,00 RSD.", "pravni_element": None,
             "nacin_pronalaska": "nije_pronadjen", "izvor_snage": "podrazumevano", "snaga": "srednja",
             "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
            {"id": T5, "predmet_id": PA, "user_id": "uid-A", "dokument_id": None, "kategorija": "ostalo",
             "tvrdnja": "Stara beleška iz spisa bez zabeleženog porekla.", "izvor_snage": None, "snaga": "srednja",
             "deleted_at": None},
        ],
        "rocista": [{"id": ROCISTE, "predmet_id": PA, "user_id": "uid-A", "sud": "Osnovni sud u Beogradu",
                     "datum": (danas + timedelta(days=6)).isoformat(), "vreme": "10:00", "status": "zakazano"}],
        "predmet_genome_history": [
            {"id": "h3", "predmet_id": PA, "user_id": "uid-A", "verzija": 3, "genome_data": v3,
             "trigger_event": "case_evolution:" + DOGADJAJ_V4, "created_at": "2026-10-09T08:00:00+00:00"},
        ],
        "predmet_issues": [{"id": I1, "predmet_id": PA, "user_id": "uid-A", "label": "datum uručenja rešenja o otkazu",
                            "status": "DISCOVERED"}],
        "predmet_contradictions": [{"id": K1, "issue_id": I1, "relation_type": "cinjenica_cinjenica", "state": "OPEN",
                                    "tezina": "kriticna", "state_reason": None, "created_at": "2026-10-09T08:00:00+00:00",
                                    "updated_at": "2026-10-09T08:00:00+00:00"}],
        "predmet_contradiction_claims": [{"contradiction_id": K1, "dokaz_id": T1, "removed_at": None},
                                         {"contradiction_id": K1, "dokaz_id": T2, "removed_at": None}],
        "case_actions": [], "events": [], "case_evolution_consequences": [], "zadaci": [], "intake_jobs": [],
        "case_intelligence_summaries": [],
    }
