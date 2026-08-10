# -*- coding: utf-8 -*-
"""
P0-C — naplata kredita za operacije bez AI poziva (BTM-P0-14).

ŠTA JE PRONAĐENO

Otvaranje ekrana „Podešavanja" naplaćivalo je 1 AI kredit. Bez dugmeta, bez
potvrde: `settingsLoad()` (static/vindex.js:2265) bezuslovno zove
`confidenceAuditLoad()` (:2278) → `GET /api/audit/kalibracija` →
`UsageService.consume(..., "confidence_audit")`. A `services/confidence_auditor.py`
nema nijedan AI poziv — to je Brier proračun nad korisnikovim redovima.

Nije izolovan bug. Sedam naplatnih mesta naplaćuje bez dostižnog AI poziva.
Uzrok je jedan commit — `73083099` (2026-07-14), „wire PermissionService/
UsageService into all AI endpoints" — koji je kolonu `feature_registry.ai_model`
tretirao kao DOKAZ da AI poziv postoji, umesto da proveri kod.

ZAŠTO GA NIJEDNA POSTOJEĆA PROVERA NIJE UHVATILA

`scripts/validate_feature_registry.py:76` upozorava na „krediti>0 a `ai_model`
prazan" — tačno OBRNUTO od stvarnog defekta. Red koji samouvereno deklariše
`gpt-4o-mini` za funkciju bez AI prolazi svaku postojeću proveru.
`scripts/audit_dead_features.py` proverava samo postojanje ključa.

Zato je centralni test ovde DETEKTOR (`test_c_*`), ne popis današnjih imena.

DVA RAZLIČITA LEKA — I ZAŠTO

Ne može se sve popraviti u registry-ju. Ključ koji dele AI i ne-AI endpointi
mora se popraviti u KODU, jer bi `krediti=0` poklonio i stvarnu GPT potrošnju:

  registry (migracija 111)  confidence_audit, conflict_check,
                            da_wallet_risk_assessment  — sva mesta bez AI
  kod (ovaj commit)         case_commander:483, zastarelost_guardian:476
                            — ključ deljen sa endpointima koji zovu GPT
"""
import ast
import os
import re

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRACIJA = os.path.join(_KOREN, "migrations", "111_phantom_ai_charges.sql")

# Imena kroz koja u ovom repou ide poziv provajderu. `_pozovi_*_api` je
# dosledna konvencija za tanki `@llm_retry` wrapper oko SDK poziva.
_AI_TRAGOVI = (
    "OpenAI", "openai", "chat.completions", "embeddings.create",
    "embed_query", "embed_documents", "co.rerank", "AsyncOpenAI",
)
_AI_WRAPPER = re.compile(r"_pozovi_\w*_api\s*\(|_gpt_json\s*\(|_gpt_text\s*\(|_call_gpt\s*\(|_call_openai\s*\(")


def _funkcija_oko(tree, lineno):
    najbolja = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n.lineno <= lineno <= (n.end_lineno or n.lineno):
                if najbolja is None or n.lineno > najbolja.lineno:
                    najbolja = n
    return najbolja


def _consume_pozivi(tree):
    """Stvarni `UsageService.consume(...)` Call čvorovi, preko AST-a.

    NE tekstualna pretraga. Prvi nacrt ovog testa je tražio string
    `"UsageService.consume("` u telu funkcije i time uhvatio KOMENTAR koji
    objašnjava zašto je poziv uklonjen -- prijavio je popravljen endpoint kao
    pokvaren. Uz to je regex hvatao prvi string u liniji, pa je iz
    `consume(user["user_id"], ...)` izvlačio `user_id` umesto ključa funkcije.
    AST rešava oba: komentari ne postoje u stablu, a `feature_key` je 3.
    pozicioni argument bez obzira na prelome redova.
    """
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and f.attr == "consume"):
            continue
        vlasnik = f.value
        ime = getattr(vlasnik, "id", None) or getattr(vlasnik, "attr", None)
        if ime != "UsageService":
            continue
        kljuc = None
        if len(n.args) >= 3 and isinstance(n.args[2], ast.Constant) and isinstance(n.args[2].value, str):
            kljuc = n.args[2].value
        yield n, kljuc


