"""
Browse API: list top-level sections, fetch a node with its children, and
search across headings/body text.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/nodes", tags=["Browse"])


@router.get("", response_model=list[schemas.NodeSummary])
def list_top_level_sections(db: Session = Depends(get_db)):
    """List top-level sections (direct children of the document root)."""
    return crud.get_top_level_nodes(db)


@router.get("/search", response_model=list[schemas.NodeSummary])
def search_nodes(
    q: str = Query(..., min_length=1, description="Text to search in headings and body"),
    db: Session = Depends(get_db),
):
    """Search node headings and body text (case-insensitive substring match)."""
    return crud.search_nodes(db, q)


@router.get("/{node_id}", response_model=schemas.NodeDetail)
def get_node(node_id: int, db: Session = Depends(get_db)):
    """Get a single node by ID, including its full body text and children."""
    node = crud.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return node
