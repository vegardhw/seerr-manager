# seerr-manager — Agent Context

## Project Purpose
A self-hosted web dashboard for managing **Overseerr / Jellyseerr** requests.
It surfaces stuck, flagged, or deleted media and lets the user re-request individual
items or a whole batch in one click, fixing common edge-cases that Seerr itself
does not handle (e.g. Watchlist imports that land with only a TVDB ID, requests
permanently stuck in PROCESSING, media deleted from the library with no active
request).

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12, FastAPI, httpx (async), Pydantic v2, Uvicorn |
| Frontend | Svelte 4, Vite 5 (SPA, no framework router) |
| Container | Docker multi-stage (Node build → Python runtime), port **8765** |
| CI/CD | GitHub Actions → `ghcr.io/vegardhw/seerr-manager:latest` on PR merge to `main` |

---

## Repository Layout

```
seerr-manager/
├── backend/
│   ├── main.py            # All backend logic — FastAPI app + Seerr/TMDB calls
│   └── requirements.txt   # fastapi, uvicorn, httpx, pydantic
├── frontend/
│   ├── src/
│   │   ├── App.svelte         # Root component — state, filtering, actions
│   │   └── lib/
│   │       ├── api.js          # Thin fetch wrapper + API surface
│   │       ├── CardGrid.svelte # Responsive grid, forwards card events
│   │       ├── DetailDrawer.svelte # Side/bottom sheet with full details + re-request
│   │       ├── FilterBar.svelte    # Sticky header: search, filters, batch actions
│   │       ├── MediaCard.svelte    # Single card with poster, badges, IDs
│   │       └── Toast.svelte        # Global toast notifications
│   ├── vite.config.js     # Builds into ../backend/static; dev proxies /api → :8765
│   └── package.json
├── Dockerfile             # Multi-stage: node:22-alpine build → python:3.12-slim
├── docker-compose.yml
├── .env.example
└── .github/workflows/docker.yml
```

---

## Environment Variables (all required)

| Variable | Description |
|----------|-------------|
| `SEERR_URL` | Base URL of Overseerr or Jellyseerr (no trailing slash) |
| `SEERR_API_KEY` | Seerr API key |
| `TMDB_API_KEY` | TMDB v3 API key (for poster images and metadata) |

The backend raises `RuntimeError` at startup if any are missing.

---

## Key Backend Concepts (`backend/main.py`)

### Request Status Codes (Seerr)
`1=PENDING, 2=APPROVED, 3=DECLINED, 4=AVAILABLE, 5=PARTIALLY_AVAILABLE`

### Media Status Codes (Seerr)
`1=UNKNOWN, 2=PENDING, 3=PROCESSING, 4=PARTIALLY_AVAILABLE, 5=AVAILABLE, 7=DELETED`

### Flagging Logic (`is_flagged`)
An item is **flagged** (shown with ⚑) when any of the following are true:
- Missing TMDB ID
- TV or movie request with only a TVDB ID (Watchlist import bug)
- Media status is `DELETED` (7)
- Media stuck in PENDING (2) or PROCESSING (3) for **> 7 days**

### Orphan Detection
Media records with `status == 7` (DELETED) that have **no active request** are
surfaced as synthetic "orphan" items. They are identified in `GET /api/requests`
by cross-referencing all media records against the set of request media IDs.

### Re-request Flow
1. `GET /api/v1/request/{id}` — fetch full request to get TMDB ID, type, seasons
2. `DELETE /api/v1/request/{id}` — remove the stale request
3. `DELETE /api/v1/media/{mediaInternalId}` — purge Seerr's cached media record
   so the new request gets a clean TMDB lookup
4. `POST /api/v1/request` — submit a fresh request with `{mediaType, mediaId, seasons?}`

