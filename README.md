# seerr-manager

A self-hosted web dashboard for managing **Seerr** requests.
It surfaces stuck, flagged, or deleted media and lets you re-request individual items or a whole batch in one click — fixing common edge-cases that Seerr itself does not handle.
A second **Watchlist** tab compares your Plex watchlist against Seerr and lets you bulk-request anything that is missing.

---

## Features

### Requests tab
- Lists every Seerr request enriched with TMDB poster, title, year, and overview
- Flags problematic items (⚑) automatically:
  - Missing TMDB ID
  - TV/movie imported from Plex watchlist with only a TVDB ID
  - Media deleted from the library (`DELETED`)
  - Request stuck in `PENDING` or `PROCESSING` for more than 7 days
- Surfaces **orphaned** deleted media records that have no active request
- Re-request a single item or batch-re-request multiple selected items in one click
- Filter by media type, media status, flagged-only, or free-text title search

### Watchlist tab
- Fetches your Plex watchlist directly from Seerr and compares it to your existing requests and library
- Three columns: **Watchlist Only** (not in Seerr yet), **In Seerr** (request exists), **Available** (already in library)
- Stats bar shows totals at a glance, including items requested from sources other than your watchlist
- Select any number of un-requested watchlist items and submit them all with a single click

### Other
- Bearer-token authentication (optional but strongly recommended for public-facing deployments)
- Server-side TTL cache to reduce load on Seerr and TMDB — configurable, with a manual flush button
- Dark theme only; works on mobile and desktop

---

## Requirements

- Docker (or Python 3.12 + Node 22 to run locally)
- A running Overseerr or Jellyseerr instance with an API key
- A TMDB API key (v3 string key **or** v4 read-access JWT token)

---

## Environment variables

### Required

| Variable | Description |
|---|---|
| `SEERR_URL` | Base URL of your Overseerr/Jellyseerr instance (no trailing slash). Must be `http://` or `https://`. |
| `SEERR_API_KEY` | Seerr API key (Settings → General → API Key). |
| `TMDB_API_KEY` | TMDB v3 API key **or** v4 read-access token (JWT starting with `eyJ`). |

### Optional

| Variable | Default | Description |
|---|---|---|
| `APP_SECRET` | *(empty — auth disabled)* | A strong random secret that protects all `/api/*` routes. When set, every request must include `Authorization: Bearer <APP_SECRET>`. The UI shows a login screen until the correct token is entered. Generate with `openssl rand -hex 32`. |
| `CACHE_TTL_SECONDS` | `300` | How long (in seconds) to cache responses from Seerr and TMDB. Set to `0` to disable caching entirely. |
| `CORS_ORIGINS` | *(empty — cross-origin blocked)* | Comma-separated list of origins allowed to make cross-origin requests to the API (e.g. `http://localhost:5173`). Leave empty unless you access the API from a different origin than where the UI is served. |

---

## Setup

Copy `.env.example` to `.env` and fill in your values:

```env
SEERR_URL=https://your-overseerr-or-jellyseerr-url
SEERR_API_KEY=your-api-key
TMDB_API_KEY=your-tmdb-api-key

# Strongly recommended: protects all /api/* routes with a bearer token.
# Generate with: openssl rand -hex 32
APP_SECRET=your-strong-random-secret

# Optional
# CACHE_TTL_SECONDS=300
# CORS_ORIGINS=http://localhost:5173
```

---

## Run with Docker Compose

```bash
docker compose up -d
```

Open [http://localhost:8765](http://localhost:8765).

To pass optional variables, add them to your `.env` file or set them inline in `docker-compose.yml` under the `environment` key.

---

## Run locally

```bash
# Backend (hot-reload)
cd backend && pip install -r requirements.txt
SEERR_URL=... SEERR_API_KEY=... TMDB_API_KEY=... uvicorn main:app --reload --port 8765

# Frontend (separate terminal — proxies /api to :8765)
cd frontend && npm install && npm run dev
```

The Vite dev server proxies `/api` to `localhost:8765`, so you only need to open the Vite URL (default `http://localhost:5173`).

---

## Authentication

When `APP_SECRET` is set the app shows a login screen on first visit.
Enter the secret and click **Unlock** — the token is stored in `localStorage` so you won't be prompted again on the same device.

If you are deploying on a private network behind a VPN or a reverse proxy that handles auth, you can leave `APP_SECRET` empty, but **do not expose the port publicly without it**.

---

## Cache

Responses from Seerr and TMDB are cached in memory for `CACHE_TTL_SECONDS` (default 5 minutes).
The filter bar shows a small cache indicator with the time remaining.
Click the **↻ Refresh** button (top-right of the filter bar) to flush the cache and force a full re-fetch immediately.

Set `CACHE_TTL_SECONDS=0` to disable caching — useful during development or for small instances.

---

## API reference

All endpoints (except `/api/auth-required`) require `Authorization: Bearer <APP_SECRET>` when `APP_SECRET` is configured.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/auth-required` | Public — returns `{"required": true/false}` so the UI knows whether to show the login screen. |
| `GET` | `/api/status` | Health check — returns Seerr connectivity, version, and TMDB connectivity. |
| `GET` | `/api/requests` | All Seerr requests plus orphaned deleted media records, enriched with TMDB metadata and flag reasons. |
| `POST` | `/api/rerequest/{id}` | Re-request a single item by Seerr request ID. Deletes the old request and media record, then submits a fresh one. |
| `POST` | `/api/rerequest/orphan` | Re-request an orphaned media record (no existing request). Body: `{seerrMediaId, tmdbId, mediaType}`. |
| `POST` | `/api/rerequest/batch` | Batch re-request. Body: `{ids: int[], orphans: [{seerrMediaId, tmdbId, mediaType}]}`. |
| `GET` | `/api/watchlist/comparison` | Fetches the Plex watchlist for the API-key owner and compares it against Seerr requests and media. Returns three buckets: `watchlistOnly`, `alreadyRequested`, `available`, plus summary stats. |
| `POST` | `/api/watchlist/request` | Submit Seerr requests for watchlist items. Body: `{items: [{tmdbId, mediaType}]}`. |
| `GET` | `/api/cache/status` | Returns current cache entries and their remaining TTL in seconds. |
| `DELETE` | `/api/cache` | Flush the entire server-side cache. |

---

## TMDB API key versions

Both TMDB key formats are supported:

- **v3 string key** — passed as the `api_key` query parameter (classic format, found in TMDB account settings under API → API Key).
- **v4 read-access token** — a JWT starting with `eyJ`. Passed as an `Authorization: Bearer` header automatically. Found in TMDB account settings under API → Read Access Token.

Either value works in the `TMDB_API_KEY` environment variable.

---

## Upgrading / pulling a new image

```bash
docker compose pull
docker compose up -d
```

---

## Building from source

```bash
docker build -t seerr-manager .
```

The `Dockerfile` is a multi-stage build: Node 22 compiles the Svelte frontend into `backend/static/`, then a Python 3.12 slim image installs the backend dependencies and runs Uvicorn on port `8765`.
