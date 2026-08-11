# -*- coding: utf-8 -*-
"""
Wave 7 — A/B izolacija kroz STVARNI `build_case_context`, ne kroz mock.

ŠTA JE BILA RUPA U RANIJEM DOKAZU

`tests/test_p0d2_user_path_binding.py` dokazuje A/B izolaciju tako što ZAMENI
`build_case_context` funkcijom koja vraća različit kontekst po ID-u. To dokazuje
da ruta prosleđuje pravi ID i da se kontekst propagira kroz svih 7 GPT poziva —
ali NE dokazuje da sam `build_case_context` izoluje predmete, jer se nikad ne
izvršava.

Konkretno, nikad se nisu izvršili:
  - vlasnički filter `predmeti.user_id == uid` (`shared/case_context.py:161`)
  - `_fetch_raw` sa svojih 7 upita
  - `_select_documents` / `_excerpt` / `_fetch_document_texts`
  - `error` grana za tuđi/nepostojeći predmet (`:403`)

Ovde se mock-uje SAMO Supabase klijent. Sve iznad njega je stvarni kod.

ZAŠTO LAŽNA BAZA MORA STVARNO DA FILTRIRA

`tests/test_tau002_case_context.py:38-47` koristi `_FakeQuery` koji eksplicitno
no-op-uje sve `.eq()` osim `id` — i sam docstring to priznaje. Sa takvim
lažnjakom test vlasništva prolazi lažno, jer `user_id` filter nikad ništa ne
radi. Zato ovde `_Upit` primenjuje SVAKI filter koji dobije.

MARKERI
Svaki izvor nosi niz koji se ne pojavljuje nigde drugde. Test koji bi prošao i
kad se A i B zamene nije test izolacije.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija  # noqa: E402

# ─── Markeri ────────────────────────────────────────────────────────────────
ALFA_ID = "aaaaaaaa-0000-4000-8000-00000000000a"
BETA_ID = "bbbbbbbb-0000-4000-8000-00000000000b"
UID_A = "11111111-0000-4000-8000-000000000001"
UID_B = "22222222-0000-4000-8000-000000000002"

ALFA_MARKER = "FORENSIC_ALPHA_7A9"
BETA_MARKER = "FORENSIC_BETA_4K2"
ALFA_DOK = "ALPHA_SECRET_DOCUMENT_731"
BETA_DOK = "BETA_SECRET_DOCUMENT_842"

_OPIS = (
    "Stranka tvrdi da je ugovor raskinut zbog kašnjenja u isporuci, dok protivna strana "
    "osporava osnovanost raskida i tvrdi da je rok produžen usmenim dogovorom. Vrednost "
    "spora je 4.200.000 dinara, postupak je u prvom stepenu pred Privrednim sudom."
)


# ─── Lažna baza koja STVARNO filtrira ───────────────────────────────────────

class _Rez:
    def __init__(self, data):
        self.data = data


class _Upit:
    """Chainable lažnjak koji primenjuje SVAKI `.eq()` / `.in_()` filter.

    Za razliku od `_FakeQuery` u `test_tau002_case_context.py`, koji no-op-uje
    sve osim `id` — sa njim bi tvrdnja o vlasništvu prolazila lažno.
    """

    def __init__(self, redovi):
        self._redovi = list(redovi)
        self._f = {}
        self._in = {}
        self._single = False
        self._limit = None

    def select(self, *a, **k):
        return self

    def eq(self, polje, vrednost):
        self._f[polje] = vrednost
        return self

    def in_(self, polje, vrednosti):
        self._in[polje] = set(vrednosti)
        return self

    def is_(self, polje, vrednost):
        # `.is_("deleted_at", "null")` -> zadrži redove bez te vrednosti
        if vrednost in ("null", None):
            self._f[polje] = None
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def gte(self, *a, **k):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        red = self._redovi
        for polje, vrednost in self._f.items():
            red = [r for r in red if r.get(polje) == vrednost]
        for polje, dozvoljeni in self._in.items():
            red = [r for r in red if r.get(polje) in dozvoljeni]
        if self._limit:
            red = red[:self._limit]
        if self._single:
            return _Rez(red[0] if red else None)
        return _Rez(red)


def _baza():
    """Dva potpuno izolovana predmeta, različitih vlasnika, sa dokumentima."""
    tabele = {
        "predmeti": [
            {"id": ALFA_ID, "user_id": UID_A, "naziv": f"Spor {ALFA_MARKER}",
             "tip_postupka": "privredni", "sud": "Privredni sud", "status": "aktivan",
             "stranka": "DOO Alfa", "protivnik": "DOO Kontra-Alfa", "case_dna": None},
            {"id": BETA_ID, "user_id": UID_B, "naziv": f"Spor {BETA_MARKER}",
             "tip_postupka": "radni", "sud": "Osnovni sud", "status": "aktivan",
             "stranka": "DOO Beta", "protivnik": "DOO Kontra-Beta", "case_dna": None},
        ],
        "predmet_dokumenti": [
            {"id": "doc-a", "predmet_id": ALFA_ID, "naziv_fajla": "alfa-ugovor.pdf",
             "redni_broj": 1, "tip_dokaza": "ugovor", "status": "spreman",
             "created_at": "2026-08-01T00:00:00Z",
             "tekst_sadrzaj": f"{ALFA_DOK}: Član 7 ugovora određuje rok isporuke od 30 dana."},
            {"id": "doc-b", "predmet_id": BETA_ID, "naziv_fajla": "beta-otkaz.pdf",
             "redni_broj": 1, "tip_dokaza": "resenje", "status": "spreman",
             "created_at": "2026-08-01T00:00:00Z",
             "tekst_sadrzaj": f"{BETA_DOK}: Rešenje o otkazu ugovora o radu."},
        ],
        "predmet_dokazi": [], "rocista": [], "case_actions": [],
        "predmet_hronologija": [], "predmet_komentari": [],
    }
    supa = MagicMock()
    supa.table.side_effect = lambda ime: _Upit(tabele.get(ime, []))
    return supa


# ─── Hvatač GPT poziva ──────────────────────────────────────────────────────

class _Hvatac:
    def __init__(self):
        self.poruke = []

    def __call__(self, client, **kwargs):
        p = kwargs.get("messages") or []
        self.poruke.append(next((m["content"] for m in p if m["role"] == "user"), ""))
        m = MagicMock()
        m.usage = None
        m.model = "gpt-4o"
        poruka = MagicMock()
        poruka.content = json.dumps({"confidence": "SREDNJA", "summary": "ok"})
        poruka.tool_calls = None
        izbor = MagicMock()
        izbor.message = poruka
        m.choices = [izbor]
        return m


async def _ceo_lanac(predmet_id, uid):
    """`_kanonski_kontekst_blok` -> STVARNI build_case_context -> orkestrator."""
    import routers.strategija as rs

    with patch("shared.deps._get_supa", return_value=_baza()), \
         patch("routers.strategija._get_supa", return_value=_baza()):
        blok = await rs._kanonski_kontekst_blok(predmet_id, uid)

    h = _Hvatac()
    with patch("strategija._pozovi_strategija_api", side_effect=h):
        strategija.orkestrator_kompletna_analiza_sync(
            _OPIS, "sk-test", None, None, case_context_blok=blok,
        )
    return blok, h.poruke


# ─── 1. A/B IZOLACIJA KROZ STVARNU FUNKCIJU ────────────────────────────────

@pytest.mark.asyncio
async def test_a_alfa_vidi_samo_alfu():
    """RUN A. Stvarni `build_case_context`, stvarni vlasnički filter."""
    blok, poruke = await _ceo_lanac(ALFA_ID, UID_A)

    assert blok, "kanonski kontekst je prazan — lanac ne radi"
    assert ALFA_MARKER in blok and ALFA_DOK in blok
    assert BETA_MARKER not in blok and BETA_DOK not in blok

    assert len(poruke) == 7
    for i, p in enumerate(poruke, 1):
        assert ALFA_DOK in p, f"GPT poziv #{i} ne vidi Alfin dokument"
        assert BETA_DOK not in p, f"GPT poziv #{i} SADRŽI Betin dokument"
        assert BETA_MARKER not in p, f"GPT poziv #{i} SADRŽI Betin marker"


@pytest.mark.asyncio
async def test_b_beta_vidi_samo_betu():
    """RUN B. Isto u suprotnom smeru — inače bi test prolazio i sa fiksnim kontekstom."""
    blok, poruke = await _ceo_lanac(BETA_ID, UID_B)
    assert BETA_MARKER in blok and BETA_DOK in blok
    assert ALFA_MARKER not in blok and ALFA_DOK not in blok
    for p in poruke:
        assert BETA_DOK in p and ALFA_DOK not in p


# ─── 2. VLASNIČKA MATRICA ───────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("uid,pid,sme", [
    (UID_A, ALFA_ID, True),
    (UID_A, BETA_ID, False),
    (UID_B, BETA_ID, True),
    (UID_B, ALFA_ID, False),
    (UID_A, "cccccccc-0000-4000-8000-00000000000c", False),
    (UID_A, "nije-uuid", False),
])
async def test_c_vlasnicka_matrica(uid, pid, sme):
    """Ključna razlika u odnosu na raniji dokaz.

    Ovde se izvršava STVARNI filter `predmeti.user_id == uid`
    (`shared/case_context.py:161`). Ranije je bio mock-ovan, pa se nikad nije
    proverio — a lažnjak u `test_tau002` `user_id` filter no-op-uje.
    """
    blok, poruke = await _ceo_lanac(pid, uid)
    if sme:
        assert blok, f"{uid[:8]} nije dobio SVOJ predmet {pid[:8]}"
    else:
        assert blok == "", (
            f"{uid[:8]} je dobio kontekst za {pid[:8]} koji mu NE pripada"
        )
        for p in poruke:
            assert ALFA_DOK not in p and BETA_DOK not in p, (
                "tuđi dokument je procureo u analizu"
            )


@pytest.mark.asyncio
async def test_d_tudji_predmet_ne_curi_ni_delimicno():
    """Najstroža tvrdnja: NIJEDAN atribut tuđeg predmeta ne sme se pojaviti.

    `build_case_context` lansira svih 7 upita pre svoje interne provere
    (`:158`), pa tuđi redovi prođu kroz memoriju procesa. Ovo dokazuje da ipak
    ne dospevaju u odgovor.
    """
    blok, poruke = await _ceo_lanac(BETA_ID, UID_A)   # A traži B
    assert blok == ""
    sve = blok + "\n".join(poruke)
    for tajna in (BETA_MARKER, BETA_DOK, "DOO Beta", "Osnovni sud", "beta-otkaz.pdf"):
        assert tajna not in sve, f"atribut tuđeg predmeta je procureo: {tajna}"


# ─── 3. KONKURENTNOST ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e_konkurentni_A_B_A_B_se_ne_mesaju():
    """Četiri istovremena posla u različitim taskovima.

    Ako bi kontekst curio kroz deljeno stanje (globalni keš, contextvar bez
    izolacije), ovo bi ga otkrilo.
    """
    import asyncio
    rezultati = await asyncio.gather(
        _ceo_lanac(ALFA_ID, UID_A),
        _ceo_lanac(BETA_ID, UID_B),
        _ceo_lanac(ALFA_ID, UID_A),
        _ceo_lanac(BETA_ID, UID_B),
    )
    for i, (blok, poruke) in enumerate(rezultati):
        ocekivan, zabranjen = (ALFA_DOK, BETA_DOK) if i % 2 == 0 else (BETA_DOK, ALFA_DOK)
        assert ocekivan in blok, f"posao #{i} izgubio svoj kontekst"
        assert zabranjen not in blok, f"posao #{i} dobio TUĐI kontekst"
        for p in poruke:
            assert zabranjen not in p


# ─── 4. DEDUPE NE SME SPOJITI RAZLIČITE PREDMETE ───────────────────────────

async def _dedupe_kljuc_iz_rute(predmet_id):
    """Vraća `dedupe_key` koji je STVARNA ruta poslala u `create_job_deduped`.

    Ključ se ne računa ovde — `routers/strategija.py:706-716` ga gradi, a ovde
    se samo presreće na jedinoj tački kroz koju prolazi (`create_job_deduped`
    kwarg). Sve što bi promenilo sastav ključa u produkciji odmah menja i ono
    što ova funkcija vrati.

    Mock-uje se isključivo ono što nije predmet merenja: vlasnička kapija,
    audit, tarifa/bilans i sam registar poslova. Izgradnja ključa se ne dira.
    """
    from fastapi import BackgroundTasks

    import routers.copilot_ambient as ca
    import routers.jobs as jobs
    import routers.strategija as rs
    import shared.permissions as perms

    uhvaceni = []

    def _lazni_create(uid, tip, *a, dedupe_key=None, **kw):
        uhvaceni.append(dedupe_key)
        return f"job-{len(uhvaceni)}", False

    async def _bez_kapije(pid, uid):
        return None

    async def _bez_audita(*a, **k):
        return None

    # `@limiter.limit` (slowapi) omotava rutu `functools.wraps`-om; `__wrapped__`
    # je sama funkcija endpointa. Rate limiter nije predmet ovog dokaza, a bez
    # zaobilaženja bi tražio pravi `Request` sa klijentskom adresom.
    ruta = getattr(rs.post_kompletna_analiza, "__wrapped__", rs.post_kompletna_analiza)

    with patch.object(jobs, "create_job_deduped", _lazni_create), \
         patch.object(ca, "_proveri_vlasnistvo_predmeta", _bez_kapije), \
         patch.object(rs, "_audit", _bez_audita), \
         patch.object(rs, "_audit_strategija_durably", lambda *a, **k: None), \
         patch.object(perms, "_is_founder", lambda *a, **k: True):
        zahtev = rs.OrkestratorRequest(opis_predmeta=_OPIS, predmet_id=predmet_id)
        odgovor = await ruta(
            zahtev,
            MagicMock(),
            BackgroundTasks(),
            user={"user_id": UID_A, "email": "advokat@vindex.rs"},
        )

    assert odgovor.status_code == 202, "ruta nije stigla do kreiranja posla"
    assert len(uhvaceni) == 1, f"create_job_deduped pozvan {len(uhvaceni)} puta"
    kljuc = uhvaceni[0]
    assert isinstance(kljuc, str) and len(kljuc) == 64, (
        f"dedupe ključ nije sha256 heks-niz: {kljuc!r} — ruta je promenila oblik "
        "identiteta posla, pa tvrdnje ispod više ne mere ono što misle"
    )
    return kljuc


@pytest.mark.asyncio
async def test_f_isti_tekst_razlicit_predmet_daje_razlicit_dedupe():
    """Isti opis nad različitim predmetima mora dati različit identitet posla.

    Da `predmet_id` nije u ključu, drugi zahtev bi dobio rezultat prvog — a
    kontekst je različit.

    WAVE 11 (2026-08-11) — ŠTA JE OVDE BILO PRE I ZAŠTO SE MENJA

    Raniji oblik ovog testa je u sopstvenom telu REIMPLEMENTIRAO sha256 formulu
    (`hashlib.sha256("\\x1f".join([_OPIS, repr([]), repr([]), pid or ""]))`) i
    poredio dve svoje kopije. Nikad nije dodirnuo `routers/strategija.py`, gde
    se ključ stvarno gradi. Da produkcija sutra izbaci `req.predmet_id` iz
    ključa, test bi ostao zelen — merio bi sopstvenu kopiju, ne original.
    Docstring je pritom tvrdio „Runtime provera, ne čitanje izvora", što nije
    bilo tačno ni u jednom smislu: nije čitao izvor, ali nije ni izvršavao
    produkcioni kod.

    Tvrdnje su iste tri, samo se sada mere nad ključem koji ruta STVARNO
    proizvede. Ime testa je zadržano jer se na njega poziva
    `tests/test_rc_beta_flows.py::test_d5` (koji istu stvar meri na nivou
    ponašanja rute — dva job_id-a).
    """
    alfa = await _dedupe_kljuc_iz_rute(ALFA_ID)
    beta = await _dedupe_kljuc_iz_rute(BETA_ID)
    bez_predmeta = await _dedupe_kljuc_iz_rute(None)

    assert alfa != beta, (
        "dedupe ključ koji produkcija gradi ne razlikuje predmete — druga "
        "analiza istog opisa nad DRUGIM predmetom bi vratila rezultat prve"
    )
    assert alfa == await _dedupe_kljuc_iz_rute(ALFA_ID), (
        "isti zahtev daje različit ključ — dedupe uopšte ne bi hvatao dvoklik"
    )
    assert bez_predmeta != alfa, (
        "analiza bez predmeta i analiza nad predmetom dele ključ"
    )


# ─── 5. NEGATIVNE KONTROLE NAD SAMIM HARNESS-om ────────────────────────────

@pytest.mark.asyncio
async def test_ng_lazna_baza_stvarno_filtrira_po_user_id():
    """Bez ovoga bi cela vlasnička matrica bila bezvredna.

    Dokazuje da `_Upit` primenjuje `user_id`, za razliku od `_FakeQuery` u
    `test_tau002_case_context.py`, koji ga eksplicitno ignoriše.
    """
    supa = _baza()
    tacan = supa.table("predmeti").select("*").eq("id", ALFA_ID).eq("user_id", UID_A).maybe_single().execute()
    tudji = supa.table("predmeti").select("*").eq("id", ALFA_ID).eq("user_id", UID_B).maybe_single().execute()
    assert tacan.data is not None, "lažna baza ne vraća sopstveni predmet"
    assert tudji.data is None, "lažna baza IGNORIŠE user_id — matrica bi lažno prolazila"


@pytest.mark.asyncio
async def test_ng_markeri_su_stvarno_razliciti():
    """Test koji bi prošao i kad se A i B zamene nije test izolacije."""
    a_blok, _ = await _ceo_lanac(ALFA_ID, UID_A)
    b_blok, _ = await _ceo_lanac(BETA_ID, UID_B)
    assert a_blok != b_blok
    assert ALFA_DOK in a_blok and ALFA_DOK not in b_blok
    assert BETA_DOK in b_blok and BETA_DOK not in a_blok
