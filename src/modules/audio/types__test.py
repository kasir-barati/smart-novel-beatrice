from __future__ import annotations

from src.modules.audio.types import GenerateAudioJob


def test_generate_audio_job_parses_camel_case_message_body() -> None:
    result = GenerateAudioJob.model_validate(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://client.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
        }
    )

    assert result.job_id == "job-1"
    assert result.text == "hello"
    assert result.voice == "qwen-voice-a"
    assert result.gen_upload_url == "https://client.example.com/upload"
    assert result.status_callback_url == "https://client.example.com/status"
    assert result.instruct is None


def test_generate_audio_job_parses_instruct_when_present() -> None:
    result = GenerateAudioJob.model_validate(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://client.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
            "instruct": "speak in a whisper",
        }
    )

    assert result.instruct == "speak in a whisper"
