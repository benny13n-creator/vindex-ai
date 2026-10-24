# -*- coding: utf-8 -*-
"""MIR001 FINAL CLOSURE — TASK-C4: JEDAN neprekinut sintetički E2E (isti proces, ista baza, isti korisnik, isti predmet)
koji spaja tri korektivna zadatka:

  spis (7 dok., OCR, odluka suda u DOK-07) → DUG dokument sa presudnom činjenicom na kraju (C2) → nova informacija (DOK-08,
  rok → radnja) → nacrt iz spisa sa procesnim stanjem (C3) → pregled/izmena/odobrenje/DOCX → brisanje nepovezanog
  dokumenta (ništa) → brisanje DOK-08 (radnja zatvorena sa razlogom i izvorom, C1) → ponovljena isporuka (idempotentno)
  → izolacija korisnika B.

Stvarno: rute prijema, worker, Tesseract, dispečer, Genome osvežavanje, V2 projekcija, PRAVI klasifikator sa prozorima,
usklađivanje case_actions, staging, DOCX, ruta brisanja. Zamenjeni: pozivi modela (klasifikator vidi samo poslati prozor;
Genome kao u TASK-07; savetnik vraća zadat nacrt), Pinecone, Supabase i prijava (baza u memoriji, `tests/ns005_harness.py`),
atomski RPC brisanja (Python zamena `_atomsko_rpc`/`_brisanje_rpc`, ne SQL funkcije iz migracija 131/133/137), dozvole i
naplata (`get_policy`, `UsageService`), `audit.log_action` (upis u tabelu u memoriji), ocena kvaliteta nacrta i
`asyncio.create_task` u savetniku (zadatak se izvršava eksplicitno). Sadržaj STVARNIH modela je meren u C2/C3
(`docs/v2-execution/mir001_c2_model/`, `mir001_c3_model/`).
"""
import asyncio
import copy
import io
import json
import types
from unittest.mock import MagicMock

from tests import mir001_golden_case as gc
from tests.test_mir001_t07_dogadjaj_posledica import ROK, _dodaj, _obrisi, _rok_akcije, spis, treba_ocr  # noqa: F401
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401
from routers.evidence import _klasifikuj_dokument as _PRAVI_KLASIFIKATOR   # pre fixture-a (koji ga zamenjuje)
from tests.nacrt_json_zamena import kao_json

SEGMENTI = []
PRESUDNA = "CINJENICA: tuzeni je dopisom br. 118/26 od 03.03.2026. pismeno priznao dug od 2.345.678 dinara."
DUG = {"oznaka": "DOK-09", "ime": "09 Dopis tuzenog i prepiska.pdf", "skeniran": False,
       "redovi": [gc.SUD, f"Broj predmeta: {gc.BROJ}", "PREPISKA STRANAKA (SINTETICKI PREDMET)"]
       + [f"Dopis broj {i}: stranke su razmenile misljenja o rokovima isporuke i kvalitetu radova na krovu hale." for i in range(70)]
       + [PRESUDNA, "Kraj prepiske."]}
NACRT = ("PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026\n"
         "Vestak u nalazu navodi da je uzrok neodgovarajuce izvedena hidroizolacija (DOK-05). "
         "Tuzilac smatra da dopuna vestacenja nije potrebna jer je steta od 3.150.000 dinara jasno navedena.\n"
         "Tuzeni je dopisom br. 118/26 priznao dug (DOK-09).\n"
         "⚠️ Ovaj nacrt generisala je AI i mora ga pregledati i potpisati ovlašćeni advokat pre podnošenja sudu.")


def _seg(ime, uslov, detalj=""):
    SEGMENTI.append((ime, bool(uslov)))
    assert uslov, (ime, detalj)


