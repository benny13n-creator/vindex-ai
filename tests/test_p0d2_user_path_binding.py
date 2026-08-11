# -*- coding: utf-8 -*-
"""
P0-D2 — vezivanje korisničkog toka za identitet predmeta.

ŠTA JE OVAJ SPRINT ZATVORIO

Prethodni sprint (P0-D, `0bb847be`) je dokazao da backend MOŽE da rezonuje nad
celim predmetom. Ali `static/vindex.js:3590` je slao samo `{opis_predmeta}` —
pa je ispravka bila uspavana u stvarnom korisničkom toku. Sistem je izgledao
ispravno dok je tiho radio u osiromašenom režimu. To je tačno lažno-zeleno
ponašanje koje ovaj program uklanja.

ODAKLE DOLAZI ID — I ZAŠTO BAŠ ODATLE

Ne iz `activePredmetId`. Ta promenljiva je mutabilna i menja se čim korisnik
otvori drugi predmet; analiza traje 60-90 s, pa bi se rezultat vezao za predmet
koji je korisnik u međuvremenu otvorio.

Umesto toga: `_predAutoFill` (`vindex.js:9617`) već upisuje
`el.dataset.predId = activePredmetId` na polje `strat-tekst` kad ga popuni iz
predmeta. Taj atribut prati POREKLO TEKSTA, ne trenutni UI izbor. Ako je
advokat sam nalepio tekst, atributa nema i analiza se ispravno ne vezuje ni za
jedan predmet.

Čita se PRE prvog `await`, pa ga nijedan asinhroni korak ne može promeniti.

NAJVAŽNIJI TEST U FAJLU

`test_c_alfa_ne_vidi_betine_dokumente`. Ne proverava da `predmet_id` postoji u
telu zahteva — proverava da ISPRAVAN predmet stigne do rezonovanja, i da
dokumenti drugog predmeta u njega ne uđu.
"""
import json
import os
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija  # noqa: E402

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VINDEX = os.path.join(_KOREN, "static", "vindex.js")

_UID = "11111111-1111-1111-1111-111111111111"
_UID_DRUGI = "99999999-9999-9999-9999-999999999999"

ALFA_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BETA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

ALFA_OPIS = "CASE-ALPHA-OPIS-MARKER-7719"
ALFA_DOKUMENT = "CASE-ALPHA-DOKUMENT-MARKER-4402"
BETA_OPIS = "CASE-BETA-OPIS-MARKER-8815"
BETA_DOKUMENT = "CASE-BETA-DOKUMENT-MARKER-2036"

_OPIS_ZAHTEVA = (
    f"{ALFA_OPIS}. Stranka tvrdi da je ugovor raskinut 15.07.2026. zbog kašnjenja u isporuci. "
    "Protivna strana osporava osnovanost raskida i tvrdi da je rok produžen usmenim dogovorom. "
    "Vrednost spora je 4.200.000 dinara, postupak je pred Privrednim sudom u prvom stepenu."
)


def _polje(v):
    return {"value": v, "source": "test", "owner": "test", "refresh": "test",
            "timestamp": "2026-08-11T00:00:00+00:00"}


_KONTEKSTI = {
    ALFA_ID: {
        "case_identity": _polje({"naziv": "Spor ALFA", "tip_postupka": "privredni"}),
        "relevant_documents": _polje({"included": [
            {"naziv": "alfa-ugovor.pdf", "excerpt": f"{ALFA_DOKUMENT}: Član 7 određuje rok od 30 dana."},
        ]}),
    },
    BETA_ID: {
        "case_identity": _polje({"naziv": "Spor BETA", "tip_postupka": "radni"}),
        "relevant_documents": _polje({"included": [
            {"naziv": "beta-otkaz.pdf", "excerpt": f"{BETA_DOKUMENT}: Rešenje o otkazu ugovora o radu."},
        ]}),
    },
}


