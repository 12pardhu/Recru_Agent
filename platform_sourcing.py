"""Recruiter-controlled search plans across approved sourcing platforms.

This module creates search instructions and official platform entry links only.
It never logs in, scrapes profiles, or sends messages/submissions.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "recru_agent.db"
router = APIRouter(prefix="/api/platform-sourcing", tags=["Multi-platform Sourcing"])

PLATFORMS = {
    "LinkedIn": "https://www.linkedin.com/search/results/people/",
    "Dice": "https://www.dice.com/",
    "Indeed": "https://www.indeed.com/",
    "Monster": "https://www.monster.com/",
}
STATUSES = {"Prepared", "In Progress", "Completed", "Skipped"}


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def stamp():
    return datetime.now(timezone.utc).isoformat()


def init():
    with connect() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS platform_sourcing_searches (
          id INTEGER PRIMARY KEY,
          job_id INTEGER NOT NULL,
          platform TEXT NOT NULL,
          location TEXT DEFAULT '',
          search_type TEXT NOT NULL,
          query_text TEXT NOT NULL,
          platform_url TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'Prepared',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_platform_search_job ON platform_sourcing_searches(job_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_platform_search_status ON platform_sourcing_searches(status)")


init()


class PlanRequest(BaseModel):
    target_count: int = Field(default=50, ge=50, le=100)
    platforms: list[str] = Field(default_factory=lambda: list(PLATFORMS.keys()), min_length=1)


class SearchUpdate(BaseModel):
    status: str


@router.post("/jobs/{job_id}/plan")
def create_platform_plan(job_id: int, payload: PlanRequest):
    unknown = sorted(set(payload.platforms) - set(PLATFORMS))
    if unknown:
        raise HTTPException(400, "Unsupported platforms: " + ", ".join(unknown))
    with connect() as c:
        job = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job requirement not found.")
        confirmed = c.execute("SELECT id FROM job_versions WHERE job_id=? LIMIT 1", (job_id,)).fetchone()
        if not confirmed:
            raise HTTPException(409, "Confirm the job requirement before preparing sourcing.")
        locations = [x.strip() for x in (job["location"] or "").split(";") if x.strip()] or [""]
        skills = [x.strip() for x in (job["skills"] or "").replace("\n", ",").replace(";", ",").split(",") if x.strip()]
        variants = []
        for platform in payload.platforms:
            for location in locations:
                queries = [
                    ("Role", " ".join(x for x in [job["title"], location] if x)),
                    ("Role + skills", " ".join(x for x in [job["title"], ", ".join(skills[:5]), location] if x)),
                ]
                for search_type, query in queries:
                    variants.append((job_id, platform, location, search_type, query, PLATFORMS[platform], "Prepared", stamp(), stamp()))
        c.executemany("""
          INSERT INTO platform_sourcing_searches
          (job_id,platform,location,search_type,query_text,platform_url,status,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?)
        """, variants)
        c.commit()
    return {
        "job_id": job_id,
        "job_title": job["title"],
        "target_count": payload.target_count,
        "search_count": len(variants),
        "searches": list_platform_searches(job_id),
        "note": "Open the platform in your authorized account and paste the search terms. Candidate profiles are not scraped or imported automatically."
    }


@router.get("/jobs/{job_id}")
def list_platform_searches(job_id: int):
    with connect() as c:
        if not c.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise HTTPException(404, "Job requirement not found.")
        return [dict(r) for r in c.execute(
            "SELECT * FROM platform_sourcing_searches WHERE job_id=? ORDER BY id DESC",
            (job_id,)
        ).fetchall()]


@router.patch("/searches/{search_id}")
def update_platform_search(search_id: int, payload: SearchUpdate):
    if payload.status not in STATUSES:
        raise HTTPException(400, "Status must be Prepared, In Progress, Completed, or Skipped.")
    with connect() as c:
        cur = c.execute(
            "UPDATE platform_sourcing_searches SET status=?, updated_at=? WHERE id=?",
            (payload.status, stamp(), search_id)
        )
        if not cur.rowcount:
            raise HTTPException(404, "Platform search not found.")
        row = c.execute("SELECT * FROM platform_sourcing_searches WHERE id=?", (search_id,)).fetchone()
    return dict(row)
