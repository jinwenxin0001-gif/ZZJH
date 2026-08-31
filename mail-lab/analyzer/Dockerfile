FROM python:3.12-slim-bookworm@sha256:c04b3281c4e15650a4a7e5294bac44e7e0a4164f8839c8f0f09356b89cf42009

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/tmp

RUN groupadd --system --gid 10001 analyzer \
    && useradd --system --uid 10001 --gid analyzer --home-dir /nonexistent analyzer \
    && install -d -o analyzer -g analyzer /app /data/results

COPY analyzer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt \
    && rm /tmp/requirements.txt

ENV OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

COPY --chown=analyzer:analyzer analyzer/src/ /app/
COPY --chown=analyzer:analyzer analyzer/tests/ /app/tests/

USER analyzer
EXPOSE 10025

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=12 \
  CMD ["python", "-c", "import socket; s=socket.create_connection(('127.0.0.1',10025),2); assert s.recv(64).startswith(b'220'); s.close()"]

CMD ["python", "-m", "attachment_analyzer.service"]
