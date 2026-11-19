---
name: audio-extract
description: Extract a 16kHz mono WAV audio track from any media file, probe metadata, and transcribe speech to text with the local Whisper model baked into the agent image (no internet, no API key required).
metadata: {"clawdbot":{"emoji":"🎧","requires":{"bins":["ffmpeg","ffprobe"]},"install":[{"id":"brew","kind":"brew","formula":"ffmpeg","bins":["ffmpeg"],"label":"Install ffmpeg (brew)"}]}}
---

# Audio Extract & Transcribe

This skill turns any audio/video file into (a) a clean 16kHz mono WAV and
(b) a plain-text transcript. Both steps run entirely inside the sandbox: the
WAV is produced locally by `ffmpeg`, and the transcript by the `openai-whisper`
Python package with the `small` weights baked into the image at
`/opt/wb_whisper_models`. The agent container has **no direct internet
access** — do NOT try `pip install openai-whisper`, `pip install pypdf`, or
`curl https://api.openai.com/...`; those all fail with `Temporary failure in
name resolution`. `transcribe.sh` is the supported transcription path.

## Quick start — transcribe (most common case)

```bash
{baseDir}/scripts/transcribe.sh /path/to/recording.m4a
```

Output (stdout): the transcript text, one block.
The intermediate WAV is left at `/tmp_workspace/_scratch/<basename>.wav` so
you can re-use it (e.g. send a second pass with different prompt context).

## Probe only (metadata, no extraction, no transcription)

```bash
{baseDir}/scripts/extract.sh --probe /path/to/recording.mp4
```

Prints duration, format, codecs, stream count.

## Extract only (no transcription) — useful when you want to control the WAV path

```bash
{baseDir}/scripts/extract.sh /path/to/recording.mp4 /tmp_workspace/results/audio.wav
```

The 16kHz mono WAV is the standard input format for speech-to-text. If you
have already produced a WAV yourself, you can transcribe it directly:

```bash
{baseDir}/scripts/transcribe.sh /tmp_workspace/results/audio.wav
```

## How transcription works (so you can debug if it fails)

`transcribe.sh` re-encodes the input with `ffmpeg` to 16kHz mono WAV, then runs
the local Whisper model (CPU inference; a few seconds per minute of audio):

```python
import whisper
model = whisper.load_model("small", download_root="/opt/wb_whisper_models")
print(model.transcribe("/path/to/audio.wav")["text"])
```

Exit codes: `1` input not found · `3` no weights under `/opt/wb_whisper_models`
(harness image regression — report it, do not try to download) · `4` ffmpeg
produced no audio · `8` whisper failed.

The two `whisper` skills shipped inside the openclaw runtime remain
unusable here, so prefer `transcribe.sh` over both:

- `openai-whisper` wants the `whisper` CLI binary, which is not on `PATH`
  (the package is importable from Python, but the CLI is not installed).
- `openai-whisper-api` wants `OPENAI_API_KEY` plus a direct HTTPS call to
  `api.openai.com`, neither of which is available in the agent
  container.

## Requires

- `ffmpeg`, `ffprobe` — installed in the image. Used by both
  `extract.sh` and `transcribe.sh`.
- `/opt/wb_whisper_models` — local Whisper weights baked into the image
  (`WCB_WHISPER_MODEL_DIR` overrides the path).
