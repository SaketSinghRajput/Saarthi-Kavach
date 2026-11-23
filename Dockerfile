# Saarthi public-demo image (linux/amd64). Offline/stub-capable: boots with no env vars.
# Build: docker build --platform linux/amd64 -t saarthi:demo .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime deps only (no pytest, no Kokoro/torch). App lives in /opt (Agent37 masks the image user's home).
COPY deploy/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN pip install -r /tmp/requirements-runtime.txt && rm /tmp/requirements-runtime.txt

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin saarthi
WORKDIR /opt/saarthi
COPY app/ app/
COPY web/ web/
COPY fixtures/ fixtures/
COPY audio/cache/ audio/cache/
# prompts/ is not read by app/ at runtime (grep-verified), so it is not copied.
RUN mkdir -p data && chown -R saarthi:saarthi /opt/saarthi

USER saarthi
ENV PORT=8000 DATA_DIR=/opt/saarthi/data
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