def _fajl_ima_ai(src: str) -> bool:
    """Da li fajl uopšte sadrži ijedan trag poziva provajderu."""
    return any(t in src for t in _AI_TRAGOVI) or bool(_AI_WRAPPER.search(src))


def _consume_mesta(putanja):
    """Vraća [(linija, feature_key, ime_funkcije)] za fajlove BEZ ijednog AI traga.

    ZAŠTO BAŠ OVAJ KRITERIJUM

    Prvi nacrt je gledao samo telo funkcije koja sadrži `consume` — lažno je
    optužio ~30 endpointa čiji je AI poziv posredan (`post_red_team` zove
    `strategija.red_team_analiza_sync` iz drugog modula).

    Drugi nacrt je gradio tranzitivno zatvaranje po IMENIMA funkcija. Njega je
    oborila sopstvena negativna kontrola: proširivanje na sva referencirana
    imena učinilo je SVAKO naplatno mesto AI-dosežnim, pa detektor više ne bi
    uhvatio nijedan phantom — `test_c` je prolazio prazno. To je bio pravi
    kvar, ne kozmetika, i uhvaćen je jedino zato što negativna kontrola postoji.

    Treći i zadržani kriterijum je uži i merljiv: fajl koji naplacuje kredite
    a NEMA nijedan trag provajdera u celom svom sadržaju. To daje 8 kandidata,
    od kojih su 5 dokazano pravi (AI je u drugom modulu) i stoje u
    `_DOZVOLJENI` sa linijom dokaza. Signal je uzak, ali istinit — i hvata
    upravo obrazac koji je pustio `73083099`: endpoint bez ijednog AI poziva
    koji naplacuje jer Registry tako kaže.
    """
    src = open(putanja, encoding="utf-8").read()
    if "UsageService.consume" not in src:
        return []
    if _fajl_ima_ai(src):
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for cvor, kljuc in _consume_pozivi(tree):
        if kljuc is None:
            continue
        fn = _funkcija_oko(tree, cvor.lineno)
        out.append((cvor.lineno, kljuc, fn.name if fn else "?"))
    return out


def _svi_izvori():
    """Korpus za analizu.

    Moduli u KORENU su obavezni: `routers/web3.py` zove `web3_compliance.py`,
    a `routers/strategija.py` zove `strategija.py` — oba su u korenu repoa.
    Bez njih bi detektor gledao samo pola aplikacije.
    """
    korpus = []
    for pod in ("routers", "services", "shared", "app", "drafting", "analiza",
                "uploaded_doc", "klijenti", "nacrti"):
        d = os.path.join(_KOREN, pod)
        if not os.path.isdir(d):
            continue
        for koren, _, fajlovi in os.walk(d):
            if "__pycache__" in koren:
                continue
            for f in fajlovi:
                if f.endswith(".py"):
                    korpus.append(os.path.join(koren, f))
    for f in os.listdir(_KOREN):
        if f.endswith(".py") and not f.startswith(("test_", "diag_", "ingest_", "scrape_")):
            korpus.append(os.path.join(_KOREN, f))
    return korpus


# ─── 1. DVA MESTA POPRAVLJENA U KODU ────────────────────────────────────────

@pytest.mark.parametrize("fajl,funkcija", [
    ("routers/case_commander.py", "commander_quick_check"),
    ("routers/zastarelost.py", "guardian_scan"),
])
def test_a_ne_ai_endpoint_vise_ne_naplacuje(fajl, funkcija):
    """Ova dva endpointa nemaju AI poziv, a naplaćivala su 2 odnosno 1 kredit.

    `commander_quick_check` je poseban slučaj: njegov SOPSTVENI docstring
    (case_commander.py:463-464) kaže „Nema GPT poziva u ovom endpoint-u uopšte."
    Program Sigma Sprint 005 je uklonio GPT poziv i ostavio naplatu.
    """
    putanja = os.path.join(_KOREN, *fajl.split("/"))
    src = open(putanja, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funkcija), None)
    assert fn is not None, f"{funkcija} nije pronađena u {fajl}"
    naplate = [c.lineno for c, _ in _consume_pozivi(fn)]
    assert not naplate, (
        f"{fajl}::{funkcija} ponovo naplaćuje kredite (linija {naplate}), a nema AI poziv"
    )


