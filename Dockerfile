# Single image containing both the built frontend and the API — this is
# what makes the platform "one thing to deploy" instead of a
# frontend-host + backend-host + DB-console assembly.

# --- Stage 1: build the React (Vite) frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python backend + LibreOffice (needed for PPTX->PDF conversion) ---
FROM python:3.11-slim AS backend

# soffice is required by reports/pdf_generator.py's pptx_to_pdf conversion.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Remove the frontend source (already built in stage 1); keep the built
# output only, so the runtime image doesn't carry node_modules etc.
RUN rm -rf frontend
COPY --from=frontend-build /app/frontend/dist ./frontend_dist

ENV FRONTEND_DIST=/app/frontend_dist
ENV PYTHONUNBUFFERED=1

# Directory for local report storage (see api/storage.py, STORAGE_BACKEND=local)
RUN mkdir -p /data/reports /data/uploads
VOLUME ["/data/reports", "/data/uploads"]

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
