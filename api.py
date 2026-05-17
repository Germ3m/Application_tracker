import asyncio
import json
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from db import (init_db, add_application, get_applications, update_status,
                delete_application, STATUSES, save_cached_jobs, get_cached_jobs,
                get_new_job_count, get_last_fetched, mark_jobs_seen)
from scraper import search_all_keywords, search_jobs, stream_search_jobs, KEYWORDS

POLL_INTERVAL = 30 * 60  # 30 minutes


async def refresh_jobs():
    jobs = await search_all_keywords()
    if jobs:
        save_cached_jobs(jobs, datetime.now().isoformat(timespec="minutes"))


async def poll_loop():
    await refresh_jobs()  # fetch immediately on startup
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        await refresh_jobs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poll_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
init_db()


class AppIn(BaseModel):
    company: str
    role: str
    type: str
    status: str = "Applied"
    notes: str = ""
    url: str = ""


class StatusUpdate(BaseModel):
    status: str


# --- Applications ---

@app.get("/api/applications")
def list_applications(status: str = None, type: str = None):
    return get_applications(status, type)


@app.post("/api/applications", status_code=201)
def create_application(data: AppIn):
    if data.type not in ("Internship", "Graduate"):
        raise HTTPException(400, "Invalid type")
    if data.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    new_id = add_application(data.company, data.role, data.type, data.status, data.notes, data.url)
    return {"id": new_id, **data.model_dump()}


@app.patch("/api/applications/{app_id}")
def change_status(app_id: int, body: StatusUpdate):
    if body.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    if not update_status(app_id, body.status):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@app.delete("/api/applications/{app_id}")
def remove_application(app_id: int):
    if not delete_application(app_id):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@app.get("/api/statuses")
def list_statuses():
    return STATUSES


# --- Job Search (live) ---

@app.get("/api/jobs/search")
async def job_search(keyword: str = Query(default=None), page: int = Query(default=1)):
    if keyword:
        return await search_jobs(keyword, page)
    return await search_all_keywords()


@app.get("/api/jobs/stream")
async def job_stream(keyword: str = Query(...), page: int = Query(default=1)):
    """SSE endpoint — streams each source's results as they arrive."""
    async def event_generator():
        async for batch in stream_search_jobs(keyword, page):
            yield f"data: {json.dumps(batch)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/keywords")
def get_keywords():
    return KEYWORDS


# --- Cached Jobs ---

@app.get("/api/jobs/cached")
def cached_jobs():
    return {
        "jobs": get_cached_jobs(),
        "new_count": get_new_job_count(),
        "last_fetched": get_last_fetched(),
    }


@app.post("/api/jobs/seen")
def mark_seen():
    mark_jobs_seen()
    return {"ok": True}


@app.post("/api/jobs/refresh")
async def manual_refresh():
    await refresh_jobs()
    return {"ok": True, "last_fetched": get_last_fetched()}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
