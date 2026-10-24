# C3b FINAL CLOSURE — read-only procena uticaja na produkciju, kontrolisani QA i povratak

Ništa u ovom dokumentu ne pokreće izvršilac. Upite pokreće osnivač u Supabase SQL editoru; svi su **samo za čitanje**.
Izvršilac nikad nije pristupio produkcionoj bazi.

## A. Read-only upiti pre release review-a

```sql
-- A1. Da li u produkciji već postoje nacrti iz spisa ili dokumenti za sud? (očekivano: 0 redova — T06/C3b nikad pušteni)
select tip, status, count(*) from public.staging_memory
 where tip in ('nacrt_iz_spisa', 'dokument_za_sud') group by 1, 2 order by 1, 2;

-- A2. Ostali nacrti na pregledu (ponašanje drugih tipova se NE menja; samo za uvid u obim)
select tip, status, count(*) from public.staging_memory group by 1, 2 order by 3 desc limit 30;

-- A3. RLS nad staging_memory (GATE-01 N2: politika vlasnika FOR ALL dozvoljava direktan upis mimo ruta)
select policyname, cmd, roles, qual, with_check from pg_policies
 where schemaname = 'public' and tablename = 'staging_memory';

-- A4. Kolona quality_detail je jsonb (ugovor je ne menja; filter quality_detail->>usvajanje_rev)
select column_name, data_type, is_nullable, column_default from information_schema.columns
 where table_schema = 'public' and table_name = 'staging_memory' order by ordinal_position;
```

Ako A1 vrati redove: to su nacrti napravljeni van ovog toka. Novi kod ih ne izvozi i ne odobrava (409); osnivač
odlučuje da li ih treba odbiti pre puštanja.

## B. Kontrolisani QA scenario (posle eventualnog puštanja, osnivač, sintetički predmet)

Predmet: Golden Case (sintetički, `tests/mir001_golden_case.py` — 7 PDF-ova; isti fajlovi kao u
`live-mir001-spis-e2e.mjs`). Nikad stvarni klijentski spis.

1. Nov predmet → Prijem: 7 fajlova → prikači sve (sken DOK-05 mora proći OCR).
2. Savetnik za ovaj predmet → „Pisanje podnesaka“ → zahtev „Sastavi podnesak tužioca … DOK-05 … DOK-06 … stanje
   postupka.“ Očekivano: naslov „AI radni predlog — samo za pregled …“; 1 naplata.
3. Kartica Nacrt → red „AI predlog — za pregled, ne izvozi se“ → Otvori. Očekivano: tri dela; deo 3 prazan;
   nijedna tačka izabrana; stare dugmadi (Sačuvaj/Odobri/DOCX nad AI tekstom) nema.
4. **Provera PostgREST filtera (preduslov 3):** „Proverio sam — usvajam“ na zaglavlju → mora uspeti (stavka u delu 3).
   Ako vrati grešku → STOP, prijaviti (ruta pada zatvoreno; ništa nije upisano tiho).
5. Uporediti svaku stavku sa spisom; usvojiti tačne, odbiti netačne (npr. „4.200.000 … uključuje … 600.000“ ako se
   pojavi). Otvoriti bar jedan izvor iz stavke.
6. Dopisati rečenicu; Sačuvaj. Odobri → mora tražiti procesne tačke.
7. 8 tačaka: npr. ODLUKE_SUDA = ispravljeno + opis; ostale „nepoznato“. Promeniti jednu i NE sačuvati → Odobri mora
   reći „nesačuvane odluke … Ništa nije odobreno.“ Sačuvati → Odobri → „odobren“.
8. Preuzeti DOCX: otvoriti u Wordu — tekst = deo 3; nema „NACRT IZ SPISA“, nema „Generisano … Vindex AI“, nema
   internih napomena. Pogledati izvode oblika „(DOK-07 …)“ (odluka osnivača, izveštaj §8).
9. „Nova verzija“ → tačke prazne, odobrenje nije nasleđeno; „Odbij“ iz liste → v2 odbijena, v1 i dalje izvoziva.
10. Drugi nalog: link/ID dokumenta za sud → nedostupan.
11. Read-only posle QA: A1 (očekivano: 1 `nacrt_iz_spisa`, 1 `dokument_za_sud` approved, 1 rejected) i
    `select pinecone_indexed from staging_memory where tip = 'dokument_za_sud'` → false.

## C. Povratak (rollback)

- Ponovo pustiti `f33dcce8` (Render: redeploy prethodnog commita). Migracija nema — baza se ne vraća.
- **Pre povratka** — stari kod (`f33dcce8`) ne zna za ove tipove i tretira ih kao obične nacrte:
  - red **na čekanju**: stari „odobri“ ga može uneti u bazu znanja kancelarije (Pinecone) ako mu je ocena kvaliteta
    ≥ 0,85;
  - **odobren** red sa `pinecone_indexed = false` i ocenom ≥ 0,85: stari `_ponovni_upis_moguc` vraća true, V2 nudi
    „Ponovi upis u bazu znanja“, a `POST /api/staging/{id}/ponovi-upis` (RPC iz migracije 140, ako je primenjena) bi
    ga uneo u bazu znanja (GATE-04 B1). Dokument za sud dobija ocenu pri `PATCH /tekst`, pa je ovo realno.
  ```sql
  -- svi redovi ova dva tipa koje bi stari kod mogao da unese u bazu znanja
  select id, tip, status, is_lawyer_approved, pinecone_indexed, confidence_score from public.staging_memory
   where tip in ('nacrt_iz_spisa', 'dokument_za_sud')
     and (status = 'pending' or (status = 'approved' and pinecone_indexed = false and confidence_score >= 0.85));
  ```
  Osnivač odlučuje šta sa tim redovima pre povratka (npr. odbijanje redova na čekanju i spuštanje ocene ili drugo
  isključenje odobrenih) — upis radi osnivač, ne izvršilac. Bez te odluke povratak krši invarijantu „AI predlog i
  dokument za sud nikad ne ulaze u bazu znanja“ (MIR001 T06 / C3b).
- Odobreni redovi koji nisu u gornjem upitu ostaju kao zapis; stari kod nema staging DOCX rutu za njih.

## D. Trošak i ponavljanje

- Izrada predloga: 1 poziv modela i 1 naplata (bez automatskog ponavljanja; nepouzdan JSON → 502 bez naplate i upisa).
- Usvajanje, tačke, odobrenje, DOCX: 0 poziva modela, 0 naplate.
- Ponovljen klik: stavka (ista odluka) bez promene; dokument za sud vraća postojeću verziju na čekanju; odobrenje
  drugi put „već obrađen“; paralelni upisi → 409 (revizija). `/api/agents/run` pokriva postojeća trajna idempotencija.
- Poznato od ranije (nepromenjeno): ponovljena izrada u kratkom roku za isti predmet naplaćuje drugi poziv, a drugi
  predlog se ne upisuje na pregled (zaštita od duplikata u `_stage_draft_for_review`).
