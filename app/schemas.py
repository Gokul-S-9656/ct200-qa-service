"""
Pydantic schemas: the contract between the API and its clients.

Kept separate from `models.py` on purpose -- ORM models describe how data
is stored, schemas describe how data looks over the wire. Conflating the
two is a common beginner shortcut that breaks the moment you want a field
in the API response that isn't a raw DB column (e.g. `children`, which is
computed, not stored).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------- Nodes ----------

class NodeSummary(BaseModel):
    """Lightweight node representation, used in lists and as children."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    heading: str
    level: int
    parent_id: Optional[int]


class NodeDetail(NodeSummary):
    """Full node representation: includes body text and nested children."""
    body: str
    children: list["NodeSummary"] = []


# ---------- Selections ----------

class SelectionCreate(BaseModel):
    node_ids: list[int] = Field(..., min_length=1, description="IDs of nodes the user selected")
    name: Optional[str] = Field(None, description="Optional human-readable label")


class SelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str]
    created_at: datetime
    nodes: list[NodeSummary]


# ---------- Generation ----------

class TestCase(BaseModel):
    """A single QA test case idea produced by the LLM."""
    title: str
    steps: str
    expected_result: str
    priority: str = Field(description="high | medium | low")
    related_node_id: Optional[int] = None


class GenerationRequest(BaseModel):
    selection_id: int


class GenerationOut(BaseModel):
    id: str
    selection_id: int
    node_ids: list[int]
    model: str
    provider: str
    generated_at: datetime
    test_cases: list[TestCase]
