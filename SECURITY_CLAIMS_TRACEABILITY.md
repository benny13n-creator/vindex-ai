# Security/Privacy Claims Traceability

Interni dokument. Ne objavljivati javno (ne servirati preko FastAPI rute).

Svrha: svaka tvrdnja u javnoj pravnoj/security dokumentaciji (`privacy.html`,
`static/security.html`, `static/dpa.html`, `static/ai-disclosure.html`,
`static/bezbednosni-list.html`) mora imati referencu na kod koji je izvršava.
Kad se referencirani kod promeni ili obriše, ovaj dokument treba pregledati i
javne tvrdnje ažurirati u istom PR-u — ne posle.

**Pravilo (od 2026-07-21): No public security claim without executable
evidence.** Nova tvrdnja sme ući u website/DPA/Security Whitepaper/one-pager
tek kada postoji barem jedno od: automatski test, lako proverljiv kod,
infrastruktura pod verzionom kontrolom, ili auditabilna konfiguracija.
Kolona **Test** = "—" znači da ovo pravilo još nije ispunjeno za taj red —
tretiraj kao otvoren dug, ne kao prihvatljivo trajno stanje.

Poslednja puna verifikacija: 2026-07-21 (direktnim čitanjem izvornog koda).

| Tvrdnja | Gde se pojavljuje | Evidence (kod / infra) | Test | Owner | Risk if broken | Status |
|---|---|---|---|---|---|---|
| Podaci se ne koriste za treniranje AI modela | ai-disclosure.html, bezbednosni-list.html §1, security.html §5.2 | `api.py` — OpenAI klijent instanciran sa `OPENAI_API_KEY` (platform API, ne ChatGPT) | — (eksterna OpenAI politika, nije testabilno u našem kodu) | Platform | MEDIUM | ✓ Verifikovano |
| Dokumenti klijenata enkriptovani AES-256-GCM pre upload-a | bezbednosni-list.html §2, dpa.html, privacy.html | `klijenti/router.py:715-727` (enkripcija pre `bucket.upload`); `security/crypto.py` (`encrypt_field`, `_get_field_key`, `AESGCM`) | `scripts/test_crypto_roundtrip.py` | Security | HIGH | ✓ Verifikovano |
| JMBG/pasoš/PIB enkriptovani AES-256-GCM na nivou baze | bezbednosni-list.html §2, security.html §3 | `security/crypto.py: encrypt_field/decrypt_field`; `scripts/migrate_jmbg_encrypt.py` | `scripts/test_crypto_roundtrip.py` | Security | HIGH | ✓ Verifikovano |
| Lozinke — Argon2id, nikad plaintext/bcrypt/sha | bezbednosni-list.html §2, security.html §2.1 | `security/crypto.py: hash_password/verify_password` (OWASP parametri: time_cost=2, memory_cost=65536, parallelism=2) | — | Security | HIGH | ✓ Verifikovano; **preporuka:** test da needs_rehash/verify rade sa trenutnim parametrima |
| TLS 1.2/1.3 + HSTS | bezbednosni-list.html §2, security.html §3 | `api.py:976` — `Strict-Transport-Security: max-age=31536000; includeSubDomains` | — (TLS termination na Render infrastrukturi, van našeg koda) | Infra | MEDIUM | ✓ Verifikovano (HSTS header); TLS verzija je infrastrukturna (Render), ne app-level |
| Row Level Security (RLS) izoluje podatke po korisniku | bezbednosni-list.html §2, security.html §4, privacy.html | Supabase Postgres RLS politike — sada exportabilne skriptom `scripts/export_rls_policies.py` → `migrations/rls_current_snapshot.sql` | `tests/test_rbac_smoke.py` (aplikacioni nivo, ne DB nivo) | Security | **HIGH** | ⚠ Delimično — skript za export napisan 2026-07-21, ali **još nije pokrenut protiv produkcije** (treba `SUPABASE_DB_URL` + `pip install psycopg2-binary`). Dok prvi snapshot ne uđe u repo, RLS ostaje neverzionisan i neproverljiv van same Supabase konzole. **Akcija na founder-u.** |
| Brisanje naloga → anonimizacija identifikacionih podataka (email, ime), odmah | bezbednosni-list.html §3, security.html §14.1/14.3, privacy.html, dpa.html | `routers/gdpr.py: gdpr_delete_account()` — update na `profiles` (email→`deleted_xxx@deleted.vindex.rs`, full_name→"Obrisani korisnik") + `korisnik_email_notif` deaktivacija + immutable audit log | `tests/test_gdpr_delete.py::test_profile_is_anonymized_not_deleted` | Platform | HIGH | ✓ Verifikovano + regresiono testirano (2026-07-21) |
| Brisanje naloga NE briše predmete/klijente/dokumente/Pinecone | bezbednosni-list.html §3, security.html §14.3, privacy.html, dpa.html | `routers/gdpr.py: gdpr_delete_account()` — `_delete()` dodiruje isključivo `profiles` i `korisnik_email_notif` | `tests/test_gdpr_delete.py::test_only_touches_profile_and_email_notif_tables` + `::test_never_touches_case_client_or_document_tables` — namerno pokvaren i potvrđeno da test PADA (dodat `predmeti.delete()`, oba testa crvena, zatim revert) | Platform | **HIGH** — pravni model, ne samo pokrivenost | ✓ Verifikovano + regresiono testirano (2026-07-21) |
| Founder nalog se ne može obrisati preko API-ja | security.html §14.1 (implicitno) | `routers/gdpr.py: gdpr_delete_account()` — `if email.lower() in FOUNDER_EMAILS: raise 403` PRE bilo kakvog upisa | `tests/test_gdpr_delete.py::test_founder_account_cannot_be_deleted_via_api` | Platform | MEDIUM | ✓ Verifikovano + regresiono testirano (2026-07-21) |
| Nema samouslužnog "Izbriši nalog" dugmeta u UI — samo email zahtev ili direktan API poziv | security.html §14.1, bezbednosni-list.html §3 | `grep "gdpr\|Izbriši nalog\|deleteAccount"` u `static/vindex.js` i `index.html` → 0 pogodaka (samo export dugme na `index.html:3352`) | — | Platform | LOW | ✓ Verifikovano (odsustvo UI koda); re-proveriti ako se doda self-service dugme |
| Export podataka — ZIP sa predmetima/klijentima/billing/metapodacima dokumenata (JSON), BEZ originalnih fajlova | security.html §14.2, privacy.html, bezbednosni-list.html §3 | `routers/data_export.py: export_complete()` — `tables` lista; README u ZIP-u eksplicitno kaže "Fajlovi dokumenata... nisu uključeni" | — | Platform | MEDIUM | ✓ Verifikovano |
| Export dugme u UI zove `/api/export/complete` direktno (bez signed URL/24h linka) | security.html §14.2 | `static/vindex.js:731-749: exportSviPodaci()` — direktan `fetch` + `blob()` download | — | Platform | LOW | ✓ Verifikovano |
| Svaki kompletan export upisuje se u nepromenjivi audit log | security.html §14.2 | `routers/data_export.py:64-69` — `_imm_log("data_export", ...)` | `scripts/test_audit_integrity.py` | Security | MEDIUM | ✓ Verifikovano |
| Predmeti/klijenti/dokumenti se zadržavaju zbog zakonske obaveze čuvanja (Zakon o advokaturi) | privacy.html, security.html §11/§14, dpa.html, bezbednosni-list.html §3 | Pravni osnov, ne kod — potvrđeno `routers/gdpr.py` komentarom i ponašanjem (vidi red iznad) | `tests/test_gdpr_delete.py` (posredno — dokazuje da se zadržavanje stvarno dešava) | Legal | HIGH | ✓ Konzistentno kroz sva 4 dokumenta |
| Privremeni AI upload namespace-i (tmp_*) automatski se brišu | security.html §14.3 | `uploaded_doc/cleanup.py: cleanup_expired()` — `index.delete(delete_all=True, namespace=ns)` za istekle `tmp_*` | `tests/test_uploaded_doc_cleanup.py` | Platform | LOW | ✓ Verifikovano |

