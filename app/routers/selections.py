"""
Selection API: a client submits a set of node IDs, we persist it as a
named "selection" they can reference later when requesting generation.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/selections", tags=["Selections"])


@router.post("", response_model=schemas.SelectionOut, status_code=201)
def create_selection(payload: schemas.SelectionCreate, db: Session = Depends(get_db)):
    try:
        selection = crud.create_selection(db, payload.node_ids, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return selection


@router.get("/{selection_id}", response_model=schemas.SelectionOut)
def get_selection(selection_id: int, db: Session = Depends(get_db)):
    selection = crud.get_selection(db, selection_id)
    if selection is None:
        raise HTTPException(status_code=404, detail=f"Selection {selection_id} not found")
    return selection
