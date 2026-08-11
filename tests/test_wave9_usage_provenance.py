# -*- coding: utf-8 -*-
"""
Wave 9 §17 — feature_usage_log provenance (predmet_id + correlation_id).

ŠTA JE OVDE IZMERENO, A NE PRETPOSTAVLJENO

Polazna hipoteza zadatka je bila: „ako `UsageService.consume` čita
predmet_id/correlation_id iz `shared/ai_provenance` contextvar-a, dobijamo
linkage bez ijedne izmene pozivnog mesta."

Merenje je pokazalo da to važi SAMO za `correlation_id`:

  * `correlation_id` — postavlja ga `set_request_context` na auth
    chokepoint-u, `.set()` BEZ restore-a, pa važi za ceo request i preživljava
    `asyncio.to_thread` i `asyncio.create_task`. Dostupan u trenutku naplate.
    Test `test_correlation_id_je_dostupan_i_izvan_case_context_bloka` to i
    dokazuje.

  * `predmet_id` — živi u `_case_ctx`, koji `case_context` VRAĆA na prethodnu
    vrednost pri izlasku iz `with` bloka. AST prebrojavanje svih poziva
    `UsageService.consume` u repou: 0 od 113 leži unutar takvog bloka. Dakle
    contextvar bi u praksi uvek bio None. Zato je dodat eksplicitan
    keyword-only `consume(predmet_id=...)` — opcion, sa default-om, tako da
    nijedan postojeći pozivalac ne mora da se menja.

CRVENA LINIJA KOJU OVI TESTOVI ČUVAJU

Telemetrija ne sme nikad da obori naplatu, niti da promeni naplaćeni iznos.
Svaki test ispod meri jedno od to dvoje.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import shared.usage as usage  # noqa: E402
from shared.ai_provenance import case_context, set_request_context  # noqa: E402


# ─── Lažni Supabase klijent koji hvata payload upisa ────────────────────────

class _LazniSupa:
    """Beleži svaki insert payload. `odbij_kolone` simulira PostgREST pre
    pokretanja migracije 112 — poruka je doslovno onog oblika koji PostgREST
    stvarno vraća (PGRST204 / „schema cache"), ne izmišljena."""

    def __init__(self, odbij_kolone: set[str] | None = None):
        self.payloads: list[dict] = []
        self.odbij_kolone = odbij_kolone or set()
        self._tekuci: dict = {}

    def table(self, _naziv):
        return self

    def insert(self, payload):
        self._tekuci = dict(payload)
        return self

    def execute(self):
        nepoznate = self.odbij_kolone & set(self._tekuci)
        if nepoznate:
            kol = sorted(nepoznate)[0]
            raise RuntimeError(
                "{'code': 'PGRST204', 'message': \"Could not find the "
                f"'{kol}' column of 'feature_usage_log' in the schema cache\"}}"
            )
        self.payloads.append(self._tekuci)
        return SimpleNamespace(data=[{}])


@pytest.fixture
def supa(monkeypatch):
    s = _LazniSupa()
    monkeypatch.setattr(usage, "_get_supa", lambda: s)
    return s


@pytest.fixture(autouse=True)
def cist_kontekst():
    """Svaki test kreće od STVARNO praznog konteksta.

    PAŽNJA: `set_request_context(correlation_id=None)` NE prazni kontekst —
    ono kuje NOVI correlation_id (`cid = correlation_id or new_correlation_id()`).
    To je ispravno produkciono ponašanje, ali znači da se „nema konteksta"
    scenario mora napraviti direktnim pražnjenjem contextvar-a, kao kod
    pozadinskog posla koji nikad nije prošao kroz HTTP auth chokepoint.
    """
    import shared.ai_provenance as prov
    t_req = prov._request_ctx.set({})
    t_case = prov._case_ctx.set({})
    yield
    prov._request_ctx.reset(t_req)
    prov._case_ctx.reset(t_case)


# ── RC-TEST-DEBT-001 (Release Candidate gate) — PRODUKCIONO-REALNE VREDNOSTI ──
#
# Ovi testovi su koristili `"PRED-42"` kao `predmet_id`. Nad lažnim Supabase
# klijentom to prolazi, ali PRODUKCIONA šema to ODBIJA: `predmeti.id` je UUID
# (`supabase_setup.sql:301`), a `feature_usage_log.predmet_id` je `uuid`
# (migracija 112). PostgreSQL na takvu vrednost diže 22P02
# `invalid input syntax for type uuid`.
#
# Posledica je bila teža nego gubitak jednog polja: `shared/usage._nedostaje_kolona()`
# ne prepoznaje 22P02, pa se uzak fallback ne aktivira i CEO red naplatne
# telemetrije tiho nestaje — zajedno sa `user_id`, `feature_key` i
# `krediti_potroseni`.
#
# `shared/usage.py` sada validira UUID pre upisa i odbacuje samo neispravnu
# vrednost umesto celog reda. Ovi testovi zato koriste vrednosti koje produkcija
# stvarno prihvata. TVRDNJE SU NEPROMENJENE — menja se samo ulaz, tako da test
# meri ono što tvrdi da meri.
#
# Ponašanje za NEISPRAVAN `predmet_id` (polje se odbacuje, red i naplata ostaju)
# pokriveno je u `tests/test_rc_billing_gate.py` (U7), nad pravim PostgreSQL-om.
UUID_PREDMETA = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
UUID_DRUGOG = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
UUID_IZ_KONTEKSTA = "cccccccc-3333-4333-8333-cccccccccccc"
UUID_EKSPLICITAN = "dddddddd-4444-4444-8444-dddddddddddd"


def _pozovi_log(**kw):
    osnova = dict(
        user_id="u-1", feature="strategija", credits_spent=6,
        ai_model="gpt-4o", estimated_cost_usd=0.02,
        tokens_prompt=100, tokens_completion=50, latency_ms=1200,
    )
    osnova.update(kw)
    return asyncio.run(usage._log_usage_event(**osnova))


# ─── 1. SA kontekstom → obe vrednosti su upisane ────────────────────────────

def test_sa_case_context_upisuje_obe_vrednosti(supa):
    async def _scenario():
        set_request_context(user_id="u-1", correlation_id="CID-TEST-1")
        with case_context(predmet_id=UUID_PREDMETA, module_name="strategija"):
            await usage._log_usage_event(
                "u-1", "strategija", 6, "gpt-4o", 0.02, 100, 50, 1200,
            )

    asyncio.run(_scenario())

    assert len(supa.payloads) == 1
    red = supa.payloads[0]
    assert red["predmet_id"] == UUID_PREDMETA
    assert red["correlation_id"] == "CID-TEST-1"
    # Naplatna polja netaknuta.
    assert red["krediti_potroseni"] == 6
    assert red["feature_key"] == "strategija"


def test_eksplicitan_predmet_id_argument_radi_i_bez_case_context(supa):
    """Stvarni put za 113 postojećih poziva: `consume(predmet_id=...)`."""
    set_request_context(user_id="u-1", correlation_id="CID-2")
    _pozovi_log(predmet_id=UUID_DRUGOG)

    red = supa.payloads[0]
    assert red["predmet_id"] == UUID_DRUGOG
    assert red["correlation_id"] == "CID-2"


def test_eksplicitan_argument_ima_prednost_nad_kontekstom(supa):
    async def _scenario():
        set_request_context(user_id="u-1", correlation_id="CID-3")
        with case_context(predmet_id=UUID_IZ_KONTEKSTA):
            await usage._log_usage_event(
                "u-1", "strategija", 6, None, None, None, None, None,
                predmet_id=UUID_EKSPLICITAN,
            )

    asyncio.run(_scenario())
    assert supa.payloads[0]["predmet_id"] == UUID_EKSPLICITAN


# ─── 2. IZMERENO STANJE: predmet_id nije dostupan izvan bloka ───────────────

def test_correlation_id_je_dostupan_i_izvan_case_context_bloka(supa):
    """Dokazuje ASIMETRIJU koja je opravdala dizajn.

    `correlation_id` preživi izlazak iz `with` bloka (postavljen na request
    nivou, bez restore-a), `predmet_id` ne preživi (case scope se resetuje).
    Zato je correlation_id jedini deo lanca koji radi bez izmene pozivaoca —
    i zato predmet_id ima eksplicitan argument."""
    async def _scenario():
        set_request_context(user_id="u-1", correlation_id="CID-4")
        with case_context(predmet_id="PRED-NESTAJE"):
            pass
        # Ovde se consume() stvarno poziva u svih 113 slučajeva u repou.
        await usage._log_usage_event(
            "u-1", "strategija", 6, None, None, None, None, None,
        )

    asyncio.run(_scenario())
    red = supa.payloads[0]
    assert red["correlation_id"] == "CID-4", "correlation_id mora preživeti"
    assert "predmet_id" not in red, (
        "predmet_id NE SME doći iz konteksta posle izlaska iz case_context — "
        "ako ovo prođe, izmereno stanje se promenilo i dizajn treba revidirati."
    )


def test_bez_konteksta_upis_prolazi_a_kolone_su_odsutne(supa):
    """Bez ijednog konteksta — ponašanje mora biti identično stanju pre Wave 9."""
    _pozovi_log()

    assert len(supa.payloads) == 1
    red = supa.payloads[0]
    assert "predmet_id" not in red
    assert "correlation_id" not in red
    # Tačno originalni skup kolona iz migracije 065.
    assert set(red) == {
        "user_id", "feature_key", "krediti_potroseni", "ai_model",
        "estimated_cost_usd", "tokens_prompt", "tokens_completion", "latency_ms",
    }


# ─── 3. FAIL-SOFT: greška u čitanju konteksta ne obara naplatu ──────────────

def test_izuzetak_u_citanju_konteksta_ne_obara_upis(supa, monkeypatch):
    import shared.ai_provenance as prov

    def _pukni():
        raise RuntimeError("contextvar eksplodirao")

    monkeypatch.setattr(prov, "current_context", _pukni)

    _pozovi_log()  # ne sme da baci

    assert len(supa.payloads) == 1, "upis mora proći uprkos grešci u kontekstu"
    assert "correlation_id" not in supa.payloads[0]


def test_izuzetak_u_citanju_konteksta_ne_obara_naplatu(monkeypatch):
    """Ista provera na nivou cele `consume()` — naplata mora vratiti bilans."""
    import shared.ai_provenance as prov
    monkeypatch.setattr(prov, "current_context",
                        lambda: (_ for _ in ()).throw(RuntimeError("bum")))

    naplaceno = _pripremi_consume(monkeypatch, krediti=3)
    preostalo = asyncio.run(
        usage.UsageService.consume("u-1", "advokat@x.rs", "strategija")
    )
    assert preostalo == 97
    assert naplaceno["n"] == 3


# ─── 4. PRE-MIGRACIJE: nepoznata kolona ne sme progutati ceo red ────────────

def test_pre_migracije_112_red_se_i_dalje_upisuje(monkeypatch):
    """NAJVAŽNIJI regresioni test §17.

    Migraciju 112 vlasnik pokreće RUČNO. Do tada PostgREST odbija ceo INSERT
    zbog nepoznate kolone. Bez „probaj široko pa usko" fallback-a, spoljni
    `except` bi to progutao na debug nivou i SVAKI red telemetrije naplate bi
    tiho nestao — dodavanje kolona bi bilo regresija, ne poboljšanje."""
    s = _LazniSupa(odbij_kolone={"predmet_id", "correlation_id"})
    monkeypatch.setattr(usage, "_get_supa", lambda: s)

    set_request_context(user_id="u-1", correlation_id="CID-5")
    _pozovi_log(predmet_id="PRED-1")

    assert len(s.payloads) == 1, (
        "Red je izgubljen kad kolone ne postoje — fallback ne radi."
    )
    red = s.payloads[0]
    assert "predmet_id" not in red and "correlation_id" not in red
    assert red["krediti_potroseni"] == 6, "naplatni podatak mora preživeti"


def test_stvarni_kvar_baze_ne_izaziva_drugi_pokusaj(monkeypatch):
    """Fallback je NAMERNO uzak: pad konekcije nije „nedostaje kolona", pa se
    ne sme trošiti drugi osuđeni upis."""
    pokusaji = {"n": 0}

    class _Pukni(_LazniSupa):
        def execute(self):
            pokusaji["n"] += 1
            raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(usage, "_get_supa", lambda: _Pukni())
    set_request_context(user_id="u-1", correlation_id="CID-6")

    _pozovi_log(predmet_id="P-1")  # ne sme da baci

    assert pokusaji["n"] == 1, (
        f"očekivan tačno 1 pokušaj za nevezanu grešku, bilo ih je {pokusaji['n']}"
    )


def test_detekcija_nedostajuce_kolone_pokriva_postgrest_oblik():
    """PostgREST poruka ne sadrži ni '42703' ni 'does not exist' — oslanjanje
    samo na `_is_missing_column_error` bi promašilo baš ovaj slučaj."""
    pgrst = RuntimeError(
        "{'code': 'PGRST204', 'message': \"Could not find the 'predmet_id' "
        "column of 'feature_usage_log' in the schema cache\"}"
    )
    assert usage._nedostaje_kolona(pgrst)
    assert usage._nedostaje_kolona(RuntimeError('column "x" does not exist'))
    assert usage._nedostaje_kolona(RuntimeError("SQLSTATE 42703"))
    assert not usage._nedostaje_kolona(RuntimeError("connection reset by peer"))
    assert not usage._nedostaje_kolona(RuntimeError("timeout"))


# ─── 5. REGRESIJA NAPLATE: iznos je identičan ───────────────────────────────

def _pripremi_consume(monkeypatch, krediti: int):
    """Izoluje consume() od baze; vraća dict u koji upisuje naplaćen iznos."""
    naplaceno = {"n": None, "increment": 0}

    async def _policy(_feature):
        return {"krediti": krediti, "credit_multiplier": 1, "dnevni_limit": None,
                "mesecni_limit": None, "cooldown_seconds": None,
                "ai_model": "gpt-4o", "estimated_cost_usd": 0.02}

    async def _inc(user_id, feature, credits_spent, dnevni_limit=None):
        naplaceno["increment"] += 1
        return 1

    def _deduct(user_id, email, n):
        naplaceno["n"] = n
        return 100 - n

    monkeypatch.setattr(usage, "get_policy", _policy)
    monkeypatch.setattr(usage, "_increment_usage", _inc)
    monkeypatch.setattr(usage, "_is_founder", lambda e: False)
    monkeypatch.setattr(usage, "_get_credits", lambda uid: 100)
    monkeypatch.setattr(usage, "_deduct_n_credits", _deduct)
    monkeypatch.setattr(usage, "_get_supa", lambda: _LazniSupa())
    return naplaceno


@pytest.mark.parametrize("sa_kontekstom", [False, True])
def test_iznos_naplate_je_identican_sa_i_bez_provenance(monkeypatch, sa_kontekstom):
    """Provenance je telemetrija. Ako promeni ijedan dinar, izmena je pogrešna."""
    naplaceno = _pripremi_consume(monkeypatch, krediti=6)

    async def _scenario():
        if sa_kontekstom:
            set_request_context(user_id="u-1", correlation_id="CID-7")
            with case_context(predmet_id="PRED-1"):
                return await usage.UsageService.consume(
                    "u-1", "advokat@x.rs", "strategija", predmet_id="PRED-1")
        return await usage.UsageService.consume("u-1", "advokat@x.rs", "strategija")

    preostalo = asyncio.run(_scenario())

    assert naplaceno["n"] == 6, "naplaćen iznos se promenio"
    assert preostalo == 94
    assert naplaceno["increment"] == 1, "broj increment poziva se promenio (NIGHT-001)"


def test_consume_potpis_ne_lomi_postojece_pozivaoce(monkeypatch):
    """153 poziva u repou koriste stari oblik — mora raditi bez izmene."""
    naplaceno = _pripremi_consume(monkeypatch, krediti=1)
    preostalo = asyncio.run(
        usage.UsageService.consume("u-1", "advokat@x.rs", "ai_pravna_pitanja")
    )
    assert preostalo == 99
    assert naplaceno["n"] == 1


def test_predmet_id_je_keyword_only():
    """Pozicioni argument ne sme postati moguć — inače bi neko mogao slučajno
    da ga prosledi na mesto `multiplier`."""
    import inspect
    sig = inspect.signature(usage.UsageService.consume)
    p = sig.parameters["predmet_id"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is None


# ─── 6. Migracija 112 — sadržaj ─────────────────────────────────────────────

def test_migracija_112_je_idempotentna_i_bez_foreign_key():
    p = os.path.join(os.path.dirname(__file__), "..", "migrations",
                     "112_feature_usage_provenance.sql")
    with open(p, encoding="utf-8") as fh:
        sirovo = fh.read()

    assert "ADD COLUMN IF NOT EXISTS predmet_id" in sirovo
    assert "ADD COLUMN IF NOT EXISTS correlation_id" in sirovo
    assert sirovo.count("CREATE INDEX IF NOT EXISTS") == 2

    # Pre provere zabranjenih konstrukcija odbacuju se (1) `--` komentari i
    # (2) SQL string literali. Oba sadrže reč „FOREIGN KEY" — zaglavlje
    # OBJAŠNJAVA zašto ga nema, a `COMMENT ON COLUMN ... IS '...'` to ponavlja
    # u tekstu kolone. Provera nad sirovim fajlom bi pala na sopstvenoj
    # dokumentaciji, što bi bio lažno crven test.
    import re
    bez_komentara = "\n".join(
        r for r in sirovo.splitlines() if not r.lstrip().startswith("--")
    )
    izvrsni = re.sub(r"'(?:[^']|'')*'", "''", bez_komentara).upper()

    # Bez FK: brisanje predmeta ne sme brisati istoriju naplate.
    assert "FOREIGN KEY" not in izvrsni
    assert "REFERENCES" not in izvrsni
    assert "ON DELETE" not in izvrsni

    # Nove kolone su NULLABLE i bez DEFAULT-a — inače bi Postgres prepisao
    # celu tabelu naplate pod ACCESS EXCLUSIVE bravom.
    alter_linije = [r for r in izvrsni.splitlines() if r.startswith("ALTER TABLE")]
    assert len(alter_linije) == 2
    for r in alter_linije:
        assert "NOT NULL" not in r.replace("IF NOT EXISTS", ""), r
        assert "DEFAULT" not in r, r
    assert "SET NOT NULL" not in izvrsni
