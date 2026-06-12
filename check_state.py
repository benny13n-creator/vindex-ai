import json
from pathlib import Path
state = json.loads(Path('data/sudska_praksa/.ingest_state.json').read_text(encoding='utf-8'))
seed = len(state.get('seed_chunk_ids', []))
done = len(state.get('stage2_completed_ids', []))
batch = state.get('last_batch', 0)
print(f'seed_chunk_ids      : {seed}')
print(f'stage2_completed_ids: {done}')
print(f'last_batch          : {batch}')
print(f'Total ingested      : {seed + done}')
print(f'Total chunks disk   : 6397')
print(f'New to ingest       : {6397 - seed - done}')
