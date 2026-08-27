# Requirements

## Summary

I wanna enable clients of this app to generate a TTS by sending the request to Qwen3-TTS or Gemini-TTS. For this client needs to fetch the voices the LLM supports and then client can send the text in question to the service. Then it is gonna forward it to the LLM and upload the audio file into a presigned URL. We do NOT need to have any auth, but if there is a `Authorization` HTTP header attached to the incoming requests we are gonna send back and forth so client can use it if they wanted.

The goal is a clean, focused tool that does generate a TTS for a given text and upload it to an object storage such as AWS S3.

# Steps

Each step below is a standalone unit of work: implement it, test it at the tier `.github/CONTRIBUTING.md` calls for, commit it, then move to the next. Do not start a later step early even if it looks convenient — that's what breaks the "commit and test each step individually" goal. Steps are ordered so each one produces something concretely verifiable (a passing unit test suite, or a live GraphQL operation) before the next step builds on it; `audioVoices` (step 2) comes before `generateAudio` (steps 3-6) for that reason.

Follow `PROCESS.md` for the per-step loop.

## 1. Provider Abstraction Layer

Create a simple abstraction layer for me to be able to talk to different providers (for now qwen3-tts and gemini-tts) over a unified API. And for now I would like to have two APIs:

- Get voices API which returns all the voices the models supports.
  - For now just support English and write a note in the final doc about this limitation (write it as part of the DOCString doc so users can see it).
    - But please accept a string language code as argument. The languages that this voice supports, expressed as BCP-47 language tags (e.g. "en-US", "es-419", "cmn-tw").
    - Make sure the language code only is passed when we have Gemini-TTS and not Qwen3-TTS since it does have that feature.
  - Use direct API calls to fetch it:
    - For Gemini-TTS: `GET https://texttospeech.googleapis.com/v1/voices`.
    - For Qwen3-TTS: `GET https://api.deepinfra.com/v1/voices`, in empiriolabs.ai it sais it is also `GET /v1/voices`. BUT in github.com/vllm-project/vllm-omni it is `GET /v1/audio/voices`
      - Honestly I am unsure about Qwen3-TTS since all these APIs are 3rd part inference providers.
- An API to generate a TTS for a given text.
  - It stores the results in a file, and returns its address.
  - Client will use this to upload it to a presigned URL.

### AC

- Do NOT use boto3, instead just call the presigned URL and try to upload it. This way we are object storage agnostic.
  - Document that the object storage must be S3-compatible so the presigned URL can be used the same way.
- We can fetch all the voices.
- Voices change based on Qwen3-TTS or Gemini-TTS. AKA we should fetch it from their APIs.
- When we call the API to generate a TTS it can generate it and return the file absolute path.

### Test

No GraphQL surface yet — this is a pure Python module. Unit tests only, with the provider HTTP calls mocked. Skip the graphql-api-tester subagent for this step.

## 2. Add `audioVoices` Query

When client calls this API they will be getting a list of strings telling them what are their options for picking a voice. We should NOT asking over and over again from the model about what are the available options.

### AC

- Cache the result, so we can return a response immediately.
- Accept a URL as env variable to resolve voice names.
- Add to the GraphQL Doc that the voices are all for english text. This is a limitation we address later.

### Test

First step with a live GraphQL operation. Add an integration test per `.github/CONTRIBUTING.md`. Invoke the graphql-api-tester subagent with the `audioVoices` query, its file path, and this step's AC.

## 3. Add `generateAudio` Mutation — Accept, Validate, Publish

Add a new `generateAudio` mutation covering only the synchronous half of the pipeline: accept the request, validate it, publish to RabbitMQ, respond immediately. The worker side is steps 4-6.

1. Accept a text (`text`), a voice name, a callback URL which generates and returns a presigned URL (`genUploadUrl`), a callback URL for reporting back the progress and state of the synthesizing (`statusCallbackUrl`).
   - Validate the text, it should NOT exceed the configured number (read it from env variable).
   - Validate voice is what Gemini-TTS/Qwen3-TTS accepts.
   - Validate the callback URLs are valid URLs.
     - Because Beatrice is about to make an outbound HTTP call to a URL it didn't choose we need allow-list.
     - We must enumerate valid callback hosts read from an env variable.
   - The header of the message published on RabbitMQ should contain:
     - Add the timestamp to it.
   - The body should contain the incoming message body.
2. Publish a message on RabbitMQ.
   - Report back we have "queued" the message using the `statusCallbackUrl` (request body: `{ status: "queued" }`).
3. The service immediately responds:
   ```
   HTTP/1.1 202 Accepted
   Content-Type: application/json

   {
     "jobId": "550e8400-e29b-41d4-a716-446655440000",
   }
   ```

### AC

- Use nested variables instead of dumping all new env variables in `Settings` class.
- Make sure to attach the `Authorization` headers to the outgoing requests/responses if we have it.
- If there is a `Authorization` header attached to the incoming request we should add it to the RabbitMQ message.
- Make sure the outgoing requests are auto instrumented so we are attaching the OTel trace ID of a RabbitMQ message to the http call.
- Make sure to auto instrument RabbitMQ so we are attaching OTel trace ID to each message.
- Use quorum queues.
- Accept a RabbitMQ connection string to connect to it.
- Set prefetch count to 5 by default but read it from env variable.

### Test

