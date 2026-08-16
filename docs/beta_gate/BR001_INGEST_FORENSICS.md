# BR-001 — INGEST DOKUMENTA: FORENZIKA I ZATVARANJE

**Datum:** 2026-08-16
**Baseline:** `19138f69`, radno stablo čisto na početku sprinta
**Obim:** isključivo BR-001. BR-002, BR-004, BR-005, rokovi, naplata, RLS i UI kozmetika nisu dirani.

---

## 1. PITANJE NA KOJE JE TREBALO ODGOVORITI

Da li advokat **danas, sa trenutnim kodom**, može da otpremi dokument, a sistem
da ga automatski obradi, napravi vektor, upiše ga u kanonski `kancelarija_{id}` /
`user_{id}` namespace sa ispravnim metapodacima, označi `status='indeksirano'`,
i **vrati taj dokument na relevantno AI pitanje** — bez ijednog ručnog koraka.

Odgovor: **da.** Dokazano stvarnim kontrolisanim prolaskom kroz produkcijsku
rutu sa stvarnim Pinecone-om i stvarnim embedding-om. Detalji u §7–§9.

---

## 2. ŠTA JE ZATEČENO (mereno, ne pretpostavljeno)

`predmet_dokumenti`, produkcija, 2026-08-16:

| Merenje | Vrednost |
|---|---|
| ukupno redova | 43 |
| `status='sacuvano'` | 43 / 43 |
| `status='indeksirano'` | 0 / 43 |
| `pinecone_namespace` oblika `pred_<session_id>` | 43 / 43 |
| `content_sha256` popunjen | 0 / 43 |
| `storage_path` oblika `session/...` (original NIJE sačuvan) | 43 / 43 |
| različitih korisnika | **1** |
| različitih predmeta | 17 |
| dužina `tekst_sadrzaj` | 77–580 znakova |
| najstariji red | 2026-07-18 |
| najnoviji red | **2026-07-21** |

Pinecone, isti trenutak: 434.217 vektora u 11 namespace-ova. **Nijedan od 43
`pred_*` namespace-ova iz baze ne postoji u Pinecone-u.** Postoji 6 drugih
`pred_*` namespace-ova sa po 5 vektora, i nijedan od njih ne odgovara nijednom
redu u `predmet_dokumenti` (to je BR-004 — orphani, izvan ovog sprinta).

Dakle: nijedan od 43 dokumenta nije pretraživ, i baza to **tačno prijavljuje**
(`sacuvano`, ne `indeksirano`).

---

## 3. CALL GRAPH (FAZA 0, bez ijedne izmene)

`static/vindex.js:20286 pred_upload_doc()` → `POST /api/predmeti/{id}/upload`

| # | Karika | Fajl / linija | Identitet / namespace | Ponašanje pri padu |
|---|---|---|---|---|
| 1 | auth | `api.py:5054 _require_auth_async` | postavlja `set_request_context(user_id=<JWT sub>)` (`api.py:3804`) | 401, ništa dalje |
| 2 | entitlement | `api.py:5060 PermissionService.require` | — | 402/403, ništa dalje |
| 3 | vlasništvo predmeta | `api.py:5063` `.eq("user_id", user.id)` | — | 404 |
| 4 | **izbor namespace-a** | `api.py:5073-5075` `get_kancelarija_id` → `rag_owner_namespace` | `kancelarija_{id}` ili `user_{uid}` | pad razrešavanja → `user_{uid}` (uži opseg, nikad širi) |
| 5 | guard fajla | `api.py:5078-5083` | — | 415 / 413 |
| 6 | original u storage | `api.py:5096+` | — | **best-effort**, `storage_path` ostaje `session/…` |
| 7 | ekstrakcija | `uploaded_doc/extractor.py::extract` | — | 422 / 500 |
| 8 | **verzija sadržaja** | `api.py:5176` `verzija_dokumenta(text)` | 32 heks znaka iz **teksta**, ne bajtova | — |
| 9 | chunk-ovanje | `uploaded_doc/chunker.py::chunk_document` | — | `total_chunks==0` → 422 |
| 10 | **ingest** | `uploaded_doc/ingest.py::ingest_session` (`api.py:5216`) | `namespace_override=_owner_ns`, `verzija_dokumenta_id=_content_sha256` | v. §4 |
| 11 | provera potpunosti | `api.py:5240` `ingest_je_potpun(count, total_chunks)` | — | `_pinecone_ok=False` |
| 12 | klasifikacija greške | `api.py:5252` `je_kvota_greska` | — | kvota → `sacuvano`; **sve ostalo → HTTP 500** |
| 13 | upis reda | `api.py:5285-5310` | `pinecone_namespace=_owner_ns`, `status='indeksirano' if _pinecone_ok else 'sacuvano'` | insert padne → `_dok_id=None` → **HTTP 500**, bez lažnog 200 |
| 14 | auto-analiza + RAG | `api.py:5455+` `retrieve_documents(kancelarija_namespace=_owner_ns, …)` | isti namespace | timeout/greška → analiza bez RAG-a |

