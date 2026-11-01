"""S02 / B7 — test podrška: „advokat je potvrdio spornu tačku POSLE uvida u njen trenutni sadržaj“.

Odluka o spornoj tački važi samo za sadržaj koji je advokat video (`shared/issue_v2.efektivna_odluka`, obuhvat iz audit
zapisa odluke — `procitaj_obuhvat_odluka`). Testovi koji proveravaju tok POTVRĐENE protivrečnosti (akcije, kontinuitet,
priprema ročišta…) postavljaju temu u `CONFIRMED` direktno u lažnoj bazi, bez rute odluke. Ova zamena gradi obuhvat iz
ISTE lažne baze — otvorene / za pregled kontradikcije teme i njihove aktivne tvrdnje — tj. tačno ono što bi advokat
video da je u tom trenutku odlučio. Ne zaobilazi pravilo: kontradikcija ili tvrdnja koje nema u bazi nije u obuhvatu.
Sama ruta odluke i obuhvat su dokazani u tests/test_s02_kontradikcije_potvrda.py i tests/test_s02_odluka_postgres.py.
"""
from __future__ import annotations


def obuhvat_trenutnog_sadrzaja(supa, issue_ids, uid=None) -> dict:
    from shared.issue_v2 import ODLUKA_ODBIJENA, ODLUKA_POTVRDJENA, STATUS_POTVRDJENA, STATUS_RAZRESENA
    ids = [str(i) for i in (issue_ids or []) if i]
    if not ids:
        return {}
    teme = supa.table("predmet_issues").select("id,status").in_("id", ids).execute().data or []
    kon = [k for k in (supa.table("predmet_contradictions").select("id,issue_id,state").in_("issue_id", ids).execute().data or [])
           if k.get("state") in ("OPEN", "REVIEW_REQUIRED")]
    cl = (supa.table("predmet_contradiction_claims").select("contradiction_id,dokaz_id,removed_at")
          .in_("contradiction_id", [k["id"] for k in kon]).execute().data or []) if kon else []
    out = {}
    for t in teme:
        if t.get("status") not in (STATUS_POTVRDJENA, STATUS_RAZRESENA):
            continue
        out[str(t["id"])] = {
            "vazi": ODLUKA_POTVRDJENA if t["status"] == STATUS_POTVRDJENA else ODLUKA_ODBIJENA,
            "obuhvat": {str(k["id"]): sorted(str(c["dokaz_id"]) for c in cl
                                             if c["contradiction_id"] == k["id"] and c.get("removed_at") is None)
                        for k in kon if str(k["issue_id"]) == str(t["id"])}}
    return out


def advokat_video_trenutni_sadrzaj(monkeypatch) -> None:
    import shared.issue_v2 as _iv2
    monkeypatch.setattr(_iv2, "procitaj_obuhvat_odluka", obuhvat_trenutnog_sadrzaja)


def obuhvat_reda(k: dict) -> dict:
    """Za ručno sastavljene V2 redove (bez baze): advokat je video tačno ovu kontradikciju i njene tvrdnje."""
    from shared.issue_v2 import ODLUKA_ODBIJENA, ODLUKA_POTVRDJENA, STATUS_POTVRDJENA
    return {"vazi": ODLUKA_POTVRDJENA if k.get("issue_status") == STATUS_POTVRDJENA else ODLUKA_ODBIJENA,
            "obuhvat": {str(k.get("id")): sorted(str(c) for c in (k.get("claim_ids") or []))}}