For **orphans** (no request, just a media record), steps 2 is skipped.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/requests` | All requests + orphaned deleted media, enriched with TMDB metadata |
| POST | `/api/rerequest/{id}` | Re-request a single item by Seerr request ID |
| POST | `/api/rerequest/orphan` | Re-request an orphan (body: `seerrMediaId`, `tmdbId`, `mediaType`) |
| POST | `/api/rerequest/batch` | Batch re-request; body: `{ids: int[], orphans: [...]}` |
| GET | `/api/status` | Health check — Seerr + TMDB connectivity |

The built Svelte app is served as static files from `/app/static` (mounted at `/`).

---

## Key Frontend Concepts

### Item Keys
Each item gets a stable `_key`: `String(id)` for normal requests, `"o-{media.id}"`
for orphans. Used for selection set management.

### Selection Model
`selected` is a `Set<string>` of `_key` values in `App.svelte`.
`selectedInView` is the intersection of `selected` and the currently filtered list —
batch actions only operate on visible items.

### Filter State (all in `App.svelte`)
- `filter` — `'all' | 'movie' | 'tv'`
- `flaggedOnly` — boolean
- `mediaStatusFilter` — `'all' | 'DELETED' | 'PROCESSING' | ...`
- `searchQuery` — title substring match (case-insensitive)

### Toast API
`Toast.svelte` exposes `addToast(message, type, duration)` and `removeToast(id)`.
`type` is `'info' | 'success' | 'error' | 'loading'`. Duration `0` = persistent.

---

## Known Issues / Gotchas

### Bug: `DELETED` missing from `DetailDrawer` status colour map
`MediaCard.svelte` has `DELETED: '#ef4444'` in `MEDIA_STATUS_COLOR` but
`DetailDrawer.svelte` does not — deleted items render with the fallback grey
(`#64748b`) in the drawer instead of red. Fix: add the entry to the map.

### Batch re-requests are sequential, not concurrent
`/api/rerequest/batch` iterates `body.ids` and `body.orphans` in serial `for`
loops. For large batches this is slow. Consider wrapping each operation in a
`asyncio.create_task` and gathering with a semaphore.

### Delete response not checked before proceeding
In `_do_rerequest`, `client.delete(...)` on both the request and the media record
is called without `.raise_for_status()`. A failed delete is silently ignored and
the code still proceeds to POST the new request, which can result in duplicates or
stale media records persisting.

### Stuck-request threshold is hardcoded
The 7-day threshold in `is_flagged` is a magic number. Consider making it
configurable via an env var (e.g. `STUCK_DAYS_THRESHOLD`).

### No list virtualisation
`CardGrid.svelte` renders all filtered cards at once. For large Seerr instances
with hundreds of requests, this can be sluggish. A windowed/virtual list would
help.

### CI only builds `linux/amd64`
`docker.yml` and `docker-compose.yml` are pinned to `linux/amd64`. Add
`linux/arm64` to the build matrix for Raspberry Pi / ARM NAS users.

### No `package-lock.json` committed
The Dockerfile copies `package-lock.json*` (optional glob). Without a lockfile,
`npm install` in CI resolves latest minor versions, which can cause non-reproducible
frontend builds. Commit the lockfile.

---

## Local Development

```bash
# Backend (hot-reload)
cd backend && pip install -r requirements.txt
SEERR_URL=... SEERR_API_KEY=... TMDB_API_KEY=... uvicorn main:app --reload --port 8765

# Frontend (separate terminal — proxies /api to :8765)
cd frontend && npm install && npm run dev
```

### Docker
```bash
cp .env.example .env   # fill in values
docker compose up -d --build
# Open http://localhost:8765
```

---

## Coding Conventions
- Backend: async-first (`httpx.AsyncClient`, `asyncio.gather` for parallel calls)
- Frontend: Svelte 4 component events via `createEventDispatcher`; no stores used —
  all state lives in `App.svelte` and flows down as props / up as events
- Dark theme only; colour palette is Tailwind slate/indigo/green/red tokens
  (`#0d1117` bg, `#6366f1` primary accent)
- No linter/formatter config committed — follow existing style (2-space indent,
  single quotes in JS, double quotes in Python strings where practical)
