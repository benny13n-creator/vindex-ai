# -*- coding: utf-8 -*-
"""
BETA-P1-FEEDBACK-TRUTH — PRIJAVA NETAČNOG PRAVNOG ODGOVORA MORA NEGDE DA STIGNE.

ŠTA JE BILO — mereno protiv produkcije 2026-08-14, samo čitanjem

Advokat ima dva kanala da prijavi da je pravni odgovor netačan. **Oba su bila
mrtva jer im skladište ne postoji:**

  1. `reported_errors` — **ne postoji** među 166 tabela u `public`
     (PostgREST `PGRST205`). To je jedino mesto u celoj bazi gde bi se čuvao
     **tekst** spornog odgovora.

  2. `feedback.q_hash` — **kolona ne postoji**. Produkciona tabela ima tačno
     `id, user_id, tip, created_at` (`?select=q_hash&limit=0` → 400/42703).
     `routers/drafting.py` upisuje `q_hash` na svaki poziv → svaki poziv pada.

I to nije bilo vidljivo, jer je `except` glasio:

    except Exception:
        logger.exception("Greška u /api/feedback")
        return {"status": "ok"}          # ← doslovno ista vrednost kao uspeh

DVE NEUSKLAĐENE DEKLARACIJE

`supabase_migration.sql:45` deklariše `feedback(pitanje, odgovor)`,
`supabase_setup.sql:186` deklariše `feedback(q_hash)`. Obe koriste
`CREATE TABLE IF NOT EXISTS`, pa je ona koja je pokrenuta druga **tiho ništa
uradila**. Produkcija nema nijedan od ta dva oblika u celini.

ZAŠTO SE OVO NE MOŽE ZATVORITI SAMO KODOM

Signal koji vredi je „koji odgovor je bio pogrešan". Bez `q_hash` i bez
`reported_errors` taj signal ne postoji ni u jednom obliku. Zato je uz kod
napisana migracija `113_feedback_truth.sql` — **nije pokrenuta**, čeka vlasnika.

Do tada kod govori istinu: prijava koja nije zabeležena vraća grešku.
"""
import asyncio
import io
import os
import re
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import routers.drafting as dr  # noqa: E402

UID = "uid-advokat"
PITANJE = "Da li otkaz bez pisanog upozorenja proizvodi dejstvo?"
ODGOVOR = "Član 180 ZOR — otkaz je ništav."

# Kolone koje `feedback` STVARNO ima u produkciji danas (izmereno preko
# PostgREST OpenAPI korena, ne pretpostavljeno).
KOLONE_DANAS = {"id", "user_id", "tip", "created_at"}

# Kolone posle migracije 113.
KOLONE_POSLE_113 = KOLONE_DANAS | {"q_hash"}


class _Supa:
    """Lažni Supabase koji STVARNO odbija nepostojeće kolone, kao PostgREST."""

    def __init__(self, kolone, prazan=False):
        self.kolone, self.upisano, self._prazan = set(kolone), [], prazan

    def table(self, ime):
        spolja = self

        class _Q:
            def insert(self, red):
                nepoznate = set(red) - spolja.kolone
                if nepoznate:
                    # Doslovno ponašanje PostgREST-a: 42703 odbija CEO zahtev.
                    raise RuntimeError(
                        "column %r of relation %r does not exist (42703)"
                        % (sorted(nepoznate)[0], ime))
                spolja.upisano.append({"tabela": ime, "red": red})
                self._red = [] if spolja._prazan else [dict(red, id="f1")]
                return self

            def execute(self):
                return MagicMock(data=self._red)
        return _Q()


def _pozovi(supa, tip="greska"):
    req = dr.FeedbackReq(pitanje=PITANJE, odgovor=ODGOVOR, tip=tip)
    with patch.object(dr, "_get_supa", return_value=supa):
        return asyncio.run(dr.feedback(req, {"user_id": UID, "email": "a@a.rs"}))


def _status(odgovor):
    """`_greska_odgovor` vraća `JSONResponse`, uspeh vraća dict."""
    return getattr(odgovor, "status_code", 200)


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — NEUSPELA PRIJAVA NIKAD NIJE „ok"
# ═══════════════════════════════════════════════════════════════════════════

def test_prijava_na_DANASNJOJ_semi_ne_sme_da_kaze_ok():
    """NAJVAŽNIJI TEST U FAJLU.

    Ovo je tačno današnja produkcija: `feedback` bez `q_hash`. Pre popravke je
    ovaj poziv vraćao `{"status": "ok"}` — dakle sistem je 100% prijava
    netačnih pravnih odgovora bacao i svaku od njih potvrđivao.
    """
    supa = _Supa(KOLONE_DANAS)
    odg = _pozovi(supa)
    assert _status(odg) >= 500, f"neuspela prijava vraća {odg!r}"
    assert supa.upisano == [], "ništa nije upisano, a to je i poenta"


def test_prijava_POSLE_migracije_113_prolazi():
    """Ista ruta, ista šema kakvu migracija 113 pravi — sada mora da uspe.
    Bez ovoga bi popravka mogla biti „uvek vraćaj grešku"."""
    supa = _Supa(KOLONE_POSLE_113)
    odg = _pozovi(supa)
    assert _status(odg) == 200
    assert odg == {"status": "ok"}
    assert len(supa.upisano) == 1
    assert supa.upisano[0]["tabela"] == "feedback"