Unutar karike 10:

| Korak | Linija | Ponašanje pri padu |
|---|---|---|
| embedding | `ingest.py:76` | izuzetak izlazi napolje |
| broj vektora ≠ broj chunk-ova | `ingest.py:88` | `RuntimeError`, **ništa se ne upisuje** |
| verzija nedostaje / nije kanonska | `ingest.py:143`, `proveri_kanonsku_verziju` | `NedovoljanIdentitet`, ništa se ne upisuje |
| ID vektora | `canonical_vector_id(scope, verzija, chunk_index)` | deterministički; `scope = predmet_id` |
| upsert po 50 | `ingest.py:182-194` | izuzetak izlazi napolje; broj već upisanih se loguje |
| povratna vrednost | `ingest.py:198` | broj **stvarno** upisanih vektora |

---

## 4. UZROK — ODGOVOR NA „Dokument staje ovde zato što ______"

**Danas dokument nigde ne staje.** Ceo lanac je izmeren i prolazi (§7).

43 zatečena dokumenta su stala na kariki 10 (Pinecone upsert) pod kodom koji je
tada bio na snazi, a taj kod je tada svejedno upisivao red sa
`status='sacuvano'`.

Klasifikacija: **B — kod je ispravan, 43 dokumenta su istorijski talog.**

Dokaz koji tu klasifikaciju drži, a ne oslanja se na pretpostavku:

- `pred_<session_id>` šema je zamenjena vlasničkim namespace-om u commit-u
  `fa7129ff` (**2026-07-26**).
- Najnoviji od 43 reda je od **2026-07-21**.
- Svih 43 redova nosi `pred_*` namespace i `content_sha256 = NULL`.

Dakle **nijedan** od 43 dokumenta nije prošao kroz današnji pisač. Kroz današnji
kod nije prošao **nijedan** produkcijski upload uopšte — poslednji upload u
sistemu je pet dana stariji od migracije namespace-a. Zatečeno stanje zato ne
govori ništa o današnjem kodu, ni u dobrom ni u lošem smislu, i moralo je biti
izmereno zasebno.

---

## 5. FAZA 2 — POPRAVKA

**Nijedna izmena produkcijskog koda nije bila potrebna.** Sve što je BR-001
tražio već postoji i radi:

- kanonski vlasnički namespace (`fa7129ff`),
- deterministički identitet vektora (`78ff5d73`, `dcbf3fd9`),
- odbijanje delimičnog ingesta i lažnog uspeha (`82450875`),
- `status='indeksirano'` isključivo posle potvrđenog potpunog upsert-a,
- UI koji pretraživost izvodi **samo** iz `status === 'indeksirano'`
  (`static/vindex.js:12504`).

Izmišljanje popravke tamo gde kvara nema bilo bi lošije od nikakve popravke.
Umesto toga je uložen napor u dokaz (§7) i u bravu (§10).

