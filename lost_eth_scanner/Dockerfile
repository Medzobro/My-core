FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . /app/

# Create non-root user
RUN useradd -m -u 1000 scanner && chown -R scanner:scanner /app
USER scanner

EXPOSE 8000

# Default: run API server. Override with `docker run ... lost_eth.py scan ADDR`
CMD ["python3", "api_server.py"]
