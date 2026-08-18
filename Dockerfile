FROM python:3.12-slim

WORKDIR /app

# System deps for building any C-extension wheels not shipped for the
# target platform (cryptography/asyncpg usually have wheels, but keep
# this cheap fallback so builds don't break on odd architectures).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
