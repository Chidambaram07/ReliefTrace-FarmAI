# ReliefTrace backend (FastAPI). Build:  docker build -t relieftrace-backend .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY scripts ./scripts
COPY demo ./demo

# Reference dataset / images / boundaries are mounted at runtime (see docker-compose.yml); never baked into the image.
ENV RT_CSV_PATH=/data/raw/Ground_truth_Points.csv \
    RT_IMAGES_DIR=/data/images \
    RT_GEO_DIR=/data/geo \
    RT_DB_PATH=/data/processed/reliefTrace.db \
    RT_UPLOAD_DIR=/data/uploads \
    AWS_REGION=ap-south-1

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
