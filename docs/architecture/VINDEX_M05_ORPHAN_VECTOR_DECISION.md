# VINDEX — M05: siročad vektora posle neuspelog upisa dokumenta — odluka o arhitekturi

**Status:** PREDLOG ZA ODLUKU OSNIVAČA. **Ništa od ovoga nije implementirano.** Nema promene šeme, identiteta vektora, radnika za čišćenje ni brisanja.
Osnova: `main` = produkcija `469085b6`. Oznake: **PROVEN** (izvršeno ili pročitano iz koda), **INFERRED**, **UNKNOWN**.

---

## 1. Trenutno verifikovano ponašanje

| Činjenica | Status | Dokaz |
|---|---|---|
| ID vektora je `"{scope}__{verzija}__k{chunk_schema}_c{chunk_index}"`; za dokumente predmeta `scope = predmet_id`, `verzija = verzija_dokumenta(tekst)` (SHA-256 kanonskog teksta) | PROVEN | `shared/vector_identity.py` (model, `canonical_vector_id`, `prefiks_dokumenta`) |
| Isti sadržaj u istom predmetu ⇒ isti ID-evi; upsert prepisuje („RULE 9“) | PROVEN | isti fajl, docstring modela |
| Upload (`api.py::predmet_upload_auto_analyze`) upisuje vektore u namespace vlasnika **pre** reda `predmet_dokumenti`; ako upis reda padne (3 pokušaja), ruta vraća 500, vektori ostaju | PROVEN | `api.py` ~6120–6280; M05 RED (PR #45) |
| Čišćenje posle neuspeha je **uklonjeno** (PR #45, `e58c967f`); `tests/test_m05_bez_destruktivnog_ciscenja.py` čuva da neuspeo upis ne dira indeks | PROVEN | git istorija, test |
| RAG nad namespace-om vlasnika filtrira samo po `predmet_id ∈ dozvoljeni` (+ `type`) — **ne** po postojanju reda dokumenta | PROVEN | `shared/rag_acl.py::filter_za_namespace_vlasnika` (`{"type": {"$in": …}, "predmet_id": {"$in": …}}`) |
| ⇒ Siroče iz predmeta P je **dohvatljivo u RAG-u predmeta P** (sadržaj koji ne postoji u spisku dokumenata) | INFERRED (iz dva PROVEN reda iznad; nije izvršeno nad stvarnim indeksom) | |
| Brisanje predmeta (`shared/predmet_deletion.py`) briše vektore **po redovima dokumenata** (`obrisi_vektore_dokumenta` za svaki `predmet_dokumenti.id`) ⇒ siroče (bez reda) **preživljava brisanje predmeta** | PROVEN čitanjem (~440–478) | brisanje nije potpuno — pitanje prava na zaborav |
| Ponovni uspešan upload ISTOG sadržaja u isti predmet „usvaja“ siroče (isti ID-evi, red sada postoji) | INFERRED iz modela | |
| Vektori nose `vx_scope`, `vx_verzija`, `vx_chunk_schema`, `chunk_index`, `predmet_id`, opciono `document_id` | PROVEN | `metapodaci_identiteta`, `uploaded_doc/ingest.py` |
| `predmet_dokumenti.id` je `UUID DEFAULT gen_random_uuid()`; `content_sha256` postoji (mig. 095) i **nema** UNIQUE po `(predmet_id, content_sha256)` | PROVEN | `supabase_setup.sql:356`, `migrations/095` |

## 2. Redosled kvara (M05)

1. A: tekst → `verzija_A`; vektori `P__verzija_A__k*_c*` upisani u `ns_vlasnika`.
2. A: `insert predmet_dokumenti` pada 3 puta → 500 advokatu.
3. Vektori A ostaju; RAG predmeta P ih vidi; spisak dokumenata ih ne vidi.
4. Brisanje predmeta P kasnije: briše po redovima → vektori A ostaju trajno.

## 3. Problem deljenog identiteta

Identitet vektora je (predmet, sadržaj), a ne (predmet, **dokument**). Sve što briše „vektore jednog upload-a / dokumenta“ preko prefiksa briše i vektore svakog drugog reda sa istim sadržajem u istom predmetu.

### 3a. Kontraprimer 0 — POSTOJEĆI, bez ikakve konkurentnosti (novi nalaz NS3-N16)

Upload put A (Pipeline A) **namerno** dozvoljava isti sadržaj dvaput u istom predmetu (samo informativno upozorenje, `api.py` ~6132–6150, LIVINGSYS-DEBT-020). Tada D1 i D2 dele ID-eve. `DELETE` dokumenta D1 (`api.py` ~7200 → `obrisi_vektore_dokumenta`) briše po prefiksu `P__verzija__` — **i vektore D2**; red D2 ostaje „indeksirano“, ali D2 više nije u pretrazi.

**Izvršeno** (stvarna `obrisi_vektore_dokumenta`, baza i indeks u memoriji, `scratchpad/ns3/n16_deljeni_identitet_demo.py`): ishod brisanja D1 = `DELETED`, obrisano 3; vektora koji ostaju za D2 = **0 od 3**.

Ovo je ista greška koju je M05 povlačenje izbeglo — samo bez trke. Nije menjano (misija N16 je samo arhitektura).

## 4. Opcija A — identitet vektora po dokumentu (ne po upload-u)

**Mehanizam:** `predmet_dokumenti.id` se generiše u aplikaciji PRE ingest-a (UUID v4; kolona već prima zadat id), ID vektora postaje `"{scope}__{verzija}__d{dokument_id}__k{schema}_c{i}"`, red se upisuje SA tim id-om. Neuspeo upis briše prefiks `P__verzija__d{svoj_id}__` — samo svoje.

| Pitanje | Odgovor |
|---|---|
| Semantika identiteta | (predmet, sadržaj, **dokument**). Menja RULE 9: isti sadržaj dvaput = dva skupa vektora |
| Kompatibilnost dohvatanja | Metapodaci se ne menjaju; filter `predmet_id` isti. Duplikat sadržaja daje duplirane pogotke → treba dedup pogodaka po `vx_verzija` (postojeći dedup? **UNKNOWN**) |
| Kompatibilnost brisanja | Novi dokumenti: prefiks sa `__d{id}__`. Legacy (bez `d`): prefiks `P__verzija__` bi uhvatio i nove ID-eve istog sadržaja → legacy brisač mora isključiti ID-eve sa `__d` |
| Duplikat sadržaja | Rešava Kontraprimer 0 (nezavisni skupovi) |
| Dedup predmet/dokument | Ne menja (Smart Intake i dalje vezuje postojeći red po `content_sha256`) |
| Idempotentnost ponovnog pokušaja | Ponovni pokušaj istog upload-a sa NOVIM `dokument_id` pravi nov skup; sopstveni neuspeli skup je već počišćen → nema rasta. Pipeline A nema ključ idempotentnosti → isti fajl poslat dvaput uspešno = dva dokumenta (kao danas) |
| Reindeksacija | Nije potrebna (legacy ostaje adresabilan) |
| Migracija | **Nije potrebna** (id je UUID sa default-om; zadat id se prihvata) — **PROVEN čitanjem šeme; ne i izvršeno nad produkcijom** |
| Uvođenje | Samo novi upload-i; brisač zna oba formata |
| Povratak (rollback) | Novi ID-evi i dalje počinju sa `P__verzija__` → stari kod ih briše po starom (širem) pravilu — ponašanje kao danas, bez gubitka podataka |

**Dokaz bezbednosti pod konkurentnošću:** A briše samo ID-eve koji sadrže `__d{id_A}__`; `id_A` je UUID koji je A generisao i koji niko drugi ne upisuje ⇒ nijedan uspešno sačuvan dokument B ne može imati vektor sa tim segmentom. Važi za sve rasporede (pre/posle B-ove provere, posle završne provere), za više procesa i servera, bez zaključavanja. Preostaje samo prozor: A pao **pre** nego što je saznao da je pao (proces ubijen) → siroče bez čišćenja (isto kao danas; vidi Opciju C).

## 5. Opcija B — koordinacija kroz bazu

**Mehanizam:** tabela zakupa (npr. `vector_ingest_lease(predmet_id, verzija, upload_id, stanje, istice)`) + RPC; upload uzima zakup pre upsert-a; čišćenje briše samo ako pod `FOR UPDATE` nema drugog živog/uspelog zakupa za isti (predmet, verzija); uspeh mora držati istu bravu kroz upsert.

| Pitanje | Odgovor |
|---|---|
| Vlasnik stanja | Nova tabela — **migracija** |
| Transakcione garancije | Pinecone nije u transakciji: provera pod bravom pa `delete()` posle COMMIT-a ponovo otvara prozor, osim ako i B drži bravu kroz upsert ⇒ serijalizacija svih upload-a istog sadržaja u predmetu, brava preko spoljnog poziva (sekunde) |
| Više procesa | Radi (brava u bazi), za razliku od procesnog lock-a |
| Pad između baze i Pinecone-a | Zakup ostaje „u toku“ → istek + reaper; reaper ne sme brisati dok ne dokaže da nijedan red ne postoji (vraća se isti problem) |
| Pad servera tokom čišćenja | Zakup ističe; ponovno čišćenje idempotentno |
| Potvrda brisanja izgubljena | Ponovni list → ništa → u redu |
| Baza nedostupna | Nema zakupa → nema upload-a (fail-closed) ili upload bez zakupa (nebezbedno) — odluka |
| Deadlock | Nizak (jedan ključ), ali brava preko mrežnog poziva = rizik dugih čekanja |
| **Ocena** | Najsloženija; migracija + RPC + reaper; ne preporučuje se kao najmanja |

## 6. Manje opcije u postojećoj arhitekturi

**C1 — kapija na strani čitanja (nedestruktivna).** RAG odbacuje pogodak čiji par (`predmet_id`, `vx_verzija`) nema red `predmet_dokumenti` sa tim `content_sha256` u tom predmetu. Jedan upit po pretrazi (`in_` nad ≤ top_k parova). Siroče se nikad ne prikazuje; kasniji uspešan upis istog sadržaja ga automatski „usvaja“. **Ništa se ne briše ⇒ invarijanta je trivijalno zadovoljena.** Mesto: jedino usko grlo `shared/rag_acl.py` / `app/services/retrieve.py` (docstring rag_acl tvrdi da je jedino — **INFERRED**, treba popis svih čitača namespace-a vlasnika).
Rizik: redovi čiji `content_sha256` nije kanonska verzija (legacy bajt-heš, vidi `NedovoljanIdentitet` grana) ⇒ njihovi vektori bi se sakrili. Broj takvih redova u produkciji: **UNKNOWN** — mora se izmeriti (read-only upit) pre uključivanja; legacy pogoci bez `vx_verzija` moraju proći.

**C2 — brisanje predmeta po prefiksu predmeta.** Posle brisanja po redovima, briše se ostatak po prefiksu `"{predmet_id}__"` u namespace-u vlasnika. Bezbedno jer se ceo predmet briše (tombstone već postoji; scope je predmet, različit tenant ⇒ različit scope). Zatvara rupu u pravu na zaborav za siročad. **PROVEN čitanjem: upload ruta (`api.py::predmet_upload_auto_analyze`, provera predmeta ~6005: `select("id,naziv,tip") … .single()`) NE proverava `brisanje_zapoceto`** — predmet u brisanju i dalje prima upload, pa vektori mogu nastati i POSLE brisanja po prefiksu (red bi potom pao na FK kad predmet nestane ⇒ novo siroče). C2 zato traži i proveru tombstone-a na upload ruti (isti obrazac kao `_je_u_brisanju` na drugim rutama), plus verifikaciju posle brisanja (list = prazno).

**C0 — odmah, nedestruktivno, za Kontraprimer 0.** `obrisi_vektore_dokumenta` ne briše vektore ako drugi red u istom predmetu ima isti `content_sha256` (vektori pripadaju i njemu); red se briše, vektori ostaju. Ne dodaje brisanje, uklanja jedno. Bez migracije.

## 7. Kontraprimeri pod konkurentnošću

| # | Scenario | Danas (bez čišćenja) | Povučen M05 | A (dokument-id) | B (zakup) | C1 + C2 |
|---|---|---|---|---|---|---|
| 1 | A pada, B uspe, isti sadržaj | siroče = vektori B (deljeni) — **bezopasno** | B izgubi vektore | A briše samo svoje; B netaknut | B netaknut ako B drži bravu | ništa se ne briše; B vidljiv |
| 2 | B upiše red između A-ove provere i `delete()` | — | **B izgubi** (PROVEN, PR #45) | nemoguće (različit segment) | sprečeno samo uz bravu kroz upsert | nema brisanja |
| 3 | B upiše red posle A-ove završne provere | — | **B izgubi bez signala** (PROVEN) | nemoguće | isto kao 2 | nema brisanja |
| 4 | Oba pada | 1 skup siročadi | očišćeno | oba čiste svoje | oba čiste | sakriveno (C1); brisanje predmeta čisti (C2) |
| 5 | Oba uspeju | 2 reda, 1 skup (Kontraprimer 0 pri brisanju jednog) | isto | 2 nezavisna skupa (duplikati pogodaka) | isto kao danas | isto kao danas (+C0 štiti) |
| 6 | Server A padne tokom čišćenja | — | delimično | ponovni pokušaj nemoguć (A ne zna) → siroče; C1/C2 pokrivaju | zakup ističe → reaper | C1/C2 |
| 7 | `delete` uspe, potvrda izgubljena | — | VERIFICATION_FAILED | list → prazno → u redu | isto | — |
| 8 | Baza privremeno nedostupna | — | REFUSED (siroče) | čišćenje i dalje bezbedno (ne čita bazu) | upload blokiran ili nebezbedan | C1 bez baze: pogodak se ne može proveriti → mora fail-closed (sakriti) ili fail-open — **odluka** |
| 9 | Isti sadržaj, različiti predmeti istog korisnika | različit scope ⇒ nezavisno | nezavisno | nezavisno | nezavisno | nezavisno |
| 10 | Dva tenanta, isti sadržaj | različit scope + namespace ⇒ nezavisno | nezavisno | nezavisno | nezavisno | nezavisno |

## 8. Operativni rizici

- A: duplirani vektori za duplirani sadržaj (trošak skladišta, duplirani pogoci); dvoformatno brisanje mora biti testirano na oba formata.
- B: dugotrajne brave preko mreže; reaper koji ponovo uvodi problem dokaza.
- C1: dodatni upit po pretrazi; rizik sakrivanja legacy dokumenata dok se ne izmeri `content_sha256` pokrivenost; ponašanje kad baza ne odgovara.
- C2: upload ruta danas NE odbija predmet u brisanju (PROVEN) — bez te provere C2 ostavlja prozor.
- Siročad ostaju fizički u Pinecone-u kod C1 (trošak), dok ih C2 ne očisti pri brisanju predmeta.

## 9. Migracije

A: nijedna (zadat UUID). B: nova tabela + RPC + indeksi. C0/C1/C2: nijedna. Svaka opcija bez migracije i dalje traži odluku jer menja ponašanje brisanja ili pretrage.

## 10. Uvođenje i povratak

- C0 → odmah iza zastavice ili direktno (samo uklanja brisanje); povratak = staro ponašanje.
- C1 → prvo read-only merenje (broj redova bez kanonske verzije; broj pogodaka koje bi sakrio na uzorku), pa uključivanje; povratak = isključiti kapiju.
- C2 → deo puta brisanja predmeta; povratak = bez ostatka po prefiksu (rupa ostaje).
- A → samo novi upload-i; brisač čita oba formata pre prvog upisa novog formata; povratak bez gubitka (novi ID-evi ostaju adresabilni starim prefiksom).

## 11. Preporuka — najmanji bezbedan dizajn

**Faza 1 (bez migracije, bez novog identiteta, bez novog brisanja): C0 + C1 + C2.**
- C0 zatvara postojeći deterministički gubitak (Kontraprimer 0).
- C1 čini siroče nevidljivim dok red ne postoji — M05 korisnički simptom (sadržaj koji nije u spisku dokumenata u RAG-u) nestaje, a invarijanta važi jer se ništa ne briše.
- C2 zatvara rupu u pravu na zaborav.
Preduslov: read-only merenje pokrivenosti `content_sha256` kanonskom verzijom (C1) i dodavanje provere tombstone-a na upload rutu (C2 — danas je nema, PROVEN).

**Faza 2 (opciono, ako osnivač želi fizičko uklanjanje siročadi pri neuspehu): Opcija A** — jedini mehanizam koji uz pun dokaz dozvoljava brisanje pod konkurentnošću bez brava i bez migracije, po ceni promene RULE 9.

Opcija B se ne preporučuje.

## 12. Odluke koje su isključivo osnivačeve

1. Da li je promena RULE 9 („isti sadržaj = isti vektori“) prihvatljiva (Opcija A) ili identitet ostaje (predmet, sadržaj).
2. C1 kad baza ne odgovara: sakriti pogotke (fail-closed, prazniji odgovori) ili prikazati (fail-open, siroče moguće).
3. Da li Pipeline A treba da ODBIJA isti sadržaj u istom predmetu (danas samo upozorava) — to bi uklonilo Kontraprimer 0 na izvoru.
4. Odobrenje read-only merenja nad produkcijom (pokrivenost `content_sha256`, broj siročadi po `vx_verzija` bez reda).
5. Redosled: C0 odmah (najmanji rizik) ili sve zajedno.
