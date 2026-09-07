# Requirements

## Summary

Add an optional `instruct` argument to the `generateAudio` mutation, letting a caller supply a general style guide for how the whole call should be read — e.g. "A male narrator with a clear voice. Treat bracketed words like [dramatic] or [proud] as emotion cues, not literal text. Don't read `<`/`>` characters aloud, just pause briefly where they appear." `text` itself is passed through untouched, inline tags and all (e.g. `"The system chimed: [Berserker Core Activated]. My new skill, Soul-Shaking Roar <LEVEL 1>, ..."`) — Beatrice does not parse, strip, or segment `text` in any way. It's Qwen3-TTS's own instruction-following that interprets the tags inside `text` according to `instruct`, in a single synthesis call.

Qwen3-TTS is the only provider that supports this today: `generate_custom_voice(text, language, speaker, instruct)` takes a fixed preset speaker plus an optional natural-language `instruct` string, preserving a consistent voice identity whether or not `instruct` is used. Gemini Cloud TTS has no equivalent — requests with `instruct` set must be rejected outright when Gemini is the configured provider, not silently ignored.

This requires switching Qwen3-TTS voices from the current custom `ref_audio`/`ref_text` clone (`"default"`) to Qwen's fixed preset speakers (Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee), since `generate_custom_voice` only accepts a preset speaker name, not a cloned reference clip. This is a deliberate trade-off: we lose the specific cloned voice identity in exchange for `instruct` support with a stable voice.

No batching, no segmentation — one `text` + one `instruct` maps to exactly one synthesis call, regardless of how many tags appear in `text`.

## Steps

Each step below is a standalone unit of work: implement it, test it at the tier `.github/CONTRIBUTING.md` calls for, commit it, then move to the next. Follow `PROCESS.md` for the per-step loop.

## 1. Provider Layer — `instruct` Plumbing

Add `instruct: str | None = None` to `TtsProvider.synthesize` (the `Protocol` in `src/modules/audio/provider.py`) and both implementations:

- `Qwen3TtsProvider.synthesize`: forward `instruct` in the JSON body to the shim (`POST /v1/audio/speech`) only when it's not `None`.
- `GeminiTtsProvider.synthesize`: raise a new `InstructNotSupportedError` (in `src/modules/audio/exceptions.py`, same shape as `InvalidVoiceError`) when `instruct is not None`.

### AC

- `TtsProvider` Protocol's docstring documents the Gemini limitation, matching the existing note about `language` filtering.
- `Qwen3TtsProvider.synthesize` omits `instruct` from the request body entirely when it's `None`, rather than sending `null`.

### Test

No GraphQL surface — pure Python. Unit tests for both providers (Qwen sends `instruct` in the body when given, omits it when absent; Gemini raises `InstructNotSupportedError` when `instruct` is given) with `httpx` mocked at the transport boundary per `.github/CONTRIBUTING.md`. Skip graphql-api-tester.

## 2. `generateAudio` Mutation — Accept & Validate `instruct`

Add `instruct: str | None = None` as an optional argument to `generate_audio` (`src/modules/audio/resolver.py`). Validate against the *configured* provider at resolver time (not deferred to the worker), so an unsupported combination fails fast with a normal GraphQL error instead of a queued job that fails later:

- If `instruct` is provided and `settings.tts.default_provider is not TtsProviderName.QWEN3_TTS`, raise `InstructNotSupportedError`.
- Otherwise include `instruct` in the RabbitMQ message body (`message_body["instruct"] = instruct`), omitted/`None` when not given.

### AC

- Validation happens before publishing to RabbitMQ — an invalid `instruct`/provider combination never reaches the queue.
- `instruct` has no length cap beyond GraphQL's own string handling — don't add one that wasn't asked for.
- Update the GraphQL schema docs (`strawberry.argument(description=...)`) to explain `instruct` is Qwen3-TTS-only, applies to the whole call as one style guide, and that `text` is never parsed or stripped — any inline tags in `text` are passed through verbatim for the model to interpret per `instruct`.

### Test

Extend `src/modules/audio/resolver__test.py` (unit, agent mocked/provider not invoked at this layer) plus one integration test in `tests/` covering the reject-when-Gemini path and the accept-and-publish-when-Qwen path (assert the RabbitMQ message body via the existing queue fixtures). Invoke graphql-api-tester with the `generateAudio` mutation, its file path, and this step's AC.

## 3. Worker — Forward `instruct` to the Provider

`GenerateAudioJob` (`src/modules/audio/types.py`) gains an `instruct: str | None` field parsed off the queue message. `synthesize_job` (`src/modules/audio/worker.py`) passes it through to `provider.synthesize(text=..., voice=..., instruct=...)`.

### AC

- Missing `instruct` in an older/foreign message on the queue deserializes to `None`, not a validation failure — this field did not exist before this feature.

### Test

No new GraphQL surface. Unit tests for `synthesize_job` mocking the provider, asserting `instruct` is forwarded. Extend the existing integration test(s) driving a message end-to-end (`worker_container` fixture) to cover a job carrying `instruct`.

## 4. Local Qwen3-TTS Shim — Preset Speakers + `instruct`

Update `local-setup/qwen-tts/server.py`:

- Replace the custom `ref_audio`/`ref_text` clone in `_VOICES` with a mapping from the voice names Beatrice exposes to one of Qwen3-TTS's 9 preset speaker names (`Vivian`, `Serena`, `Uncle_Fu`, `Dylan`, `Eric`, `Ryan`, `Aiden`, `Ono_Anna`, `Sohee`). Keep `"default"` mapped to an English speaker (`Ryan`).
- `SpeechRequest` gains `instruct: str | None = None`.
- `synthesize` calls `model.generate_custom_voice(text=request.input, language=LANGUAGE, speaker=..., instruct=request.instruct)` instead of `generate_voice_clone`.

### AC

- Module docstring at the top of `server.py` updated to describe the new contract (no more `ref_audio`/`ref_text` cloning).
- No behavior change for calls that omit `instruct`, beyond the voice now being a Qwen preset rather than the previous custom clone.

### Test

This is dev-only infra with no pytest coverage today — verify manually via `docker compose up --build -d` and a `generateAudio` mutation with and without `instruct`, confirming both produce audio and the `instruct` case audibly changes delivery style. No unit/integration/eval tier applies; skip graphql-api-tester (no GraphQL contract change here, `generateAudio`'s shape was already covered in step 2).
