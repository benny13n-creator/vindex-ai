# Vindex AI — Institutional Learning & RAG Architecture Audit (2026-07-26)

**Metod:** direktno čitanje koda (`api.py`, `app/services/retrieve.py`,
`routers/dokument.py`, `routers/evidence.py`, `routers/smart_intake.py`,
`routers/cross_doc.py`, `routers/knowledge_base.py`, `routers/drafting.py`,
`routers/batch_ingest.py`, migracije), ne pretpostavke. Svaki nalaz ima
file:line dokaz. Analiza, nula izmena koda.

**Korekcija premise iz zahteva:** vektorska pretraga u Vindex AI ide
isključivo preko **Pinecone-a**, ne pgvector/Postgres-a (potvrđeno i u
`docs/PRODUCTION_READINESS_REPORT_2026-07-25.md` §2 — nula pgvector/ivfflat
u migracijama). Fajlovi `documents.py`/`cases.py`/`rag_service.py`/
`vector_search.py` iz zahteva ne postoje pod tim imenima — stvarna imena su
`api.py` (upload endpoint), `app/services/retrieve.py` (RAG servis) i
`routers/dokument.py`/`routers/evidence.py`/`routers/smart_intake.py`
(dokument-tokovi). Analiza je urađena na stvarnim fajlovima.

**Verdikt u jednoj rečenici:** Auto-indeksiranje POSTOJI i radi sinhrono
pri svakom uploadu, ali arhitektura namespace-a je toliko fragmentirana da
efektivno **ne postoji nijedan način da sistem pretraži "sve dokumente u
ovom predmetu"**, a kamoli "sve predmete kancelarije" — Vindex AI danas ima
RAG za spoljašnje pravo, ali nema institucionalno pamćenje sopstvenog rada.

---

## 1. Auto-Indeksiranje Novih Predmeta

| Pitanje | Nalaz |
|---|---|
| Da li se dokument automatski embed-uje? | **DA, sinhrono.** `POST /api/predmeti/{predmet_id}/upload` (`api.py:4134-4278`) ekstraktuje tekst (`uploaded_doc.extractor.extract()`, sa OCR fallback-om), chunk-uje (`api.py:4223-4235`) i odmah poziva `ingest_session(...)` (`uploaded_doc/ingest.py:38-90`) — **u istom HTTP request-u**, nema background worker-a. |
| Gde se čuva sirov tekst? | `predmet_dokumenti.tekst_sadrzaj` (Supabase), skraćeno na 100k karaktera (`api.py:4247,4273`). |
| **Namespace problem** | **KRITIČAN NALAZ.** Namespace je `pred_{session_id}` gde je `session_id` **slučajan ID generisan pri SVAKOM uploadu** (`api.py:4227`), NE `pred_{predmet_id}`. Rezultat: svaki dokument u istom predmetu završava u SVOM SOPSTVENOM, izolovanom Pinecone namespace-u. Jedina veza nazad je `predmet_dokumenti.pinecone_namespace` po redu. **Ne postoji nijedan namespace koji predstavlja "ceo predmet"** — pretraga "kroz sve dokumente ovog predmeta" fizički nije moguća bez ručnog nabrajanja i paralelnog upita na N različitih namespace-ova. |
| Metadata uz vektor | `source_filename`, `source_format`, `source_sha256`, `chunk_index`, `article_label`, tekst (do 40k karaktera po chunk-u) — **`predmet_id` se NE čuva u samoj vektor metadati** (`uploaded_doc/ingest.py:12,65`). |
| Otpornost na grešku | Dobro rešeno: ako Pinecone padne (429/storage full), dokument ostaje sačuvan u Supabase sa status-om `"sacuvano"` umesto `"indeksirano"` (`api.py:4238-4267`) — dokument se nikad ne gubi, samo gubi pretraživost. |
| Duplikat put | Identičan obrazac (i identičan namespace problem) ponovljen u `routers/smart_intake.py:502-539` za dokumente prikačene tokom intake wizard-a. |
| Retroaktivni/batch mehanizam | **NE POSTOJI za klijentske dokumente.** `routers/batch_ingest.py` je admin-only i hardkodovan na `ALLOWED_NAMESPACES = {"sudska_praksa", "misljenja"}` (`batch_ingest.py:27`) — isključivo spoljašnji pravni korpus. Nijedan `workers/` fajl ne dodiruje `predmet_dokumenti`. Ako je dokument ostao `"sacuvano"` (Pinecone bio nedostupan), **nema retry/backfill job-a** — ostaje trajno neindeksiran dok advokat ručno ne otpremi ponovo. |
| Verzionisanje | **Ne postoji.** Svaki upload dobija nov redni broj (DOK-01, DOK-02...) i nov namespace — nema polja "supersedes"/"previous_version_id", nema delete-pa-reinsert logike. Finalna potpisana verzija ugovora postaje DRUGI, nezavisan pretraživ dokument pored drafta — oba ostaju trajno u indeksu, jednako "validna" u očima RAG-a. |
| AI-generisani nacrti | **Nikad se ne čuvaju kao referenca.** `routers/drafting.py`'s `/api/nacrt` i `/api/podnesak` (linije 399, 545) generišu tekst i vraćaju ga — nula Pinecone poziva na izlazu. Jedini writeback mehanizam je `/api/playbook/upload` (`drafting.py:319-361`) — RUČAN, opt-in upload firm-style šablona od strane advokata, skopiran **po pojedinačnom `user_id`**, ne po firmi, i hvata korisnikov materijal, ne AI-jev generisani rad. Sistem nikad ne "pamti" da je već napisao sličnu tužbu prošli put. |