@pytest.mark.parametrize("fajl,funkcija", [
    ("routers/case_commander.py", "commander_analiza"),
    ("routers/case_commander.py", "commander_checklist"),
    ("routers/zastarelost.py", "deadline_guardian"),
])
def test_b_ai_endpoint_ISTOG_kljuca_i_dalje_naplacuje(fajl, funkcija):
    """Negativna kontrola za obim popravke — i najvažniji test u fajlu.

    `case_commander` i `zastarelost_guardian` su DELJENI ključevi. Da je neko
    „popravio" phantom naplatu tako što je u registry-ju postavio `krediti=0`,
    ovi endpointi bi i dalje zvali GPT, ali besplatno. Ovaj test dokazuje da
    je popravka bila hirurška: naplata je uklonjena SAMO sa ne-AI endpointa.
    """
    putanja = os.path.join(_KOREN, *fajl.split("/"))
    src = open(putanja, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funkcija), None)
    assert fn is not None
    assert list(_consume_pozivi(fn)), (
        f"{fajl}::{funkcija} ZOVE GPT ali više ne naplaćuje -- stvarna AI "
        f"potrošnja je postala besplatna"
    )


# ─── 2. DETEKTOR RAZREDA ──────────────────────────────────────────
# Fajlovi bez ijednog AI traga koji ipak naplacuju. Svaki izuzetak nosi DOKAZ
# — tačnu liniju gde se AI zaista poziva u drugom modulu. Lista ne sme rasti
# bez tog dokaza; "verovatno zove AI negde" nije razlog.
_DOZVOLJENI = {
    "case_pipeline":      "AI u services/case_pipeline.py:37 (_pozovi_pipeline_api)",
    "copilot_ambient":    "AI u services/ambient_analyzer.py:62 (_pozovi_sugestije_api)",
    "interni_stavovi":    "OpenAI embeddings u interni_stavovi.py:62,94",
    "knowledge_graph":    "embedding upita u app/services/retrieve.py:610",
    "da_source_of_funds": "gpt-4o kroz web3_compliance.py:24 (_pozovi_web3_api)",
    # Grupa A — phantomi koje migracija 111 spusta na krediti=0. Ostaju ovde jer
    # `consume` poziv namerno OSTAJE (cuva telemetriju, cooldown i limite;
    # v. shared/usage.py:385 i :476), a cena se resava u Registry-ju.
    "confidence_audit":         "phantom; migracija 111 -> krediti=0, chargeable=false",
    "conflict_check":           "phantom; migracija 111 -> krediti=0, chargeable=false",
    "da_wallet_risk_assessment": "phantom; migracija 111 -> krediti=0, chargeable=false",
}


def test_c_detektor_naplate_bez_ai_poziva():
    """Trajna invarijanta: ako fajl naplacuje, negde mora postojati AI poziv.

    Ovo je provera koju projekat nije imao. `validate_feature_registry.py:76`
    proverava OBRNUTO (krediti>0 a ai_model prazan), pa red koji LAŽNO deklarise
    model prolazi čist — sto je i pustilo sedam mesta u produkciju.

    Ako padne sa novim imenom: NE dodaji ga u `_DOZVOLJENI` dok ne nadjes
    konkretnu liniju gde se AI stvarno poziva. Ako je ne nadjes, to je nalaz,
    ne lazna uzbuna — i cena mora u Registry na 0.
    """
    prekrsaji = []
    for putanja in _svi_izvori():
        for linija, kljuc, fn in _consume_mesta(putanja):
            if kljuc in _DOZVOLJENI:
                continue
            rel = os.path.relpath(putanja, _KOREN).replace("\\", "/")
            prekrsaji.append(f"{rel}:{linija} {fn}() -> naplacuje '{kljuc}', a fajl nema nijedan AI poziv")
    assert not prekrsaji, "naplata bez AI poziva:\n  " + "\n  ".join(sorted(prekrsaji))


def test_ng_detektor_stvarno_nalazi_kandidate():
    """Negativna kontrola — i ona koja je već jednom spasla ovaj test.

    Raniji nacrt detektora (tranzitivno zatvaranje po imenima) proglasio je
    SVAKO naplatno mesto AI-dosežnim, pa je `test_c` prolazio prazno i ne bi
    uhvatio nijedan phantom. Uhvatila ga je tačno ova provera.

    Zato: ako detektor prestane da vidi ijednog kandidata, on je pokvaren —
    bez obzira sto je `test_c` zelen.
    """
    kandidati = []
    for putanja in _svi_izvori():
        kandidati.extend(_consume_mesta(putanja))
    assert kandidati, "detektor ne vidi nijedan naplatni fajl bez AI — pokvaren je"
    kljucevi = {k for _, k, _ in kandidati}
    assert "confidence_audit" in kljucevi, (
        "detektor više ne vidi `confidence_audit` — poznat, dokazan phantom "
        "koji je pokrenuo ceo P0-C"
    )


