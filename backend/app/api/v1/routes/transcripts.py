from __future__ import annotations

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import NotFound, ValidationFailed
from app.db.session import get_db
from app.models import Profile, Transcript
from app.schemas import TranscriptOut, TranscriptUpdate
from app.services.access import get_clip, get_project
from app.services.captions import build_cues, to_srt, to_vtt

router = APIRouter(tags=["transcripts"])


def _transcript(db: Session, project_id: uuid.UUID) -> Transcript:
    row = db.scalar(select(Transcript).where(Transcript.project_id == project_id))
    if row is None:
        raise NotFound("This video has not been transcribed yet.", code="NO_TRANSCRIPT")
    return row


@router.get("/projects/{project_id}/transcript", response_model=TranscriptOut)
def get_transcript(
    project_id: uuid.UUID, user: Profile = Depends(current_user), db: Session = Depends(get_db)
) -> Transcript:
    return _transcript(db, get_project(db, user, project_id).id)


@router.patch("/projects/{project_id}/transcript", response_model=TranscriptOut)
def update_transcript(
    project_id: uuid.UUID,
    body: TranscriptUpdate,
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> Transcript:
    """Correct transcript text. Timings are kept; captions use the corrected text."""
    row = _transcript(db, get_project(db, user, project_id).id)
    segments = [dict(s) for s in row.segments]
    for edit in body.segments:
        if edit.index >= len(segments):
            raise ValidationFailed(f"Segment {edit.index} does not exist.")
        text = " ".join(edit.text.split())
        if not text:
            raise ValidationFailed("Segment text must not be blank.")
        segments[edit.index]["text"] = text
    row.segments = segments
    row.full_text = " ".join(s["text"] for s in segments)
    db.commit()
    db.refresh(row)
    return row


@router.get("/clips/{clip_id}/subtitles", response_class=PlainTextResponse)
def clip_subtitles(
    clip_id: uuid.UUID,
    format: Literal["srt", "vtt"] = Query("srt"),
    user: Profile = Depends(current_user),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Subtitles for the clip, timed relative to the clip start."""
    clip = get_clip(db, user, clip_id)
    cues = build_cues(
        _transcript(db, clip.project_id).segments, clip.start_seconds, clip.end_seconds
    )
    body = to_srt(cues) if format == "srt" else to_vtt(cues)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", clip.title).strip("-").lower()[:80] or "clip"
    media = "application/x-subrip" if format == "srt" else "text/vtt"
    return PlainTextResponse(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{slug}.{format}"'},
    )
