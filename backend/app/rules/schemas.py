"""Pydantic models mirroring the rule JSON schema (ontology/schema/rule.schema.json)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.rules.bands import Band

Op = Literal["and", "or", "not", "gte", "gt", "lte", "lt", "eq", "neq", "between", "in"]
Scalar = float | bool


class LogicNode(BaseModel):
    op: Op
    operands: list["LogicNode"] | None = None
    input: str | None = None
    value: Scalar | None = None
    values: list[Scalar] | None = None


class RuleInput(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    type: Literal["numeric", "boolean"]
    description: str | None = None


class Evidence(BaseModel):
    title: str
    source_type: Literal["clinical_guideline", "systematic_review", "health_authority", "other"]
    organization: str | None = None
    year: int | None = None
    url: str | None = None
    note: str | None = None


class ChangelogEntry(BaseModel):
    version: str
    note: str


class Rule(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    condition: str
    min_age: int = Field(ge=13)
    red_flag: bool = False
    priority: int = Field(ge=0, le=100, default=50)
    inputs: list[RuleInput] = Field(min_length=1)
    logic: LogicNode
    output_band: Band
    evidence: list[Evidence] = Field(min_length=1)
    clinically_validated: bool
    reviewer_name: str | None = None
    reviewer_registration_no: str | None = None
    signed_at: datetime | None = None
    changelog: list[ChangelogEntry] = Field(min_length=1)


class Evaluation(BaseModel):
    band: str  # Band value or NOT_ENOUGH_DATA
    indicators: list[str]
    urgent: bool
    safeguarding: bool
    rule_set_version: str
    evaluated_at: datetime
