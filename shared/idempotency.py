# -*- coding: utf-8 -*-
"""
Vindex AI — shared/idempotency.py

NS005 Gate A2 — TRAJNA zaštita V2 upisa od mrežnog ponavljanja istog zahteva.

ZAŠTO (izmereno, docs/v2-recovery/NS005_OVERNIGHT_EVIDENCE.md, Gate A): kada edge
(Cloudflare, HTTP/2) izgubi sesiju ka browseru POSLE obrade na serveru, Chromium SAM
ponovo pošalje isti POST — jedan klik stiže do servera dva puta. „Ishod nepoznat“ na
klijentu ne sprečava dvostruki efekat (kredit, beleška, stavka naplate, faktura).

UGOVOR
  • Klijent (V2 NG `VxApi.send`) šalje `Idempotency-Key: <UUID v4>` — jedan ključ po
    korisničkoj radnji; ponovljen mrežni zahtev nosi ISTI ključ.
  • Zahtev BEZ ključa ide kao i pre (legacy `/app-legacy`, `/app-v2`, drugi pozivaoci).
  • Štite se SAMO rute sa efektom ili trošenjem kredita (`ZASTICENE_RUTE`), ne svaki POST.
  • Vlasnik ključa je korisnik iz TOKENA (`shared.deps._verify_token`), nikad iz tela/zaglavlja.

TOK (jedan zahtev sa ključem na zaštićenoj ruti)
  1. Otisak = SHA-256(metod, putanja + upit, SHA-256(telo)). Telo se NE čuva.
  2. Zauzimanje = INSERT reda (user_id, idempotency_key) u stanju IN_PROGRESS.
     Jedinstvenost (PRIMARNI KLJUČ u bazi) odlučuje — nema SELECT-pa-INSERT, nema
     Python brava, nema Redis-a, nema memorije procesa. Važi preko radnika, instanci i
     restarta.
  3. Uspelo zauzimanje → ruta se izvrši JEDNOM; ceo odgovor se baferuje, šifruje
     (`security.crypto.encrypt_field`, AES-256-GCM) i upiše kao COMPLETED — samo ako je
     red i dalje IN_PROGRESS sa ISTIM `owner_token` (samo vlasnik završava) — pa se tek
     onda šalje klijentu (ponovljen zahtev koji stigne posle toga dobija sačuvan odgovor).
  4. Sudar ključa (23505):
       drugi otisak            → 409 IDEMPOTENCY_CONFLICT, ruta se NE poziva
       COMPLETED, isti otisak  → sačuvan status + telo, ruta se NE poziva
       IN_PROGRESS, isti otisak→ 409 IDEMPOTENCY_IN_PROGRESS (+ Retry-After), ruta se NE poziva
  5. Skladište nedostupno → 503 IDEMPOTENCY_UNAVAILABLE, ruta se NE poziva (fail-closed).
  6. IN_PROGRESS koji niko ne završi (pad procesa, izuzetak u ruti, neuspeo upis
     završetka) OSTAJE IN_PROGRESS: ključ se nikad ne smatra slobodnim samo zato što je
     vreme prošlo — efekat je možda izvršen pre pada. `expires_at` je rok čuvanja, ne
     dozvola za ponovno izvršavanje.

ZAŠTO ODMAH 409 ZA IN_PROGRESS, A NE ČEKANJE: poziv modela ima podrazumevani limit 60 s
(`shared/ai_client.py::_DEFAULT_LLM_TIMEOUT_S`) uz do 2 ponavljanja u SDK-u, a nacrt
pravi dva poziva — jedan zahtev može trajati minutima, duže od podrazumevanih 100 s
koliko Cloudflare čeka origin. Čekanje bi zauzimalo radnika i završavalo se istekom na
edge-u; V2 klijent 409 IN_PROGRESS prikazuje kao „ishod nepoznat“ i ponovo čita stanje.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger("vindex.idempotency")

TABELA = "v2_mutation_idempotency"
ZAGLAVLJE = b"idempotency-key"
# UUID v4, kanonski oblik, mala slova (crypto.getRandomValues → v4 u VxApi.send).
_KLJUC_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SENTINEL_DEKRIPCIJE = "[GREŠKA DEKRIPTOVANJA]"   # security/crypto.py::decrypt_field na grešci
_MAX_ODGOVOR_B = 2 * 1024 * 1024
_RETRY_AFTER_S = "5"

_SEG = r"[A-Za-z0-9_-]{1,64}"
# (metod, putanja) — SAMO rute sa efektom (SIDE_EFFECTING) ili trošenjem kredita
# (CREDIT_CONSUMING). Inventar i razvrstavanje: NS005_OVERNIGHT_EVIDENCE.md, Gate A2.
# NAMERNO IZOSTAVLJENO: POST /api/praksa/search (PURE_QUERY — bez kredita i upisa),
# POST /api/nacrti/export/docx (FILE_EXPORT — bez efekta, binarni odgovor).
ZASTICENE_RUTE = tuple((m, re.compile(p)) for m, p in (
    ("POST", r"^/api/predmeti$"),
    ("PATCH", rf"^/api/predmeti/{_SEG}$"),
    ("POST", rf"^/api/predmeti/{_SEG}/beleske$"),
    ("POST", rf"^/api/predmeti/{_SEG}/confirm-links$"),
    ("POST", r"^/klijenti$"),
    ("POST", r"^/api/conflict-check$"),
    ("POST", r"^/api/rocista$"),
    ("POST", r"^/api/pitanje$"),
    ("POST", r"^/api/podnesak$"),
    ("POST", rf"^/api/staging/{_SEG}/(approve|reject)$"),
    ("POST", r"^/interni-stavovi/(dodaj|pretraga)$"),
    ("POST", rf"^/api/rokovi/{_SEG}/(potvrdi|odbij)$"),
    ("POST", r"^/billing/entries$"),
    ("POST", r"^/billing/faktura$"),
    ("POST", r"^/billing/timer/(start|stop)$"),
    # Smart Intake (Task 14): pregled, ispravka i prikačivanje imaju efekat. Otpremanje
    # (`POST /api/smart-intake/documents`, multipart do 25 MB po fajlu) NAMERNO nije ovde: štiti ga
    # jači ugovor na nivou posla — `idempotency_key = korisnik:sha256(sadržaj)` + UNIQUE indeks +
    # `enqueue_intake_job` RPC (isti sadržaj istog korisnika = isti posao, bez novog bloba).
    ("POST", rf"^/api/smart-intake/jobs/{_SEG}/(finalize|review/resolve|review/reject)$"),
    ("POST", rf"^/api/smart-intake/entities/{_SEG}/correct$"),
    # NS007: pregled autonomnog radnog proizvoda (prihvati/odbaci = promena stanja; mrežno ponavljanje = 1 prelaz).
    ("POST", rf"^/api/autonomy/work-items/{_SEG}/(accept|reject)$"),
    # NS008: ljudski ishod predmeta (jedini izvor istine o ishodu za Law Brain) + zatvaranje predmeta.
    ("POST", r"^/api/learning/outcome$"),
    ("PATCH", rf"^/api/learning/lessons/{_SEG}/potvrdi$"),
))


def je_zasticena(metod: str, putanja: str) -> bool:
    return any(m == metod and p.match(putanja) for m, p in ZASTICENE_RUTE)


def otisak(metod: str, putanja: str, upit: bytes, telo: bytes) -> str:
    h = hashlib.sha256()
    h.update(metod.encode("ascii") + b"\n" + putanja.encode("utf-8") + b"?" + (upit or b"") + b"\n")
    h.update(hashlib.sha256(telo or b"").digest())
    return h.hexdigest()


# ─── Skladište ───────────────────────────────────────────────────────────────

class GreskaSkladista(Exception):
    """Skladište nije dostupno ili je odgovorilo neočekivano — zahtev se ne izvršava."""


def _je_sudar(e: Exception) -> bool:
    t = str(e)
    return "23505" in t or "duplicate key" in t.lower()


class SupabaseSkladiste:
    """Produkcija: service_role klijent (shared.deps._get_supa). RLS + grantovi u
    migraciji 134 zabranjuju anon/authenticated pristup."""

    def _supa(self):
        from shared import deps
        return deps._get_supa()

    def zauzmi(self, red: dict) -> bool:
        try:
            r = self._supa().table(TABELA).insert(red).execute()
        except Exception as e:
            if _je_sudar(e):
                return False
            raise GreskaSkladista(str(e)[:200])
        if not r or not getattr(r, "data", None):
            raise GreskaSkladista("insert bez potvrde")
        return True

    def procitaj(self, user_id: str, kljuc: str) -> Optional[dict]:
        try:
            r = (self._supa().table(TABELA)
                 .select("state, request_fingerprint, status_code, response_content_type, response_payload_enc")
                 .eq("user_id", user_id).eq("idempotency_key", kljuc).limit(1).execute())
        except Exception as e:
            raise GreskaSkladista(str(e)[:200])
        rows = (r.data or []) if r else []
        return rows[0] if rows else None

    def zavrsi(self, user_id: str, kljuc: str, owner_token: str, polja: dict) -> bool:
        try:
            r = (self._supa().table(TABELA).update(polja)
                 .eq("user_id", user_id).eq("idempotency_key", kljuc)
                 .eq("state", "IN_PROGRESS").eq("owner_token", owner_token).execute())
        except Exception as e:
            raise GreskaSkladista(str(e)[:200])
        return bool(r and getattr(r, "data", None))


_skladiste_fabrika: Callable[[], object] = SupabaseSkladiste


def postavi_skladiste(fabrika: Callable[[], object]) -> None:
    """Samo za testove (npr. stvaran PostgreSQL preko psycopg)."""
    global _skladiste_fabrika
    _skladiste_fabrika = fabrika


# ─── Šifrovanje sačuvanog odgovora ───────────────────────────────────────────

def _sifruj(telo: bytes) -> str:
    from security.crypto import encrypt_field
    # base64 pre šifrovanja: telo su bajtovi; encrypt_field("") vraća "" pa prazno telo
    # dobija oznaku umesto praznog stringa (da bi se razlikovalo od nedostajuće vrednosti).
    return encrypt_field("b64:" + base64.b64encode(telo).decode("ascii"))


def _desifruj(vrednost: str) -> Optional[bytes]:
    from security.crypto import decrypt_field, is_encrypted
    if not vrednost or not is_encrypted(vrednost):
        return None   # nikad ne prihvati nešifrovanu vrednost kao odgovor
    t = decrypt_field(vrednost)
    if t == _SENTINEL_DEKRIPCIJE or not t.startswith("b64:"):
        return None
    try:
        return base64.b64decode(t[4:], validate=True)
    except Exception:
        return None


# ─── ASGI middleware ─────────────────────────────────────────────────────────

def _json(status: int, kod: str, poruka: str, dodatna: Optional[list] = None) -> tuple[int, list, bytes]:
    telo = json.dumps({"detail": poruka, "kod": kod}, ensure_ascii=False).encode("utf-8")
    h = [(b"content-type", b"application/json"), (b"content-length", str(len(telo)).encode())]
    return status, h + (dodatna or []), telo


async def _posalji(send, status: int, headers: list, telo: bytes) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": telo, "more_body": False})


def _korisnik(headers: dict) -> Optional[str]:
    a = headers.get(b"authorization", b"").decode("latin-1")
    if not a.lower().startswith("bearer "):
        return None
    from shared import deps
    payload = deps._verify_token(a[7:].strip())
    sub = (payload or {}).get("sub")
    return str(sub) if sub else None


class IdempotencyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        metod, putanja = scope.get("method", ""), scope.get("path", "")
        headers = {}
        for k, v in scope.get("headers") or []:
            headers.setdefault(k.lower(), v)
        kljuc_b = headers.get(ZAGLAVLJE)
        if kljuc_b is None or not je_zasticena(metod, putanja):
            return await self.app(scope, receive, send)

        kljuc = kljuc_b.decode("latin-1").strip()
        if not _KLJUC_RE.match(kljuc):
            return await _posalji(send, *_json(400, "IDEMPOTENCY_KEY_INVALID", "Ključ zahteva nije ispravan. Ništa nije izvršeno."))

        try:
            uid = await asyncio.to_thread(_korisnik, headers)
        except Exception:
            uid = None
        if not uid:
            # Fail-closed: zahtev SA ključem se nikad ne izvršava nezaštićen. Bez proverenog
            # identiteta ne postoji vlasnik ključa — 401 odmah, ruta se ne poziva (ista
            # `_verify_token` provera koju koriste i `get_current_user` i `api._require_auth`).
            return await _posalji(send, *_json(401, "AUTH_REQUIRED", "Prijava više nije važeća. Ništa nije izvršeno."))

        # Celo telo se čita jednom; ruta ga dobija nepromenjeno.
        delovi, kraj = [], False
        while not kraj:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            delovi.append(msg.get("body", b""))
            kraj = not msg.get("more_body", False)
        telo = b"".join(delovi)
        fp = otisak(metod, putanja, scope.get("query_string", b""), telo)

        skladiste = _skladiste_fabrika()
        owner = str(uuid.uuid4())
        red = {"user_id": uid, "idempotency_key": kljuc, "method": metod, "path": putanja[:512],
               "request_fingerprint": fp, "state": "IN_PROGRESS", "owner_token": owner}
        try:
            zauzeto = await asyncio.to_thread(skladiste.zauzmi, red)
            postojeci = None if zauzeto else await asyncio.to_thread(skladiste.procitaj, uid, kljuc)
        except Exception as e:
            logger.error("[IDEMPOTENCY] skladište nedostupno (%s %s): %s", metod, putanja, str(e)[:160])
            return await _posalji(send, *_json(503, "IDEMPOTENCY_UNAVAILABLE",
                                               "Zaštita od dvostrukog upisa trenutno nije dostupna. Ništa nije izvršeno; pokušajte ponovo."))

        if not zauzeto:
            if not postojeci:
                return await _posalji(send, *_json(503, "IDEMPOTENCY_UNAVAILABLE",
                                                   "Zaštita od dvostrukog upisa trenutno nije dostupna. Ništa nije izvršeno; pokušajte ponovo."))
            if postojeci.get("request_fingerprint") != fp:
                return await _posalji(send, *_json(409, "IDEMPOTENCY_CONFLICT",
                                                   "Isti ključ je već upotrebljen za drugi zahtev. Ništa nije izvršeno."))
            if postojeci.get("state") == "COMPLETED":
                sacuvano = _desifruj(postojeci.get("response_payload_enc") or "")
                status = postojeci.get("status_code")
                if sacuvano is None or not isinstance(status, int):
                    logger.error("[IDEMPOTENCY] sačuvan odgovor nije čitljiv (%s %s) — ne izvršava se ponovo", metod, putanja)
                    return await _posalji(send, *_json(503, "IDEMPOTENCY_REPLAY_UNAVAILABLE",
                                                       "Zahtev je već obrađen, ali njegov ishod trenutno ne može da se prikaže. Ništa nije ponovo izvršeno."))
                tip = (postojeci.get("response_content_type") or "application/json").encode("latin-1", "replace")
                return await _posalji(send, status, [(b"content-type", tip), (b"content-length", str(len(sacuvano)).encode()),
                                                     (b"idempotent-replayed", b"true")], sacuvano)
            return await _posalji(send, *_json(409, "IDEMPOTENCY_IN_PROGRESS",
                                               "Isti zahtev se još obrađuje. Ishod nije poznat; proverite stanje pre ponovnog pokušaja.",
                                               [(b"retry-after", _RETRY_AFTER_S.encode())]))

        # ── Vlasnik: ruta se izvršava tačno jednom ──
        predato = False

        async def receive_jednom():
            nonlocal predato
            if not predato:
                predato = True
                return {"type": "http.request", "body": telo, "more_body": False}
            return await receive()

        pocetak, delovi_odg = None, []

        async def send_bafer(msg):
            nonlocal pocetak
            if msg["type"] == "http.response.start":
                pocetak = msg
                return
            if msg["type"] == "http.response.body":
                delovi_odg.append(msg.get("body", b""))
                if not msg.get("more_body", False):
                    await _zavrsi_i_posalji()
                return
            await send(msg)

        async def _zavrsi_i_posalji():
            odg = b"".join(delovi_odg)
            status = pocetak["status"]
            hdr = list(pocetak.get("headers") or [])
            tip = next((v.decode("latin-1") for k, v in hdr if k.lower() == b"content-type"), "application/json")
            if len(odg) <= _MAX_ODGOVOR_B:
                try:
                    polja = {"state": "COMPLETED", "status_code": status, "response_content_type": tip[:200],
                             "response_payload_enc": _sifruj(odg), "completed_at": datetime.now(timezone.utc).isoformat()}
                    if not await asyncio.to_thread(skladiste.zavrsi, uid, kljuc, owner, polja):
                        logger.error("[IDEMPOTENCY] završetak nije upisan (vlasnik/stanje se ne poklapa) %s %s", metod, putanja)
                except Exception as e:
                    # Efekat JE izvršen; red ostaje IN_PROGRESS → ponovljen zahtev dobija 409 (fail-closed).
                    logger.error("[IDEMPOTENCY] završetak nije upisan %s %s: %s", metod, putanja, str(e)[:160])
            else:
                logger.error("[IDEMPOTENCY] odgovor prevelik za čuvanje (%d B) %s %s — red ostaje IN_PROGRESS", len(odg), metod, putanja)
            await send({"type": "http.response.start", "status": status, "headers": hdr})
            await send({"type": "http.response.body", "body": odg, "more_body": False})

        await self.app(scope, receive_jednom, send_bafer)