---

## 2. Scope i Deljenje Znanja unutar Kancelarije

| Pitanje | Nalaz |
|---|---|
| Kako se konstruiše scope u `retrieve.py`? | Fiksni namespace-ovi za spoljašnji korpus (`_ZAKONI_NS`, `_MISLJENJA_NS`, `_PRAKSA_NS`) + opcioni `extra_namespaces` parametar (linija 1572) za paralelnu pretragu proizvoljnih Pinecone namespace-ova (koristi se za `tmp_<session_id>` kod ad-hoc analize dokumenta). **Nema `organization_id`/`kancelarija_id`/`org_id` parametra nigde u fajlu.** |
| Pretraga "svih predmeta korisnika"? | **Ne postoji.** Jedini put ka klijentskim dokumentima je eksplicitno prosleđen namespace (per-dokument). `routers/cross_doc.py` (~linija 306) zahteva da korisnik RUČNO izabere 2+ `dokument_id` i rekonstruiše tekst po dokumentu — ovo je manuelni alat za poređenje, ne case-wide RAG pretraga. |
| Pretraga "svih predmeta kancelarije"? | **Ne postoji — i ne bi mogla da postoji čak i da neko pokuša.** `kancelarije` + `kancelarija_clanovi` (migracija 018) definišu STVARNE multi-user firm naloge (admin/partner/saradnik/čitanje uloge) — `kancelarija_id` se koristi za `ai_corrections`, `zadaci`, `memory_entries`, `partner_profiles` (045/046). **Ali `predmeti`, `klijenti`, `predmet_dokumenti` NEMAJU `kancelarija_id` kolonu.** RLS (migracija 078) strogo ograničava `klijenti`/`predmet_komentari` na `USING (auth.uid()::text = user_id)` — bez firm grane. Čak i da aplikacija POKUŠA cross-user pretragu, RLS bi je blokirao na nivou baze. |
| Zaključak | **Vindex AI je danas single-user-per-predmet arhitektura na nivou podataka o predmetima**, uprkos tome što "Kancelarija" kao billing/role koncept već postoji i radi za druge funkcije. Firma i predmeti su dve paralelne, nespojene šeme. |

---

## 3. Razdvajanje Izvora Znanja

**Delimično dobra vest — postoji stvarna labela, ali dva sloja gde se to
gubi.**