---

## 6. DVE GREŠKE MERENJA — obe su izgledale kao kvar proizvoda

Zabeležene jer je svaka od njih mogla da završi kao lažan nalaz u ovom izveštaju.

**6.1 „IndexError: list index out of range" u `embed_documents`.**
Prvi E2E prolaz je pukao unutar `ingest_session`, i to je izgledalo kao ozbiljan
kvar ingesta. Uzrok je bio harness: `openai.OpenAI` je bio zamenjen MagicMock-om
u celosti, pa je i `langchain_openai` dobio lažan klijent i vratio praznu listu
vektora. Isti kod sa stvarnim klijentom radi. Harness je prepravljen tako da
delegira na stvaran klijent za sve osim za `chat`/`responses`.

**6.2 Pinecone `describe_index_stats` je eventualno konzistentan.**
Skripta je posle brisanja test namespace-a pročitala `0` vektora i prijavila
čisto stanje. Nezavisna provera nekoliko minuta kasnije pokazala je da namespace
**postoji** sa 1 vektorom. Jedno čitanje odmah posle brisanja **nije dokaz
brisanja**. Čišćenje je ponovljeno sa proverom u petlji do odsustva namespace-a
(§11). Ovo direktno pogađa i BR-004: svaka buduća tvrdnja „vektori su obrisani"
zasnovana na jednom `describe_index_stats` pozivu je neosnovana.

---

## 7. FAZA 4/5 — STVARAN KONTROLISAN E2E DOKAZ

Pokrenuto je telo prave rute `predmet_upload_auto_analyze` sa **stvarnim
Pinecone-om i stvarnim embedding-om**. Lažni su bili samo delovi koji nisu
predmet merenja: auth, entitlement, Supabase, naplata i završni GPT poziv.
Ekstrakcija, chunk-ovanje, verzija, izbor namespace-a, ingest, upsert i odluka o
statusu bili su stvarni.

Kontrolna činjenica, jedinstvena i bez veze sa bilo kojim stvarnim predmetom:

> „svedok … je 14. marta 2019. video plavi kombi registracije **NS-BR001-XZ**
> ispred skladišta u Temerinskoj 77"

Namespace: `user_00000000-br00-1000-0000-000000000001` — ne postoji u produkciji.

| Merenje | Rezultat |
|---|---|
| `status` upisan u red | **`indeksirano`** |
| `pinecone_namespace` u redu | `user_00000000-br00-…-000000000001` |
| `content_sha256` u redu | `2d6df3b8295a90985321bfbac092bf91` (32 heks) |
| vektora stvarno u Pinecone-u | 1 od 1 chunk-a |
| ID vektora | `…__2d6df3b8295a90985321bf…` — deterministički, izveden iz `predmet_id` + verzije |
| metapodaci vektora | `type='case_doc'`, `predmet_id=<predmet>` |
| **pretraga vraća kontrolnu činjenicu** | **DA** (`score=0.575`, filter `predmet_id ∈ {…}`) |

Dodatno, iz loga same rute tokom istog prolaza:

```
[KANC_NS:user_00000000-br00-1000-0000-000000000001] 1 pasusa dodato u kontekst (od 1 rezultata)
```

To je **auto-analiza** koja je, kroz `retrieve_documents`, sama pronašla
dokument otpremljen sekundu ranije — dakle karika 14 je takođe izmerena uživo, a
ne samo testom.

**Bez ijednog ručnog koraka (FAZA 5):** jedini poziv u skripti je poziv rute.
Ingest, izbor namespace-a, identitet, upsert i upis statusa dogodili su se unutar
tog jednog poziva.

**Granica ovog dokaza, izričito:** ruta je pozvana kao funkcija, ne preko HTTP
sloja; Supabase je bio lažan. Oblik reda je zato dokazan zasebno protiv **prave**
produkcijske tabele (§8). Putanja običnog pitanja advokata (`/api/pitanje`)
pokrivena je BR-003 testovima, a ovde je uživo izmerena samo kroz retrieval
auto-analize.

