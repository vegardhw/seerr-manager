import asyncio
import hmac
import logging
import os
import time
import warnings
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("seerr_manager")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEERR_URL = os.getenv("SEERR_URL", "").rstrip("/")
SEERR_API_KEY = os.getenv("SEERR_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

# Optional Arr service configuration - both default to empty (feature disabled)
RADARR_URL = os.getenv("RADARR_URL", "").rstrip("/")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "")
SONARR_URL = os.getenv("SONARR_URL", "").rstrip("/")
SONARR_API_KEY = os.getenv("SONARR_API_KEY", "")

# Optional shared secret - if set, all /api/* routes require:
#   Authorization: Bearer <APP_SECRET>
# Strongly recommended for any deployment reachable beyond localhost.
APP_SECRET = os.getenv("APP_SECRET", "")

# TMDB auth: v3 keys are short hex strings; v4 read-access tokens are JWTs
# (start with "eyJ"). The v3 endpoint accepts both, but JWTs must be sent
# as a Bearer header - they are not valid as ?api_key= query params.
_TMDB_IS_BEARER = TMDB_API_KEY.startswith("eyJ")

# Cache TTL in seconds - configurable via env, defaults to 5 minutes.
# Set to 0 to disable caching (always re-fetch from Seerr/TMDB).
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

_missing = [name for name, val in [
    ("SEERR_URL", SEERR_URL),
    ("SEERR_API_KEY", SEERR_API_KEY),
    ("TMDB_API_KEY", TMDB_API_KEY),
] if not val]

# Validate SEERR_URL is a proper http(s) URL (guards against SSRF via env injection).
if SEERR_URL:
    _parsed = urlparse(SEERR_URL)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        raise RuntimeError(
            f"SEERR_URL must be a valid http(s) URL, got: {SEERR_URL!r}"
        )

for _arr_var, _arr_val in [("RADARR_URL", RADARR_URL), ("SONARR_URL", SONARR_URL)]:
    if _arr_val:
        _p = urlparse(_arr_val)
        if _p.scheme not in ("http", "https") or not _p.netloc:
            raise RuntimeError(
                f"{_arr_var} must be a valid http(s) URL, got: {_arr_val!r}"
            )

# Warn about partial arr configuration (URL without key or vice-versa)
for _svc, _url, _key in [
    ("Radarr", RADARR_URL, RADARR_API_KEY),
    ("Sonarr", SONARR_URL, SONARR_API_KEY),
]:
    if bool(_url) != bool(_key):
        warnings.warn(
            f"{_svc} is partially configured - both {_svc.upper()}_URL and "
            f"{_svc.upper()}_API_KEY must be set. Library view will be disabled for {_svc}.",
            RuntimeWarning,
            stacklevel=1,
        )

# In dev mode (no creds yet) we warn rather than crash so the frontend can
# still boot and be inspected.  Every API endpoint guards itself.
if _missing:
    warnings.warn(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "API endpoints will return 503 until all variables are set.",
        RuntimeWarning,
        stacklevel=1,
    )

if not APP_SECRET:
    warnings.warn(
        "APP_SECRET is not set. The /api/* endpoints are unprotected. "
        "Set APP_SECRET to a strong random string to enable bearer-token auth.",
        RuntimeWarning,
        stacklevel=1,
    )

# ---------------------------------------------------------------------------
# FastAPI app + middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="Seerr Manager")

