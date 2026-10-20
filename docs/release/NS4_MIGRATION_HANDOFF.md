# NS4 — paket za primenu migracija 138 → 139 → 140

Za osnivača, za Supabase SQL Editor produkcionog projekta. Agent nema bezbedan kanal za DDL (nema
`SUPABASE_DB_URL`, nema pristupnog tokena, nema `exec_sql` RPC-a) i zato migracije NE izvršava. Sadržaj migracija
se ne prenosi kroz chat: izvršava se TAČNO sadržaj fajlova iz repozitorijuma, proveren heševima ispod.

## 0. Fajlovi i heševi (SHA-256, sadržaj pregledan i odobren u NS4; commit `ed7c7ee2`, od tada nepromenjen)

| Red | Fajl | SHA-256 |
|---|---|---|
| 1 | `migrations/138_ns4_memorija_bez_direktnog_pristupa.sql` | `b1eb7a18e29c714e2f74069f1998733f2f4a0a7474e416bde9ba707919318933` |
| 2 | `migrations/139_ns4_atomski_ishod_predmeta.sql` | `ba162bcab8d19746dd5f63c9849f57b777eb8c53333a7f908a2fadd9ac373e33` |
| 3 | `migrations/140_ns4_oporavak_promocije_nacrta.sql` | `93226eaa6db5c7642af6c32cfa41c08a2519595408bc0e16bc1aca1326693aa7` |