---

## 8. UPIS U BAZU — dokazan bez ijedne izmene podataka

Insert sa tačnim produkcijskim oblikom reda (svih 10 kolona, uključujući
`content_sha256` i `tekst_sadrzaj`) poslat je pravoj tabeli sa namerno
nepostojećim `predmet_id`.

Odgovor: **`23503` — `predmet_dokumenti_predmet_id_fkey`.**

Da neka kolona nedostaje, greška bi bila `42703`/`PGRST204` i nikad ne bi
stigla do provere stranog ključa. Oblik reda je time dokazan, a nijedan red nije
napisan. `predmet_dokumenti` je i posle sprinta imao tačno 43 reda, najnoviji od
2026-07-21.

---

## 9. FAZA 6 — ODLUKA O 43 ISTORIJSKA DOKUMENTA

Nalazi koji tu odluku treba da nose:

- svih 43 pripada **jednom** korisniku — `384a7149-938b-4b83-99e0-8d7524e0581a`,
  nalogu osnivača;
- dužine teksta 77–580 znakova: to su kratki probni dokumenti, ne pravni akti;
- originalni fajlovi **ne postoje** (`storage_path = session/…`), pa je ponovni
  ingest moguć samo iz `tekst_sadrzaj`, koji je prisutan za svih 43;
- kanonski namespace tog korisnika danas bi bio
  `user_384a7149-938b-4b83-99e0-8d7524e0581a`;
- u Pinecone-u nema nijednog njihovog vektora, pa backfill ne bi ništa dupliralo.

**Preporuka: ne raditi backfill.** Vratio bi 43 probna dokumenta ukupne dužine
ispod 20 KB u pretragu, gde bi zauvek zagađivali rezultate stvarnih predmeta.
Vrednija opcija je brisanje tih redova.

**Nijedan produkcijski red nije izmenjen niti obrisan u ovom sprintu** — to je
odluka vlasnika podataka, ne inženjerska. Obe opcije su izvodljive kad odluka
stigne.

---

## 10. FAZA 3 — REGRESIONA BRAVA

`tests/test_br001_ingest_chain.py`, **20 testova**, bez ijednog naplativog poziva
(embedding i Pinecone zamenjeni na granici modula `uploaded_doc.ingest`).

Brava ne meri „da li ruta vrati 200" — 43 postojeća reda su nastala uz uredan
200. Meri **spoj**: namespace koji je stvarno otišao u `index.upsert()` mora biti
identičan onome upisanom u `predmet_dokumenti.pinecone_namespace`, a
`status='indeksirano'` sme da postoji samo posle potvrđenog potpunog upsert-a.

| Grupa | Šta drži |
|---|---|
| 1, 1b | upsert ide u kanonski vlasnički namespace; `pred_*` se nikad ne vraća |
| 2, 2b, 2c | bez kanonske verzije se ne upisuje ništa; isti dokument daje iste ID-eve |
| 3, 3b | svaki vektor nosi `predmet_id`, `type`, tekst; pozivalac ne može pregaziti `vx_*` identitet |
| 4, 4b, 4c | delimičan embedding i pad batcha dižu grešku; `ingest_je_potpun` je fail-closed |
| 5, 5b | status i namespace u bazi odgovaraju onome što je u Pinecone-u |
| 5c | kvota → `sacuvano`, nikad `indeksirano` |
| 5d | ne-kvota greška → 500 i **nijedan red u bazi** |
| 5e, 5f | delimičan upis nikad ne dobija `indeksirano` |

### Mutaciono testiranje