# CORS: deny cross-origin requests by default.
# Set CORS_ORIGINS env var to a comma-separated list of allowed origins
# (e.g. "http://localhost:5173") only if you need cross-origin access.
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
):
    """Require a valid Bearer token when APP_SECRET is configured."""
    if not APP_SECRET:
        return  # auth disabled - open deployment
    if creds is None or not hmac.compare_digest(creds.credentials, APP_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _require_credentials():
    """Raise 503 if any credential is not configured yet."""
    if _missing:
        raise HTTPException(
            status_code=503,
            detail="Server not configured - one or more required environment variables are missing.",
        )


def seerr_headers() -> dict:
    return {"X-Api-Key": SEERR_API_KEY}


def tmdb_headers() -> dict:
    """Return the correct auth header for TMDB (Bearer for v4 JWT tokens)."""
    if _TMDB_IS_BEARER:
        return {"Authorization": f"Bearer {TMDB_API_KEY}"}
    return {}


def tmdb_params(**kwargs) -> dict:
    """Return query params for TMDB - api_key only needed for v3 string keys."""
    if _TMDB_IS_BEARER:
        return {**kwargs}
    return {"api_key": TMDB_API_KEY, **kwargs}


def radarr_headers() -> dict:
    return {"X-Api-Key": RADARR_API_KEY}


def sonarr_headers() -> dict:
    return {"X-Api-Key": SONARR_API_KEY}


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

REQUEST_STATUS = {
    1: "PENDING",
    2: "APPROVED",
    3: "DECLINED",
    4: "AVAILABLE",
    5: "PARTIALLY_AVAILABLE",
}

MEDIA_STATUS = {
    1: "UNKNOWN",
    2: "PENDING",
    3: "PROCESSING",
    4: "PARTIALLY_AVAILABLE",
    5: "AVAILABLE",
    7: "DELETED",
}


# ---------------------------------------------------------------------------
# In-memory TTL cache
# ---------------------------------------------------------------------------
# Structure: key -> (expires_at: float, data: any)
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = asyncio.Lock()


async def cache_get(key: str):
    """Return cached value if still fresh, else None."""
    if CACHE_TTL <= 0:
        return None
    async with _cache_lock:
        entry = _cache.get(key)
        if entry and time.monotonic() < entry[0]:
            return entry[1]
        return None


async def cache_set(key: str, data):
    """Store data in cache with the configured TTL."""
    if CACHE_TTL <= 0:
        return
    async with _cache_lock:
        _cache[key] = (time.monotonic() + CACHE_TTL, data)


async def cache_invalidate(*keys: str):
    """Evict one or more keys; pass no args to flush everything."""
    async with _cache_lock:
        if keys:
            for k in keys:
                _cache.pop(k, None)
        else:
            _cache.clear()


# ---------------------------------------------------------------------------
# Flagging logic
# ---------------------------------------------------------------------------

def is_flagged(item: dict) -> tuple[bool, list[str]]:
    media = item.get("media", {})
    tmdb_id = media.get("tmdbId")
    tvdb_id = media.get("tvdbId")
    media_type = item.get("type", "")
    reasons = []

    if not tmdb_id:
        if media_type == "tv" and tvdb_id:
            reasons.append("TV request with only TVDB ID (Watchlist bug)")
        elif media_type == "movie" and tvdb_id:
            reasons.append("Movie request with only TVDB ID")
        else:
            reasons.append("Missing TMDB ID")

    media_status = media.get("status")
    if media_status == 7:
        reasons.append("Media deleted from library - needs re-request")
    elif media_status in (2, 3):
        created_at = item.get("createdAt", "")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created).days
                if age_days > 7:
                    reasons.append(f"Stuck {MEDIA_STATUS.get(media_status, 'PENDING')} for {age_days} days")
            except Exception:
                pass

    return bool(reasons), reasons


# ---------------------------------------------------------------------------
# TMDB enrichment (requests view)
# ---------------------------------------------------------------------------

