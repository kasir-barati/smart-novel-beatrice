---
name: caplog-extra-typing
description: Use when writing a test that asserts on custom fields attached via a log call's extra={...}, read back through caplog.records — avoids a pyright error on undeclared LogRecord attributes.
---

`logging.LogRecord` doesn't statically declare arbitrary `extra={...}` fields, even though they're real attributes at runtime — pyright rejects `record.your_field`.

Type the local as `Any` at the point you pull it out of `caplog.records`, rather than suppressing each field access individually:

```python
from typing import Any

record: Any = next(r for r in caplog.records if r.message == "...")
assert record.your_field == expected
```
