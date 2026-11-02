# Early Access — Faza B: komercijalna spremnost (B1–B4)

**Grana:** `feature/early-access-commercial` (od `main` = `aaea99a4`), izolovana od Faze A (PR #66) i od Word grane.
**Status:** `BLOCKED_WITH_EVIDENCE`. Svaka izmena koda ili sajta zavisi od odluka i podataka osnivača koji ne postoje u repozitorijumu (v. „Odluke osnivača“). Ovaj PR sadrži samo dokumentaciju.
**Oznake:** PROVEN = pročitan kod ili fajl; INFERRED = zaključak; ASSUMED = pretpostavka; UNKNOWN = nije vidljivo odavde.

## B1. Sajt — tekst za Early Access

| Tvrdnja | Status |
|---|---|
| Ugovor odobrava „Existing Early Access text supplied by founder“, ali sam tekst nije priložen. Nema ga ni u repozitorijumu ni na Google Drive-u (pretraga po „Early Access“, „rani pristup“, „29 EUR“, „69 EUR“, „Isprobajte Vindex“). | PROVEN (pretraga) |
| Sajt (`site/_izvor`, generator `scripts/gradi_sajt.py`) danas ima jedan poziv na akciju: „Prijavi se za rani pristup“ → `/beta`. Samostalna registracija je opisana tek na dnu `/beta`. | PROVEN |
| Tekst na `/beta` je tačan: „Prijava je zahtev… sama prijava ne otvara nalog“, „Automatska potvrda se ne šalje e-poštom“, „nov nalog dobija ograničen broj kredita“. Ne obećava aktivaciju ni plaćenu uslugu. | PROVEN |
| Javni sajt nigde ne prikazuje cene. | PROVEN (`git grep`) |

**Odluka:** tekst se ne piše samostalno („do not independently rewrite approved marketing statements“). Dva poziva na akciju, „Isprobajte Vindex“ (`/app`, registracija) i „Zatražite pristup za kancelariju“ (`/beta`, postojeći zahtev), uvode se tek uz dostavljen tekst. To je jedan commit u `site/_izvor` + `gradi_sajt.py` (konstanta `CTA`) + test u `tests/test_website_premium_pozicioniranje.py`.

## B2. Cene i prava — pregled doslednosti

**Kanonski izvor:** `tier_config` (migracija 068), keš `shared/tier_config.py`, javni `GET /api/plan/info`. Izmena ide preko Admin konzole (`PATCH /api/admin/tier-config/{tier}`) i beleži se u `tier_config_audit` (upis je fail-soft: neuspeh se samo loguje, `routers/admin_dashboard.py:635`). PROVEN.

| Stavka | Stanje u kodu (seed 068 / fallback) | Odobreno | Doslednost |
|---|---|---|---|
| Basic mesečno | 29 € | 29 € | ✓ |
| Professional mesečno | **79 €** (seed + `_FALLBACK` u `shared/tier_config.py:34`) | **69 €** | ✗ potrebna izmena u Admin konzoli; produkcijska vrednost UNKNOWN |
| Professional godišnje | 758,40 € (= 79 × 12 × 0,8) | ne menja se bez posebnog odobrenja | ⚠ uz 69 €/mes aplikacija sama prikazuje „uštedite **8 %**“ umesto 20 % (`static/vindex.js:8366-8368`) |
| Basic godišnje | 278,40 € (20 %) | ne menja se | ✓ |
| Enterprise | 249 €/mes, 3 mesta, 49 €/dodatno mesto; **cena se prikazuje** u aplikaciji | „Team/Enterprise: individualna ponuda“; Enterprise cene se ne menjaju | ⚠ prikaz 249 € je u sukobu sa „individualna ponuda“; promena prikaza = odluka |
| Uključena mesta | Basic 1, Professional 1 | — | ✓ |
| **Uključeni AI fond** | **Ne postoji mehanizam.** Krediti se dodeljuju jednom (15 na registraciji). Nema mesečnog punjenja po tarifi. Konstante 200/600 „mesečnih pitanja“ (`shared/deps.py:62-63`) žive samo u `require_credits`, koja ima **0 pozivalaca**. | „pretplata sa uključenim AI fondom“ | ✗ **materijalno**: plaćeni Basic/Professional bi danas dobio 15 kredita ukupno |
| Naplata | Aplikacija: dugme „Aktivirajte X →“ šalje email (`pricing_kontakt`, mailto + `PRICING_INTEREST` povratna informacija). Nema checkout-a ni automatske obnove. | bez automatske naplate | ✓ PROVEN |
| Istek pretplate | `effective_tier()` vraća `basic` posle `subscription_expires_at` (`shared/permissions.py:91-96`); CRUD i podaci ostaju | — | ✓ PROVEN, bez brisanja podataka |
| Stavke na karticama u aplikaciji | `_PT_BULLETS` su ručni tekst (npr. „Tim od 6 AI agenata“, „SEF e-faktura“), nisu izvedeni iz registra | — | UNKNOWN da li se poklapaju sa `minimum_plan` u produkcijskom registru |

**Minimalni redosled (odluke osnivača, bez koda):**
1. Odluka o godišnjoj ceni Professional: zadržati 758,40 (8 %) ili posebno odobriti 662,40 (20 %).
2. Odluka o uključenom AI fondu: broj kredita mesečno po tarifi i mehanizam dodele.
3. Tek tada izmena Professional 79 → 69 u Admin konzoli. Za doslednost fallback-a u istom PR-u ide `_FALLBACK` 79 → 69 i test koji upoređuje fallback sa očekivanim cenama.

## B3. Ručno B2B fakturisanje — spremnost

| Uslov | Nalaz | Status |
|---|---|---|
| Pravni identitet prodavca | `terms.html:44`: „Benjamin Nađ, osnivač Vindex AI“. To je **fizičko lice**, bez PIB-a i matičnog broja i bez registrovanog subjekta. | PROVEN (tekst) |
| Može li fizičko lice da izdaje B2B fakture za SaaS | Verovatno ne bez registracije (preduzetnik ili d.o.o.). B2B fakture u Srbiji idu kroz SEF (e-fakture). | INFERRED, **traži knjigovođu ili pravnika** |
| Poreski tretman (PDV, paušal, prag) | — | UNKNOWN |
| Sadržaj fakture | zavisi od subjekta i PDV statusa | UNKNOWN |
| Ručna potvrda uplate | Nema rute. Uplata bi se proveravala van aplikacije. | PROVEN (nema koda) |
| Ovlašćena aktivacija tarife | Nema admin rute za `profiles.subscription_type` / `subscription_expires_at` / `user_credits`. Menja se samo direktno u bazi. | PROVEN |
| Revizioni trag svake promene prava | Postoji samo za `tier_config` (`tier_config_audit`) i registar. **Nema traga za dodelu tarife ili kredita korisniku.** | PROVEN |
| Period i istek | `subscription_expires_at` + `effective_tier` | PROVEN |
| Otkaz i neobnavljanje | `terms.html` §„Pretplata, plaćanje i raskid“: raskid bilo kada, pravo do isteka plaćenog perioda. Odeljak važi „tek kada se uvede plaćeno korišćenje“. | PROVEN |
| Pristup podacima posle isteka | spuštanje na basic; podaci ostaju; AI zavisi od kredita | PROVEN |
| Fakturisanje advokat → klijent kao zamena | `routers/billing.py` je modul advokata prema njegovim klijentima i nema granicu obračuna za Vindex SaaS. **Ne koristiti.** | INFERRED |

**Minimalna ispravka pre prve fakture (posebno odobrenje, nije u ovom sprintu):**
1. Registrovan subjekat, PDV status i SEF nalog.
2. Founder-only ruta „dodeli tarifu / produži / dodeli kredite“ sa upisom u revizioni trag. Mora koristiti postojeće `profiles` kolone i `deduct/refund` primitive (migracija 107); bez nove tabele prava.
3. Ažurirani `terms.html`: aktiviranje odeljka o naplati i identitet prodavca.

## B4. Prihvatanje — plan testova (za commit koji sledi posle odluka)

| Kriterijum | Test |
|---|---|
| jedna prikazana cena | `/api/plan/info` == kartice u aplikaciji == sajt (ako se cena objavi); fallback == odobrene cene |
| API i frontend prava dosledni | `_PT_BULLETS` stavke ↔ `minimum_plan` u registru |
| bez neovlašćenog Professional pristupa | `PermissionService` nad basic nalogom → 403 za `strategija` i ostale professional funkcije (postojeći testovi + nov) |
| bez brisanja podataka pri spuštanju | istekao `subscription_expires_at` → basic, CRUD radi |
| bez automatskog plaćanja | nema checkout/stripe/auto-renew niza u `site/`, `static/`, `frontend-v2-ng/` |
| istinite poruke | zabranjeni nizovi „automatska potvrda“, „odmah aktivno“ na sajtu |
| bez starog beta teksta | postojeći `test_website_premium_pozicioniranje.py` + nova lista |
| bez slanja produkcione forme | testovi presreću `/api/waitlist` |
| determinističan generator | `gradi_sajt.py` dvaput → isti bajtovi |
| desktop/mobilni | Playwright 1440/390 |

## Odluke osnivača

1. **Dostaviti odobreni Early Access tekst** (doslovno) i potvrditi oznake dugmadi „Isprobajte Vindex“ / „Zatražite pristup za kancelariju“.
2. Godišnja cena Professional uz 69 €/mes (8 % ili posebno odobrenih 20 %).
3. Uključeni AI fond po tarifi (broj kredita mesečno) i način dodele (ručno uz revizioni trag ili automatski).
4. Da li Enterprise u aplikaciji i dalje prikazuje 249 € ili „individualna ponuda“.
5. Pravni subjekat i poreski status pre prve B2B fakture (knjigovođa).
6. Promena Professional 79 → 69 u Admin konzoli, posle tačaka 2 i 3.