async def enrich_with_tmdb(client: httpx.AsyncClient, item: dict) -> dict:
    media = item.get("media", {})
    tmdb_id = media.get("tmdbId")
    tvdb_id = media.get("tvdbId")
    media_type = item.get("type", "movie")

    poster_path = title = year = overview = None
    resolved_tmdb_id = tmdb_id

    try:
        if tmdb_id:
            endpoint = "movie" if media_type == "movie" else "tv"
            resp = await client.get(
                f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}",
                params=tmdb_params(),
                headers=tmdb_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                poster_path = data.get("poster_path")
                if media_type == "movie":
                    title = data.get("title") or data.get("original_title")
                    date = data.get("release_date", "")
                else:
                    title = data.get("name") or data.get("original_name")
                    date = data.get("first_air_date", "")
                year = date[:4] if date else None
                overview = data.get("overview")

        elif tvdb_id:
            resp = await client.get(
                f"https://api.themoviedb.org/3/find/{tvdb_id}",
                params=tmdb_params(external_source="tvdb_id"),
                headers=tmdb_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("tv_results", []) if media_type == "tv" else data.get("movie_results", [])
                if results:
                    r = results[0]
                    poster_path = r.get("poster_path")
                    title = r.get("name") or r.get("title")
                    date = r.get("first_air_date") or r.get("release_date", "")
                    year = date[:4] if date else None
                    overview = r.get("overview")
                    resolved_tmdb_id = r.get("id")
    except Exception:
        pass

    flagged, flag_reasons = is_flagged(item)

    return {
        **item,
        "posterUrl": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
        "title": title or "Unknown Title",
        "year": year,
        "overview": overview,
        "flagged": flagged,
        "flagReasons": flag_reasons,
        "resolvedTmdbId": resolved_tmdb_id,
        "statusLabel": REQUEST_STATUS.get(item.get("status"), "UNKNOWN"),
        "mediaStatusLabel": MEDIA_STATUS.get(media.get("status"), "UNKNOWN"),
    }


# ---------------------------------------------------------------------------
# TMDB enrichment (watchlist view)
# ---------------------------------------------------------------------------

async def enrich_watchlist_item(client: httpx.AsyncClient, item: dict) -> dict:
    """Enrich a categorised watchlist comparison item with TMDB poster + metadata."""
    tmdb_id = item.get("tmdbId")
    media_type = item.get("type", "movie")

    poster_path = title = year = overview = None

    try:
        if tmdb_id:
            endpoint = "movie" if media_type == "movie" else "tv"
            resp = await client.get(
                f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}",
                params=tmdb_params(),
                headers=tmdb_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                poster_path = data.get("poster_path")
                if media_type == "movie":
                    title = data.get("title") or data.get("original_title")
                    date_str = data.get("release_date", "")
                else:
                    title = data.get("name") or data.get("original_name")
                    date_str = data.get("first_air_date", "")
                year = date_str[:4] if date_str else None
                overview = data.get("overview")
    except Exception:
        pass

    # Determine best request to surface (approved > available > pending > others)
    _STATUS_PRIORITY = {2: 0, 4: 1, 5: 2, 1: 3, 3: 4}
    requests = item.get("seerrRequests", [])
    best_request = None
    if requests:
        best_request = sorted(
            requests,
            key=lambda r: _STATUS_PRIORITY.get(r.get("status", 99), 99),
        )[0]

    media = item.get("seerrMedia")
    media_status_num = media.get("status") if media else None

    return {
        "tmdbId": tmdb_id,
        "tvdbId": item.get("tvdbId"),
        "type": media_type,
        "title": title or item.get("title") or "Unknown Title",
        "year": year,
        "overview": overview,
        "posterUrl": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
        "ratingKey": item.get("ratingKey"),
        "requestStatus": REQUEST_STATUS.get(best_request.get("status")) if best_request else None,
        "requestStatusNum": best_request.get("status") if best_request else None,
        "requestId": best_request.get("id") if best_request else None,
        "mediaStatus": MEDIA_STATUS.get(media_status_num) if media_status_num else None,
        "mediaStatusNum": media_status_num,
        "requestCount": len(requests),
        "seerrMediaId": media.get("id") if media else None,
    }


# ---------------------------------------------------------------------------
# Seerr pagination helper
# ---------------------------------------------------------------------------

async def fetch_all_pages(client: httpx.AsyncClient, path: str, params: dict | None = None) -> list:
    results, skip, take = [], 0, 50
    extra = params or {}
    while True:
        resp = await client.get(
            f"{SEERR_URL}{path}",
            headers=seerr_headers(),
            params={"take": take, "skip": skip, **extra},
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("results", [])
        results.extend(batch)
        if len(results) >= data.get("pageInfo", {}).get("results", 0) or not batch:
            break
        skip += take
    return results


async def fetch_watchlist(client: httpx.AsyncClient, user_id: int) -> list:
    """Fetch all Plex watchlist items for a Seerr user.

    Overseerr/Seerr 3.x uses ?page=N pagination (not take/skip) for the
    watchlist endpoint.  Top-level response keys: page, totalPages,
    totalResults, results.
    """
    results, page = [], 1
    while True:
        resp = await client.get(
            f"{SEERR_URL}/api/v1/user/{user_id}/watchlist",
            headers=seerr_headers(),
            params={"page": page},
        )
        # 404/501 = endpoint not available or watchlist not configured
        if resp.status_code in (404, 501):
            break
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(batch)
        if page >= data.get("totalPages", 1):
            break
        page += 1
    return results


# ---------------------------------------------------------------------------
# Orphan helper
# ---------------------------------------------------------------------------

def make_orphan_item(media: dict) -> dict:
    """Wrap a raw Seerr media record as a synthetic request-like item for the frontend."""
    return {
        "id": None,
        "orphan": True,
        "status": None,
        "createdAt": media.get("createdAt"),
        "updatedAt": media.get("updatedAt"),
        "type": media.get("mediaType", "movie"),
        "seasons": [],
        "requestedBy": None,
        "media": media,
    }


# ---------------------------------------------------------------------------
# Arr service helpers (Radarr + Sonarr)
# ---------------------------------------------------------------------------

async def _empty() -> list:
    """No-op coroutine returning [] - used when an arr service is not configured."""
    return []


async def fetch_radarr_movies(client: httpx.AsyncClient) -> list:
    """Fetch all movies from Radarr. Returns [] on error so Sonarr still works."""
    try:
        resp = await client.get(f"{RADARR_URL}/api/v3/movie", headers=radarr_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Could not fetch Radarr movies: %s", exc)
        return []


async def fetch_sonarr_series(client: httpx.AsyncClient) -> list:
    """Fetch all series from Sonarr. Returns [] on error so Radarr still works."""
    try:
        resp = await client.get(f"{SONARR_URL}/api/v3/series", headers=sonarr_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Could not fetch Sonarr series: %s", exc)
        return []


def _arr_poster_url(images: list) -> str | None:
    """Extract the remote TMDB poster URL from a Radarr/Sonarr images array.

    Only returns URLs with an explicit http/https scheme so that a compromised
    or misconfigured arr instance cannot inject data:/javascript:/file:// URIs
    into the frontend <img src> attribute.
    """
    for img in images:
        if img.get("coverType") != "poster":
            continue
        url = img.get("remoteUrl")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    return None


# Maximum number of Sonarr series for which we will fire TMDB /find fallback
# requests.  Protects against unbounded API call storms on very large libraries
# and keeps total latency well within the httpx client timeout.
_MAX_TMDB_FALLBACK_LOOKUPS = 500


def normalize_radarr_movie(m: dict) -> dict:
    # Cast tmdbId to int so it matches the integer keys in the Seerr cross-
    # reference sets.  A string "12345" != integer 12345 in a Python set lookup.
    _raw_tmdb = m.get("tmdbId")
    try:
        _tmdb_id: int | None = int(_raw_tmdb) if _raw_tmdb else None
    except (TypeError, ValueError):
        _tmdb_id = None

    return {
        "libraryId": m.get("id"),
        "tmdbId": _tmdb_id,
        "imdbId": m.get("imdbId") or None,
        "title": m.get("title") or m.get("originalTitle") or "Unknown",
        "year": m.get("year") or None,
        "overview": m.get("overview") or None,
        "posterUrl": _arr_poster_url(m.get("images", [])),
        "hasFile": bool(m.get("hasFile")),
        "sizeOnDisk": m.get("sizeOnDisk") or 0,
        "status": m.get("status"),   # released / announced / inCinemas / tba / deleted
        "monitored": bool(m.get("monitored")),
        "genres": m.get("genres") or [],
        "source": "radarr",
        "type": "movie",
    }


def normalize_sonarr_series(s: dict, resolved_tmdb_id: int | None = None) -> dict:
    stats = s.get("statistics") or {}
    tmdb_id = s.get("tmdbId") or resolved_tmdb_id or None
    return {
        "libraryId": s.get("id"),
        "tmdbId": int(tmdb_id) if tmdb_id else None,
        "tvdbId": s.get("tvdbId") or None,
        "title": s.get("title") or "Unknown",
        "year": s.get("year") or None,
        "overview": s.get("overview") or None,
        "posterUrl": _arr_poster_url(s.get("images", [])),
        "hasFile": (stats.get("episodeFileCount", 0) > 0),
        "sizeOnDisk": stats.get("sizeOnDisk") or 0,
        "status": s.get("status"),   # continuing / ended
        "monitored": bool(s.get("monitored")),
        "genres": s.get("genres") or [],
        "network": s.get("network") or None,
        "seasonCount": stats.get("seasonCount") or 0,
        "totalEpisodeCount": stats.get("totalEpisodeCount") or 0,
        "episodeFileCount": stats.get("episodeFileCount") or 0,
        "source": "sonarr",
        "type": "tv",
    }


async def resolve_sonarr_tmdb_ids(
    client: httpx.AsyncClient,
    series: list[dict],
) -> dict[int, int]:
    """Batch-resolve TVDB IDs → TMDB IDs for Sonarr series that have no tmdbId.

    Safety measures:
    - tvdbId values are validated and cast to int before being interpolated into
      the TMDB URL path, preventing path-injection from malformed Sonarr data.
    - Total lookups are capped at _MAX_TMDB_FALLBACK_LOOKUPS to prevent
      unbounded API call storms on large libraries exceeding the request timeout.
    - A semaphore limits concurrency to stay within TMDB rate limits.
    """
    # Validate and cast tvdbId to int; skip any non-integer values.
    valid: list[int] = []
    for s in series:
        raw = s.get("tvdbId")
        if raw is None:
            continue
        try:
            valid.append(int(raw))
        except (TypeError, ValueError):
            logger.warning("Sonarr series has non-integer tvdbId %r — skipping TMDB lookup", raw)

    if len(valid) > _MAX_TMDB_FALLBACK_LOOKUPS:
        logger.warning(
            "Sonarr returned %d series without tmdbId; capping TMDB fallback "
            "lookups at %d to avoid request timeout.",
            len(valid), _MAX_TMDB_FALLBACK_LOOKUPS,
        )
        valid = valid[:_MAX_TMDB_FALLBACK_LOOKUPS]

    sem = asyncio.Semaphore(10)

    async def _one(tvdb_id: int) -> tuple[int, int | None]:
        async with sem:
            try:
                resp = await client.get(
                    # tvdb_id is guaranteed int — safe to interpolate in path.
                    f"https://api.themoviedb.org/3/find/{tvdb_id}",
                    params=tmdb_params(external_source="tvdb_id"),
                    headers=tmdb_headers(),
                )
                if resp.status_code == 200:
                    tv_results = resp.json().get("tv_results", [])
                    if tv_results:
                        return tvdb_id, tv_results[0].get("id")
            except Exception:
                pass
            return tvdb_id, None

    pairs = await asyncio.gather(*[_one(tvdb_id) for tvdb_id in valid])
    return {tvdb_id: tmdb_id for tvdb_id, tmdb_id in pairs if tmdb_id}


# ---------------------------------------------------------------------------
# Endpoints - Requests view
# ---------------------------------------------------------------------------

@app.get("/api/requests")
async def get_requests(_: None = Depends(require_auth)):
    _require_credentials()
    cached = await cache_get("requests")
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=60) as client:
        all_requests, all_media = await asyncio.gather(
            fetch_all_pages(client, "/api/v1/request", {"sort": "added"}),
            fetch_all_pages(client, "/api/v1/media"),
        )

        requested_media_ids = {r["media"]["id"] for r in all_requests}
        orphaned = [
            make_orphan_item(m)
            for m in all_media
            if m.get("status") == 7 and m["id"] not in requested_media_ids
        ]

        combined = all_requests + orphaned
        enriched = await asyncio.gather(
            *[enrich_with_tmdb(client, item) for item in combined]
        )

    result = list(enriched)
    await cache_set("requests", result)
    return result


# ---------------------------------------------------------------------------
# Re-request helpers
# ---------------------------------------------------------------------------

async def _do_rerequest(client: httpx.AsyncClient, request_id: int) -> dict:
    resp = await client.get(
        f"{SEERR_URL}/api/v1/request/{request_id}",
        headers=seerr_headers(),
    )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    resp.raise_for_status()
    req_data = resp.json()

    media = req_data.get("media", {})
    tmdb_id = media.get("tmdbId")
    media_type = req_data.get("type", "movie")
    seasons = req_data.get("seasons", [])

    if not tmdb_id:
        raise HTTPException(
            status_code=422,
            detail=f"Request {request_id} has no TMDB ID - resolve the ID mismatch first",
        )

    del_req = await client.delete(
        f"{SEERR_URL}/api/v1/request/{request_id}",
        headers=seerr_headers(),
    )
    del_req.raise_for_status()

    media_internal_id = media.get("id")
    if media_internal_id:
        del_media = await client.delete(
            f"{SEERR_URL}/api/v1/media/{media_internal_id}",
            headers=seerr_headers(),
        )
        del_media.raise_for_status()

    payload: dict = {"mediaType": media_type, "mediaId": tmdb_id}
    if media_type == "tv" and seasons:
        payload["seasons"] = [
            s["seasonNumber"] for s in seasons if s.get("seasonNumber") is not None
        ]

    new_resp = await client.post(
        f"{SEERR_URL}/api/v1/request",
        headers=seerr_headers(),
        json=payload,
    )
    new_resp.raise_for_status()
    return new_resp.json()


async def _do_request_orphan(client: httpx.AsyncClient, seerr_media_id: int, tmdb_id: int, media_type: str) -> dict:
    """Request an orphaned deleted media item that has no existing request."""
    if not tmdb_id:
        raise HTTPException(status_code=422, detail="No TMDB ID available for this media item")

    del_media = await client.delete(
        f"{SEERR_URL}/api/v1/media/{seerr_media_id}",
        headers=seerr_headers(),
    )
    del_media.raise_for_status()

    new_resp = await client.post(
        f"{SEERR_URL}/api/v1/request",
        headers=seerr_headers(),
        json={"mediaType": media_type, "mediaId": tmdb_id},
    )
    new_resp.raise_for_status()
    return new_resp.json()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

MediaType = Literal["movie", "tv"]


class OrphanBody(BaseModel):
    seerrMediaId: int
    tmdbId: int
    mediaType: MediaType


class BatchOrphan(BaseModel):
    seerrMediaId: int
    tmdbId: int
    mediaType: MediaType


class BatchBody(BaseModel):
    ids: list[int] = []
    orphans: list[BatchOrphan] = []


class ResetOrphanBody(BaseModel):
    seerrMediaId: int


class BatchResetBody(BaseModel):
    ids: list[int] = []
    orphanMediaIds: list[int] = []


class WatchlistItem(BaseModel):
    tmdbId: int
    mediaType: MediaType


class WatchlistRequestBody(BaseModel):
    items: list[WatchlistItem]


# ---------------------------------------------------------------------------
# Reset helpers  (delete request + media record, no new request submitted)
# ---------------------------------------------------------------------------

async def _do_reset(client: httpx.AsyncClient, request_id: int) -> None:
    """Delete a request and its associated media record without re-requesting."""
    resp = await client.get(
        f"{SEERR_URL}/api/v1/request/{request_id}",
        headers=seerr_headers(),
    )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    resp.raise_for_status()
    req_data = resp.json()
    media = req_data.get("media", {})

    del_req = await client.delete(
        f"{SEERR_URL}/api/v1/request/{request_id}",
        headers=seerr_headers(),
    )
    del_req.raise_for_status()

    media_internal_id = media.get("id")
    if media_internal_id:
        del_media = await client.delete(
            f"{SEERR_URL}/api/v1/media/{media_internal_id}",
            headers=seerr_headers(),
        )
        del_media.raise_for_status()


async def _do_reset_orphan(client: httpx.AsyncClient, seerr_media_id: int) -> None:
    """Delete just the media record for an orphan (no request to remove)."""
    del_media = await client.delete(
        f"{SEERR_URL}/api/v1/media/{seerr_media_id}",
        headers=seerr_headers(),
    )
    del_media.raise_for_status()


# ---------------------------------------------------------------------------
# Endpoints - Re-request actions
# ---------------------------------------------------------------------------

@app.post("/api/rerequest/batch")
async def rerequest_batch(body: BatchBody, _: None = Depends(require_auth)):
    _require_credentials()
    results = []
    errors = []

    async with httpx.AsyncClient(timeout=60) as client:
        for request_id in body.ids:
            try:
                new_req = await _do_rerequest(client, request_id)
                results.append({"id": request_id, "success": True, "newId": new_req.get("id")})
            except HTTPException as exc:
                errors.append({"id": request_id, "error": exc.detail})
            except Exception as exc:
                logger.error("Unexpected error re-requesting id=%s: %s", request_id, exc)
                errors.append({"id": request_id, "error": "Internal error"})

        for orphan in body.orphans:
            try:
                new_req = await _do_request_orphan(
                    client, orphan.seerrMediaId, orphan.tmdbId, orphan.mediaType
                )
                results.append({"seerrMediaId": orphan.seerrMediaId, "success": True, "newId": new_req.get("id")})
            except HTTPException as exc:
                errors.append({"seerrMediaId": orphan.seerrMediaId, "error": exc.detail})
            except Exception as exc:
                logger.error("Unexpected error re-requesting orphan mediaId=%s: %s", orphan.seerrMediaId, exc)
                errors.append({"seerrMediaId": orphan.seerrMediaId, "error": "Internal error"})

    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"results": results, "errors": errors}


@app.post("/api/rerequest/orphan")
async def rerequest_orphan(body: OrphanBody, _: None = Depends(require_auth)):
    _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        new_req = await _do_request_orphan(
            client, body.seerrMediaId, body.tmdbId, body.mediaType
        )
    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"success": True, "newRequest": new_req}


@app.post("/api/rerequest/{request_id}")
async def rerequest_single(request_id: int, _: None = Depends(require_auth)):
    _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        new_req = await _do_rerequest(client, request_id)
    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"success": True, "newRequest": new_req}


