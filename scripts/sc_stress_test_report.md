# Smart Contract Analyzer — Stress Test Report (Faza 0)

**Datum**: 2026-06-11 16:15  
**Ugovori**: 8  |  **Runs/ugovor**: 3  |  **Ukupno poziva**: 24  
**Model**: gpt-4o, temperature=0.2  
**Post-processing**: offchain placeholder, AML napomena, lock-without-exit fallback

---

## Sazet pregled stabilnosti

| Ugovor | Rizici identican br. (3/3)? | ZDI identicni (3/3)? | Offchain OK (3/3)? | AML OK (3/3)? |
|--------|------------------------------|----------------------|--------------------|--------------|
| dao_voting | DA | DA | DA | DA |
| escrow | DA | NE (variira) | DA | DA |
| multisig_wallet | DA | NE (variira) | DA | DA |
| nft_mint | DA | NE (variira) | DA | DA |
| simple_erc20 | DA | NE (variira) | DA | DA |
| simple_proxy | DA | DA | DA | DA |
| simple_staking | DA | NE (variira) | DA | DA |
| vesting | DA | NE (variira) | DA | DA |

**Stabilnost broja rizika**: 8/8 ugovora (100%)  
**Stabilnost ZDI clanova**: 2/8 ugovora (25%)  
**Determinizam offchain** (post-processing): 24/24 poziva (100%)  
**Determinizam AML napomena** (post-processing): 24/24 poziva (100%)  

---

## Detalji po ugovoru

### dao_voting

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3 | - | 9.2s |
| 2 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3 | - | 9.3s |
| 3 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3 | - | 10.9s |

### escrow

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 5 | - | 13.4s |
| 2 | 1 | DA | DA | DA | HIGH | NE | - | - | 11.2s |
| 3 | 1 | DA | DA | DA | HIGH | NE | - | - | 12.7s |

**Run 1 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

**Run 2 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

**Run 3 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

### multisig_wallet

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 0 | DA | DA | DA | HIGH | NE | - | - | 13.2s |
| 2 | 0 | DA | DA | DA | HIGH | NE | - | - | 7.7s |
| 3 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 10.8s |

### nft_mint

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 12.5s |
| 2 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 9.6s |
| 3 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 2 | - | 11.4s |

### simple_erc20

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 11.7s |
| 2 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 | - | 12.1s |
| 3 | 0 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 12.2s |

### simple_proxy

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 1 | DA | DA | DA | MEDIUM | DA | čl. 3 st. 1 tač. 3 | - | 10.4s |
| 2 | 1 | DA | DA | DA | MEDIUM | DA | čl. 3 st. 1 tač. 3 | - | 8.4s |
| 3 | 1 | DA | DA | DA | MEDIUM | DA | čl. 3 st. 1 tač. 3 | - | 14.2s |

**Run 1 rizici:**
- Administrator može promeniti implementaciju u bilo kom trenutku.

**Run 2 rizici:**
- Administrator može promeniti implementaciju u bilo kom trenutku b

**Run 3 rizici:**
- Administrator može promeniti implementaciju bez vremenskog ograni

### simple_staking

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 11.8s |
| 2 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 2 | - | 12.6s |
| 3 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 | - | 9.9s |

**Run 1 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

**Run 2 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

**Run 3 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

### vesting

| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |
|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|
| 1 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 5 st. 1 | - | 10.8s |
| 2 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 5 | - | 11.9s |
| 3 | 1 | DA | DA | DA | HIGH | NE | čl. 3 st. 1 tač. 3, čl. 4 st. 1 | - | 9.2s |

**Run 1 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

**Run 2 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim

**Run 3 rizici:**
- Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim
