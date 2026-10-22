# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Build context is the novamind/ repo root (run `ibmcloud ce app create` from there).
# All paths below are relative to novamind/.

# Install Python dependencies
COPY mock_bank/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY mock_bank/main.py mock_bank/models.py mock_bank/seed.py ./
COPY mock_bank/templates/ templates/

# Copy seed data (read-only at runtime; DB is written to /data on each start)
COPY data/ /seed_data/

# SQLite DB directory — reseeded from /seed_data on every cold start (demo mode)
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/mock_bank.db
ENV SEED_DATA_DIR=/seed_data

# PORT is injected by Code Engine; default 8080
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