async def _lazni_build_case_context(predmet_id, uid, supa, include_documents=True):
    """Vraća kontekst PO ID-u — time se dokazuje da ID stvarno rutira izbor.

    Da je test mock-ovao jedan fiksni kontekst, prošao bi i da backend ignoriše
    `predmet_id` i uvek dovuče isti predmet. Ovako ne može.
    """
    if predmet_id not in _KONTEKSTI:
        return {"error": "predmet_not_found", "predmet_id": predmet_id}
    return _KONTEKSTI[predmet_id]


class _Hvatac:
    def __init__(self):
        self.pozivi = []

    def __call__(self, client, **kwargs):
        poruke = kwargs.get("messages") or []
        self.pozivi.append(next((p["content"] for p in poruke if p["role"] == "user"), ""))
        m = MagicMock()
        m.usage = None
        m.choices = [MagicMock(message=MagicMock(content=json.dumps({"confidence": "SREDNJA"})))]
        return m


async def _pokreni_ceo_lanac(predmet_id, uid=_UID):
    """Ruta → kapija → build_case_context → render → orkestrator → prompt.

    Mock-uje se SAMO baza. Sve između — kapija, izbor konteksta, serijalizacija,
    sastavljanje dokazne osnove, propagacija kroz svih 8 GPT poziva — izvršava
    se stvarnim kodom.
    """
    import routers.strategija as rs

    h = _Hvatac()
    with patch("shared.case_context.build_case_context", new=_lazni_build_case_context):
        blok = await rs._kanonski_kontekst_blok(predmet_id, uid)

    with patch("strategija._pozovi_strategija_api", side_effect=h):
        strategija.orkestrator_kompletna_analiza_sync(
            _OPIS_ZAHTEVA, "sk-test", None, None, case_context_blok=blok,
        )
    return blok, h.pozivi


# ─── 1. UGOVOR FRONTENDA ────────────────────────────────────────────────────

