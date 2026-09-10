# Self-improvement Log

## 2026-09-10 — TTS-provider-swap step 1

Removing `QwenTtsSettings.voices_path` (per the step's AC) left `qwen_provider.py`
referencing a field that no longer existed — an `AttributeError` at runtime and a
pyright error, not just a stale test. The repo's pre-commit hook runs `make test`
(full unit suite) and blocks the commit on any failure, so the step couldn't be
committed with that file left broken pending step 2, even though the requirements
doc frames the two steps as independently committable.

Fix: made the minimal change to `qwen_provider.py`'s `get_voices` (read the new
static `voices_list` instead of calling the removed path) and updated only the
directly-broken assertions in its test file (voice listing, `model` default
literal), leaving the rest of the DashScope migration (synthesize body shape,
`instruct`→`instructions`, two-hop download) untouched for step 2.

Changed `PROCESS.md` step 7 to call this out generally: a step that removes/renames
something another file depends on must fold that file's minimal fix into the same
commit, since the test gate doesn't allow a step-spanning red window.

## 2026-09-10 — TTS-provider-swap step 2

Step 2's `### Test` subsection asserted the existing `generateAudio` integration
test "should still pass unmodified — run it to confirm rather than assume." Running
it (as instructed) showed that was wrong: `Qwen3TtsProvider.get_voices` no longer
makes an HTTP call (static `voices` config, from step 1), so the `/v1/voices` WireMock
stub was dead and the `qwen-voice-a` voice was no longer in `TTS__QWEN__VOICES`,
making every test fail voice validation before even reaching synthesis. Separately,
`synthesize`'s new two-hop DashScope contract (JSON body with an audio URL, then a
second GET) meant the old single-hop `/v1/audio/speech` raw-bytes stub no longer
matched what the provider actually calls.

Fix: added `TTS__QWEN__VOICES` to `app_container`'s env in `tests/conftest.py`, and
rewrote the integration test's stubbing (`tests/test_generate_audio_graphql.py`) to
the new synthesize path/body shape and two-hop stub, dropping the now-pointless
`/v1/voices` stub entirely.

Extended `PROCESS.md` step 5's manual-verification note to also cover this case: a
"should still pass unmodified" claim about an *existing* pytest-tier test is a guess,
not a fact, and needs the same "actually run it" treatment.

## 2026-09-10 — TTS-provider-swap step 3

Two things surfaced during manual verification, both already covered by existing
`PROCESS.md`/log guidance rather than needing new rules:

- `compose.yml`'s `beatrice` service needed `TTS__QWEN__VOICES` set to match the
  shim's static `_VOICES` mapping — step 3's scope (`local-setup/qwen-tts/server.py`)
  didn't call this out, but without it `audioVoices`/`generateAudio` have nothing to
  validate against. Same "actually run it, fix what's missing" pattern as steps 1-2.
- Host port 9000 (MinIO) was taken by an unrelated local process (the user's Jupyter
  notebook), blocking `docker compose up`. Not a code issue — asked the user how to
  proceed rather than guessing, then moved MinIO's host-side port off 9000 by default
  (`MINIO_HOST_PORT`, defaulting to 9010) since internal traffic only ever uses
  `minio:9000`. One-off environment conflict, not a process gap — no `PROCESS.md`
  change from this alone.

No `PROCESS.md` edit this round — both issues were instances of patterns already
captured by the step 1/2 entries above.