# ---------------------------------------------------------------------------
# Endpoints - Reset actions  (purge without re-requesting)
# ---------------------------------------------------------------------------

@app.post("/api/reset/batch")
async def reset_batch(body: BatchResetBody, _: None = Depends(require_auth)):
    _require_credentials()
    results = []
    errors = []

    async with httpx.AsyncClient(timeout=60) as client:
        for request_id in body.ids:
            try:
                await _do_reset(client, request_id)
                results.append({"id": request_id, "success": True})
            except HTTPException as exc:
                errors.append({"id": request_id, "error": exc.detail})
            except Exception as exc:
                logger.error("Unexpected error resetting id=%s: %s", request_id, exc)
                errors.append({"id": request_id, "error": "Internal error"})

        for media_id in body.orphanMediaIds:
            try:
                await _do_reset_orphan(client, media_id)
                results.append({"seerrMediaId": media_id, "success": True})
            except HTTPException as exc:
                errors.append({"seerrMediaId": media_id, "error": exc.detail})
            except Exception as exc:
                logger.error("Unexpected error resetting orphan mediaId=%s: %s", media_id, exc)
                errors.append({"seerrMediaId": media_id, "error": "Internal error"})

    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"results": results, "errors": errors}


@app.post("/api/reset/orphan")
async def reset_orphan(body: ResetOrphanBody, _: None = Depends(require_auth)):
    _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        await _do_reset_orphan(client, body.seerrMediaId)
    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"success": True}


