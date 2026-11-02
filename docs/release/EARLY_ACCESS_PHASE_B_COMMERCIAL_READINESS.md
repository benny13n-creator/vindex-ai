# Early Access — Faza B: komercijalna spremnost

**Grana:** `feature/early-access-commercial` (od `main` = `aaea99a4`). Izolovana je od Faze A (PR #66) i od Word grane.

**Status:**

| Deo | Status |
|---|---|
| B1 | `B1_READY_FOR_FOUNDER_REVIEW` |
| B2 | `B2_DECISIONS_PENDING` |
| B3 | `B3_LEGAL_AND_OPERATIONAL_READINESS_PENDING` |

**Oznake:** PROVEN = pročitan kod ili fajl, ili izmereno testom; INFERRED = zaključak; ASSUMED = pretpostavka; UNKNOWN = nije vidljivo odavde.

Sajt je **kandidat za izdanje, ne odobrenje za javnu kampanju.** Registracija i dalje ne traži potvrdu email-a; v. `FINAL_PHASE_A_RELEASE_GATE.md` §5 i §9 na PR #66.

---

## B1. Tekst ranog pristupa — ZAVRŠENO

**Izvor i gradnja:**
- Izvor: `site/_izvor/beta.html`.
- Generator: `scripts/gradi_sajt.py`. Generisani `site/*.html` čuvaju se u git-u, a `--provera` meri usklađenost.
- Stil: `site/sajt.css`, dodata su tri pravila.

**Šta je urađeno (PROVEN, testovi):**
- **Tekst osnivača je doslovan.** Svaki blok je tačan tekst jednog elementa, istim redom i sa istim nivoom naslova (`#`/`##`/`###` → h1/h2/h3). Podebljani delovi su `<strong>`.
- **U odeljcima teksta nema nijedne neodobrene reči.** Pored odobrenog teksta stoje samo oznake dva dugmeta, a i one su iz ugovora osnivača.
- **Dva puta vode na postojeće tokove:**
  - **„Isprobajte Vindex“ → `/app#register`.** Klasični `/app` otvara modal u režimu registracije (`static/vindex.js:8570`). V2 `/app` isti hash prosleđuje na `/app-legacy#register` (`frontend-v2-ng/src/runtime.js:46-48`). `POST /api/register` traži samo `email` i `password`.
  - **„Zatražite pristup za kancelariju“ → `#zahtev`.** To je postojeća forma na istoj stranici (`POST /waitlist/prijava`, `site/sajt.js`). Forma, njena napomena o privatnosti (`/privacy#beta-prijava`) i poruke ishoda su nepromenjene.
- **Uklonjeno sa `/beta`:** stari naslov „Prijavi se za rani pristup Vindexu.“, uvod o „kontrolisanom beta testiranju“, kartice „Šta dobijate“ i odeljak „Već imate nalog“.
  - Rečenica „Ovo je beta: moguće je naići na greške“ je uklonjena. Materijalni uslov ostaje pokriven odobrenom rečenicom „pravne zaključke, rokove i dokumente proverava advokat“, kao i Uslovima korišćenja. **Osnivač može tražiti da se vrati.**
- **Svesno NIJE menjano:** zajednički poziv „Prijavi se za rani pristup“ (zaglavlje i druge stranice, → `/beta`). Nova oznaka bila bi samostalno pisan tekst. Ako osnivač želi drugu oznaku, to je jedna konstanta (`CTA` u `gradi_sajt.py`).
- **Nema obećanja ni plaćanja:** nigde se ne pominje neograničen pristup, mesečno punjenje kredita, automatsko odobrenje, cena ili valuta. Na sajtu nema kartice ni automatske naplate (test).

**Dokazi:**

| Provera | Rezultat |
|---|---|
| `tests/test_website_rani_pristup_b1.py` + `test_website_public` + `test_website_v3_rast` + `test_website_premium_pozicioniranje` + `test_website_v2_remediacija` | 359 passed |
| Mutacije (binarno vraćanje): reč u tekstu, dodata rečenica, dugme na `/app`, h2 → p, bez podebljanja, obećanje mesečnog obnavljanja, forma van `#zahtev` | **7/7 ubijeno** |
| `frontend-v2-ng/tests/site-e2e.mjs` (Chromium, stvaran `api.py`, svih 6 stranica × 6 širina) + B1 provere na 390 i 1440 | **326/326 PASS** |

B1 provere u Playwright-u:
- obe kartice su vidljive: u istom redu na 1440, jedna ispod druge na 390;
- dugmad su visoka ≥ 40 px i nema preliva;
- klik na „Zatražite…“ dovodi formu u vidno polje;
- klik na „Isprobajte Vindex“ otvara modal u režimu Registracija, sa poljima ime, e-pošta i lozinka;
- ništa nije poslato, a `/beta` nema spoljnih zahteva.

---

## B2. Komercijalne odluke

### Zabeležene odluke osnivača (2026-11-02, „PHASE A P0 MULTIPLIER FIX“, Zadatak 3)

| Stavka | Odluka | Stanje u kodu i podacima |
|---|---|---|
| Basic mesečno | **29 €** | seed 068 = 29 €, dosledno |
| Professional mesečno | **69 €** | seed 068 i `_FALLBACK` = 79 €. **Nije menjano.** Izmenu u Admin konzoli i `_FALLBACK` radi osnivač u posebnom koraku; nijedna cena nije aktivirana. |
| Professional godišnje | **ostaje 758,40 €** (opcija A ispod) | seed 068 = 758,40 €, dosledno |
| Stvarni godišnji popust uz 69 €/mes | **≈ 8,41 %** (69,60 € od 828,00 €) | aplikacija ga računa iz `tier_config` i prikazuje „uštedite 8 %“. Tvrdnja o 20 % ne postoji nigde u kodu ni na sajtu (`git grep`), pa nema šta da se uklanja. |
| Automatska naplata prekoračenja | **ne** | nema checkout-a ni automatske naplate (test B1) |
| Iznosi periodične dodele kredita | **nisu odobreni** | mehanizam ne postoji; ništa se ne implementira bez odobrenog ugovora o dodeli (v. AI fond) |
| Enterprise | **postojeća cena se ne zamenjuje nulom bez odluke** | seed 068 = 249 €/mes, 2.390,40 €/god, 3 mesta, 49 €/dodatno mesto; nije menjano |

Naplata nije aktivirana; ni `tier_config` ni stanje kredita nisu dirani.

**Kanonski izvor cena:** `tier_config` (migracija 068), javno preko `GET /api/plan/info`. Kartice u aplikaciji se crtaju iz tog odgovora (`static/vindex.js:8340-8395`). Izmena ide preko Admin konzole i beleži se u `tier_config_audit` (upis je fail-soft). Javni sajt ne prikazuje cene. PROVEN.

### Godišnja cena Professional

Seed 068 je mesečno 79 € i godišnje 758,40 € (= 79 × 12 × 0,8, tj. 20 %). Ušteda se **ne tvrdi fiksno** nigde: aplikacija je računa kao `round((1 − godišnje/12 / mesečno) × 100)` (`static/vindex.js:8366-8368`, PROVEN `git grep`).

Opcije posle odobrenih 69 €/mes (12 × 69 = 828,00 €):

| Opcija | Godišnje | Mesečni ekvivalent | Ušteda | Aplikacija prikazuje | Posledica |
|---|---:|---:|---:|---|---|
| A. Ne menjati godišnju | 758,40 € | 63,20 € | 69,60 € (8,41 %) | „uštedite **8 %**“ | Nije potrebno novo odobrenje. Prikaz je tačan, ali godišnji popust je drugačiji nego za Basic (20 %). |
| B. Isti popust kao Basic (20 %) | 662,40 € | 55,20 € | 165,60 € (20,00 %) | „uštedite **20 %**“ | **Traži odobrenje osnivača.** U odnosu na A, 96,00 € manje po godišnjem korisniku. |
| C. Godišnju ne prikazivati dok se ne odluči (`yearly_price_eur = NULL`) | — | — | — | samo mesečna | I ovo je izmena godišnje ponude u podacima, pa traži odobrenje. Godišnja naplata ionako ne postoji. |

Basic je dosledan: 278,40 € = 29 × 12 × 0,8 (20 %).

**Odluka (2026-11-02): A.** Godišnja ostaje 758,40 €; B i C nisu odobrene.

**Preostali redosled:**
1. Osnivač u Admin konzoli menja Professional 79 → 69. To je izmena produkcionih podataka i ne radi se u ovom sprintu.
2. U istom koraku `_FALLBACK` (`shared/tier_config.py:34`) postaje 69, uz test koji poredi fallback i odobrene cene. Fallback se koristi samo kad je `tier_config` prazan, pa promena koda pre izmene podataka ne sme da napravi dve različite cene.

Produkcijske vrednosti `tier_config` su UNKNOWN; mogle su biti menjane kroz konzolu.

### Mesečni AI fond — predlog mehanizma (nije implementiran)

**Stanje (PROVEN):**
- Krediti se dodeljuju **jednom**: 15, trigger `on_auth_user_created_credits` (`supabase_setup.sql`).
- Ne postoji mesečno punjenje ni dodela po tarifi.
- Konstante `BASIC_MESECNI_KREDITI = 200` / `PRO_MESECNI_KREDITI = 600` (`shared/deps.py:62-63`, `api.py:357-358`) koristi samo `require_credits`, koja ima **0 pozivalaca**. Ne smatraju se pravima i ovde se ne predlažu kao vrednosti.

**Najmanji revidiran mehanizam, samo od postojećih delova:**

| Element | Postojeći deo | Novo |
|---|---|---|
| Iznos po tarifi | `tier_config` (kanonski, revidiran kroz `tier_config_audit`) | jedna kolona `mesecni_ai_krediti INTEGER NULL`. NULL znači da nema dodele. **Iznos određuje osnivač.** |
| Dodela | atomični `refund_n_credits(user, n)` (migracija 107), isti put kao povraćaj | founder-only `POST /api/admin/krediti/dodela {user_id, period, razlog}` (`_require_founder`, kao `routers/admin_dashboard.py:183`) |
| Revizioni trag | `audit_immutable` (INSERT-only hash lanac, `shared/audit_immutable.log_action`) | jedan zapis po dodeli: ko, kome, koliko, period, razlog, stanje pre i posle |
| Idempotentnost | — | ponovljena dodela za isti (`user_id`, `period`) se odbija. Zahteva jedinstven ključ: ili jedinstven indeks nad postojećom tabelom audita, ili mala tabela `krediti_dodele` (`UNIQUE(user_id, period)`). **Izbor ide uz dizajn-pregled; nova tabela samo ako se dokaže da audit tabela ne može.** |
| Raspored | — | **Ručno, bez cron-a**, dok pravila nisu odobrena (non-goal: „no automatic user-credit replenishment“) |

**Odluke osnivača:**
1. Iznos po tarifi.
2. Prenos neiskorišćenih kredita: dodavanje (prenos) ili dopuna do iznosa (bez prenosa). Dopuna traži novu atomičnu SQL funkciju „dopuni do N“.
3. Ko i kada dodeljuje.

### Enterprise

**Kanonski prikaz danas (PROVEN, seed 068 i kod kartica):** u aplikaciji se prikazuje **249 €/mes**, „Godišnja pretplata — uštedite 20 %“ (2.390,40 €), „Uključeno: 3 korisnika · dodatno mesto 49 €/mes“ i dugme „Kontaktirajte nas →“ (mailto). Javni sajt ga ne prikazuje.

**Odluka (2026-11-02):** postojeća Enterprise cena se **ne zamenjuje nulom** bez izričite odluke. I dalje je otvoreno da li Enterprise prelazi na „individualna ponuda“; to traži zaseban dizajn prikaza, a ne `monthly_price_eur = 0`.
- Ako je odgovor „individualna ponuda“: `monthly_price_eur = 0` prikazuje „Kontakt cena“ (`ptRenderCard`), ali tada MRR procena u `routers/product_intelligence.py:128` računa 0. To je posledica koju treba prihvatiti ili rešiti zasebno.
- **Ništa nije menjano.**

---

## B3. Ručno B2B fakturisanje — PRAVNA I OPERATIVNA SPREMNOST ČEKA

| Uslov | Nalaz | Status |
|---|---|---|
| Pravni identitet prodavca | `terms.html:44`: „Benjamin Nađ, osnivač Vindex AI“, fizičko lice, bez PIB-a i matičnog broja | PROVEN (tekst) |
| Izdavanje B2B faktura za SaaS | verovatno traži registrovan subjekat (preduzetnik ili d.o.o.) i SEF | INFERRED, **traži knjigovođu ili pravnika** |
| Poreski tretman (PDV, paušal, prag) | — | UNKNOWN |
| Obavezni sadržaj fakture | zavisi od subjekta i PDV statusa | UNKNOWN |
| Ručna potvrda uplate | nema rute; uplata bi se proveravala van aplikacije | PROVEN |
| Ovlašćena aktivacija tarife | nema admin rute za `profiles.subscription_type`/`subscription_expires_at`/`user_credits`; menja se samo u bazi | PROVEN |
| Revizioni trag promene prava | postoji samo za `tier_config` i registar; **nema traga za tarifu ili kredite korisnika** | PROVEN |
| Period i istek | `subscription_expires_at` + `effective_tier` (`shared/permissions.py:91-96`) | PROVEN |
| Otkaz i neobnavljanje | `terms.html` §„Pretplata, plaćanje i raskid“ važi „tek kada se uvede plaćeno korišćenje“ | PROVEN |
| Podaci posle isteka | spuštanje na basic; podaci ostaju; AI zavisi od kredita | PROVEN |
| Fakturisanje advokat → klijent kao zamena | `routers/billing.py` je modul advokata prema klijentima, bez granice obračuna za Vindex SaaS. **Ne koristiti.** | INFERRED |

**Pre prve fakture (posebno odobrenje, ne u ovom sprintu):**
1. Registrovan subjekat, PDV status i SEF.
2. Founder-only ruta „dodeli ili produži tarifu“ sa zapisom u `audit_immutable`, po istom obrascu kao dodela kredita gore. Bez nove tabele prava.
3. Ažurirani `terms.html`: identitet prodavca i aktiviranje odeljka o naplati.

---

## B4. Prihvatanje — preostali testovi (posle odluka B2)

| Kriterijum | Test |
|---|---|
| jedna prikazana cena | `/api/plan/info` == kartice u aplikaciji; fallback == odobrene cene |
| API i frontend prava dosledni | `_PT_BULLETS` ↔ `minimum_plan` u registru |
| bez neovlašćenog Professional pristupa | basic nalog → 403 na professional funkcijama |
| bez brisanja podataka pri spuštanju | istekao `subscription_expires_at` → basic, CRUD radi |
| bez automatskog plaćanja | ✓ B1 (`test_sajt_nema_placanja_ni_automatske_naplate`) |
| istinite poruke ranog pristupa | ✓ B1 |
| bez slanja produkcione forme | ✓ B1 (Playwright presreće `/waitlist/prijava` i `/api/register`) |
| determinističan generator | ✓ B1 |
| desktop i mobilni | ✓ B1 (326/326) |
