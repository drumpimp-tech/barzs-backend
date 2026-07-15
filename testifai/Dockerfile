# TESTIFAI — runs on any container host (Fly.io, Cloud Run, Render, Railway,
# DigitalOcean, Koyeb, Azure, AWS, etc.)
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Honor the platform's $PORT (Cloud Run, Render, Railway, Heroku all set it).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
