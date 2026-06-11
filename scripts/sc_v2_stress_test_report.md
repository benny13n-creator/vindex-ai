# Smart Contract Analyzer — V2 Schema Stress Test Report

**Datum**: 2026-06-11 20:47  
**Ugovori**: 3 (simple_staking, simple_token, pause_token)  
**Runs/ugovor**: 3  |  **Ukupno poziva**: 9  
**Model**: gpt-4o, temperature=0.2  

---

## ⚡ Post-processing garantovana polja (REGRESIJA ako nije ispunjeno)

> **Ključna distinkcija**: `broj_pravnih_rizika >= min` je kod-garantovano i MORA biti stabilno.
> Varijabilnost UKUPNOG broja (npr. 3/2/3) je GPT šum — nije regresija dok su svi >= min.

| Ugovor | Min garantovanih rizika | Br. rizika R1/R2/R3 | >= min? (KRITIČNO) | Identičan br.? | Offchain OK? | AML napomena? |
|--------|------------------------|---------------------|---------------------|----------------|--------------|---------------|
| simple_staking | 1 (lock-without-exit) | 3 / 2 / 3 | ✅ DA | ⚠️ NE (GPT šum) | ✅ | ✅ |
| simple_token | 1 (unrestricted-mint) | 1 / 1 / 1 | ✅ DA | ✅ DA | ✅ | ✅ |
| pause_token | 1 (unrestricted-mint) | 2 / 2 / 2 | ✅ DA | ✅ DA | ✅ | ✅ |

**✅ NEMA REGRESIJE — svi post-processing garantovani minimumi ispunjeni 9/9 poziva.**

---

## 📊 GPT-generisana polja po ugovoru

### simple_staking

Heuristike: `lock=True` | `mint=False`  
Post-processing garantuje: lock-without-exit risk uvek prisutan.

| Polje | Run 1 | Run 2 | Run 3 | Stabilno? |
|-------|-------|-------|-------|-----------|
| confidence_tier | HIGH | HIGH | HIGH | ✅ DA |
| centralizacija.nivo | VISOKA | VISOKA | VISOKA | ✅ DA |
| adm_ovl.nivo | VISOKA | VISOKA | VISOKA | ✅ DA |
| adm_ovl.br_funkcija | 3 | 3 | 3 | ✅ DA |
| adm_ovl.br_uloga | 1 | 1 | 1 | ✅ DA |
| aml_kyc.nivo_rizika | VISOK | VISOK | VISOK | ✅ DA |
| klasif_tokena.kategorija | — | — | — | ✅ DA (prazno) |
| reg.nivo_relevantnosti | VISOK | VISOK | VISOK | ✅ DA |
| reg.broj_clanova | 1 | 1 | 1 | ✅ DA |
| br_pravni_sazetak_stavki | 5 | 5 | 5 | ✅ DA |

**Stabilnih GPT polja: 10/10**

**Run 1 rizici (3):**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim...
- Vlasnik može promeniti ključne ekonomske parametre bez saglasnosti...
- Vlasnik može povući sva sredstva iz ugovora.

**Run 2 rizici (2):**
- Centralizovana kontrola nad ključnim ekonomskim parametrima i sre...
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim...

**Run 3 rizici (3):**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim...
- Vlasnik može promeniti ključne ekonomske parametre bez saglasnosti...
- Vlasnik može povući sva sredstva iz ugovora.

> GPT šum u agregaciji: Run 2 je grupisao rizike od izmene parametara i povlačenja sredstava u jedan "centralizovana kontrola" rizik. Post-processing lock-without-exit minimum je ipak ispunjen.

---

### simple_token

Heuristike: `lock=False` | `mint=True`  
Post-processing garantuje: unrestricted-mint risk uvek prisutan.

| Polje | Run 1 | Run 2 | Run 3 | Stabilno? |
|-------|-------|-------|-------|-----------|
| confidence_tier | HIGH | HIGH | HIGH | ✅ DA |
| centralizacija.nivo | VISOKA | VISOKA | VISOKA | ✅ DA |
| adm_ovl.nivo | VISOKA | VISOKA | VISOKA | ✅ DA |
| adm_ovl.br_funkcija | 1 | 1 | 1 | ✅ DA |
| adm_ovl.br_uloga | 1 | 1 | 1 | ✅ DA |
| aml_kyc.nivo_rizika | VISOK | VISOK | VISOK | ✅ DA |
| klasif_tokena.kategorija | Utility token | Utility token, Payment token | Utility token | ❌ NE |
| klasif_tokena.status (sve) | MOGUĆE | MOGUĆE, MOGUĆE | MOGUĆE | ❌ NE (br. kategorija varira) |
| reg.nivo_relevantnosti | VISOK | VISOK | VISOK | ✅ DA |
| reg.broj_clanova | 1 | 1 | 1 | ✅ DA |
| br_pravni_sazetak_stavki | 5 | 5 | 5 | ✅ DA |

