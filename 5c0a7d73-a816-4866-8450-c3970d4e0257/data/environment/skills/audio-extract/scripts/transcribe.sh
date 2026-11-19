#!/usr/bin/env bash
# Transcribe an audio/video file to text with the LOCAL openai-whisper that is
# baked into the agent image (wildclawbench-ubuntu:v1.4, 'small' weights under
# /opt/wb_whisper_models). No network, no API key, no sidecar route.
#
# Usage:
#   transcribe.sh <media>                 # audio OR video; auto-extracts WAV
#   transcribe.sh <media> --raw           # accepted for backward compatibility (no-op)
#
# Output (stdout): the transcript text.
# Output (stderr): step markers ("== extract ==", "== transcribe ==").
# Exit codes: 0 success · 1 input not found · 2 usage · 3 no local whisper
#             weights · 4 ffmpeg produced no audio · 8 whisper failed.
#
# Design notes:
#   - Any input goes through ffmpeg -> 16kHz mono pcm_s16le for determinism.
#   - The agent container has no internet egress; the weights must already be
#     in the image. WCB_WHISPER_MODEL_DIR overrides the weights dir.

set -euo pipefail

if [[ "${1:-}" == "" || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat >&2 <<'EOF'
usage: transcribe.sh <media> [--raw]

Transcribe an audio or video file to text with the local whisper model.
The transcript is printed on stdout.
EOF
  exit 2
fi

in="$1"

if [[ ! -f "$in" ]]; then
  echo "transcribe.sh: input file not found: $in" >&2
  exit 1
fi

whisper_model_dir="${WCB_WHISPER_MODEL_DIR:-/opt/wb_whisper_models}"
if [[ ! -d "$whisper_model_dir" ]]; then
  echo "transcribe.sh: no local Whisper weights under $whisper_model_dir." >&2
  echo "  The agent image is expected to ship them (docker/agent-whisper.Dockerfile)." >&2
  echo "  Treat as a harness image regression." >&2
  exit 3
fi

basename_in="$(basename "$in")"
stem="${basename_in%.*}"
scratch_dir="/tmp_workspace/_scratch"
mkdir -p "$scratch_dir"
wav="$scratch_dir/${stem}.wav"

echo "== extract: $in -> $wav ==" >&2
ffmpeg -y -loglevel error -i "$in" -vn -acodec pcm_s16le -ar 16000 -ac 1 "$wav"

if [[ ! -s "$wav" ]]; then
  echo "transcribe.sh: ffmpeg produced no audio output for $in" >&2
  exit 4
fi

transcribe_local() {
  echo "== transcribe: local whisper (small, $whisper_model_dir) ==" >&2
  python3 - "$wav" "$whisper_model_dir" <<'PY'
import sys
import whisper
wav, model_dir = sys.argv[1], sys.argv[2]
model = whisper.load_model("small", download_root=model_dir)
text = model.transcribe(wav)["text"].strip()
sys.stdout.write(text)
if not text.endswith("\n"):
    sys.stdout.write("\n")
PY
}

transcribe_local || {
  echo "transcribe.sh: local whisper transcription failed ($whisper_model_dir)." >&2
  exit 8
}