@app.post("/api/reset/{request_id}")
async def reset_single(request_id: int, _: None = Depends(require_auth)):
    _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        await _do_reset(client, request_id)
    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"success": True}


# ---------------------------------------------------------------------------
# Endpoints - Watchlist comparison
# ---------------------------------------------------------------------------

@app.get("/api/watchlist/comparison")
async def get_watchlist_comparison(_: None = Depends(require_auth)):
    _require_credentials()
    cached = await cache_get("watchlist_comparison")
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=60) as client:
        # Identify the current API-key owner so we can fetch their watchlist
        try:
            me_resp = await client.get(
                f"{SEERR_URL}/api/v1/auth/me",
                headers=seerr_headers(),
            )
            me_resp.raise_for_status()
            me = me_resp.json()
            user_id = me["id"]
        except Exception as exc:
            logger.error("Cannot identify Seerr user: %s", exc)
            raise HTTPException(status_code=502, detail="Cannot reach Seerr - check SEERR_URL and SEERR_API_KEY.")

        # Parallel fetch: watchlist, all requests, all media
        try:
            watchlist_raw, all_requests, all_media = await asyncio.gather(
                fetch_watchlist(client, user_id),
                fetch_all_pages(client, "/api/v1/request", {"sort": "added"}),
                fetch_all_pages(client, "/api/v1/media"),
            )
        except Exception as exc:
            logger.error("Failed to fetch data from Seerr: %s", exc)
            raise HTTPException(status_code=502, detail="Failed to fetch data from Seerr.")

        # Build TMDB ID lookup maps
        requests_by_tmdb: dict[int, list] = {}
        for req in all_requests:
            tid = req.get("media", {}).get("tmdbId")
            if tid:
                requests_by_tmdb.setdefault(tid, []).append(req)

        media_by_tmdb: dict[int, dict] = {}
        for m in all_media:
            tid = m.get("tmdbId")
            if tid:
                media_by_tmdb[tid] = m

        # Build the set of watchlist TMDB IDs for reverse lookup
        watchlist_tmdb_ids: set[int] = {
            w.get("tmdbId") for w in watchlist_raw if w.get("tmdbId")
        }

        # Categorise watchlist items into three buckets
        watchlist_only: list[dict] = []
        already_requested: list[dict] = []
        available: list[dict] = []

        for w in watchlist_raw:
            tid = w.get("tmdbId")
            if not tid:
                continue

            media = media_by_tmdb.get(tid)
            requests = requests_by_tmdb.get(tid, [])
            media_status = media.get("status") if media else None

            item = {
                "tmdbId": tid,
                "tvdbId": w.get("tvdbId"),
                "type": w.get("mediaType") or w.get("type", "movie"),
                "title": w.get("title") or w.get("name", ""),
                "ratingKey": w.get("ratingKey"),
                "seerrRequests": requests,
                "seerrMedia": media,
            }

            if media_status in (4, 5):       # PARTIALLY_AVAILABLE or AVAILABLE
                available.append(item)
            elif requests:
                already_requested.append(item)
            else:
                watchlist_only.append(item)

        # Seerr requests whose TMDB ID is NOT on the watchlist
        not_on_watchlist_count = sum(
            1 for req in all_requests
            if req.get("media", {}).get("tmdbId") not in watchlist_tmdb_ids
        )

        # Enrich all watchlist buckets concurrently
        all_items = watchlist_only + already_requested + available
        enriched = list(await asyncio.gather(
            *[enrich_watchlist_item(client, item) for item in all_items]
        ))

        wonly_n = len(watchlist_only)
        areq_n = len(already_requested)

        result = {
            "watchlistOnly": enriched[:wonly_n],
            "alreadyRequested": enriched[wonly_n:wonly_n + areq_n],
            "available": enriched[wonly_n + areq_n:],
            "stats": {
                "watchlistTotal": len(watchlist_raw),
                "watchlistOnly": wonly_n,
                "alreadyRequested": areq_n,
                "available": len(available),
                "notOnWatchlist": not_on_watchlist_count,
            },
        }

    await cache_set("watchlist_comparison", result)
    return result


