FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN useradd -m -u 1000 scanner && mkdir -p /app/cache && chown -R scanner:scanner /app
USER scanner

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3).status == 200 else 1)"

# Web audit app by default; override with `docker run ... python lost_eth.py scan 0xADDR`
CMD ["uvicorn", "audit.server:app", "--host", "0.0.0.0", "--port", "8010"]