## Otvoreni dugovi (prioritet)

1. **RLS snapshot još nije pokrenut protiv produkcije** (HIGH). `scripts/export_rls_policies.py` postoji i čeka `SUPABASE_DB_URL` (Supabase Dashboard → Project Settings → Database → Connection string). Dok se ne pokrene bar jednom i commit-uje `migrations/rls_current_snapshot.sql`, RLS tvrdnja u security.html §4 i privacy.html je verifikovana samo ručnim uvidom u Supabase konzolu, ne kroz repo. Ovo mora uraditi neko sa DB kredencijalima (founder) — ja nemam pristup connection string-u.
2. RLS politike se ne verifikuju automatski posle snapshot-a (nema testa koji upoređuje `rls_current_snapshot.sql` sa stvarnim stanjem u CI-ju). Sledeći korak posle #1.
3. Argon2id parametri (`hash_password`) nemaju direktan test da OWASP parametri nisu tiho promenjeni.

## Terminologija — jedinstveni rečnik (obavezno koristiti dosledno)

- **anonimizacija** — zamena identifikacionih podataka naloga (email, ime) nepovratnim placeholder vrednostima. Odnosi se ISKLJUČIVO na `profiles` tabelu.
- **zadržavanje / retention** — podaci ostaju nepromenjeni u sistemu (predmeti, klijenti, dokumenti) zbog zakonske obaveze.
- **brisanje** — koristi se samo tamo gde se podaci stvarno i trajno uklanjaju (app logovi, tmp Pinecone namespace-i, backup rotacija, export arhiva/link posle preuzimanja). Nikad za ono što se u stvarnosti samo anonimizuje ili zadržava.
- Naslov zakonskog prava ("Pravo na brisanje", čl. 17 GDPR / čl. 30 ZZPL) sme zadržati zakonski naziv prava — ali operativni opis ispod naslova mora tačno reći anonimizacija/zadržavanje, ne "briše se".

## Kako održavati ovaj dokument

1. Svaka nova javna bezbednosna/privacy tvrdnja mora imati red u tabeli iznad PRE objavljivanja — ne posle ("No public security claim without executable evidence").
2. Kad se menja kod naveden u koloni "Evidence", pretraži ovaj fajl za taj file/funkciju i proveri da li se tvrdnja i dalje drži.
3. Kolona "Test" prazna + Risk HIGH/MEDIUM = prioritet za dodavanje testa. Kolona "Test" prazna + Risk LOW = prihvatljivo za sada.
4. `tests/test_gdpr_delete.py` je primer obrasca: test ne samo da prolazi na trenutnom kodu, nego je namerno pokvaren jednom (dodat cascade delete) da se potvrdi da STVARNO hvata regresiju, pa vraćen. Isti obrazac koristiti za buduće testove ove vrste.
