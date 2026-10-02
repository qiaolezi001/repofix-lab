"""Strict external inputs and provider output types."""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    max_tool_calls: int = Field(default=12, ge=1, le=100)
    max_model_calls: int = Field(default=16, ge=1, le=100)
    max_repairs: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=180, ge=1, le=1800)
    context_chars: int = Field(default=32000, ge=3000, le=200000)
    max_output_tokens: int = Field(default=1800, ge=128, le=8192)


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(min_length=1, max_length=2000)
    issue: str = Field(min_length=5, max_length=8000)
    mode: Literal["mock", "live"] = "mock"
    strategy: Literal["agent", "baseline"] = "agent"
    limits: Limits = Field(default_factory=Limits)
    allow_paid: bool = False


@dataclass
class Action:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Reply:
    message: dict[str, Any]
    actions: list[Action] = field(default_factory=list)
    summary: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


TERMINAL = {"succeeded", "completed", "failed", "timed_out", "cancelled"}
