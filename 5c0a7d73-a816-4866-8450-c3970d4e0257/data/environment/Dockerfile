FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    python3 \
    python3-pip \
    ffmpeg \
    poppler-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --break-system-packages pymupdf==1.28.2 pillow==12.3.0 openpyxl==3.1.5 python-docx==1.2.0 python-pptx==1.0.2 opencv-python-headless==4.14.0.94

RUN pip install --no-cache-dir --break-system-packages openai-whisper==20250625 \
    && mkdir -p /opt/wb_whisper_models \
    && python3 -c "import whisper; whisper.load_model('small', download_root='/opt/wb_whisper_models')" \
    && mkdir -p /root/.cache && ln -sfn /opt/wb_whisper_models /root/.cache/whisper

# Copy skills to all agent framework paths
COPY skills /root/.claude/skills
RUN mkdir -p /root/.codex/skills /root/.opencode/skills /root/.goose/skills /root/.factory/skills /root/.agents/skills /root/.gemini/skills /root/.cursor/skills && cp -a /root/.claude/skills/. /root/.codex/skills/ && cp -a /root/.claude/skills/. /root/.opencode/skills/ && cp -a /root/.claude/skills/. /root/.goose/skills/ && cp -a /root/.claude/skills/. /root/.factory/skills/ && cp -a /root/.claude/skills/. /root/.agents/skills/ && cp -a /root/.claude/skills/. /root/.gemini/skills/ && cp -a /root/.claude/skills/. /root/.cursor/skills/

# Copy persona
COPY persona /root/.openclaw/persona

# Copy multimodal artifacts
COPY artifacts/inputs/files /app/artifacts/inputs/files

WORKDIR /app
