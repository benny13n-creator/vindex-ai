"""NS008 — realističan (izmišljen) scenario srpske advokatske kancelarije: „Kancelarija pamti".

Kancelarija „Jovanović i partneri" (Beograd). Advokat A (uid-A) i kolega B (uid-B, ista kancelarija).

  OLD-1  „Marković protiv Tehnoprom DOO" — radni spor, nezakonit otkaz zbog navodne povrede radne discipline;
         Osnovni sud u Beogradu; dokazi: svedoci kolege, pisana upozorenja, evidencija prisustva;
         protivrečnost o datumu uručenja rešenja o otkazu. ZATVOREN — ljudski ishod: pobeda (presudni faktori:
         svedoci, pisana_komunikacija). Overena tužba (staging → advokat odobrio). Potvrđena lekcija.
  OLD-2  „Gradnja Invest DOO protiv Opštine Zemun" — privredni spor, naplata po ugovoru o građenju; Privredni sud
         u Beogradu; dokazi: ugovor, situacije. ZATVOREN — ljudski ishod: poraz.
  CURRENT „Petrović protiv Tehnoprom DOO" — radni spor, otkaz zbog navodne povrede radne discipline; Osnovni sud
         u Beogradu; svedoci i pisana upozorenja; ista vrsta protivrečnosti (datum uručenja). AKTIVAN.

Svi podaci su izmišljeni. Ništa ne ide van lažne baze.
"""
from __future__ import annotations

K1 = "e1e1e1e1-2323-4000-8000-000000000001"
OLD1 = "a0000001-2323-4000-8000-000000000001"
OLD2 = "a0000002-2323-4000-8000-000000000002"
CUR = "a0000003-2323-4000-8000-000000000003"
I1, I3 = "b0000001-2323-4000-8000-000000000001", "b0000003-2323-4000-8000-000000000003"
S_TUZBA, S_NACRT2 = "c0000001-2323-4000-8000-000000000001", "c0000002-2323-4000-8000-000000000002"
L_POTVRDJENA, L_PREDLOG = "d0000001-2323-4000-8000-000000000001", "d0000002-2323-4000-8000-000000000002"
SUD_OS, SUD_PS = "Osnovni sud u Beogradu", "Privredni sud u Beogradu"

TEKST_TUZBE = ("TUŽBA radi poništaja rešenja o otkazu ugovora o radu. Tužilac je otkaz dobio zbog navodne povrede "
               "radne discipline. Rešenje nije uručeno u skladu sa zakonom, a pisana upozorenja ne sadrže opis povrede. "
               "Predlažemo saslušanje svedoka — kolega tužioca — i uvid u evidenciju prisustva.")
LEKCIJA = ("U sporovima o otkazu zbog povrede radne discipline odmah pribaviti dostavnicu rešenja i svedoke "
           "koji mogu potvrditi stvarno vreme uručenja.")


def _p(pid, uid, naziv, tip, oblast, status, verzija, opis):
    return {"id": pid, "user_id": uid, "naziv": naziv, "tip": tip, "oblast": oblast, "status": status,
            "opis": opis, "case_dna": {"verzija": verzija, "snaga_predmeta_procent": 64}, "updated_at": "2026-09-15"}


