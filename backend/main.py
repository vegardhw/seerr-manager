import asyncio
import os
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

_missing = [name for name, val in [
    ("SEERR_URL", SEERR_URL),
    ("SEERR_API_KEY", SEERR_API_KEY),
    ("TMDB_API_KEY", TMDB_API_KEY),
] if not val]
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

app = FastAPI(title="Seerr Manager")


def seerr_headers():
    return {"X-Api-Key": SEERR_API_KEY}


def tmdb_params(**kwargs):
    return {"api_key": TMDB_API_KEY, **kwargs}


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


@app.get("/api/requests")
async def get_requests():
    async with httpx.AsyncClient(timeout=60) as client:
        # Fetch all requests and all media concurrently
        all_requests, all_media = await asyncio.gather(
            fetch_all_pages(client, "/api/v1/request", {"sort": "added"}),
            fetch_all_pages(client, "/api/v1/media"),
        )

        # Find media that is DELETED and has no active request
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

    return list(enriched)


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

    # Clear Seerr's cached media record so the new request gets a clean TMDB
    # lookup instead of re-attaching to the stale (possibly mismatched) record.
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


@app.post("/api/rerequest/batch")
async def rerequest_batch(body: BatchBody):
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

    return {"results": results, "errors": errors}


@app.post("/api/rerequest/orphan")
async def rerequest_orphan(body: OrphanBody):
    async with httpx.AsyncClient(timeout=30) as client:
        new_req = await _do_request_orphan(
            client, body.seerrMediaId, body.tmdbId, body.mediaType
        )
    return {"success": True, "newRequest": new_req}


@app.post("/api/rerequest/{request_id}")
async def rerequest_single(request_id: int):
    async with httpx.AsyncClient(timeout=30) as client:
        new_req = await _do_rerequest(client, request_id)
    return {"success": True, "newRequest": new_req}


@app.get("/api/status")
async def get_status():
    async with httpx.AsyncClient(timeout=10) as client:
        seerr_ok = False
        seerr_version = None
        tmdb_ok = False

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
                params={"api_key": TMDB_API_KEY},
            )
            tmdb_ok = resp.status_code == 200
        except Exception:
            pass

    return {
        "seerr": {"ok": seerr_ok, "version": seerr_version},
        "tmdb": {"ok": tmdb_ok},
    }


# Serve built Svelte app in production
STATIC_DIR = "/app/static"
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