@app.post("/api/watchlist/request")
async def request_watchlist_items(body: WatchlistRequestBody, _: None = Depends(require_auth)):
    _require_credentials()
    results = []
    errors = []

    async with httpx.AsyncClient(timeout=60) as client:
        async def _submit(item: WatchlistItem):
            try:
                payload: dict = {"mediaType": item.mediaType, "mediaId": item.tmdbId}
                resp = await client.post(
                    f"{SEERR_URL}/api/v1/request",
                    headers=seerr_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                return {"tmdbId": item.tmdbId, "success": True, "newId": resp.json().get("id")}
            except Exception as exc:
                logger.error("Failed to submit watchlist request tmdbId=%s: %s", item.tmdbId, exc)
                return {"tmdbId": item.tmdbId, "success": False, "error": "Failed to submit request"}

        item_results = await asyncio.gather(*[_submit(item) for item in body.items])

    for r in item_results:
        (results if r.get("success") else errors).append(r)

    await cache_invalidate("requests", "watchlist_comparison", "library_untracked")
    return {"results": results, "errors": errors}


# ---------------------------------------------------------------------------
# Endpoints - Cache management
# ---------------------------------------------------------------------------

@app.get("/api/cache/status")
async def get_cache_status(_: None = Depends(require_auth)):
    now = time.monotonic()
    async with _cache_lock:
        return {
            "ttl_seconds": CACHE_TTL,
            "entries": {
                k: {"expires_in_seconds": round(v[0] - now)}
                for k, v in _cache.items()
            },
        }


@app.delete("/api/cache")
async def clear_cache(_: None = Depends(require_auth)):
    """Flush the entire server-side cache, forcing a full re-fetch on next request."""
    await cache_invalidate()
    return {"ok": True, "message": "Cache cleared"}


# ---------------------------------------------------------------------------
# Endpoints - Health / status
# ---------------------------------------------------------------------------


@app.get("/api/auth-required")
async def auth_required():
    """Public endpoint: tells the frontend whether a Bearer token is needed."""
    return {"required": bool(APP_SECRET)}


@app.get("/api/status")
async def get_status(_: None = Depends(require_auth)):
    seerr_ok = False
    seerr_version = None
    tmdb_ok = False
    configured = not bool(_missing)

    if configured:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{SEERR_URL}/api/v1/status",
                    headers=seerr_headers(),
                )
                if resp.status_code == 200:
                    seerr_ok = True
                    seerr_version = resp.json().get("version")
            except Exception:
                pass

            try:
                resp = await client.get(
                    "https://api.themoviedb.org/3/configuration",
                    params=tmdb_params(),
                    headers=tmdb_headers(),
                )
                tmdb_ok = resp.status_code == 200
            except Exception:
                pass

    return {
        "configured": configured,
        "seerr": {"ok": seerr_ok, "version": seerr_version},
        "tmdb": {"ok": tmdb_ok},
    }


