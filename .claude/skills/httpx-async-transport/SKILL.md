---
name: httpx-async-transport
description: Use when writing or reviewing a class that owns an httpx.AsyncClient (an HTTP provider client, callback client, presigned-URL client, etc.) — ensures tests can inject a mock transport without patching internals.
---

A class that owns an `httpx.AsyncClient` must accept an optional constructor param:

```python
def __init__(self, ..., transport: httpx.AsyncBaseTransport | None = None) -> None:
    self._client = httpx.AsyncClient(..., transport=transport)
```

- Type it `httpx.AsyncBaseTransport`, not `httpx.BaseTransport` — pyright rejects the sync variant against `AsyncClient`.
- This lets tests inject `httpx.MockTransport` directly instead of patching the client or its methods.
