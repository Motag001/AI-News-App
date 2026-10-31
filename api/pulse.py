"""AI Pulse endpoints (LLD section 3.10 conventions: JSON, /api/v1 prefix, problem+json errors)."""

import hmac
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Callable, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from workers.intelligence import pulse

log = logging.getLogger("pulse-api")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PulseStory(BaseModel):
    order: int
    story_id: str | None
    headline: str
    summary: str
    why_it_matters: str | None
    category: str
    source_name: str
    source_url: str
    published_at: str


class PulseChallenge(BaseModel):
    question: str
    options: list[str]
    question_type: Literal["edition", "general"]


class PulseEdition(BaseModel):
    date: str
    edition_number: int
    introduction: str
    story_count: int
    reading_time_minutes: int
    mode: Literal["ai", "extractive"]
    generated_at: str
    stories: list[PulseStory]
    challenge: PulseChallenge
    previous_date: str | None
    next_date: str | None


class TodayResponse(BaseModel):
    status: Literal["current", "previous", "unavailable"]
    message: str | None = None
    edition: PulseEdition | None = None


class HistoryItem(BaseModel):
    date: str
    edition_number: int
    story_count: int
    reading_time_minutes: int
    lead_headline: str | None


class AnswerRequest(BaseModel):
    choice: int = Field(ge=0, le=3)


class AnswerResponse(BaseModel):
    correct: bool
    correct_index: int
    correct_answer: str
    explanation: str


def valid_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise HTTPException(status_code=404, detail="Edition not found.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=404, detail="Edition not found.") from None
    return value


def build_router(before_read: Callable[[], None]) -> APIRouter:
    """`before_read` lets the host app refresh stories on serverless before an edition is built."""
    router = APIRouter(prefix="/api/v1/pulse", tags=["pulse"])

    @router.get("/today", response_model=TodayResponse)
    def today(_: None = Depends(before_read)) -> TodayResponse:
        now = datetime.now(timezone.utc)
        today_key = now.date().isoformat()
        edition = pulse.get_edition(today_key)
        if edition is None and os.getenv("PULSE_GENERATE_ON_REQUEST", "true").lower() == "true":
            # Not an open trigger: no input is accepted, attempts per day are capped and backed off,
            # and an existing edition is never regenerated.
            edition = pulse.ensure_edition(today_key, now=now)
        if edition is not None:
            return TodayResponse(status="current", edition=PulseEdition(**edition))
        latest = pulse.latest_edition()
        if latest is not None:
            return TodayResponse(
                status="previous",
                message="Today's edition is not ready yet. Showing the most recent edition.",
                edition=PulseEdition(**latest),
            )
        return TodayResponse(status="unavailable", message="The first AI Pulse edition has not been published yet.")

    @router.get("/history", response_model=list[HistoryItem])
    def history(limit: int = Query(default=14, ge=1, le=60)) -> list[HistoryItem]:
        return [HistoryItem(**row) for row in pulse.history(limit)]

    @router.post("/refresh", response_model=PulseEdition)
    def refresh(authorization: str | None = Header(default=None)) -> PulseEdition:
        """Operator-only editorial refresh of today's edition. Disabled unless PULSE_ADMIN_TOKEN is set."""
        token = os.getenv("PULSE_ADMIN_TOKEN", "")
        if not token:
            raise HTTPException(status_code=404, detail="Not found.")
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(status_code=403, detail="Not allowed.")
        edition = pulse.ensure_edition(datetime.now(timezone.utc).date().isoformat(), force=True)
        if edition is None:
            raise HTTPException(status_code=503, detail="No edition could be generated.")
        log.info("AI Pulse refresh completed")  # audit trail without secrets
        return PulseEdition(**edition)

    @router.get("/{edition_date}", response_model=PulseEdition)
    def by_date(edition_date: str) -> PulseEdition:
        edition = pulse.get_edition(valid_date(edition_date))
        if edition is None:
            raise HTTPException(status_code=404, detail="Edition not found.")
        return PulseEdition(**edition)

    @router.post("/{edition_date}/challenge/answer", response_model=AnswerResponse)
    def answer(edition_date: str, body: AnswerRequest) -> AnswerResponse:
        try:
            result = pulse.check_answer(valid_date(edition_date), body.choice)
        except ValueError:
            raise HTTPException(status_code=422, detail="Choice is not one of the options.") from None
        if result is None:
            raise HTTPException(status_code=404, detail="Edition not found.")
        return AnswerResponse(**result)

    return router
