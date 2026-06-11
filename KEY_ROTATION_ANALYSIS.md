# KEY_ROTATION_ANALYSIS.md
## Vindex AI — Analiza rotacije FIELD_ENCRYPTION_KEY

**Dokument:** Tehnicka analiza (NIJE implementacija)  
**Datum:** 2026-06-11  
**Autor:** CRM Hardening Phase  
**Status:** Analiza — ne implementovati bez zasebnog planiranja

---

## 1. Trenutno stanje

### Arhitektura enkripcije
- **Algoritam:** AES-256-GCM  
- **Format:** `enc_v1:<base64url(nonce[12B] || ciphertext+tag)>`  
- **Prefiks:** `enc_v1:` — verzija hardkodovana u prefiksu  
- **Ključ:** Jedan statički ključ iz `FIELD_ENCRYPTION_KEY` env var  
- **Polja:** `jmbg_encrypted`, `broj_pasosa_encrypted`, `pib_encrypted` u tabeli `klijenti`

### Kritičan problem: Nema KEY_VERSION tracking-a
Svaki enkriptovani zapis trenutno ima oblik `enc_v1:...` gde `v1` označava **format enkripcije** (AES-256-GCM), **ne verziju ključa**. Ako se ključ rotira:

1. Svi stari zapisi su enkriptovani starim ključem
2. Novi zapisi se enkriptuju novim ključem
3. Nema načina da se razlikuju — oba imaju isti prefiks `enc_v1:`
4. **Posledica:** Aplikacija ne zna koji ključ da koristi za dekripciju

---

## 2. Rizici bez rotacione podrške

| Rizik | Verovatnoća | Uticaj | Opis |
|-------|-------------|--------|------|
| Kompromitovan ključ | Niska | KRITIČAN | Svi klijenti izloženi odjednom. Bez rotacije, jedina opcija je emergency re-enkripcija celog skupa podataka. |
| Insider threat | Niska | VISOK | Bivši zaposlenik sa ključem može dešifrovati istorijske podatke. |
| Env var leak | Srednja | KRITIČAN | Ključ u .env fajlu, CI/CD logovima, itd. |
| Regulatorna obaveza | Visoka | SREDNJI | GDPR/Zakon o zaštiti podataka može zahtevati periodičnu rotaciju ključeva. |
| Quantum computing | Dugoročna | VISOK | AES-256 otporan za sada, ali rotacija na post-quantum šifre zahteva verzioniranje. |

---

## 3. Plan implementacije KEY_VERSION

### 3a. Novi format enkriptovanih vrednosti

```
# Trenutni format (v1):
enc_v1:<base64url(nonce+ciphertext+tag)>

# Novi format sa KEY_VERSION:
enc_v1:k2:<base64url(nonce+ciphertext+tag)>
#          ^^ KEY_ID — Integer koji identifikuje koji ključ je korišten
```

### 3b. Env var šema

```bash
# Aktivan ključ (za šifrovanje novih podataka):
FIELD_ENCRYPTION_KEY_ID=2
FIELD_ENCRYPTION_KEY_2=<base64url(32B)>

# Stari ključevi (samo za dekripciju, ne za enkripciju novih):
FIELD_ENCRYPTION_KEY_1=<base64url(32B)>   # prethodni ključ

# NIKAD brisati stare ključeve dok postoje zapisi koji ih koriste!
```

### 3c. Izmene u `security/crypto.py`

```python
def _get_all_keys() -> dict[int, bytes]:
    """Vraća sve ključeve: {key_id: key_bytes}. Čita KEY_1, KEY_2, ..."""
    keys = {}
    for i in range(1, 10):  # do 9 generacija ključeva
        raw = os.environ.get(f"FIELD_ENCRYPTION_KEY_{i}", "").strip()
        if raw:
            keys[i] = base64.urlsafe_b64decode(raw + "==")[:32]
    return keys

def _get_active_key() -> tuple[int, bytes]:
    """Vraća (key_id, key_bytes) aktivnog ključa za šifrovanje."""
    kid = int(os.environ.get("FIELD_ENCRYPTION_KEY_ID", "1"))
    keys = _get_all_keys()
    if kid not in keys:
        raise RuntimeError(f"Aktivan ključ KEY_{kid} nije postavljen")
    return kid, keys[kid]

def encrypt_field(plaintext: str) -> str:
    if not plaintext:
        return ""
    kid, key = _get_active_key()
    # ... AES-GCM enkripcija ...
    return f"enc_v1:k{kid}:{encoded}"

def decrypt_field(ciphertext: str) -> str:
    if not ciphertext.startswith("enc_v1:"):
        return ciphertext
    # Parsing: enc_v1:k{id}:{data} ili enc_v1:{data} (legacy bez KEY_ID)
    parts = ciphertext[len("enc_v1:"):].split(":", 1)
    if parts[0].startswith("k") and parts[0][1:].isdigit():
        kid = int(parts[0][1:])
        data = parts[1]
    else:
        kid = 1  # Legacy zapisi pre KEY_VERSION — pretpostavi KEY_1
        data = parts[0]
    keys = _get_all_keys()
    if kid not in keys:
        logger.error("Ključ k%d nije dostupan za dekripciju", kid)
        return "[GREŠKA DEKRIPTOVANJA]"
    # ... AES-GCM dekripcija sa keys[kid] ...
```