# ─── 3. MIGRACIJA 111 — sadržaj i obim ──────────────────────────────────────

def test_d_migracija_cilja_kljuceve_koji_stvarno_postoje():
    """Ključ koji ne postoji u registry-ju bi značio da migracija tiho ne radi ništa.

    Ovo nije hipotetički rizik: prvi nacrt ove migracije koristio je
    `commander_quick`, `zastarelost_scan` i `wallet_provenance` -- imena
    izvedena iz naziva endpointa. Nijedno ne postoji; stvarni ključevi su
    `case_commander`, `zastarelost_guardian`, `da_wallet_risk_assessment`.
    """
    sql = open(_MIGRACIJA, encoding="utf-8").read()
    kljucevi = set(re.findall(r"'([a-z0-9_]+)'", sql.split("BEGIN;")[1].split("COMMIT;")[0]))
    kljucevi -= {"basic", "professional", "enterprise", "migration_111_phantom_ai_charges"}

    seed = ""
    for f in sorted(os.listdir(os.path.join(_KOREN, "migrations"))):
        if f.endswith(".sql"):
            seed += open(os.path.join(_KOREN, "migrations", f), encoding="utf-8").read()
    for k in kljucevi:
        assert f"'{k}'" in seed, f"migracija 111 cilja '{k}', a taj feature_key ne postoji nigde"


def test_e_migracija_NE_dira_deljene_kljuceve():
    """Grupa B se popravlja u kodu, ne u registry-ju.

    Ako neko doda `case_commander` ili `zastarelost_guardian` u UPDATE, stvarna
    GPT potrošnja na `commander_analiza`/`commander_checklist`/`deadline_guardian`
    postaje besplatna. To je skuplja greška od one koja se ispravlja.
    """
    sql = open(_MIGRACIJA, encoding="utf-8").read()
    telo = sql.split("BEGIN;")[1].split("COMMIT;")[0]
    for k in ("case_commander", "zastarelost_guardian"):
        assert f"'{k}'" not in telo, (
            f"migracija 111 dira deljeni ključ '{k}' -- to bi poklonilo stvarnu "
            f"GPT potrošnju besplatno"
        )


def test_f_namerno_besplatne_odluke_nisu_zahvacene():
    """`chargeable=false` znači „nema AI poziv", NE „besplatno kao poslovna odluka".

    Razlika je definisana u `migrations/070_feature_registry_feature_type.sql:29-34`.
    `morning_briefing`, `voice` i `sudska_praksa` su krediti=0 po poslovnoj
    odluci i moraju ostati `chargeable=true`.
    """
    sql = open(_MIGRACIJA, encoding="utf-8").read()
    telo = sql.split("BEGIN;")[1].split("COMMIT;")[0]
    for k in ("morning_briefing", "voice", "sudska_praksa"):
        assert f"'{k}'" not in telo, f"migracija 111 pogrešno zahvata namerno besplatan '{k}'"


def test_g_settings_ekran_ne_sme_naplacivati():
    """Ugovor koji je pokrenuo ceo P0-C: otvaranje Podešavanja je besplatno.

    `settingsLoad` (vindex.js:2265) bezuslovno zove `confidenceAuditLoad`.
    Dokle god je tako, `confidence_audit` mora biti besplatan -- ili se poziv
    mora učiniti uslovnim. Ovaj test pada ako se ijedno od to dvoje pokvari.
    """
    sql = open(_MIGRACIJA, encoding="utf-8").read()
    assert "'confidence_audit'" in sql and "krediti    = 0" in sql

    js = open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()
    m = re.search(r"function settingsLoad\s*\([^)]*\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "settingsLoad nije pronađen"
    if "confidenceAuditLoad()" not in m.group(1):
        pytest.skip("settingsLoad više ne zove confidenceAuditLoad -- ugovor je zatvoren drugim putem")