def tabele() -> dict:
    return {
        "predmeti": [
            _p(OLD1, "uid-A", "Marković protiv Tehnoprom DOO", "radni", "radno", "aktivan", 4,
               "Nezakonit otkaz zbog navodne povrede radne discipline."),
            _p(OLD2, "uid-A", "Gradnja Invest DOO protiv Opštine Zemun", "privredni", "privredno", "aktivan", 2,
               "Naplata po ugovoru o građenju."),
            _p(CUR, "uid-A", "Petrović protiv Tehnoprom DOO", "radni", "radno", "aktivan", 1,
               "Otkaz zbog navodne povrede radne discipline; rešenje uručeno sa zakašnjenjem."),
        ],
        "rocista": [
            {"predmet_id": OLD1, "user_id": "uid-A", "sud": SUD_OS, "status": "odrzano"},
            {"predmet_id": OLD2, "user_id": "uid-A", "sud": SUD_PS, "status": "odrzano"},
            {"predmet_id": CUR, "user_id": "uid-A", "sud": SUD_OS, "status": "zakazano", "datum": "2099-01-01"},
        ],
        "predmet_dokazi": [
            {"predmet_id": OLD1, "user_id": "uid-A", "kategorija": "svedok", "tvrdnja": "Kolega potvrđuje da je radio tog dana."},
            {"predmet_id": OLD1, "user_id": "uid-A", "kategorija": "dokaz", "tvrdnja": "Evidencija prisustva."},
            {"predmet_id": OLD2, "user_id": "uid-A", "kategorija": "dokaz", "tvrdnja": "Ugovor o građenju."},
            {"predmet_id": CUR, "user_id": "uid-A", "kategorija": "svedok", "tvrdnja": "Kolega Petrovića."},
            {"predmet_id": CUR, "user_id": "uid-A", "kategorija": "dokaz", "tvrdnja": "Pisano upozorenje."},
        ],
        "predmet_issues": [{"id": I1, "predmet_id": OLD1, "user_id": "uid-A", "status": "CONFIRMED", "label": "Uručenje"},
                           {"id": I3, "predmet_id": CUR, "user_id": "uid-A", "status": "DISCOVERED", "label": "Uručenje"}],
        "predmet_contradictions": [
            {"issue_id": I1, "relation_type": "cinjenica_cinjenica", "tezina": "kriticna", "state": "OPEN"},
            {"issue_id": I3, "relation_type": "cinjenica_cinjenica", "tezina": "kriticna", "state": "OPEN"}],
        "staging_memory": [
            {"id": S_TUZBA, "user_id": "uid-A", "kancelarija_id": K1, "predmet_id": OLD1, "tip": "tuzba",
             "naziv": "Tužba — poništaj rešenja o otkazu", "tekst": TEKST_TUZBE, "confidence_score": 0.91,
             "quality_detail": {}, "status": "pending", "is_lawyer_approved": False, "pinecone_indexed": False},
            {"id": S_NACRT2, "user_id": "uid-A", "kancelarija_id": K1, "predmet_id": OLD1, "tip": "zalba",
             "naziv": "Nacrt žalbe (AI, neodobren)", "tekst": "AI nacrt žalbe — nije pregledan.", "confidence_score": 0.97,
             "quality_detail": {}, "status": "pending", "is_lawyer_approved": False, "pinecone_indexed": False},
        ],
        "lessons_learned": [
            {"id": L_POTVRDJENA, "user_id": "uid-A", "predmet_id": OLD1, "tip_spora": "radni", "lecija": LEKCIJA,
             "kategorija": "dokaz", "status_lekcije": "predlog_ai", "zastarela": False},
            {"id": L_PREDLOG, "user_id": "uid-A", "predmet_id": OLD1, "tip_spora": "radni",
             "lecija": "Uvek tražiti veštačenje.", "kategorija": "strategija", "status_lekcije": "predlog_ai", "zastarela": False},
        ],
        "outcome_log": [], "case_patterns": [], "recommendation_log": [], "predmet_hronologija": [],
        "predmet_delegiranja": [], "predmet_dokumenti": [], "events": [], "case_actions": [],
        "case_evolution_consequences": [], "notifications": [], "autonomy_work_items": [],
        "kancelarije": [{"id": K1, "admin_uid": "uid-A", "naziv": "Jovanović i partneri"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": "uid-B", "status": "ACTIVE"}],
        "memory_entries": [{"id": "e0000001-2323-4000-8000-000000000001", "kancelarija_id": K1, "user_id": "uid-B",
                            "entity_type": "sudija", "entity_id": "Nikolić", "entity_name": "Sudija Nikolić",
                            "tip": "obrazac", "sadrzaj": "Na pripremnom ročištu traži tabelarni pregled rokova.",
                            "aktivan": True, "izvor": "manual", "potvrde_count": 2}],
        "memory_graph_edges": [], "klijenti": [], "v2_mutation_idempotency": [], "audit_immutable": [],
        "predmet_contradiction_claims": [], "zadaci": [], "intake_jobs": [],
    }


def pripremi_istoriju(k, zaglavlje) -> dict:
    """Istorija kancelarije kroz STVARNE rute: ishodi (zatvaraju predmete), odobren rad, potvrđena lekcija."""
    out = {}
    out["ishod_old1"] = k.post("/api/learning/outcome", headers=zaglavlje("A"),
                               json={"predmet_id": OLD1, "ishod": "pobeda", "presudni_faktori": ["svedoci", "pisana_komunikacija"]})
    out["ishod_old2"] = k.post("/api/learning/outcome", headers=zaglavlje("A"),
                               json={"predmet_id": OLD2, "ishod": "poraz", "presudni_faktori": ["finansijska_dok"]})
    out["odobrenje"] = k.post(f"/api/staging/{S_TUZBA}/approve", headers=zaglavlje("A"))
    out["lekcija"] = k.patch(f"/api/learning/lessons/{L_POTVRDJENA}/potvrdi", headers=zaglavlje("A"), json={"akcija": "potvrdi"})
    return out
