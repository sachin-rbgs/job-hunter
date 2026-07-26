"""Database tables."""
from datetime import date, datetime
from typing import Optional

from sqlmodel import JSON, Column, Field, SQLModel


class CVVariant(SQLModel, table=True):
    __tablename__ = "cv_variants"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    file_path: str
    full_text: str
    # Bullet paragraphs, as {"index": int, "text": str}. Index maps to the
    # position in the .docx paragraph list so edits can be applied in place.
    bullets: list = Field(default_factory=list, sa_column=Column(JSON))
    lean_tags: list = Field(default_factory=list, sa_column=Column(JSON))
    active: bool = True


class Source(SQLModel, table=True):
    __tablename__ = "sources"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: str = Field(index=True)
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    active: bool = True
    last_pulled: Optional[datetime] = None
    last_error: Optional[str] = None


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    external_id: str = Field(index=True)
    title: str
    company: str
    location: Optional[str] = None
    commute_miles: Optional[float] = None
    remote: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    exp_level: Optional[str] = None
    description: Optional[str] = None
    apply_url: str
    ats_type: Optional[str] = None
    questions_json: Optional[list] = Field(default=None, sa_column=Column(JSON))
    match_score: Optional[int] = Field(default=None, index=True)
    score_breakdown: dict = Field(default_factory=dict, sa_column=Column(JSON))
    red_flags: list = Field(default_factory=list, sa_column=Column(JSON))
    posted_at: Optional[datetime] = None
    pulled_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def job_key(self) -> str:
        return f"{self.source}:{self.external_id}"


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    cv_variant_id: Optional[int] = Field(default=None, foreign_key="cv_variants.id")
    cv_variant_name: Optional[str] = None
    cv_reasoning: Optional[str] = None
    # [{"index": int, "original": str, "revised": str, "why": str, "source": str}]
    bullet_edits: list = Field(default_factory=list, sa_column=Column(JSON))
    added_skills: list = Field(default_factory=list, sa_column=Column(JSON))
    missing_keywords: list = Field(default_factory=list, sa_column=Column(JSON))
    cover_letter: Optional[str] = None
    key_skill_matches: list = Field(default_factory=list, sa_column=Column(JSON))
    skills_gap: list = Field(default_factory=list, sa_column=Column(JSON))
    match_rationale: Optional[str] = None
    alignment_before: Optional[int] = None
    alignment_after: Optional[int] = None
    flagged: bool = Field(default=False, index=True)
    flag_reasons: list = Field(default_factory=list, sa_column=Column(JSON))
    generated_cv_path: Optional[str] = None
    status: str = Field(default="pending", index=True)
    skip_reason: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DailyStats(SQLModel, table=True):
    __tablename__ = "daily_stats"

    stats_date: date = Field(primary_key=True)
    jobs_pulled: int = 0
    jobs_qualified: int = 0
    apps_sent: int = 0
    llm_cost_usd: float = 0.0
    apify_cost_usd: float = 0.0