---

## 4. Migracija pri rotaciji ključa

### Koraci za bezbedan Key Rotation

```bash
# KORAK 1: Generisi novi ključ (NE brisati stari)
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
# Dodaj u Render: FIELD_ENCRYPTION_KEY_2=<novi_kljuc>

# KORAK 2: Postavi novi aktivan key ID (aplikacija počinje enkriptovati novi sadržaj sa k2)
# Render: FIELD_ENCRYPTION_KEY_ID=2
# Stari zapisi (k1) se i dalje dekriptuju jer KEY_1 ostaje!

# KORAK 3: Pokreni re-enkripciju postojećih zapisa (background job)
python scripts/migrate_key_rotation.py --from-key-id=1 --to-key-id=2 --dry-run
# Pregled → potvrda → pokretanje
python scripts/migrate_key_rotation.py --from-key-id=1 --to-key-id=2 --run

# KORAK 4: Verifikacija da nema više k1 zapisa
python scripts/migrate_key_rotation.py --verify-all-key-id=2

# KORAK 5: Brisanje starog ključa iz env vars (TEK POSLE verifikacije!)
# Render: Obrišite FIELD_ENCRYPTION_KEY_1

# KORAK 6: Audit log — zabilježi rotaciju
INSERT INTO klijenti_audit (..., akcija='KEY_ROTATION', detalji={from:1, to:2})
```

### Skript `scripts/migrate_key_rotation.py` — pseudokod

```python
def re_encrypt_row(row, from_kid, to_kid, keys):
    for field in ['jmbg_encrypted', 'broj_pasosa_encrypted', 'pib_encrypted']:
        val = row.get(field) or ""
        if not val or not val.startswith(f"enc_v1:k{from_kid}:"):
            continue  # Nije ova generacija ključa, preskoči
        plaintext = decrypt_field_with_key(val, keys[from_kid])
        row[field] = encrypt_field_with_key(plaintext, to_kid, keys[to_kid])
    return row
```

---

## 5. Rollback plan

Ako nova verzija ključa ne radi:

1. **Vrati `FIELD_ENCRYPTION_KEY_ID` na stari key_id** — aplikacija odmah počinje koristiti stari ključ za nove zapise
2. **Ne brišite nikad ključeve dok postoje zapisi koji ih koriste** — dekripcija starih zapisa i dalje radi
3. Rollback je bez downtime-a ako su oba ključa dostupna

---

## 6. Kompleksnost i prioritizacija

| Komponenta | Procena | Napomena |
|-----------|---------|---------|
| Izmena `crypto.py` | 4h | Novi format + parsing legacy |
| Migracija skript | 4h | Re-enkripcija sa batch insert |
| Test suite | 4h | Testovi za multi-key scenario |
| Render env var setup | 1h | Dokumentacija i procedure |
| **Ukupno** | **~13h** | |

**Preporuka prioritizacije:**
- **Faza 1 (odmah):** Implementovati novi format `enc_v1:k1:...` za sve **nove** zapise — backwards compatible, legacy bez `k{id}` se tretira kao k1.
- **Faza 2 (pre 1000+ klijenata):** Migracija skript + Render env var šema.
- **Faza 3 (na zahtev):** Pokrenuti stvarnu rotaciju samo ako dođe do kompromitacije ili regulatorne obaveze.

---

## 7. Što NE raditi

- **NE brisati stare ključeve** dok postoje zapisi enkriptovani njima
- **NE koristiti isti KEY_ID za različite ključeve** — jednom postavljen id ostaje zauvek vezan za taj ključ
- **NE rotirati ključ bez re-enkripcije** — to nije rotacija, to je zaključavanje podataka
- **NE čuvati ključeve u kodu ili git istoriji** — samo env vars

---

## 8. Veza sa trenutnom implementacijom

Trenutni `enc_v1:` prefiks je kompatibilan sa planom iznad:
- Novi format `enc_v1:k1:...` — aplikacija može parsovati oba oblika
- Legacy zapisi ostaju `enc_v1:...` — tretiraju se kao k1 (prvi ključ)
- Nema potrebe za hitnom migracijom existujućih podataka

**Jedina hitna akcija koja se preporučuje:** Promeniti `encrypt_field()` da generiše `enc_v1:k1:...` format od sada, tako da buduće rotacije budu moguće bez dodatnog kompleksiteta.

---

*Dokument je samo analiza — implementacija zahteva zasebni task/PR.*
