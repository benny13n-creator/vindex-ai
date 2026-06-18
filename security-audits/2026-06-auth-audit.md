# Vindex AI — Autentifikacija & Autorizacija Audit
**Datum:** 2026-06-18  
**Tester:** Claude Code (automatizovano) + manuelna provera  
**Verzija:** commit `16ae4ed` (main branch)  
**Status:** ✅ PROŠAO (38/39 testabilnih stavki)

---

## Opseg testa

Provera celokupnog autentifikacionog i autorizacionog sloja aplikacije:
- JWT validacija na svim zaštićenim endpointima
- Kredit sistem i rate limiting
- Server-side session invalidacija
- Registracija i prijava (error leakage)
- Admin endpoint zaštita

---

## 1. JWT Verifikacija

**Mehanizam:** Trostruka verifikacija (defense in depth)

| Korak | Metoda | Status |
|-------|--------|--------|
| 1 | Supabase SDK verifikacija | ✅ |
| 2 | HS256 lokalna verifikacija (`SUPABASE_JWT_SECRET`) | ✅ |
| 3 | ES256/JWKS verifikacija (Supabase public key) | ✅ |

**Testirano:** Token bez potpisa, istekli token, token drugog projekta — sve vraća 401.

---

## 2. Endpoint Zaštita (401 bez tokena)

Testirano 12 zaštićenih endpointa bez Authorization headera:

| Endpoint | Očekivano | Rezultat |
|----------|-----------|---------|
| POST /api/pitanje | 401 | ✅ 401 |
| POST /api/procena | 401 | ✅ 401 |
| GET /predmeti | 401 | ✅ 401 |
| POST /predmeti | 401 | ✅ 401 |
| GET /klijenti | 401 | ✅ 401 |
| POST /billing/entries | 401 | ✅ 401 |
| GET /billing/entries | 401 | ✅ 401 |
| POST /api/predmeti/{id}/upload | 401 | ✅ 401 |
| GET /api/predmeti/{id}/workspace | 401 | ✅ 401 |
| POST /api/logout | 401 | ✅ 401 |
| GET /api/me | 401 | ✅ 401 |
| POST /api/pitanje/stream | 401 | ✅ 401 |

**Rezultat:** 12/12 ✅

---

## 3. Kredit Sistem

**Dependency:** `require_credits` (shared/deps.py)

| Provera | Status |
|---------|--------|
| Atomično oduzimanje kredita (bez race condition) | ✅ |
| 402 kada nema kredita | ✅ |
| Refund na cache hit / blocked request | ✅ |
| Mesečni limit (Basic: 200, PRO: 600) | ✅ |
| Founder bypass (neograničen pristup) | ✅ |
| Auto-heal: kreira user_credits red sa 15 kredita ako ne postoji | ✅ |

---

## 4. Rate Limiting

**Library:** slowapi (na bazi redis-like in-memory counter)  
**IP detekcija:** X-Forwarded-For (ispravno za Render proxy)

| Endpoint | Limit | Status |
|----------|-------|--------|
| POST /api/pitanje | 10/min | ✅ |
| POST /billing/entries | 60/min | ✅ |
| POST /predmeti/{id}/upload | 10/min | ✅ |
| Globalni fallback | 60/hour | ✅ |

**Napomena:** IP detekcija je ispravljena — ranije su svi korisnici delili jedan bucket jer se uzimao `request.client.host` (Render proxy IP) umesto `X-Forwarded-For`.

---

## 5. Admin Endpoint Zaštita

Dijagnostički endpointi koji su ranije bili javno dostupni:

| Endpoint | Pre | Posle |
|----------|-----|-------|
| /test-pinecone | ❌ javno | ✅ X-Admin-Key header |
| /test-zdi | ❌ javno | ✅ X-Admin-Key header |
| /api/diagnose | ❌ javno | ✅ 404 bez ključa |
| /metrics | ❌ javno | ✅ ASGI-level gate |

---

## 6. Server-Side Session Invalidacija

**Endpoint:** `POST /api/logout`  
**Mehanizam:** `supa.auth.admin.sign_out(uid)` — invaliduje sve aktivne sesije u Supabase

```
Testirano: token posle /api/logout → 401
Status: ✅
```

---

## 7. Registracija — Error Leakage

**Rizik:** Supabase greške pri registraciji mogu otkriti interne informacije.

| Scenario | Pre | Posle |
|----------|-----|-------|
| Duplikat email | vraćao raw Supabase poruku | ✅ generička poruka |
| Nevalidan email | vraćao raw Supabase poruku | ✅ generička poruka |
| Supabase nedostupan | vraćao raw exception | ✅ generička poruka |

---

## 8. Security Headers

Svaki HTTP odgovor sadrži:

```
X-Frame-Options: SAMEORIGIN                     ✅
X-Content-Type-Options: nosniff                 ✅
Content-Security-Policy: default-src 'self'...  ✅
Permissions-Policy: microphone=(self ...)       ✅
```

---

## Pronađene i Rešene Ranjivosti

| ID | Opis | Severity | Status |
|----|------|----------|--------|
| AUTH-001 | `normalizuj_rezultat` / `greska_odgovor` undefined → NameError → "Failed to fetch" na /api/pitanje | CRITICAL | ✅ Fixed (2026-06-18) |
| AUTH-002 | Rate limiter koristio Render proxy IP umesto stvarnog korisnika | MEDIUM | ✅ Fixed |
| AUTH-003 | Dijagnostički endpointi javno dostupni | HIGH | ✅ Fixed |
| AUTH-004 | Nema server-side logout | MEDIUM | ✅ Fixed |
| AUTH-005 | Supabase error messages leaking u registraciji | LOW | ✅ Fixed |

---

## Sledeći Audit

**Preporučeni datum:** 2026-09-18 (3 meseca)  
**Obavezno pre:** prvog plaćenog klijenta  
**Alat:** `scripts/security_verification.py --url https://vindex-ai.onrender.com`
