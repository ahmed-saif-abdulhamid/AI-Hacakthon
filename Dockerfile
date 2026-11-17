FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app HOME=/tmp PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt requirements-voice.txt ./
RUN pip install -r requirements.txt

# Optional local British voice (Piper, open source, offline). If it cannot be installed the
# console falls back to the browser's built-in en-GB speech voice; nothing else changes.
ARG INSTALL_VOICE=1
RUN if [ "$INSTALL_VOICE" = "1" ]; then \
      (pip install -r requirements-voice.txt && mkdir -p /opt/voices && \
       python -c "import urllib.request as u; b='https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alan/medium/'; \
[u.urlretrieve(b+f, '/opt/voices/'+f) for f in ('en_GB-alan-medium.onnx','en_GB-alan-medium.onnx.json')]") \
      || echo "voice install skipped: browser speech fallback will be used"; \
    fi
ENV PIPER_VOICE=/opt/voices/en_GB-alan-medium.onnx

COPY . .
RUN mkdir -p /app/data /app/outputs /app/runs && chown -R 1000:1000 /app && chmod 1777 /app/data

# Never run as root: uid 1000 owns /app, and the named volume for /app/data starts with that owner.
USER 1000:1000

EXPOSE 8000 8501
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
