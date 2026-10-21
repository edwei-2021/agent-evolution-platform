"""Versioned, strict canonical records. Execution success is not task success."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Hash = str

class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1

class Task(Record):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    family: str = Field(min_length=1, max_length=100)
    split: Literal["search", "validation", "independent_test"]
    fixture_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    requirement: str = Field(min_length=1, max_length=8000)
    allowed_files: list[Literal["solution.py"]] = Field(default_factory=lambda: ["solution.py"])

class Usage(Record):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    wall_time_ms: float = Field(default=0, ge=0)

class RunResult(Record):
    run_id: str
    task_id: str
    status: Literal["succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"]
    release_snapshot_id: str
    environment_snapshot_id: str
    loaded_skill_hash: str
    event_ids: list[int] = Field(default_factory=list)
    output: dict = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    artifacts: list[str] = Field(default_factory=list)
    error_code: str | None = None

class Evaluation(Record):
    id: str
    run_id: str
    task_id: str
    repetition: int = Field(ge=0)
    label: Literal["baseline", "candidate"]
    split: Literal["search", "validation", "independent_test"]
    verdict: Literal["pass", "fail", "invalid_evaluation"]
    evaluator_hash: str
    dataset_hash: str
    snapshot_hash: str
    artifacts: list[str]
    failure_category: Literal["none", "assertion", "timeout", "policy", "infrastructure", "integrity"]
    score: Literal[0, 1] | None
    @model_validator(mode="after")
    def consistent(self):
        expected = None if self.verdict == "invalid_evaluation" else int(self.verdict == "pass")
        if self.score != expected:
            raise ValueError("Score must match trusted verdict")
        if not self.artifacts:
            raise ValueError("Evaluation requires evidence references")
        return self

class Event(Record):
    seq: int = Field(ge=1)
    aggregate_id: str
    correlation_id: str
    type: str
    at: float
    payload: dict

class Candidate(Record):
    id: str
    parent_id: str | None
    skill_hash: str
    workflow_hash: str
    body: str = Field(min_length=1, max_length=8000)

class Experiment(Record):
    id: str
    state: Literal["draft", "queued", "running", "evaluating", "cancelling", "completed", "failed", "cancelled", "interrupted"]
    snapshots: dict
    budgets: dict
    consumed: dict
    checkpoint_hash: str | None = None

class Release(Record):
    skill_hash: str
    workflow_hash: str
    runtime_hash: str
    model_policy_hash: str
    tool_policy_hash: str
    evaluator_hash: str
    dataset_hash: str
    memory_snapshot_hash: str
    fixture_hashes: list[str]
    budgets: dict
    result_ids: list[str]
    parent_release: str | None
    seed: int | None = None
    @model_validator(mode="after")
    def snapshots(self):
        import re
        for name in ("skill_hash", "workflow_hash", "runtime_hash", "model_policy_hash", "tool_policy_hash",
                     "evaluator_hash", "dataset_hash", "memory_snapshot_hash"):
            if not re.fullmatch(r"[a-f0-9]{64}", getattr(self, name)):
                raise ValueError("Missing immutable snapshot: " + name)
        if not self.fixture_hashes or any(not re.fullmatch(r"[a-f0-9]{64}", h) for h in self.fixture_hashes):
            raise ValueError("Missing fixture snapshots")
        if not self.result_ids or not self.budgets:
            raise ValueError("Release needs evaluated results and budgets")
        return self

class StepCheck(Record):
    id: str
    step: Literal["M1", "M2", "M3", "M4", "M5", "M6", "M7"]
    status: Literal["passed", "failed", "blocked"]
    debug_code: str
    source_hash: str
    input_hash: str
    started_at: float
    finished_at: float
    command: list[str]
    exit_code: int
    bundle: str
    remediation: str

MODELS = (Task, RunResult, Evaluation, Candidate, Experiment, Release, Event, StepCheck)
