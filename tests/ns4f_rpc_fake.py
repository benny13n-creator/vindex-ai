# -*- coding: utf-8 -*-
"""NS4 završno zatvaranje — lažne (u memoriji) verzije RPC funkcija iz migracija 139 i 140.

Služe SAMO testovima rute (ožičenje, autorizacija, poruke) nad `tests/ns005_harness.Baza`. Semantiku
transakcije, brava i dozvola dokazuje `tests/test_ns4f_pg_*.py` nad STVARNIM PostgreSQL-om sa pravim SQL-om —
ovaj fajl nije dokaz atomičnosti. Ponašanje prati SQL:
  • `zabelezi_ishod_predmeta`: vlasništvo predmeta → upsert `outcome_log` (po predmet_id) → zbir za novu i
    staru vrstu spora iz `outcome_log` (prvih 10 faktora, ponovljen faktor jednom); greška → ništa upisano.
  • `preuzmi_ponovni_upis_nacrta` / `zavrsi_promociju_nacrta`: preuzimanje sa tokenom i rokom, zatvaranje samo
    istim tokenom.
Greška tabele (`baza.greske["outcome_log"]` itd.) obara ceo poziv, kao pad transakcije.
"""
from __future__ import annotations

import datetime as _dt
import uuid


def _greska(b, *tabele):
    for t in tabele:
        if t in b.greske:
            raise b.greske[t]


def _zbir(b, uid, vrsta):
    cp = b.tabele.setdefault("case_patterns", [])
    brojaci: dict = {}
    for o in b.tabele.get("outcome_log", []):
        if str(o.get("user_id")) != str(uid) or o.get("tip_spora") != vrsta:
            continue
        for f in dict.fromkeys(x for x in (o.get("presudni_faktori") or [])[:10] if x is not None):
            z = brojaci.setdefault(f, {"pobede": 0, "porazi": 0, "ukupno": 0})
            z["pobede"] += o.get("ishod") == "pobeda"
            z["porazi"] += o.get("ishod") == "poraz"
            z["ukupno"] += 1
    postojeci = {r["faktor"]: r for r in cp if str(r.get("user_id")) == str(uid) and r.get("tip_spora") == vrsta}
    for f in set(postojeci) | set(brojaci):
        vr = brojaci.get(f, {"pobede": 0, "porazi": 0, "ukupno": 0})
        if f in postojeci:
            postojeci[f].update(vr)
        else:
            cp.append({"id": str(uuid.uuid4()), "user_id": uid, "tip_spora": vrsta, "faktor": f, **vr})


def zabelezi_ishod_predmeta(b, p):
    _greska(b, "outcome_log", "case_patterns", "predmeti")
    uid, pid = p.get("p_user_id"), p.get("p_predmet_id")
    if not uid or not pid:
        raise Exception('{"code": "22023", "message": "nedostaje identitet"}')
    pred = [r for r in b.tabele.get("predmeti", []) if str(r.get("id")) == str(pid) and str(r.get("user_id")) == str(uid)]
    if not pred:
        raise Exception('{"code": "P0002", "message": "predmet nije pronađen"}')
    tip = pred[0].get("tip")
    ol = b.tabele.setdefault("outcome_log", [])
    stari = next((r for r in ol if str(r.get("predmet_id")) == str(pid)), None)
    if stari and str(stari.get("user_id")) != str(uid):
        raise Exception('{"code": "42501", "message": "ishod predmeta pripada drugom korisniku"}')
    stari_tip = stari.get("tip_spora") if stari else None
    polja = {"predmet_id": pid, "user_id": uid, "ishod": p.get("p_ishod"),
             "presudni_faktori": list(p.get("p_faktori") or []), "trajanje_meseci": p.get("p_trajanje_meseci"),
             "vrednost_spora_rsd": p.get("p_vrednost_spora"), "komentar": p.get("p_komentar"), "tip_spora": tip,
             "uzroci": list(p.get("p_uzroci") or []), "kontekst_poraza": p.get("p_kontekst_poraza")}
    sada = _sada().isoformat()  # kao DEFAULT now() (037) i `updated_at = now()` u ON CONFLICT (139)
    if stari:
        stari.update(polja, updated_at=sada)
    else:
        ol.append({"id": str(uuid.uuid4()), **polja, "created_at": sada, "updated_at": sada})
    b.dnevnik.append({"tabela": "outcome_log", "radnja": "upsert", "filteri": []})
    for vrsta in sorted({x for x in (tip, stari_tip) if x}):
        _zbir(b, uid, vrsta)
    faktora = len(dict.fromkeys(x for x in (p.get("p_faktori") or [])[:10] if x is not None))
    return {"tip_spora": tip, "prethodna_vrsta": stari_tip, "faktora": faktora}


def _sada():
    return _dt.datetime.now(_dt.timezone.utc)


def preuzmi_ponovni_upis_nacrta(b, p):
    _greska(b, "staging_memory")
    istek = _dt.timedelta(seconds=max(int(p.get("p_istek_sekundi") or 0), 60))
    for s in b.tabele.get("staging_memory", []):
        if str(s.get("id")) != str(p.get("p_staging_id")) or str(s.get("user_id")) != str(p.get("p_user_id")):
            continue
        preuzeta = s.get("promocija_preuzeta_at")
        slobodan = not s.get("promocija_token") or (
            preuzeta is not None and _dt.datetime.fromisoformat(str(preuzeta)) < _sada() - istek)
        if (s.get("status") == "approved" and s.get("is_lawyer_approved") is True and s.get("pinecone_indexed") is not True
                and float(s.get("confidence_score") or 0) >= max(float(p.get("p_prag") or 0), 0) and slobodan):
            s["promocija_token"] = str(uuid.uuid4())
            s["promocija_preuzeta_at"] = _sada().isoformat()
            b.dnevnik.append({"tabela": "staging_memory", "radnja": "update", "filteri": [("rpc", "preuzmi")]})
            return [dict(s)]
    return []


def zavrsi_promociju_nacrta(b, p):
    _greska(b, "staging_memory")
    tok = p.get("p_token")
    for s in b.tabele.get("staging_memory", []):
        if str(s.get("id")) == str(p.get("p_staging_id")) and tok and s.get("promocija_token") == tok:
            s["pinecone_indexed"] = bool(p.get("p_indeksiran")) and s.get("status") == "approved" \
                and s.get("is_lawyer_approved") is True
            s["promocija_token"] = None
            s["promocija_preuzeta_at"] = None
            b.dnevnik.append({"tabela": "staging_memory", "radnja": "update", "filteri": [("rpc", "zavrsi")]})
            return s["pinecone_indexed"]
    return False


RPC_NS4 = {
    "zabelezi_ishod_predmeta": zabelezi_ishod_predmeta,
    "preuzmi_ponovni_upis_nacrta": preuzmi_ponovni_upis_nacrta,
    "zavrsi_promociju_nacrta": zavrsi_promociju_nacrta,
}
