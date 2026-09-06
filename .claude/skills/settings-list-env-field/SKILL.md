---
name: settings-list-env-field
description: Use when adding a field to a pydantic-settings BaseSettings class that should read a human-friendly (e.g. comma-separated) value from an environment variable — prevents a broken list[...] field type.
---

Don't give a `BaseSettings` field a `list[...]` type if you want a delimited (e.g. comma-separated) env var for it.

pydantic-settings JSON-decodes any list/dict-typed field read from an env var **before** any `field_validator` runs — a custom "split on comma" validator is never reached, and a non-JSON value raises `SettingsError` at startup.

Instead, type the field as `str` and expose a computed `@property` that parses it:

```python
class CallbackSettings(BaseSettings):
    allowed_hosts: str = ""

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
```

See `CallbackSettings.allowed_hosts` / `allowed_hosts_list` in `src/utils/config.py` for the existing pattern.

Only use a real `list[...]` field if the env var is meant to hold actual JSON.