# ---------------------------------------------------------------------------
# Endpoints - Library view (Radarr + Sonarr cross-reference)
# ---------------------------------------------------------------------------

@app.get("/api/library/untracked")
async def get_library_untracked(_: None = Depends(require_auth)):
    _require_credentials()
    cached = await cache_get("library_untracked")
    if cached is not None:
        return cached

    radarr_ok = bool(RADARR_URL and RADARR_API_KEY)
    sonarr_ok = bool(SONARR_URL and SONARR_API_KEY)

    # Neither service configured - return an empty payload so the frontend
    # can render its "not configured" panel without a 503.
    if not radarr_ok and not sonarr_ok:
        return {
            "untracked": [],
            "watchlistedNotInSeerr": [],
            "inSeerr": [],
            "stats": {
                "radarrTotal": 0, "sonarrTotal": 0,
                "untracked": 0, "watchlistedNotInSeerr": 0,
                "inSeerr": 0, "noTmdbId": 0,
            },
            "configured": {"radarr": False, "sonarr": False},
        }

    async with httpx.AsyncClient(timeout=60) as client:
        # Identify the API-key owner so we can fetch their watchlist
        try:
            me_resp = await client.get(
                f"{SEERR_URL}/api/v1/auth/me",
                headers=seerr_headers(),
            )
            me_resp.raise_for_status()
            user_id = me_resp.json()["id"]
        except Exception as exc:
            logger.error("Cannot identify Seerr user: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Cannot reach Seerr - check SEERR_URL and SEERR_API_KEY.",
            )

        # Parallel fetch: arr libraries + Seerr media + watchlist
        radarr_raw, sonarr_raw, seerr_media, watchlist_raw = await asyncio.gather(
            fetch_radarr_movies(client) if radarr_ok else _empty(),
            fetch_sonarr_series(client) if sonarr_ok else _empty(),
            fetch_all_pages(client, "/api/v1/media"),
            fetch_watchlist(client, user_id),
        )

        # Normalise Radarr movies
        radarr_items = [normalize_radarr_movie(m) for m in radarr_raw]

        # Normalise Sonarr series; batch-resolve any missing TMDB IDs via TMDB /find
        sonarr_no_tmdb = [s for s in sonarr_raw if not s.get("tmdbId")]
        resolved_ids: dict[int, int] = {}
        if sonarr_no_tmdb:
            resolved_ids = await resolve_sonarr_tmdb_ids(client, sonarr_no_tmdb)

        sonarr_items = [
            normalize_sonarr_series(
                s,
                resolved_tmdb_id=resolved_ids.get(s.get("tvdbId") or 0),
            )
            for s in sonarr_raw
        ]

        # Build TMDB ID sets / maps from Seerr
        seerr_tmdb_ids: set[int] = {
            m["tmdbId"] for m in seerr_media if m.get("tmdbId")
        }
        seerr_media_by_tmdb: dict[int, dict] = {
            m["tmdbId"]: m for m in seerr_media if m.get("tmdbId")
        }

        # Build TMDB ID set from watchlist
        watchlist_tmdb_ids: set[int] = {
            w["tmdbId"] for w in watchlist_raw if w.get("tmdbId")
        }

        # Categorise every library item into one of three buckets
        untracked: list[dict] = []
        watchlisted_not_in_seerr: list[dict] = []
        in_seerr: list[dict] = []
        no_tmdb_count = 0

        for item in radarr_items + sonarr_items:
            tid = item.get("tmdbId")
            if not tid:
                no_tmdb_count += 1
                continue

            if tid in seerr_tmdb_ids:
                seerr_m = seerr_media_by_tmdb.get(tid, {})
                in_seerr.append({
                    **item,
                    "seerrMediaStatus": MEDIA_STATUS.get(seerr_m.get("status")) if seerr_m else None,
                    "seerrMediaStatusNum": seerr_m.get("status") if seerr_m else None,
                    "seerrMediaId": seerr_m.get("id") if seerr_m else None,
                })
            elif tid in watchlist_tmdb_ids:
                watchlisted_not_in_seerr.append(item)
            else:
                untracked.append(item)

    result = {
        "untracked": untracked,
        "watchlistedNotInSeerr": watchlisted_not_in_seerr,
        "inSeerr": in_seerr,
        "stats": {
            "radarrTotal": len(radarr_items),
            "sonarrTotal": len(sonarr_items),
            "untracked": len(untracked),
            "watchlistedNotInSeerr": len(watchlisted_not_in_seerr),
            "inSeerr": len(in_seerr),
            "noTmdbId": no_tmdb_count,
        },
        "configured": {"radarr": radarr_ok, "sonarr": sonarr_ok},
    }
    await cache_set("library_untracked", result)
    return result


# ---------------------------------------------------------------------------
# Serve built Svelte app in production
# ---------------------------------------------------------------------------

STATIC_DIR = "/app/static"
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