Integration test asserting the 202 response shape and that a message actually lands on the queue (Testcontainers RabbitMQ), including its headers/body. Also assert the queue is actually declared as quorum using unit tests. Use the `wiremock` fixture (`tests/conftest.py`) for the `statusCallbackUrl` "queued" callback assertion instead of a hand-rolled stub server. Invoke graphql-api-tester with the `generateAudio` mutation, its file path, and this step's AC — including at least one invalid-input case (bad callback host, oversized text). No worker exists yet, so don't ask it to verify anything past the 202 response.

## 4. Worker — Consume & Synthesize

Consume the job in a separate worker process:

1. Call the `statusCallbackUrl` with `{ status: "generating", percent: 0 }`.
2. Call the Qwen3-TTS/Gemini-TTS for audio bytes.
   - Report back progress (`{ status: "generating", percent: 12 }`), I guess for this we need to estimate it and cannot really offer a real value, right?
   - Stream the audio file into a temp file.

Progress reporting is coarse-grained by default (`pending → generating → uploading → succeeded/failed`). Synthesis progress is deferred/estimated: Qwen3-TTS's HTTP shim does not currently expose incremental progress.

### Test

No GraphQL surface (internal worker process). Unit tests with the provider and the callback HTTP calls mocked. Save the `wiremock` fixture for integration tests — unit tests should mock at the HTTP-client boundary directly, per `.github/CONTRIBUTING.md`.

## 5. Worker — Upload & Completion

3. Get a new presigned URL.
   - Add a `Idempotency-Key` to the outgoing request so it knows when it is the same thing.
   - Report back progress (`{ status: "uploading", percent: 0 }`), I guess for this we need to estimate it based on file size and cannot really offer a real value, right?
4. PUT the audio file to the presigned URL.
5. Report progress and terminal state (with `{ status: "completed"; fileSizeBytes: number }` / with `{status: "failed"; failedAt: string; error: { code: SynthesizeErrorCode; message: string }}`) back to the client via the callback URL.

Note that Beatrice **owns no persistent state**. Audio storage is the caller's responsibility.

### Test

No GraphQL surface. Unit tests with the presigned-URL and status-callback HTTP calls mocked, plus one integration test driving a message end-to-end through steps 3-5: Testcontainers RabbitMQ, `wiremock` stubbing `genUploadUrl` to return a URL from `presigned_upload_url_factory` and stubbing `statusCallbackUrl`, and `minio_verify_client`/`minio_bucket` to assert the uploaded object actually landed (right bytes, right size).

## 6. Retry & DLQ

If step 5 failed we MUST retry using the `x-attempt` and `x-delivery-limit` + DLQ. Read the limits from env variables. In TTS service when you pick up a message from RabbitMQ to process you have to think about when to NOT retry and drop the message. So when we call the callbacks and get a:

- `4xx` in general = client error = "this request is malformed and retrying it unchanged won't help." A `400` on our callback because the payload doesn't match client's schema, a `404` because the job was deleted on client's side, a `401`/`403` because the token is wrong. None of these get better by trying again in 30 seconds. Retrying them just burns our attempt budget on something that will fail identically three times.
- `408` (Request Timeout) and `429` (Too Many Requests) are the exceptions because they're not really about our request being wrong, they're the server saying "I couldn't process this in time" or "slow down, I'm rate-limiting you." Both are explicitly transient by design (`429` typically comes with a Retry-After header for exactly this reason) worth honoring that header if present rather than always waiting our fixed 30s, since Service A is telling you exactly how long to back off.
- `5xx` and network errors (timeouts, connection refused) are always retryable, these mean the server (or network) failed, not that our request was invalid, so retrying is the correct default behavior for all of them, no exceptions to enumerate the way there is for `4xx`.

### Test

Unit tests simulating each response class (4xx, 408, 429 with/without Retry-After, 5xx, network error) against the retry decision function. Integration test for the DLQ path: exhaust `x-delivery-limit` and assert the message lands on the DLQ.

## 7. Observability & Logging

I wanna log and be really observable about what is happening in Beatrice. So that is why I would like to have these logged and observable in OTel:

- Attempt: when we say we failed/succeeded in processing and generating a TTS we should log attempt counter.
- Instance ID: Beatrice will be replicated, so it is a good idea to log this.
- job ID.
- Voice name.
- Model: e.g. is it Gemini-TTS, or Qwen3-TTS.
- state: In which state did we log something.
- And since logs MUST be instrumented I believe I can easily link it to a request.
- text character count.
- How long it waited in the queue before being picked up by an instance and consequently started to be processed.
- How long it took our service to process it.
- How long it took in total to synthesize (wait in queue + processing time).
- File size in byte.
- Error code if we encountered one.
- Error message if have one.
- When it failed to process the message regardless of wether it was retried or dropped entirely.
- Max attempt.
- Redacted presigned URL (if redaction failed just return the plain URL as it is with a warning that redaction failed).

### Test

Unit tests asserting the log record contains each required field for the success and failure paths. No new GraphQL surface — skip graphql-api-tester.

### Architecture

```
Client Service
    │  (1) mutation generateAudio(input)
    ▼
Beatrice GraphQL (FastAPI process)
    │  validate input
    │  publish message to RabbitMQ
    │  return { jobId: "some UUID", status: "pending" }
    ▼
RabbitMQ  ──►  Beatrice consumer (separate process)
                    │  (1) Reports back it is {statusL "processing", progress: 0.0}
                    │  (2) POST qwen-tts-server /v1/audio/speech (streaming download)
                    │  (3) Reports back progress improvement
                    │  (4) Get a new presigned URL.
                    |  (5) Upload the file.
                    │  (6) Reports back progress improvement
                    │  (7) Reports back success/failure
                    ▼
```