@treba_ocr
def test_ceo_tok_dug_dokument_odluka_suda_brisanje_izvora(spis, monkeypatch):
    k, b, pid, doks = spis
    import routers.evidence as ev
    import routers.multi_agent as MA
    import services.quality_gate as QG
    import shared.usage as US

    # 1. spis: 7 dokumenata, OCR skena, odluka suda u DOK-07
    moji = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    _seg("01 spis 7 dokumenata + OCR", len(moji) == 7 and gc.NAVODI["N-09"]["tekst"] in " ".join(
        (next(d for d in moji if d["id"] == doks["DOK-05"]).get("tekst_sadrzaj") or "").split()))

    # 2. DUG dokument kroz stvaran prijem i PRAVI klasifikator (model vidi samo poslati prozor)
    poruke = []

    def _model_klas(client, user_msg):
        poruke.append(user_msg)
        prozor = user_msg.split("znakova):\n", 1)[-1]
        r = MagicMock()
        r.choices = [MagicMock()]
        r.choices[0].finish_reason = "stop"
        r.choices[0].message.content = json.dumps({"tip_dokaza": "dopis", "pravni_elementi": [], "kljucne_cinjenice":
                                                   [" ".join(l.split()) for l in prozor.splitlines() if "CINJENICA" in l]})
        return r
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _PRAVI_KLASIFIKATOR)
    monkeypatch.setattr(ev, "_pozovi_evidence_api", _model_klas)
    d9 = _dodaj(k, b, pid, DUG)
    dok9 = next(d for d in b.tabele["predmet_dokumenti"] if d["id"] == d9)
    tekst9 = " ".join((dok9.get("tekst_sadrzaj") or "").split())
    tvrdnja = [t for t in b.tabele["predmet_dokazi"] if t["dokument_id"] == d9 and "118/26" in t["tvrdnja"]]
    ai = dok9.get("ai_tags")
    ekstr = (json.loads(ai) if isinstance(ai, str) else (ai or {})).get("_ekstrakcija") or {}
    _seg("02 kasna činjenica (iza 4.500. znaka) postaje tvrdnja sa izvorom, čitanje potpuno",
         tekst9.find("CINJENICA") > 4500 and len(tvrdnja) == 1 and ekstr.get("potpuno") is True and len(poruke) >= 2,
         str((tekst9.find("CINJENICA"), ekstr, len(poruke))))
    gv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    [dk] = [x for x in gv["dokazi"]["dokumenti"] if x["id"] == d9]
    _seg("03 graf dokaza: stanje čitanja izloženo", dk["klasifikacija"].get("citanje", {}).get("potpuno") is True)
    _seg("04 Genome vidi kasnu činjenicu kroz katalog tvrdnji, tekst označen kao skraćen",
         "118/26" in b.genome_pozivi[-1] and "TEKST SKRAĆEN" in b.genome_pozivi[-1])

    # 3. nova informacija → radnja sa izvorom
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    [rok] = [x for x in _rok_akcije(b, pid) if x["dokaz"].get("dokument_id") == d8]
    _seg("05 DOK-08 otvara radnju roka sa izvorom", rok["status"] == "open" and ROK in str(rok.get("rok") or rok["razlog"]))

    # 4. nacrt iz spisa sa procesnim stanjem
    snim, odlozeni = [], []

    def _model_savetnik(client, system, user_msg):
        snim.append(user_msg)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=NACRT))])

    async def _politika(f):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free", "krediti": 1}

    async def _stanje(u, e):
        return 100

    async def _kvalitet(t, tip):
        return {"confidence_score": 0.5, "detail": {}}

    class _Asyncio:
        def __getattr__(self, ime):
            return getattr(asyncio, ime)

        def create_task(self, coro):
            odlozeni.append(coro)
    monkeypatch.setattr(MA, "_pozovi_agent_api", _model_savetnik)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", kao_json(_model_savetnik))     # C3b: nacrt iz spisa = JSON
    monkeypatch.setattr(US, "get_policy", _politika)
    monkeypatch.setattr(US.UsageService, "balance", staticmethod(_stanje))
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    import app.services.retrieve as R
    monkeypatch.setattr(R, "retrieve_documents", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(MA, "asyncio", _Asyncio())
    b.podrazumevano.setdefault("staging_memory", {}).update({"status": "pending", "is_lawyer_approved": False,
                                                            "pinecone_indexed": False, "quality_detail": {}, "naziv": ""})
    r = k.post("/api/agents/run", json={"agent": "drafting", "predmet_id": pid,
                                        "task": "Sastavi izjasnjenje tuzioca na nalaz vestaka (DOK-05) i na DOK-06."}, headers=A)
    o = r.json()
    u = snim[-1]
    # C3b STRUCTURAL: procesno stanje servera u poruci. C3b FINAL CLOSURE: tekst modela je AI RADNI PREDLOG — ceo
    from shared.nacrt_za_sud import GRANICA
    natpis = "PROCESNO STANJE IZ SPISA — utvrdio SISTEM"
    _seg("06 procesno stanje servera u poruci nacrta (granica poverenja, pre zahteva)", r.status_code == 200
         and natpis in u and u.rfind(natpis) > u.rfind("[KRAJ DOKUMENATA]")
         and "izvod: Sud prihvata predlog za dopunu vestacenja." in u.split(natpis, 1)[1])
    _seg("07 AI radni predlog je ceo (protivrečna rečenica vidljiva advokatu, ništa nije obrisano)",
         o.get("status_teksta") == "AI_RADNI_PREDLOG" and "nije potrebna" in o.get("predlog_teksta", "")
         and "priznao dug (DOK-09)." in o.get("predlog_teksta", "") and "[IZOSTAVLJENO" not in o.get("odgovor", ""),
         o.get("predlog_teksta"))
    while odlozeni:
        asyncio.run(odlozeni.pop(0))
    [nac] = [s for s in b.tabele["staging_memory"] if s.get("predmet_id") == pid]
    prvobitan = str(nac["tekst"])                                      # red je isti objekat kao u bazi
    sud_deo, interno = prvobitan.split(GRANICA)
    # C3b FINAL CLOSURE: predlog se ne menja, ne odobrava i ne izvozi; dokument za sud = usvojene stavke + tekst advokata
    ok_predlog = (k.patch(f"/api/staging/{nac['id']}/tekst", json={"tekst": "x"}, headers=A).status_code == 409
                  and k.post(f"/api/staging/{nac['id']}/approve", headers=A).status_code == 409
                  and k.post(f"/api/staging/{nac['id']}/docx", headers=A).status_code == 409)
    from tests import c3b_usvajanje_pomoc as U
    stv = U.predlog(k, A, nac["id"])["predlog"]["stavke"]
    usvoji = [x["id"] for x in stv if "nije potrebna" not in x["tekst"] and "⚠" not in x["tekst"]]
    n_vektora = len(b.vektori)
    dok, dx = U.ceo_tok(k, A, nac["id"], usvoji,
                        izmeni=lambda t: U.bez_oznaka(t) + "\n\nTuzilac ce se izjasniti po izvrsenju dopune vestacenja.")
    sadrzaj = "\n".join(U.docx_pasusi(dx.content)) if dx.status_code == 200 else ""
    _seg("08 predlog nepromenljiv; usvojene stavke + tekst advokata -> odobren dokument za sud -> DOCX (bez promocije)",
         "Sud prihvata predlog za dopunu vestacenja." in interno and ok_predlog and dx.status_code == 200
         and "po izvrsenju dopune" in sadrzaj and "nije potrebna" not in sadrzaj and "INTERNE NAPOMENE" not in sadrzaj
         and "⚠" not in sadrzaj and len(b.vektori) == n_vektora,
         str({"predlog": ok_predlog, "docx": dx.status_code, "usvojeno": usvoji}))

    # 5. brisanje NEPOVEZANOG dokumenta: ništa se ne zatvara
    pre = {a["id"]: a["status"] for a in b.tabele["case_actions"] if a["predmet_id"] == pid}
    assert pre.get(rok["id"]) == "open" and list(pre.values()).count("open") >= 2      # ima šta da se (pogrešno) zatvori
    _obrisi(k, b, pid, doks["DOK-04"])
    _seg("09 brisanje nepovezanog dokumenta ne zatvara nijednu radnju",
         all(x["status"] == pre[x["id"]] for x in b.tabele["case_actions"] if x["id"] in pre))

    # 6. brisanje DOK-08: radnja zatvorena sa razlogom, izvorom i prethodnim stanjem
    n_aud = len(b.tabele["audit_immutable"])
    rok_pre = copy.deepcopy(rok)
    _obrisi(k, b, pid, d8)
    sada = next(x for x in b.tabele["case_actions"] if x["id"] == rok["id"])
    z = (sada.get("dokaz") or {}).get("zatvaranje") or {}
    aud = {c["id"]: c for a in b.tabele["audit_immutable"][n_aud:] if a.get("action") == "case_action_refreshed"
           for c in (a.get("metadata") or {}).get("closed_actions", [])}
    _seg("10 povučen izvor zatvara SAMO povezanu radnju, sa razlogom i prethodnim stanjem u auditu",
         sada["status"] == "closed" and z.get("razlog") == "IZVOR_POVUCEN" and z.get("source_id") == d8
         and aud.get(rok["id"], {}).get("prethodno", {}).get("razlog") == rok_pre["razlog"] and set(aud) == {rok["id"]})
    snimak = copy.deepcopy([x for x in b.tabele["case_actions"] if x["predmet_id"] == pid])
    from services.case_evolution import handle_case_changed
    from services.event_bus import Event, EventType
    [ev8] = [e for e in b.tabele["events"] if e.get("event_type") == "SourceInvalidated"
             and (e.get("payload") or {}).get("source_id") == d8]
    asyncio.run(handle_case_changed(Event(type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=pid,
                                          payload=ev8["payload"], event_id=ev8["id"])))
    _seg("11 ponovljena isporuka istog povlačenja ne menja ništa",
         [x for x in b.tabele["case_actions"] if x["predmet_id"] == pid] == snimak)

    # 7. izolacija
    _seg("12 korisnik B ne vidi ni ne menja ništa od predmeta A",
         all(k.get(u2, headers=B).status_code in (403, 404) for u2 in
             (f"/api/predmeti/{pid}", f"/api/predmeti/{pid}/genome-v2", f"/api/staging/{nac['id']}",
              f"/api/case-actions/predmeti/{pid}"))
         and k.delete(f"/api/predmeti/{pid}/dokumenti/{d9}", headers=B).status_code in (403, 404)
         and any(d["id"] == d9 for d in b.tabele["predmet_dokumenti"]))
    print("\nSEGMENTI:", ascii([(i, ok) for i, ok in SEGMENTI]))