**Stabilnih GPT polja: 9/11** — nestabilno: `klasif_tokena` Run 2 dodaje "Payment token"

**Rizici (1/1/1 — identični):**
- Vlasnik ima diskreciono pravo neograničenog povećanja ponude toke... (garantovano post-processing-om)

---

### pause_token

Heuristike: `lock=False` | `mint=True`  
Post-processing garantuje: unrestricted-mint risk uvek prisutan.

| Polje | Run 1 | Run 2 | Run 3 | Stabilno? |
|-------|-------|-------|-------|-----------|
| confidence_tier | HIGH | HIGH | HIGH | ✅ DA |
| centralizacija.nivo | VISOKA | VISOKA | VISOKA | ✅ DA |
| adm_ovl.nivo | VISOKA | VISOKA | VISOKA | ✅ DA |
| adm_ovl.br_funkcija | 4 | 4 | 4 | ✅ DA |
| adm_ovl.br_uloga | 1 | 1 | 1 | ✅ DA |
| aml_kyc.nivo_rizika | VISOK | VISOK | VISOK | ✅ DA |
| klasif_tokena.kategorija | Utility token | Utility token | Utility token, Payment token | ❌ NE |
| reg.nivo_relevantnosti | VISOK | VISOK | VISOK | ✅ DA |
| reg.broj_clanova | 1 | 1 | 2 | ❌ NE |
| br_pravni_sazetak_stavki | 5 | 5 | 5 | ✅ DA |

**Stabilnih GPT polja: 8/10** — nestabilno: `klasif_tokena` Run 3 dodaje "Payment token"; `reg.broj_clanova` Run 3 = 2 umesto 1

**Rizici (2/2/2 — identičan broj):**
- Vlasnik ima diskreciono pravo neograničenog povećanja ponude toke... (garantovano)
- Vlasnik može pauzirati sve transakcije / transfer aktivnosti... (GPT-generisan, identičan 3/3)

---

## Ukupni sažetak

### Post-processing integritet — 100% ČISTO

| Provera | Rezultat |
|---------|----------|
| `broj_rizika >= min` (9/9 poziva) | ✅ 100% — NEMA REGRESIJE |
| `offchain_ima_placeholder` (9/9) | ✅ 100% |
| `anon_ima_aml_napomenu` (9/9) | ✅ 100% |

### GPT polja — stabilnost 3/3 runs

| Polje | Staking | Token | Pause | Ukupno |
|-------|---------|-------|-------|--------|
| confidence_tier | ✅ | ✅ | ✅ | **3/3** |
| centralizacija.nivo | ✅ | ✅ | ✅ | **3/3** |
| adm_ovl.nivo | ✅ | ✅ | ✅ | **3/3** |
| adm_ovl.br_funkcija | ✅ | ✅ | ✅ | **3/3** |
| aml_kyc.nivo_rizika | ✅ | ✅ | ✅ | **3/3** |
| reg.nivo_relevantnosti (ZDI) | ✅ | ✅ | ✅ | **3/3** |
| reg.broj_clanova (ZDI) | ✅ | ✅ | ❌ | 2/3 |
| klasif_tokena.kategorija | ✅ (N/A) | ❌ | ❌ | 1/3 |

**GPT polja stabilna 3/3: ~81%** (nestabilnost u 2 polja)

### Ključne opservacije

1. **Novi v2 "nivo" polja su praktično deterministična** pri temperature=0.2 — `confidence_tier`, `centralizacija.nivo`, `adm_ovl.nivo`, `aml_kyc.nivo_rizika` su 100% identični kroz sva 9 poziva. Ovo je bolji rezultat nego što se očekivao.

2. **`klasifikacija_tokena`** — nestabilna. GPT povremeno dodaje "Payment token" kao drugu kategoriju pored "Utility token" (1/3 run-ova za oba token ugovora). Isti ugovor, isti kod, različit zaključak. Ovo je inherentna GPT varijabilnost u graničnim slučajevima token klasifikacije — nije pogrešan odgovor, ali nije deterministički.

3. **`reg.broj_clanova` (ZDI)** — nestabilno za pause_token: Run 3 vratio 2 člana umesto 1. Identičan pattern kao pre redesigna — ZDI granularnost citiranja varira.

4. **`broj_pravnih_rizika` (GPT šum u simple_staking)** — 3/2/3 je GPT agregacija, ne regresija. Post-processing minimum (1) uvek ispunjen. `simple_token` i `pause_token` imaju identičan broj sva 3 puta.

### Zaključak

✅ **Post-processing garantovana polja: 100% stabilna — nema regresije.**  
✅ **Novi v2 "nivo" tipovi polja: praktično deterministični (3/3 sva 3 ugovora).**  
⚠️ **Dve nestabilnosti nasleđene od pre redesigna:** `klasif_tokena` kategorije i `reg.broj_clanova` (ZDI granularnost). Nisu regresija — isti pattern je bio prisutan i ranije.
