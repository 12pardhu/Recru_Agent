"""Centralized intake for client and vendor OPT staffing requirements.

This module records where a requirement came from before JD analysis and sourcing.
It deliberately does not ingest email/WhatsApp/LinkedIn automatically; integrations
must be separately authorized and configured.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "recru_agent.db"
router = APIRouter(prefix="/api/requirement-intake", tags=["Requirement Intake"])

CHANNELS = {"Email", "WhatsApp", "Phone", "LinkedIn", "Other"}
RELATIONSHIPS = {"Client", "Vendor", "Both"}
STATUSES = {"Received", "Under Analysis", "Clarification Pending", "Verified", "Ready for Sourcing", "On Hold", "Closed"}


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def stamp():
    return datetime.now(timezone.utc).isoformat()


def init():
    with connect() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS requirement_intakes (
          id INTEGER PRIMARY KEY,
          job_title TEXT NOT NULL,
          jd_text TEXT DEFAULT '',
          relationship_type TEXT NOT NULL,
          received_via TEXT NOT NULL,
          received_at TEXT NOT NULL,
          client_company TEXT DEFAULT '',
          client_contact_name TEXT DEFAULT '',
          client_contact_email TEXT DEFAULT '',
          vendor_company TEXT DEFAULT '',
          vendor_contact_name TEXT DEFAULT '',
          vendor_contact_email TEXT DEFAULT '',
          end_client TEXT DEFAULT '',
          location TEXT DEFAULT '',
          employment_type TEXT DEFAULT 'Unknown',
          rate_range TEXT DEFAULT '',
          submission_deadline TEXT DEFAULT '',
          interview_process TEXT DEFAULT '',
          clarification_notes TEXT DEFAULT '',
          verification_notes TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'Received',
          linked_job_id INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_requirement_intakes_status ON requirement_intakes(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_requirement_intakes_received ON requirement_intakes(received_at)")


init()


class IntakeCreate(BaseModel):
    job_title: str = Field(min_length=2, max_length=200)
    jd_text: str = Field(default="", max_length=50000)
    relationship_type: str
    received_via: str
    received_at: str = ""
    client_company: str = Field(default="", max_length=200)
    client_contact_name: str = Field(default="", max_length=160)
    client_contact_email: str = Field(default="", max_length=254)
    vendor_company: str = Field(default="", max_length=200)
    vendor_contact_name: str = Field(default="", max_length=160)
    vendor_contact_email: str = Field(default="", max_length=254)
    end_client: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=500)
    employment_type: str = Field(default="Unknown", max_length=40)
    rate_range: str = Field(default="", max_length=120)
    submission_deadline: str = Field(default="", max_length=80)
    interview_process: str = Field(default="", max_length=1000)
    clarification_notes: str = Field(default="", max_length=5000)

    @field_validator("relationship_type")
    @classmethod
    def valid_relationship(cls, value):
        if value not in RELATIONSHIPS:
            raise ValueError("relationship_type must be Client, Vendor, or Both")
        return value

    @field_validator("received_via")
    @classmethod
    def valid_channel(cls, value):
        if value not in CHANNELS:
            raise ValueError("received_via must be Email, WhatsApp, Phone, LinkedIn, or Other")
        return value

    @field_validator("job_title")
    @classmethod
    def clean_title(cls, value):
        return value.strip()


class IntakeUpdate(BaseModel):
    status: Optional[str] = None
    clarification_notes: Optional[str] = Field(default=None, max_length=5000)
    verification_notes: Optional[str] = Field(default=None, max_length=5000)
    client_company: Optional[str] = Field(default=None, max_length=200)
    client_contact_name: Optional[str] = Field(default=None, max_length=160)
    client_contact_email: Optional[str] = Field(default=None, max_length=254)
    vendor_company: Optional[str] = Field(default=None, max_length=200)
    vendor_contact_name: Optional[str] = Field(default=None, max_length=160)
    vendor_contact_email: Optional[str] = Field(default=None, max_length=254)
    end_client: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=500)
    employment_type: Optional[str] = Field(default=None, max_length=40)
    rate_range: Optional[str] = Field(default=None, max_length=120)
    submission_deadline: Optional[str] = Field(default=None, max_length=80)
    interview_process: Optional[str] = Field(default=None, max_length=1000)
    linked_job_id: Optional[int] = None


@router.post("")
def create_intake(payload: IntakeCreate):
    data = payload.model_dump()
    received_at = data.pop("received_at") or stamp()
    if data["relationship_type"] in ("Client", "Both") and not data["client_company"]:
        raise HTTPException(400, "Enter the client company for a direct client requirement.")
    if data["relationship_type"] in ("Vendor", "Both") and not data["vendor_company"]:
        raise HTTPException(400, "Enter the vendor company for a vendor-mediated requirement.")
    with connect() as c:
        # Flag, but do not silently merge, similar open requirements.
        possible = c.execute("""
          SELECT id, job_title, client_company, vendor_company, end_client, location, status
          FROM requirement_intakes
          WHERE lower(job_title)=lower(?)
            AND lower(COALESCE(end_client,''))=lower(?)
            AND lower(COALESCE(location,''))=lower(?)
            AND status NOT IN ('Closed')
          ORDER BY id DESC LIMIT 5
        """, (data["job_title"], data["end_client"], data["location"])).fetchall()
        cur = c.execute("""
          INSERT INTO requirement_intakes (
            job_title,jd_text,relationship_type,received_via,received_at,
            client_company,client_contact_name,client_contact_email,
            vendor_company,vendor_contact_name,vendor_contact_email,end_client,
            location,employment_type,rate_range,submission_deadline,
            interview_process,clarification_notes,status,created_at,updated_at
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Received',?,?)
        """, (
            data["job_title"], data["jd_text"], data["relationship_type"], data["received_via"], received_at,
            data["client_company"], data["client_contact_name"], data["client_contact_email"],
            data["vendor_company"], data["vendor_contact_name"], data["vendor_contact_email"], data["end_client"],
            data["location"], data["employment_type"], data["rate_range"], data["submission_deadline"],
            data["interview_process"], data["clarification_notes"], stamp(), stamp()
        ))
        intake_id = cur.lastrowid
    return {
        "id": intake_id,
        "status": "Received",
        "possible_duplicates": [dict(row) for row in possible],
        "message": "Requirement intake recorded. Review and verify it before creating a sourcing-ready job."
    }


@router.get("")
def list_intakes(status: Optional[str] = None, relationship_type: Optional[str] = None):
    if status and status not in STATUSES:
        raise HTTPException(400, "Unknown requirement status.")
    if relationship_type and relationship_type not in RELATIONSHIPS:
        raise HTTPException(400, "relationship_type must be Client, Vendor, or Both.")
    sql = "SELECT * FROM requirement_intakes WHERE 1=1"
    args = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if relationship_type:
        sql += " AND relationship_type=?"
        args.append(relationship_type)
    sql += " ORDER BY received_at DESC, id DESC"
    with connect() as c:
        return [dict(row) for row in c.execute(sql, args).fetchall()]


@router.get("/{intake_id}")
def get_intake(intake_id: int):
    with connect() as c:
        row = c.execute("SELECT * FROM requirement_intakes WHERE id=?", (intake_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Requirement intake not found.")
    return dict(row)


@router.patch("/{intake_id}")
def update_intake(intake_id: int, payload: IntakeUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "Provide at least one field to update.")
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(400, "Unknown requirement status.")
    if "linked_job_id" in changes and changes["linked_job_id"] is not None:
        with connect() as c:
            if not c.execute("SELECT id FROM jobs WHERE id=?", (changes["linked_job_id"],)).fetchone():
                raise HTTPException(404, "Linked job requirement not found.")
    with connect() as c:
        if not c.execute("SELECT id FROM requirement_intakes WHERE id=?", (intake_id,)).fetchone():
            raise HTTPException(404, "Requirement intake not found.")
        assignments = ", ".join(f"{key}=?" for key in changes)
        c.execute(
            f"UPDATE requirement_intakes SET {assignments}, updated_at=? WHERE id=?",
            (*changes.values(), stamp(), intake_id)
        )
        row = c.execute("SELECT * FROM requirement_intakes WHERE id=?", (intake_id,)).fetchone()
    return dict(row)