| Mutacija produkcijskog koda | Ishod |
|---|---|
| M1 — `namespace_override` ignorisan, povratak na `pred_{session_id}` | 3 testa padaju ✓ |
| M2 — uklonjen guard „broj vektora ≠ broj chunk-ova" | 1 test pada ✓ |
| M3 — `status` uvek `'indeksirano'` | 1 test pada ✓ |
| M4 — `extra_metadata` pregazi `vx_*` identitet | 1 test pada ✓ |
| M5 — uklonjena provera `ingest_je_potpun` u ruti | **PREŽIVELA** → dodat `test_5f` → 1 test pada ✓ |

M5 je preživela prvi krug jer su svi ostali testovi merili slučaj u kom
`ingest_session` **diže** grešku, pa se sopstvena provera rute nikad nije
izvršavala. `test_5f` tera `ingest_session` da uredno vrati **manji** broj —
tačno oblik u kom bi buduća regresija tiho proizvela dokument predstavljen kao
pretraživ. Posle dodavanja: **5/5 mutacija ubijeno.**

---

## 11. FAZA 7 — ČIŠĆENJE, DOKAZANO

| Provera | Pre sprinta | Posle sprinta |
|---|---|---|
| Pinecone `total_vector_count` | 434.217 | **434.217** |
| Pinecone broj namespace-ova | 11 | **11** |
| test namespace `user_00000000-br00-…` | ne postoji | **ne postoji** (potvrđeno posle ponovljenog brisanja, §6.2) |
| `predmet_dokumenti` broj redova | 43 | **43** |
| najnoviji red | 2026-07-21 | **2026-07-21** |
| izmenjeni produkcijski redovi | — | **0** |

Skripte E2E dokaza žive u scratchpad-u, izvan repozitorijuma. U repozitorijum
ulaze samo regresioni testovi i ovaj izveštaj.

---

## 12. NALAZI IZVAN OBIMA — evidentirani, nedirani

| ID | Nalaz | Pripada |
|---|---|---|
| BR-004 | 6 `pred_*` namespace-ova (po 5 vektora) bez ijednog reda u `predmet_dokumenti` | BR-004 |
| BR-004 | tvrdnja o brisanju vektora zasnovana na jednom `describe_index_stats` pozivu je neosnovana (§6.2) | BR-004 |
| — | original dokumenta se ne čuva kad Supabase Storage upis padne; `storage_path` ostaje `session/…` (namerno, best-effort) | Intake |
| — | odluka o 43 istorijska reda | osnivač (§9) |
| BR001-FLAKE-001 | `test_get_supa_thread_safe_single_client_created` je nestabilan u punom prolasku | dug testova |

### BR001-FLAKE-001 — dokaz da NIJE regresija ovog sprinta

Pun prolaz suite-a sa BR-001 fajlom: `1 failed, 5612 passed, 1 skipped`.
Pun prolaz **sa fizički uklonjenim** BR-001 fajlom: `1 failed, 5592 passed,
1 skipped` — **isti test pada**. Sam, i zajedno sa BR-001 fajlom, test prolazi.

Test postavlja `deps._supa = None`, pusti 20 niti u `_get_supa()` sa
`time.sleep(0.02)` u lažnom `create_client`, i traži tačno jedno kreiranje. To je
merenje osetljivo na opterećenje mašine i na niti koje su preživele ranije
testove. Nije popravljan jer je izvan obima BR-001, ali je evidentiran: zeleno
stanje suite-a se od sada ne sme tvrditi bez pogleda u ovaj red.

---

## 13. VERDIKT

## 🟢 BR-001 — ZATVOREN

Lanac upload → obrada → vektor → kanonski namespace → metapodaci →
`status='indeksirano'` → povratak dokumenta na AI pitanje **radi sa trenutnim
kodom**, dokazan stvarnim kontrolisanim E2E prolaskom sa stvarnim Pinecone-om, i
zaključan sa 20 testova i 5/5 ubijenih mutacija.

43 zatečena reda nisu kvar današnjeg koda nego talog koda od pre 2026-07-26.
Njihova sudbina je odluka vlasnika podataka, evidentirana u §9, i **ne blokira**
zatvaranje BR-001.