Provera heša pre lepljenja (PowerShell, u korenu repozitorijuma na grani PR #47):
`Get-FileHash migrations\138_ns4_memorija_bez_direktnog_pristupa.sql -Algorithm SHA256` (isto za 139 i 140).
Ako se heš razlikuje → STOP, ne primenjivati.

Svaki fajl ima sopstveni `BEGIN; … COMMIT;`: greška bilo gde u fajlu poništava ceo fajl. Svi su idempotentni.
Kompatibilni su sa trenutno puštenim kodom (`cc8bd548`) — primena PRE spajanja koda je ispravan redosled.

## 1. Pre primene (samo čitanje)

1. **Prava instanca:** u Supabase Dashboard-u projekat čiji je URL onaj iz `SUPABASE_URL` na Render-u. Zatim:
   ```sql
   SELECT current_database(), (SELECT count(*) FROM public.predmeti) AS predmeti,
          (SELECT count(*) FROM public.klijenti) AS klijenti;
   ```
   Očekivano (čitanje 2026-10-19/20): `predmeti` ≈ 150, `klijenti` ≈ 8. Bitno odstupanje → STOP (pogrešan projekat).
2. **Nijedna nije primenjena:**
   ```sql
   SELECT to_regprocedure('public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)') AS f139,
          to_regprocedure('public.preuzmi_ponovni_upis_nacrta(uuid,text,numeric,integer)')                         AS f140a,
          to_regprocedure('public.zavrsi_promociju_nacrta(uuid,uuid,boolean)')                                     AS f140b,
          (SELECT count(*) FROM information_schema.columns
            WHERE table_schema='public' AND table_name='staging_memory' AND column_name LIKE 'promocija_%')     AS kolone140,
          (SELECT count(*) FROM pg_indexes WHERE indexname='uq_predmet_dokumenti_nacrt_staging')                 AS indeks140;
   ```
   Očekivano: `NULL, NULL, NULL, 0, 0`. Delimično primenjeno stanje → STOP i javiti agentu.
3. **Kompatibilnost jedinstvenog indeksa 140** (očekivano: 0 redova):
   ```sql
   SELECT storage_path, count(*) FROM public.predmet_dokumenti
    WHERE storage_path LIKE 'draft/staging/%' GROUP BY 1 HAVING count(*) > 1;
   ```
4. **Zatečene dozvole za 138 (sačuvati izlaz — potreban je samo za eventualni povratak):**
   ```sql
   SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
    WHERE table_schema='public' AND table_name IN ('memory_entries','memory_graph_edges','client_memory',
          'partner_profiles','judge_patterns','firm_style_profile','workflow_instances','workflow_steps',
          'outcome_log','case_patterns')
    ORDER BY 1,2,3;
   ```
5. **Nema paralelne izmene šeme** (očekivano: 0 redova):
   ```sql
   SELECT pid, state, query_start, left(query, 80) FROM pg_stat_activity
    WHERE pid <> pg_backend_pid() AND state <> 'idle'
      AND query ~* '\m(ALTER|CREATE|DROP|REVOKE|GRANT)\M';
   ```
6. **Rezervna kopija:** Dashboard → Database → Backups — postoji današnja dnevna kopija (ili PITR). Ako je nema → STOP.

## 2. Primena i provera posle svakog koraka

Redosled je obavezan: **138 → provera → 139 → provera → 140 → provera.** Neuspela provera = STOP pre sledećeg fajla.

### 138 — memorija bez direktnog Data API pristupa
```sql
SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
 WHERE table_schema='public' AND grantee IN ('anon','authenticated')
   AND table_name IN ('memory_entries','memory_graph_edges','client_memory','partner_profiles',
                      'judge_patterns','firm_style_profile','workflow_instances','workflow_steps');
```
Očekivano: **0 redova**. Uz to (backend radi kao `service_role` i mora zadržati pristup):
```sql
SELECT has_table_privilege('service_role','public.memory_entries','SELECT'),
       has_table_privilege('service_role','public.client_memory','INSERT');
```
Očekivano: `t, t`.

### 139 — atomski ishod predmeta
```sql
SELECT has_function_privilege('anon',          'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)','EXECUTE'),
       has_function_privilege('authenticated', 'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)','EXECUTE'),
       has_function_privilege('service_role',  'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)','EXECUTE'),
       has_table_privilege('authenticated','public.outcome_log','INSERT'),
       has_table_privilege('authenticated','public.case_patterns','UPDATE'),
       has_table_privilege('service_role','public.outcome_log','INSERT');
```
Očekivano: `f, f, t, f, f, t`. Usklađenost zbira: upit (b) iz zaglavlja fajla 139 → očekivano **0 redova**
(u produkciji `outcome_log` = 0 redova, pa je i `case_patterns` prazno).

### 140 — oporavak promocije nacrta
```sql
SELECT (SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='staging_memory'
          AND column_name IN ('promocija_token','promocija_preuzeta_at'))                                   AS kolone,
       (SELECT count(*) FROM pg_indexes WHERE indexname='uq_predmet_dokumenti_nacrt_staging')               AS indeks,
       has_function_privilege('authenticated','public.preuzmi_ponovni_upis_nacrta(uuid,text,numeric,integer)','EXECUTE') AS auth_a,
       has_function_privilege('authenticated','public.zavrsi_promociju_nacrta(uuid,uuid,boolean)','EXECUTE')             AS auth_b,
       has_function_privilege('service_role','public.preuzmi_ponovni_upis_nacrta(uuid,text,numeric,integer)','EXECUTE')  AS sr_a,
       has_function_privilege('service_role','public.zavrsi_promociju_nacrta(uuid,uuid,boolean)','EXECUTE')             AS sr_b;
```
Očekivano: `2, 1, f, f, t, t`.

Na kraju: Dashboard → API → „Reload schema" (ili sačekati osvežavanje PostgREST keša), da RPC funkcije budu
vidljive Data API-ju pre spajanja koda.

## 3. Zaustavljanje i povratak

- Greška tokom fajla: transakcija se sama poništava; ništa od tog fajla nije primenjeno. Ne ponavljati ručno
  delove fajla — javiti agentu tačnu poruku greške.
- Kod NS4 još nije spojen dok migracije nisu potvrđene, pa produkcija i dalje radi na `cc8bd548`, koji je
  kompatibilan sa sve tri migracije (ne zahteva povratak šeme).
- Povratak šeme samo ako se dokaže problem, po bloku „Povratak" u zaglavlju svakog fajla, obrnutim redom
  (140 → 139 → 138), i nikada dok je pušten kod koji poziva funkcije 139/140.

## 4. Posle potvrde osnivača (agent, bez nove implementacije)

1. Agent proverava šemu preko Data API-ja (samo čitanje): RPC funkcije i kolone `promocija_*` postoje;
   `anon` čitanje `memory_entries` odbijeno.
2. PR #47: Draft → Ready → spajanje uobičajenim putem (bez zaobilaženja zaštite).
3. Render AutoDeploy (bez paralelnog ručnog deploy-a) → `/health` vraća SHA spajanja → bezbednosni smoke
   (O1/O2/G1/G2/O3) bez stvarnih podataka klijenata → izveštaj i komentar na PR-u.
