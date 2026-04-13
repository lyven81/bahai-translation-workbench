FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -fsS "http://localhost:${PORT}/healthz" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
