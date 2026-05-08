# seerr-manager

A small web dashboard for managing Seerr requests. It surfaces stuck, flagged, or deleted media and lets you re-request individual items or a batch in one click.

## Requirements

- Docker (or Python 3.12 + Node 22 to run locally)
- A Seerr instance with an API key
- A TMDB API key

## Setup

Copy `.env.example` to `.env` and fill in your values:

```env
SEERR_URL=https://your-seerr-url
SEERR_API_KEY=your-api-key
TMDB_API_KEY=your-tmdb-api-key
```

## Run with Docker Compose

```bash
docker compose up -d
```

Open [http://localhost:8765](http://localhost:8765).

## Run locally

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8765

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Frontend dev server proxies `/api` to `localhost:8765`.
