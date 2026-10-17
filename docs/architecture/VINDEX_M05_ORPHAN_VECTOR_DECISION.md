# VINDEX — M05: siročad vektora posle neuspelog upisa dokumenta — odluka o arhitekturi

**Status:** PREDLOG ZA ODLUKU OSNIVAČA (ispravljeno u PR #46 C03: C0 i C2 ponovo procenjeni pod konkurentnošću, vidi §6a). **Ništa od ovoga nije implementirano.** Nema promene šeme, identiteta vektora, radnika za čišćenje ni brisanja.
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

**C2 — brisanje predmeta po prefiksu predmeta.** Posle brisanja po redovima, briše se ostatak po prefiksu `"{predmet_id}__"` u namespace-u vlasnika. Bezbedno jer se ceo predmet briše (tombstone već postoji; scope je predmet, različit tenant ⇒ različit scope). Smanjuje (ne zatvara — vidi §6a) rupu u pravu na zaborav za siročad. **PROVEN čitanjem: upload ruta (`api.py::predmet_upload_auto_analyze`, provera predmeta ~6005: `select("id,naziv,tip") … .single()`) NE proverava `brisanje_zapoceto`** — predmet u brisanju i dalje prima upload, pa vektori mogu nastati i POSLE brisanja po prefiksu (red bi potom pao na FK kad predmet nestane ⇒ novo siroče). Provera tombstone-a na ulazu upload rute je potrebna, ali **nije dovoljna**: upload koji je već prošao proveru i dalje može da upiše vektore posle brisanja po prefiksu (§6a, C2-P1). „List = prazno“ posle brisanja nije dokaz da kasniji upsert neće stići (§6a).

**C0 — odmah, nedestruktivno, za Kontraprimer 0.** `obrisi_vektore_dokumenta` ne briše vektore ako drugi red u istom predmetu ima isti `content_sha256` (vektori pripadaju i njemu); red se briše, vektori ostaju. Ne dodaje brisanje, uklanja jedno. Bez migracije. **Ograničenje (§6a, C0-P1):** C0 je provera-pa-brisanje bez brave; štiti samo red koji je već upisan u trenutku provere. Upload istog sadržaja koji je u toku (vektori upisani ili se upisuju, red još ne) i dalje može ostati bez vektora.

## 6a. Ponovna procena C0 i C2 pod konkurentnošću (PR #46 C03)

Ranija verzija ovog dokumenta je C0 i C2 predstavila jače nego što jesu. Ispravka:

**Činjenice od kojih zavisi procena**

| Činjenica | Status |
|---|---|
| Upload upisuje vektore PRE reda `predmet_dokumenti` (red je poslednji korak) | PROVEN čitanjem (§1) |
| Isti sadržaj u istom predmetu ⇒ isti ID-evi vektora; upsert drugog upload-a prepisuje iste ID-eve | PROVEN (§1) |
| Između provere u bazi i `delete()` u Pinecone-u nema zajedničke transakcije ni brave | PROVEN (dve odvojene usluge) |
| Upload ruta proverava predmet jednom, na ulazu, pa radi ekstrakciju i embedding (sekunde do minuta) | PROVEN čitanjem (`api.py::predmet_upload_auto_analyze`) |
| Pinecone `list` odmah posle `delete` odražava sve ranije upsert-e | **ASSUMPTION** — nije izmereno (serverless indeks ima kašnjenje svežine) |
| Redosled u `shared/predmet_deletion.py`: tombstone (`brisanje_zapoceto`, ~222) → zavisni redovi → vektori po redovima (~440–478) → red `predmeti` POSLEDNJI (~480) | PROVEN čitanjem ⇒ upload u toku tokom brisanja vidi predmet (sa tombstone-om) sve do kraja, pa C2-P2 grana „red upisan u predmet u brisanju“ postoji |

### C0 — šta garantuje, šta ne

| | |
|---|---|
| **Dokazana garancija** | Ako je red D2 sa istim `content_sha256` u istom predmetu **već upisan i vidljiv** u trenutku provere, brisanje D1 ne dira vektore. To zatvara Kontraprimer 0 (§3a), koji je deterministički i bez konkurentnosti. |
| **Nije garantovano (C0-P1)** | Upload B istog sadržaja u isti predmet je u toku: B je upisao (ili upisuje) vektore, a red D2 još ne postoji. Provera D1 ne vidi D2 → D1 briše prefiks → B upiše red i vrati uspeh, a vektora nema. **Početna provera u bazi NE sprečava da kasniji uspešan upload deli obrisane vektore.** |
| **Nije garantovano (C0-P2)** | Isti ishod ako B upiše red između provere i `delete()` (ista klasa kao PR #45 kontraprimeri 2 i 3). |
| Pretpostavka | Prozor je kratak (provera → `delete()`), a preklapanje traži isti sadržaj, isti predmet i istovremeno brisanje — retko, ali nije dokazano da se ne dešava. |
| Šta prozor zatvara | Samo identitet po dokumentu (Opcija A, različit segment `__d{id}__`) ili brava koju i upload drži kroz upsert (Opcija B). C0 nijedno ne obezbeđuje. |
| Poređenje sa danas | C0 ne dodaje nijedno brisanje i strogo je bolji od današnjeg ponašanja (danas Kontraprimer 0 važi i bez trke). Nije „bezbedan pod konkurentnošću“. |

### C2 — šta garantuje, šta ne

| | |
|---|---|
| **Dokazana garancija** | Brisanje po prefiksu `"{predmet_id}__"` u namespace-u vlasnika uklanja sve vektore tog predmeta **koji su vidljivi indeksu u trenutku brisanja** (uklj. siročad bez reda). Scope je predmet (UUID) ⇒ ne dira druge predmete ni tenante. |
| **Nije garantovano (C2-P1)** | Upload U je prošao proveru predmeta (i proveru tombstone-a, ako se doda) PRE početka brisanja i još radi. Brisanje postavi tombstone, obriše redove i prefiks; U zatim upiše vektore. Rezultat: vektori obrisanog predmeta posle brisanja. **Provera tombstone-a na ulazu NE sprečava da upload koji je već u toku završi posle brisanja predmeta.** |
| **Nije garantovano (C2-P2)** | Upis reda posle brisanja: ako red `predmeti` još postoji (tombstone), U upiše `predmet_dokumenti` u predmet u brisanju; ako ne postoji, upis pada na FK → 500, vektori ostaju. U oba slučaja vektori preživljavaju brisanje. |
| **Nije garantovano (C2-P3)** | Proces U ubijen posle upsert-a ⇒ niko ne zna za te vektore. |
| **Nije dokaz** | `list(prefix) = prazno` odmah posle brisanja (ASSUMPTION o svežini; i U može upisati kasnije). |
| Ublažavanja (nisu implementirana) | (1) provera tombstone-a na ulazu: zatvara samo NOVE upload-e posle početka brisanja; (2) U ponovo čita tombstone **posle** upsert-a i, ako je predmet u brisanju, briše prefiks svog predmeta — bezbedno po scope-u jer se ceo predmet briše, ali ostaje prozor čitanje→upsert i C2-P3; (3) odloženi drugi prolaz brisanja po prefiksu (npr. za predmete obrisane pre > T) — hvata C2-P1/P3 uz pretpostavku da upload traje kraće od T. |
| Vidljivost u međuvremenu | Vektori obrisanog predmeta nisu dohvatljivi kroz RAG (filter `predmet_id ∈ dozvoljeni`, PROVEN §1) — rizik je fizičko zadržavanje podataka (pravo na zaborav), ne prikaz. |

### Preostali prozori posle Faze 1 (C0 + C1 + C2)

1. C0-P1/P2: retka trka brisanje dokumenta ↔ upload istog sadržaja ⇒ dokument bez vektora (tiho izostaje iz RAG-a). Zatvara samo Opcija A ili B.
2. C2-P1/P2/P3: vektori upload-a koji je bio u toku tokom brisanja predmeta ⇒ fizičko zadržavanje dok ih drugi prolaz ne ukloni; bez drugog prolaza — trajno.
3. Pretpostavka o svežini Pinecone `list` nije izmerena.

## 7. Kontraprimeri pod konkurentnošću

| # | Scenario | Danas (bez čišćenja) | Povučen M05 | A (dokument-id) | B (zakup) | C1 + C2 |
|---|---|---|---|---|---|---|
| 1 | A pada, B uspe, isti sadržaj | siroče = vektori B (deljeni) — **bezopasno** | B izgubi vektore | A briše samo svoje; B netaknut | B netaknut ako B drži bravu | ništa se ne briše; B vidljiv |
| 2 | B upiše red između A-ove provere i `delete()` | — | **B izgubi** (PROVEN, PR #45) | nemoguće (različit segment) | sprečeno samo uz bravu kroz upsert | nema brisanja |
| 3 | B upiše red posle A-ove završne provere | — | **B izgubi bez signala** (PROVEN) | nemoguće | isto kao 2 | nema brisanja |
| 4 | Oba pada | 1 skup siročadi | očišćeno | oba čiste svoje | oba čiste | sakriveno (C1); brisanje predmeta čisti (C2) |
| 5 | Oba uspeju | 2 reda, 1 skup (Kontraprimer 0 pri brisanju jednog) | isto | 2 nezavisna skupa (duplikati pogodaka) | isto kao danas | isto kao danas (+C0 štiti kad su oba reda već upisana; ne i upload u toku — §6a C0-P1) |
| 6 | Server A padne tokom čišćenja | — | delimično | ponovni pokušaj nemoguć (A ne zna) → siroče; C1/C2 pokrivaju | zakup ističe → reaper | C1/C2 |
| 7 | `delete` uspe, potvrda izgubljena | — | VERIFICATION_FAILED | list → prazno → u redu | isto | — |
| 8 | Baza privremeno nedostupna | — | REFUSED (siroče) | čišćenje i dalje bezbedno (ne čita bazu) | upload blokiran ili nebezbedan | C1 bez baze: pogodak se ne može proveriti → mora fail-closed (sakriti) ili fail-open — **odluka** |
| 9 | Isti sadržaj, različiti predmeti istog korisnika | različit scope ⇒ nezavisno | nezavisno | nezavisno | nezavisno | nezavisno |
| 10 | Dva tenanta, isti sadržaj | različit scope + namespace ⇒ nezavisno | nezavisno | nezavisno | nezavisno | nezavisno |

## 8. Operativni rizici

- A: duplirani vektori za duplirani sadržaj (trošak skladišta, duplirani pogoci); dvoformatno brisanje mora biti testirano na oba formata.
- B: dugotrajne brave preko mreže; reaper koji ponovo uvodi problem dokaza.
- C1: dodatni upit po pretrazi; rizik sakrivanja legacy dokumenata dok se ne izmeri `content_sha256` pokrivenost; ponašanje kad baza ne odgovara.
- C2: upload ruta danas NE odbija predmet u brisanju (PROVEN). Provera na ulazu sužava, ali ne zatvara prozor: upload u toku može da upiše vektore posle brisanja (§6a C2-P1..P3); potreban je i drugi prolaz ili provera posle upsert-a.
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
- C0 zatvara postojeći deterministički gubitak (Kontraprimer 0); **ne** zatvara trku sa upload-om istog sadržaja koji je u toku (§6a C0-P1/P2).
- C1 čini siroče nevidljivim dok red ne postoji — M05 korisnički simptom (sadržaj koji nije u spisku dokumenata u RAG-u) nestaje, a invarijanta važi jer se ništa ne briše.
- C2 uklanja siročad koja postoje u trenutku brisanja predmeta; upload u toku i dalje može ostaviti vektore posle brisanja (§6a C2-P1..P3) — potreban drugi prolaz.
Preduslov: read-only merenje pokrivenosti `content_sha256` kanonskom verzijom (C1), provera tombstone-a na upload ruti (danas je nema, PROVEN) **i** odluka o drugom prolazu brisanja po prefiksu ili proveri posle upsert-a (§6a). Faza 1 ostavlja imenovane prozore iz §6a; potpuno zatvaranje trke dokument ↔ upload traži Fazu 2.

**Faza 2 (opciono, ako osnivač želi fizičko uklanjanje siročadi pri neuspehu): Opcija A** — jedini mehanizam koji uz pun dokaz dozvoljava brisanje pod konkurentnošću bez brava i bez migracije, po ceni promene RULE 9.

Opcija B se ne preporučuje.

## 12. Odluke koje su isključivo osnivačeve

1. Da li je promena RULE 9 („isti sadržaj = isti vektori“) prihvatljiva (Opcija A) ili identitet ostaje (predmet, sadržaj).
2. C1 kad baza ne odgovara: sakriti pogotke (fail-closed, prazniji odgovori) ili prikazati (fail-open, siroče moguće).
3. Da li Pipeline A treba da ODBIJA isti sadržaj u istom predmetu (danas samo upozorava) — to bi uklonilo Kontraprimer 0 na izvoru.
4. Odobrenje read-only merenja nad produkcijom (pokrivenost `content_sha256`, broj siročadi po `vx_verzija` bez reda).
5. Redosled: C0 odmah (najmanji rizik) ili sve zajedno.
6. Da li su preostali prozori iz §6a prihvatljivi za Fazu 1 ili je Opcija A uslov.
7. Da li se uvodi drugi prolaz brisanja predmeta po prefiksu i sa kojom vrednošću T.