- **LLM KONTEKST (dobro rešeno):** `app/services/doc_formatter.py`
  eksplicitno labelira svaki pasus iz korisnikovog dokumenta kao
  `KORISNIKOV DOKUMENT [filename, article, chunk]` (linije 14-38) — LLM
  ZAISTA vidi razliku između zakona/sudske prakse i korisnikovog dokumenta
  u istom promptu, i može da prilagodi stil citiranja. Ovo je jasno
  namerno dizajnirano (docstring: *"so the LLM can distinguish it from
  zakon and sudska_praksa entries"*).
- **STRUKTURNI IZLAZ (mrtvo polje):** `retrieve_documents()` vraća
  `doc_passages` kao odvojen ključ od `izvori` (`retrieve.py:1915-1916`) —
  namera je bila da UI prikaže "izvore" i "vaše dokumente" odvojeno. Ali
  **nijedan router ni `static/vindex.js` ne čita `doc_passages`** — polje
  se računa i vraća, ali se nikad ne prikazuje korisniku niti drugačije
  koristi. Razdvajanje postoji u podatku, ne i u korisničkom iskustvu.
- **"Interno kancelarijsko znanje" (stari predmeti, beleške) ≠ "trenutni
  upload".** Pošto cross-case pretraga ne postoji (§2), pitanje "da li se
  RAZLIKUJE interno kancelarijsko znanje od eksterne prakse" je danas
  bez praktičnog objekta — jedino "interno" što RAG ikad vidi je dokument
  IZ TRENUTNOG PREDMETA, ne iz prošlih predmeta iste kancelarije. Čak i
  kad bi cross-case pretraga postojala, `format_doc_passage` bi i dalje
  sve klijentske dokumente (bilo iz trenutnog ili prošlog predmeta)
  označio identičnom `KORISNIKOV DOKUMENT` labelom — nema signala "ovo je
  IZ DRUGOG predmeta" ugrađenog u sam label.
- **Tri paralelne, nespojene "memorije":** ova analiza je otkrila da
  danas postoje **tri odvojena mehanizma znanja** koji se nikad ne
  ukrštaju:
  1. Per-dokument, random-namespace klijentski fajlovi (§1) — nisu ni
     agregabilni unutar istog predmeta.
  2. `routers/knowledge_base.py` — **stvarna, radna** lična baza znanja
     (`user_knowledge` tabela + Pinecone `kb_{user_id}` namespace,
     `/api/knowledge/search`) — ali strogo per-user, izolovana i od
     predmeta i od firme.
  3. `memory_entries` (firm-level, migracija 045/046) — strukturisana
     firm memorija, ali **čisto Postgres, bez embeddinga** — nije
     semantički pretraživa, samo strukturni upiti.

---

## 4. Identifikacija Rupa (Gaps) i Preporuke

### Gap-lista (rangirano po uticaju na "sistem uči od svakog predmeta")

1. **[NAJVEĆI GAP] Namespace fragmentacija sprečava čak i pretragu unutar jednog predmeta.** `pred_{session_id}` umesto `pred_{predmet_id}` znači da RAG ne može odgovoriti na "šta smo do sada saznali u ovom predmetu" bez ručnog nabrajanja svih namespace-ova tog predmeta i N paralelnih upita.
2. **Nema cross-predmet pretrage — institucionalno pamćenje ne postoji.** Ni na nivou korisnika (jedan advokat, više predmeta), a kamoli na nivou kancelarije. Svaki predmet je informaciona ostrvo.
3. **AI-generisani nacrti se ne čuvaju kao buduća referenca.** Sistem piše tužbu danas i "zaboravi" je sutra — nema petlje "prikaži mi slične nacrte koje sam ranije pisao za sličan slučaj".
4. **Nema verzionisanja dokumenata.** Draft i finalna verzija su ravnopravni, trajno koegzistirajući "izvori istine" u indeksu — RAG može citirati zastarelu verziju ugovora kao da je važeća.
5. **Nema retry/backfill za neuspešno indeksirane dokumente.** `status: "sacuvano"` je tiha, trajna rupa dok neko ručno ne primeti i ne re-uploaduje.
6. **Kancelarija (multi-user firm) postoji kao koncept, ali je odvojena od RAG-a i od šeme predmeta.** `kancelarija_id` ne postoji na `predmeti`/`klijenti`/`predmet_dokumenti` — firm-deljenje znanja zahteva schema migraciju, ne samo promenu upita.
7. **Tri paralelne memorije se ne ukrštaju** (per-dokument fajlovi, lična knowledge base, firm memory_entries) — čak i unutar granica koje danas postoje, tri sistema ne razgovaraju međusobno.
8. **`doc_passages` je mrtvo polje** — infrastruktura za "prikaži korisniku odvojeno njegove dokumente od zakona" postoji u kodu ali se nigde ne koristi.

### Preporuke (redosled predložen po zavisnosti, ne nužno po prioritetu — founder odlučuje redosled)

1. **Popraviti namespace šemu za nove uploade:** `pred_{predmet_id}` umesto `pred_{session_id}` (ili barem dodati `predmet_id` u vektor metadata + omogućiti metadata-filter upit unutar zajedničkog namespace-a) — ovo je preduslov za bilo šta ostalo na ovoj listi. Zahteva odluku o migraciji postojećih, već-indeksiranih dokumenata (re-embed ili ostave "kako jesu" uz jasnu napomenu).
2. **Dodati "pretraži sve dokumente ovog predmeta" kao eksplicitnu RAG opciju** (agregacija po `predmet_id` posle #1) — direktan odgovor na pitanje #2 iz zahteva.
3. **Odlučiti da li i kako kancelarija (firm) deli predmete/znanje** — ovo je proizvodna/pravna odluka (advokatska tajna, pristup podacima klijenta unutar firme), ne samo tehnička; zahteva `kancelarija_id` na `predmeti`/`klijenti` + odgovarajuće RLS politike, tek posle eksplicitne odluke o tome ko sme šta da vidi.
4. **Zatvoriti petlju za AI-generisane nacrte** — opciono, uz eksplicitan pristanak advokata (isti nivo pažnje kao KORAK D odluka o content-agentu ranije ove sesije, po istom principu čuvanja advokatske tajne) sačuvati generisani nacrt kao referencu za buduće slične zahteve.
5. **Retry/backfill job za `status: "sacuvano"` dokumente** — nizak rizik, jasna vrednost, može se uraditi nezavisno od ostalih stavki.
6. **Ukrstiti tri memorije ili barem dokumentovati da su namerno odvojene** — ako ostaju odvojene, to treba da bude eksplicitna arhitektonska odluka, ne slučajni nusproizvod tri odvojene sesije razvoja.
7. **Ili ukloniti `doc_passages` (mrtav kod) ili ga stvarno ožičiti u UI** — najmanja stavka, ali čisti postojeći dug.
