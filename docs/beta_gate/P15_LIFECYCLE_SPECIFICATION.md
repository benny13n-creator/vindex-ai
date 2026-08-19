# P1-5 — LIFECYCLE SPECIFIKACIJA (brisanje predmeta i naloga)

**Baseline:** `1d0a4181` · **Režim:** READ-ONLY forenzika, nula izmena produkcije.
**Metod:** merenje nad DDL-om (`supabase_setup.sql` + 104 migracije) i nad produkcionim
kodom (AST + regex), ne nad ranijim izveštajima.

---

## 0. Ispravka zatečenog nalaza

Prethodni sprint je tvrdio: *„FK ka `predmeti` deklarisan u samo 3 migracije"* i
*„najmanje 12 predmet-tabela nema FK"*.

**Izmereno — obe brojke su netačne:**

| Mera | Prethodna tvrdnja | Izmereno |
|---|---|---|
| Tabela vezanih za predmet (DDL ∪ kod) | — | **61** |
| Sa deklarisanim FK ka `predmeti` | 3 migracije | **21 tabela** |
| Bez FK (orphan rizik) | „najmanje 12" | **40** |

Uzrok ranije greške: grep je hvatao samo jednoredni `REFERENCES predmeti(id)` obrazac
i promašio `ALTER TABLE ... ADD CONSTRAINT` i višeredne `CREATE TABLE` deklaracije.

Druga ispravka: prethodni sprint je zaključio da *„brisanje vektora po predmetu ne
postoji"*. Funkcija zaista ne postoji — **ali primitive i model identiteta postoje**
(v. §4), pa je izvodljiva bez nove arhitekture.

---

## 1. FK semantika — izmereno (21 tabela)

| Semantika | Broj | Tabele |
|---|---|---|
| `ON DELETE CASCADE` | 16 | `predmet_beleske`, `predmet_dokumenti`, `predmet_dokazi`, `predmet_hronologija`, `predmet_istorija`, `predmet_klijenti`, `predmet_komentari`, `predmet_health_log`, `predmet_delegiranja`, `rocista`, `timer_sessions`, `notifications`, `agent_recommendations`, `simulator_partije`, `twin_simulacije`, `user_knowledge` |
| `ON DELETE SET NULL` | 4 | `fakture`, `klijent_dokumenti`, `recurring_templates`, `usage_events` |
| **`ON DELETE RESTRICT`** | **1** | **`billing_entries`** |

**`billing_entries` je jedina tvrda blokada:** dok postoji ijedan red naplate vezan za
predmet, `DELETE FROM predmeti` biva **odbijen od baze**. To nije bug — to je postojeća
odluka da se finansijski trag ne gubi.

---

## 2. Klasifikacija entiteta — svih 61

| Politika | Broj | Značenje |
|---|---|---|
| `PURGE` | 50 | fizički se briše zajedno sa predmetom |
| `PURGE+VECTORS` | 2 | red **i** vektori (`predmet_dokumenti`, `user_knowledge`) |
| `RETAIN/ANONYMIZE` | 5 | finansijski trag ostaje, veza se prekida (`billing_entries`, `fakture`, `timer_sessions`, `recurring_templates`, `usage_events`, `case_profitability`) |
| `RETAIN` | 3 | audit (`audit_immutable`, `audit_log`, `saradnja_audit`, …) |
| `BLOCK→RESOLVE` | 1 | `billing_entries` — blokira dok se ne razreši |

Puna tabela po entitetu (FK, PII, pravni sadržaj, vektori, audit, orphan rizik)
generisana je merenjem; skripta je u sprint scratchpad-u.

---

## 3. Šta danas STVARNO briše — izmereno

| Ruta | Briše red | Briše vektore |
|---|---|---|
| `DELETE /api/predmeti/{id}/dokumenti/{dok_id}` (`api.py:6053`) | DA | **DA** (`obrisi_vektore_dokumenta`) |
| `DELETE /api/knowledge/{entry_id}` (`knowledge_base.py:376`) | DA | **DA** + filter u pretrazi |
| `DELETE /api/predmeti/{id}/beleske/{beleska_id}` (`api.py:4419`) | DA | n/a (beleške se ne vektorizuju) |
| `DELETE /klijenti/{klijent_id}` | DA | NE |
| **`DELETE /api/gdpr/account`** | **NE** — anonimizuje `profiles` + `korisnik_email_notif` | **NE** |
| **`DELETE /api/predmeti/{id}`** | **NE POSTOJI** | — |