def test_prazan_upis_je_takodje_neuspeh():
    """0 upisanih redova je isto što i pad — samo tiše."""
    odg = _pozovi(_Supa(KOLONE_POSLE_113, prazan=True))
    assert _status(odg) >= 500


def test_pad_baze_je_neuspeh():
    class _Puca:
        def table(self, *a, **k):
            raise RuntimeError("baza nedostupna")
    assert _status(_pozovi(_Puca())) >= 500


# ═══════════════════════════════════════════════════════════════════════════
# 2. MINIMIZACIJA — SADRŽAJ NIKAD NE ULAZI U `feedback`
# ═══════════════════════════════════════════════════════════════════════════

def test_feedback_nikad_ne_nosi_tekst_pitanja_ni_odgovora():
    """NO-STORAGE politika (ZZPL čl. 5(1)(c)). Popravka je smela da učini upis
    uspešnim, ali ne i da prošvercuje sadržaj u tabelu koja ga ne sme imati."""
    supa = _Supa(KOLONE_POSLE_113)
    _pozovi(supa)
    upisano = str(supa.upisano[0]["red"])
    assert PITANJE not in upisano
    assert ODGOVOR not in upisano
    assert "otkaz" not in upisano.lower()


def test_hes_je_stvarno_hes_pitanja():
    """Očekivana vrednost se NE računa istim pomoćnikom koji se testira —
    izvodi se nezavisno iz hashlib-a."""
    import hashlib
    ocekivano = hashlib.sha256(PITANJE.encode()).hexdigest()[:16]
    supa = _Supa(KOLONE_POSLE_113)
    _pozovi(supa)
    assert supa.upisano[0]["red"]["q_hash"] == ocekivano


# ═══════════════════════════════════════════════════════════════════════════
# 3. UGOVOR ŠEME — ONO ŠTO KOD PIŠE MORA BITI NEGDE DEKLARISANO
# ═══════════════════════════════════════════════════════════════════════════
#
# Ovo je brava nad IZVOROM kvara, ne nad njegovom posledicom.
#
# Bug nije nastao jer je neko pogrešio uslov, nego jer je kod pisao kolonu koju
# nijedna migracija ne stvara — i to niko nije mogao da vidi, jer su i pisac i
# test bili na istoj strani ugovora. Ovi testovi čitaju DRUGU stranu: SQL.

def _sql_izvor():
    delovi = []
    for putanja in ("migrations/113_feedback_truth.sql",
                    "supabase_setup.sql", "supabase_migration.sql"):
        p = os.path.join(_KOREN, putanja)
        if os.path.exists(p):
            delovi.append(io.open(p, encoding="utf-8", errors="replace").read())
    return "\n".join(delovi)


def test_svaka_kolona_koju_ruta_pise_JE_deklarisana_u_sql_u():
    """Da je ovaj test postojao, `q_hash` nikad ne bi otišao u produkciju."""
    supa = _Supa(KOLONE_POSLE_113)
    _pozovi(supa)
    sql = _sql_izvor()
    for kolona in supa.upisano[0]["red"]:
        assert re.search(r"\b%s\b" % re.escape(kolona), sql), (
            "ruta piše kolonu %r koju nijedan SQL fajl ne deklariše" % kolona
        )


def test_migracija_113_deklarise_q_hash_i_reported_errors():
    """Popravka koda bez migracije je pola posla; ovaj test drži drugu polovinu
    napisanom čak i dok čeka vlasnika da je pokrene."""
    p = os.path.join(_KOREN, "migrations", "113_feedback_truth.sql")
    assert os.path.exists(p), "migracija 113 nije napisana"
    sql = io.open(p, encoding="utf-8").read()
    assert re.search(r"ADD COLUMN IF NOT EXISTS\s+q_hash", sql)
    assert re.search(r"CREATE TABLE IF NOT EXISTS\s+public\.reported_errors", sql)
    assert "ENABLE ROW LEVEL SECURITY" in sql, "nova tabela bi bila bez RLS-a"


def test_klijentski_upis_pise_u_tabelu_koju_sql_deklarise():
    """Druga strana istog ugovora: `sendFeedback` u `vindex.js` upisuje
    `reported_errors` sa četiri polja. Sva četiri moraju biti deklarisana.

    Postojeći Playwright test to nije mogao uhvatiti — merio je da je upis
    POZVAN, a ne da tabela u koju ide uopšte postoji."""
    js = io.open(os.path.join(_KOREN, "static", "vindex.js"),
                 encoding="utf-8").read()
    m = re.search(r"from\('reported_errors'\)\.insert\(\{(.*?)\}\)", js, re.S)
    assert m, "`sendFeedback` više ne upisuje u `reported_errors`"
    polja = re.findall(r"(\w+)\s*:", m.group(1))
    assert set(polja) >= {"user_id", "original_prompt", "ai_response"}, polja
    sql = _sql_izvor()
    for polje in polja:
        assert re.search(r"\b%s\b" % re.escape(polje), sql), (
            "klijent piše `reported_errors.%s`, a nijedan SQL to ne deklariše"
            % polje
        )