def test_a_frontend_salje_predmet_id_iz_porekla_teksta():
    """Vrednost mora poticati iz `dataset.predId`, ne iz mutabilne globalne.

    Repo nema JS test framework (`tests/test_iron_lawyer_frontend_fixes.py:5-10`
    to i dokumentuje), pa se ugovor proverava inspekcijom izvora — isti obrazac
    kao svaki drugi frontend test ovde.
    """
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(r"async function stratOrkestratorPokreni\(\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "stratOrkestratorPokreni nije pronađen"
    telo = m.group(1)

    assert "dataset.predId" in telo, (
        "ID predmeta se ne uzima iz porekla teksta (`dataset.predId`) — ako se "
        "čita `activePredmetId`, analiza se veže za predmet koji je korisnik "
        "otvorio U MEĐUVREMENU, a ne za onaj iz kog je tekst"
    )
    assert "predmet_id:" in telo, "predmet_id se ne šalje u telu zahteva"


def _telo_bez_komentara(js: str, ime: str) -> str:
    """Telo funkcije sa uklonjenim `//` komentarima.

    Nužno, i to je mutaciono testiranje dokazalo: prva verzija `test_b` je
    poredila pozicije u KOMENTARU iznad koda. U tom komentaru se `dataset.predId`
    pominje pre reči `await`, pa je test prolazio bez obzira na to gde se
    vrednost stvarno čita — mutacija koja je premestila čitanje iza `await`-a
    nije ga oborila. Test je merio tekst, ne program.
    """
    m = re.search(r"async function " + re.escape(ime) + r"\(\)\s*\{(.*?)\n\}", js, re.S)
    assert m, f"{ime} nije pronađena"
    return "\n".join(
        l for l in m.group(1).splitlines() if not l.strip().startswith("//")
    )


def test_b_id_se_hvata_PRE_prvog_await():
    """Ako se čita posle `await`, mutabilno stanje se moglo promeniti.

    Ovo je razlika između „šalje ispravan ID" i „šalje ID koji je bio ispravan
    u trenutku klika".
    """
    js = open(_VINDEX, encoding="utf-8").read()
    kod = _telo_bez_komentara(js, "stratOrkestratorPokreni")
    poz_capture = kod.index("dataset.predId")
    poz_prvi_await = kod.index("await")
    assert poz_capture < poz_prvi_await, (
        "predmet_id se čita POSLE prvog await-a — do tada je korisnik mogao "
        "promeniti predmet"
    )


def test_c_frontend_ne_koristi_activePredmetId_za_ovu_analizu():
    """Negativna tvrdnja: mutabilna globalna se NE sme koristiti ovde."""
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(r"async function stratOrkestratorPokreni\(\)\s*\{(.*?)\n\}", js, re.S)
    telo = m.group(1)
    # Dozvoljeno je pominjanje u komentaru koji objašnjava ZAŠTO se ne koristi.
    kod = "\n".join(l for l in telo.splitlines() if not l.strip().startswith("//"))
    assert "activePredmetId" not in kod, (
        "stratOrkestratorPokreni čita `activePredmetId` — to je mutabilno stanje"
    )


# ─── 2. VEZIVANJE IDENTITETA — najvažniji test ──────────────────────────────

@pytest.mark.asyncio
async def test_d_alfa_ne_vidi_betine_dokumente():
    """Najjači dokaz sprinta.

    Ne proverava „`predmet_id` postoji u telu" — proverava da ISPRAVAN predmet
    stigne do rezonovanja i da dokumenti drugog predmeta u njega ne uđu.
    """
    blok, poruke = await _pokreni_ceo_lanac(ALFA_ID)

    assert ALFA_DOKUMENT in blok, "Alfin dokument nije u kanonskom kontekstu"
    assert BETA_DOKUMENT not in blok, "Betin dokument je procureo u Alfin kontekst"

    for i, p in enumerate(poruke, start=1):
        assert ALFA_OPIS in p, f"GPT poziv #{i} ne vidi opis predmeta"
        assert ALFA_DOKUMENT in p, f"GPT poziv #{i} ne vidi Alfin dokument"
        assert BETA_DOKUMENT not in p, f"GPT poziv #{i} SADRŽI Betin dokument"
        assert BETA_OPIS not in p, f"GPT poziv #{i} SADRŽI Betin opis"


@pytest.mark.asyncio
async def test_e_beta_ne_vidi_alfine_dokumente():
    """Isti test u suprotnom smeru — inače bi prolazio i da je kontekst fiksan."""
    blok, poruke = await _pokreni_ceo_lanac(BETA_ID)
    assert BETA_DOKUMENT in blok
    assert ALFA_DOKUMENT not in blok
    for p in poruke:
        assert BETA_DOKUMENT in p
        assert ALFA_DOKUMENT not in p


# ─── 3. NAPADI ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_f_nepoznat_predmet_id_ne_dovlaci_nicij_kontekst():
    """`build_case_context` na tuđi/nepostojeći id vraća `{"error": ...}`, ne 404.

    Ako bi taj dict prošao kroz serijalizator, model bi dobio oznaku bez
    sadržaja. Mora dati prazan blok.
    """
    blok, poruke = await _pokreni_ceo_lanac("cccccccc-cccc-cccc-cccc-cccccccccccc")
    assert blok == "", "nepoznat predmet je proizveo kontekst"
    for p in poruke:
        assert ALFA_DOKUMENT not in p and BETA_DOKUMENT not in p


@pytest.mark.asyncio
@pytest.mark.parametrize("los_id", [None, "", "   ", "nije-uuid", "'; DROP TABLE predmeti;--"])
async def test_g_los_predmet_id_ne_obara_analizu_i_ne_vezuje_kontekst(los_id):
    """Analiza ne sme pući, ali ni tiho tvrditi da je utemeljena."""
    blok, poruke = await _pokreni_ceo_lanac(los_id)
    assert blok == ""
    assert poruke, "analiza nije uopšte pokrenuta"
    assert ALFA_OPIS in poruke[0], "opis predmeta je izgubljen"


@pytest.mark.asyncio
async def test_h_tudji_predmet_daje_404_pre_kreiranja_posla():
    """Kapija stoji u ruti, pre posla i pre naplate.

    Redosled je ovde bitniji od postojanja provere: da kapija stoji posle
    `create_job_deduped`, tuđi id bi već pokrenuo posao i naplatu.
    """
    import routers.strategija as rs

    redosled = []

    async def _kapija(pid, uid):
        redosled.append("kapija")
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    def _job(*a, **k):
        redosled.append("job")
        return ("job-1", False)

    req = rs.OrkestratorRequest(opis_predmeta="X" * 150, predmet_id=BETA_ID)
    with patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", new=_kapija), \
         patch("routers.jobs.create_job_deduped", new=_job), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()):
        with pytest.raises(HTTPException) as e:
            await rs.post_kompletna_analiza.__wrapped__(
                req=req, request=MagicMock(), background_tasks=MagicMock(),
                user={"user_id": _UID_DRUGI, "email": "drugi@test.rs"},
            )
    assert e.value.status_code == 404
    assert redosled == ["kapija"], f"posao je pokrenut uprkos odbijenom id-u: {redosled}"


# ─── 4. DEGRADACIJA MORA BITI VIDLJIVA ──────────────────────────────────────

def test_i_odgovor_nosi_poreklo_konteksta():
    """Bez `predmet_id` analiza i dalje radi — ali to mora biti VIDLJIVO.

    Tiha degradacija na „samo opis" je isto lažno-zeleno ponašanje kao i
    netačna tvrdnja o utemeljenosti.
    """
    from routers.strategija import _advisory_provenance

    sa = _advisory_provenance("kompletna_analiza", predmet_id=ALFA_ID, kontekst_ucitan=True)
    assert sa["kontekst_predmeta"] == "kanonski"
    assert sa["predmet_id"] == ALFA_ID
    assert "praćenim predmetom" in sa["napomena"]

    bez = _advisory_provenance("kompletna_analiza")
    assert bez["kontekst_predmeta"] == "samo_opis"
    assert bez["predmet_id"] is None
    assert "nije provera protiv" in bez["napomena"]


def test_j_predmet_id_se_ne_prijavljuje_ako_kontekst_nije_ucitan():
    """`predmet_id` prosleđen ≠ kontekst izgrađen.

    Mogao je proći kapiju a kontekst pasti (prazan predmet, greška baze). Odgovor
    tada NE SME tvrditi utemeljenost.
    """
    from routers.strategija import _advisory_provenance
    adv = _advisory_provenance("kompletna_analiza", predmet_id=ALFA_ID, kontekst_ucitan=False)
    assert adv["kontekst_predmeta"] == "samo_opis"
    assert adv["predmet_id"] is None, (
        "odgovor prijavljuje predmet_id iako kontekst nije izgrađen — to bi "
        "advokatu reklo da je AI video spis koji nije video"
    )


def test_k_frontend_prikazuje_poreklo_konteksta():
    """Signal koji niko ne vidi nije signal.

    `_ai_advisory` se do ovog sprinta NIJE renderovao nigde u frontendu — isti
    obrazac kao `izvori` pre Task 1: backend šalje poreklo, UI ga baca.
    """
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(r"function renderKompletnaAnaliza\(data\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "renderKompletnaAnaliza nije pronađen"
    telo = m.group(1)
    assert "kontekst_predmeta" in telo, "rezultat ne prikazuje poreklo konteksta"
    assert "samo nad unetim tekstom" in telo, "osiromašen režim nije vidljiv korisniku"


# ─── 5. OSTALI POZIVAOCI NISU POKVARENI ─────────────────────────────────────

def test_l_stari_pozivaoci_advisory_ja_rade_nepromenjeno():
    """7 postojećih poziva prosleđuje samo `modul` pozicijski.

    Novi parametri su keyword-only baš zato da nijedan od njih ne mora da se
    menja — i da nijedan ne može da veže vrednost na pogrešno mesto.
    """
    import inspect
    from routers.strategija import _advisory_provenance

    p = inspect.signature(_advisory_provenance).parameters
    pozicijski = [i for i, x in p.items()
                  if x.kind in (x.POSITIONAL_ONLY, x.POSITIONAL_OR_KEYWORD)]
    assert pozicijski == ["modul", "model"], f"pozicijski redosled promenjen: {pozicijski}"
    assert p["predmet_id"].kind == p["predmet_id"].KEYWORD_ONLY
    assert p["kontekst_ucitan"].kind == p["kontekst_ucitan"].KEYWORD_ONLY

    stari = _advisory_provenance("red_team")
    assert stari["kontekst_predmeta"] == "samo_opis"
    assert stari["modul"] == "red_team"


# ─── 5b. RUPE KOJE SU MUTACIJE OTKRILE ──────────────────────────────────────

@pytest.mark.asyncio
async def test_m_ruta_prosledjuje_bas_req_predmet_id():
    """Mutacija M4 nije pala — nijedan test nije dokazivao OVU vezu.

    Zamena `_kanonski_kontekst_blok(req.predmet_id, uid)` sa `(None, uid)`
    prolazila je zeleno: svi testovi su gađali `_kanonski_kontekst_blok`
    direktno, nijedan nije proveravao šta mu ruta stvarno prosleđuje.
    """
    import routers.strategija as rs

    videno = {}

    async def _hvatac(pid, uid):
        videno["predmet_id"] = pid
        videno["uid"] = uid
        return ""

    req = rs.OrkestratorRequest(opis_predmeta="X" * 150, predmet_id=ALFA_ID)
    with patch("routers.strategija._kanonski_kontekst_blok", new=_hvatac), \
         patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", new=AsyncMock()), \
         patch("routers.jobs.create_job_deduped", return_value=("job-1", False)), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()), \
         patch("routers.strategija.orkestrator_kompletna_analiza_sync",
               return_value={"koraci": {}, "sinteza": {}}), \
         patch("routers.strategija.UsageService.consume", new=AsyncMock(return_value=10)), \
         patch("routers.strategija.log_cost_to_db", new=AsyncMock()):
        bt = MagicMock()
        await rs.post_kompletna_analiza.__wrapped__(
            req=req, request=MagicMock(), background_tasks=bt,
            user={"user_id": _UID, "email": "a@test.rs"},
        )
        # `add_task(run_in_background, jid, _run_analiza)` -- posao je samo
        # ZAKAZAN. Izvršava se ručno, jer se `predmet_id` prosleđuje tek unutra.
        assert bt.add_task.call_count == 1
        args = bt.add_task.call_args[0]
        await args[2]()

    assert videno.get("predmet_id") == ALFA_ID, (
        f"ruta ne prosleđuje req.predmet_id graditelju konteksta "
        f"(prosleđeno: {videno.get('predmet_id')!r})"
    )
    assert videno.get("uid") == _UID


def test_n_veza_sa_predmetom_puca_kad_se_tekst_zameni():
    """Rupa koju je frontend forenzika našla u MOJOJ implementaciji.

    `dataset.predId` se nikad nije brisao. Advokat otvori predmet A (polje se
    autofiluje), pa označi sve i nalepi tekst predmeta B — zahtev bi nosio
    `predmet_id` predmeta A uz opis predmeta B. Backend bi spojio dokumente
    jednog sa opisom drugog, a poruka o poreklu bi to POTVRDILA kao ispravno
    utemeljenu analizu. To je gore od problema koji `dataset.predId` rešava.
    """
    js = open(_VINDEX, encoding="utf-8").read()
    assert "_vxProveriVezuSaPredmetom" in js, "nema provere da tekst i dalje pripada predmetu"
    assert "dataset.predSig" in js, "nema potpisa autofilovanog teksta"

    # Postojanje funkcije nije dovoljno — mutacija M7 je uklonila POZIV i test je
    # i dalje prolazio. Provera mora da gađa mesto upotrebe, ne samo definiciju.
    m_listener = re.search(
        r"document\.addEventListener\('input',\s*function\(e\)\s*\{(.*?)\n\}\);", js, re.S
    )
    assert m_listener, "input listener nije pronađen"
    assert "_vxProveriVezuSaPredmetom(e.target)" in m_listener.group(1), (
        "provera veze se ne zove pri kucanju — funkcija postoji ali je mrtva, "
        "a `dataset.predId` opet preživljava zamenu teksta"
    )

    m = re.search(r"function _vxProveriVezuSaPredmetom\(el\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "_vxProveriVezuSaPredmetom nije pronađena"
    telo = m.group(1)
    assert "delete el.dataset.predId" in telo, "veza se ne prekida"
    assert "indexOf(potpis) !== 0" in telo, (
        "veza se ne proverava po prefiksu — dopisivanje detalja mora da je "
        "sačuva, zamena celog teksta da je prekine"
    )

    # Potpis se mora upisivati tamo gde se upisuje i sam ID.
    m2 = re.search(r"async function _predAutoFill\(fieldId, force\)\s*\{(.*?)\n\}", js, re.S)
    assert m2 and "dataset.predSig" in m2.group(1), (
        "_predAutoFill upisuje predId bez predSig — provera bi bila bez efekta"
    )


def test_o_provenance_kontekst_nosi_predmet_id():
    """Bez ovoga sistem radi ispravno ali to ne može da dokaže.

    `ai_forensics` ima kolonu `predmet_id`, puni se iz `case_context(...)` — a
    ostajala je NULL jer je `routers/strategija.py` bio JEDINI fajl koji taj
    context manager zove bez `predmet_id`. Court Predictor, Copilot, Case DNA,
    Drafting i Evidence ga svi prosleđuju.
    """
    import inspect
    import routers.strategija as rs
    src = inspect.getsource(rs.post_kompletna_analiza)
    tacka = src.index("_ai_case_ctx(")
    prozor = src[tacka:tacka + 400]
    assert "predmet_id=req.predmet_id" in prozor, (
        "provenance kontekst ne nosi predmet_id — ai_forensics red ostaje NULL "
        "i 'rezonovani predmet' nije trajno dokaziv"
    )


def test_p_trajni_audit_belezi_predmet_ali_ne_sadrzaj():
    """Hash-chained ledger mora znati NAD ČIM je analiza pokrenuta.

    Ali samo ID. `audit_immutable` je iza BEFORE UPDATE/DELETE trigera, pa bi
    tekst predmeta upisan ovde bio van domašaja zahteva za brisanje podataka.
    """
    import inspect
    import routers.strategija as rs
    src = inspect.getsource(rs._audit_strategija_durably)
    assert 'metadata={"predmet_id": predmet_id}' in src, "audit ne beleži predmet"
    for zabranjeno in ("opis_predmeta", "tekst", "dokumenti", "sadrzaj"):
        assert f'"{zabranjeno}"' not in src, (
            f"audit upisuje `{zabranjeno}` — u append-only tabelu iza trigera "
            f"ne sme ići sadržaj predmeta"
        )


# ─── 6. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ng_lanac_stvarno_prenosi_kontekst():
    """Bez ovoga bi svi testovi iznad prolazili i da je blok uvek prazan."""
    blok, poruke = await _pokreni_ceo_lanac(ALFA_ID)
    assert blok, "kanonski kontekst je prazan — lanac ne prenosi ništa"
    assert len(poruke) == 7, f"očekivano 7 GPT poziva, viđeno {len(poruke)}"


@pytest.mark.asyncio
async def test_ng_mock_konteksta_stvarno_razlikuje_predmete():
    """Dokaz da `_lazni_build_case_context` nije fiksan.

    Da vraća isti kontekst za svaki id, `test_d`/`test_e` ne bi dokazivali
    ništa o rutiranju.
    """
    a = await _lazni_build_case_context(ALFA_ID, _UID, None)
    b = await _lazni_build_case_context(BETA_ID, _UID, None)
    assert a != b
    assert ALFA_DOKUMENT in json.dumps(a, ensure_ascii=False)
    assert BETA_DOKUMENT in json.dumps(b, ensure_ascii=False)
