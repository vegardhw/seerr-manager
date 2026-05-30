import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

SEERR_URL = os.getenv("SEERR_URL", "").rstrip("/")
SEERR_API_KEY = os.getenv("SEERR_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

# TMDB auth: v3 keys are short hex strings; v4 read-access tokens are JWTs
# (start with "eyJ"). The v3 endpoint accepts both, but JWTs must be sent
# as a Bearer header — they are not valid as ?api_key= query params.
_TMDB_IS_BEARER = TMDB_API_KEY.startswith("eyJ")

# Cache TTL in seconds — configurable via env, defaults to 5 minutes.
# Set to 0 to disable caching (always re-fetch from Seerr/TMDB).
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))

_missing = [name for name, val in [
    ("SEERR_URL", SEERR_URL),
    ("SEERR_API_KEY", SEERR_API_KEY),
    ("TMDB_API_KEY", TMDB_API_KEY),
] if not val]

# In dev mode (no creds yet) we warn rather than crash so the frontend can
# still boot and be inspected.  Every API endpoint guards itself.
if _missing:
    import warnings
    warnings.warn(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "API endpoints will return 503 until all variables are set.",
        RuntimeWarning,
        stacklevel=1,
    )

app = FastAPI(title="Seerr Manager")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _require_credentials():
    """Raise 503 if any credential is not configured yet."""
    if _missing:
        raise HTTPException(
            status_code=503,
            detail=f"Server not configured — missing: {', '.join(_missing)}",
        )


def seerr_headers() -> dict:
    return {"X-Api-Key": SEERR_API_KEY}


def tmdb_headers() -> dict:
    """Return the correct auth header for TMDB (Bearer for v4 JWT tokens)."""
    if _TMDB_IS_BEARER:
        return {"Authorization": f"Bearer {TMDB_API_KEY}"}
    return {}


def tmdb_params(**kwargs) -> dict:
    """Return query params for TMDB — api_key only needed for v3 string keys."""
    if _TMDB_IS_BEARER:
        return {**kwargs}
    return {"api_key": TMDB_API_KEY, **kwargs}


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
        reasons.append("Media deleted from library — needs re-request")
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
# Endpoints — Requests view
# ---------------------------------------------------------------------------

@app.get("/api/requests")
async def get_requests():
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
            detail=f"Request {request_id} has no TMDB ID — resolve the ID mismatch first",
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


class WatchlistItem(BaseModel):
    tmdbId: int
    mediaType: MediaType


class WatchlistRequestBody(BaseModel):
    items: list[WatchlistItem]


# ---------------------------------------------------------------------------
# Endpoints — Re-request actions
# ---------------------------------------------------------------------------

@app.post("/api/rerequest/batch")
async def rerequest_batch(body: BatchBody):
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
                errors.append({"id": request_id, "error": str(exc)})

        for orphan in body.orphans:
            try:
                new_req = await _do_request_orphan(
                    client, orphan.seerrMediaId, orphan.tmdbId, orphan.mediaType
                )
                results.append({"seerrMediaId": orphan.seerrMediaId, "success": True, "newId": new_req.get("id")})
            except HTTPException as exc:
                errors.append({"seerrMediaId": orphan.seerrMediaId, "error": exc.detail})
            except Exception as exc:
                errors.append({"seerrMediaId": orphan.seerrMediaId, "error": str(exc)})

    await cache_invalidate("requests", "watchlist_comparison")
    return {"results": results, "errors": errors}


@app.post("/api/rerequest/orphan")
async def rerequest_orphan(body: OrphanBody):
    _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        new_req = await _do_request_orphan(
            client, body.seerrMediaId, body.tmdbId, body.mediaType
        )
    await cache_invalidate("requests", "watchlist_comparison")
    return {"success": True, "newRequest": new_req}


@app.post("/api/rerequest/{request_id}")
async def rerequest_single(request_id: int):
    _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        new_req = await _do_rerequest(client, request_id)
    await cache_invalidate("requests", "watchlist_comparison")
    return {"success": True, "newRequest": new_req}


# ---------------------------------------------------------------------------
# Endpoints — Watchlist comparison
# ---------------------------------------------------------------------------

@app.get("/api/watchlist/comparison")
async def get_watchlist_comparison():
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
            raise HTTPException(status_code=502, detail=f"Cannot identify Seerr user: {exc}")

        # Parallel fetch: watchlist, all requests, all media
        try:
            watchlist_raw, all_requests, all_media = await asyncio.gather(
                fetch_watchlist(client, user_id),
                fetch_all_pages(client, "/api/v1/request", {"sort": "added"}),
                fetch_all_pages(client, "/api/v1/media"),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch data from Seerr: {exc}")

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
async def request_watchlist_items(body: WatchlistRequestBody):
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
                return {"tmdbId": item.tmdbId, "success": False, "error": str(exc)}

        item_results = await asyncio.gather(*[_submit(item) for item in body.items])

    for r in item_results:
        (results if r.get("success") else errors).append(r)

    await cache_invalidate("requests", "watchlist_comparison")
    return {"results": results, "errors": errors}


# ---------------------------------------------------------------------------
# Endpoints — Cache management
# ---------------------------------------------------------------------------

@app.get("/api/cache/status")
async def get_cache_status():
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
async def clear_cache():
    """Flush the entire server-side cache, forcing a full re-fetch on next request."""
    await cache_invalidate()
    return {"ok": True, "message": "Cache cleared"}


# ---------------------------------------------------------------------------
# Endpoints — Health / status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
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
        "missing": _missing,
        "seerr": {"ok": seerr_ok, "version": seerr_version},
        "tmdb": {"ok": tmdb_ok},
    }


# ---------------------------------------------------------------------------
# Serve built Svelte app in production
# ---------------------------------------------------------------------------

STATIC_DIR = "/app/static"
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