`gdpr_delete_account` je pošteno imenovan u UI-ju („Email i ime biće trajno
anonimizovani"), pa **lažnog obećanja nema**. Ali predmeti, dokumenti i svi vektori
ostaju posle „brisanja naloga".

---

## 4. Vektori — model identiteta postoji

`shared/vector_identity.py`:

```
vector_id = {scope}__{version}__k{chunk_schema}_c{chunk_index}
scope = predmet_id            (za dokumente predmeta)
```

`shared/vector_deletion.py` već ima: `_izlistaj_po_prefiksu(index, namespace, prefiks)`,
`_cekaj_da_nestanu(...)`, `obrisi_vektore_dokumenta(...)`, `_sme_predmet(...)`.
Namespace: `shared/kancelarija_utils.py::rag_owner_namespace(user_id, kancelarija_id)`.

**Zaključak:** brisanje vektora po predmetu je `prefiks = f"{predmet_id}__"` u vlasničkom
namespace-u. Nema potrebe za novom arhitekturom — nedostaje samo funkcija koja to sprovodi
i čeka potvrdu.

---

## 5. Kanonska mašina stanja

```
ACTIVE
  └─ DELETE REQUESTED
       ├─ BLOCKED            (billing_entries postoji → 409, ne briše se ništa)
       └─ PURGING
            ├─ vektori       (prefiks {predmet_id}__, potvrda brisanja)
            ├─ redovi        (CASCADE + eksplicitno za 40 tabela bez FK)
            ├─ RETAIN        (audit netaknut; DB trigger to i iznuđuje)
            └─ ANONYMIZE     (finansijski trag: veza se prekida, iznos ostaje)
       └─ PURGED | INCOMPLETE
```

`INCOMPLETE` je ravnopravan ishod. **Delimično brisanje se NIKAD ne sme prijaviti kao
`obrisano`.**

---

## 6. Invarijante koje implementacija mora očuvati

1. `DELETE` prijavljuje uspeh **samo** ako je svaki `PURGE`/`PURGE+VECTORS` entitet
   dokazano uklonjen. Inače `INCOMPLETE` + spisak neuspelih komponenti.
2. Vektori se brišu **pre** ili **atomično sa** redovima; zaostao vektor uz obrisan red
   je curenje sadržaja (`PINE-01` klasa).
3. `audit_immutable` se ne dira. DB trigger (mig. 043) to iznuđuje — implementacija ne
   sme pokušati ni da ga zaobiđe.
4. `billing_entries` (RESTRICT) → `409 Conflict` sa objašnjenjem, **nikad tiho preskakanje**.
5. Tenant izolacija: brisanje sme dodirnuti isključivo redove `user_id`/`kancelarija_id`
   vlasnika; `_sme_predmet` je već kanonska provera.
6. Ponovljeni `DELETE` nad već obrisanim predmetom = `404`, ne `200`.
7. 40 tabela bez FK mora se brisati **eksplicitno** — oslanjanje na kaskadu bi ostavilo
   orphan redove.
8. Nijedna migracija koja tiho gubi podatke; ako se dodaje FK, mora biti dokazano da
   nema postojećih orphan redova.

---

## 7. Šta ostaje UNKNOWN (ne izmišlja se)

- **Zakonski rok čuvanja** advokatske dokumentacije u Srbiji — repo ga nigde ne dokazuje.
  Označeno `UNKNOWN`; `RETAIN` politika za audit i finansije izvedena je iz **postojećih
  tehničkih odluka** (DB trigger, FK RESTRICT), ne iz pretpostavljenog zakona.
- Da li „brisanje naloga" po ugovoru sa kancelarijom mora obuhvatiti i predmete — poslovna
  odluka, nije tehnička.

Ove dve stavke **ne blokiraju** implementaciju brisanja **predmeta**, jer su politike za
predmet izvedene iz merenih ograničenja šeme.
