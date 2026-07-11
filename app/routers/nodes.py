"""
Browse API: list top-level sections, fetch a node with its children, and
search across headings/body text.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.exceptions import NotFoundError

router = APIRouter(prefix="/nodes", tags=["Browse"])

# Search terms come straight from a query string with no length cap, so a
# huge `q` would still hit the DB with a huge ILIKE pattern for no
# benefit -- cheap to bound up front.
MAX_SEARCH_QUERY_LENGTH = 200


@router.get("", response_model=list[schemas.NodeSummary])
def list_top_level_sections(db: Session = Depends(get_db)):
    """List top-level sections (direct children of the document root)."""
    return crud.get_top_level_nodes(db)


@router.get("/search", response_model=list[schemas.NodeSummary])
def search_nodes(
    q: str = Query(
        ...,
        min_length=1,
        max_length=MAX_SEARCH_QUERY_LENGTH,
        description="Text to search in headings and body",
    ),
    db: Session = Depends(get_db),
):
    """Search node headings and body text (case-insensitive substring match)."""
    return crud.search_nodes(db, q)


@router.get("/{node_id}", response_model=schemas.NodeDetail)
def get_node(node_id: int, db: Session = Depends(get_db)):
    """Get a single node by ID, including its full body text and children."""
    node = crud.get_node(db, node_id)
    if node is None:
        raise NotFoundError(f"Node {node_id} not found")
    return node
