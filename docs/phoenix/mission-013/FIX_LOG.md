# Mission 013 — Fix Log

### New file — `shared/query_timeout.py`
```python
DEFAULT_TIMEOUT_SECONDS = 15.0

async def gather_with_timeout(*coros, timeout=DEFAULT_TIMEOUT_SECONDS, label=""):
    try:
        return await asyncio.wait_for(asyncio.gather(*coros, return_exceptions=True), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(...)
        return (asyncio.TimeoutError(f"query timeout after {timeout}s"),) * len(coros)

async def single_with_timeout(coro, *, timeout=DEFAULT_TIMEOUT_SECONDS, label=""):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(...)
        return _EmptyResult()  # .data == []
```

### `routers/dashboard.py`
```python
from shared.query_timeout import gather_with_timeout
# command_center: asyncio.gather(..., return_exceptions=True) -> gather_with_timeout(..., label=...)
# matter_health_score: same swap, plus:
if isinstance(pred_r, asyncio.TimeoutError):
    raise HTTPException(status_code=503, detail="Upit je predugo trajao. Pokušajte ponovo.")
```

### `routers/workspace.py`
```python
from shared.query_timeout import gather_with_timeout, single_with_timeout
# _fetch_recently_completed's own gather -> gather_with_timeout
# predmeti_r standalone fetch -> single_with_timeout
# get_workspace's main 3-way gather -> gather_with_timeout
```

### `static/vindex.js`
```js
async function _fetchWithTimeout(url, options, timeoutMs) {
  var controller = new AbortController();
  var timer = setTimeout(function() { controller.abort(); }, timeoutMs);
  try {
    return await fetch(url, Object.assign({}, options || {}, { signal: controller.signal }));
  } finally {
    clearTimeout(timer);
  }
}
// pred_upload_doc: fetch(...) -> _fetchWithTimeout(..., 90000)
// catch(e): e.name === 'AbortError' -> distinct "predugo trajalo" message
```

### `static/sw.js`
`CACHE_NAME` bumped `"vindex-v103"` → `"vindex-v104"`.

## Reuse discipline

Both backend endpoints and both frontend call sites reuse the exact same, single canonical
helper (`shared/query_timeout.py` on the backend; `_fetchWithTimeout` on the frontend) rather
than each hand-rolling its own timeout boilerplate. Zero new algorithms, zero migrations.
