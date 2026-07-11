"""
Generation API: reconstruct text for a selection, call the LLM, persist
the result in TinyDB. Retrieval API: fetch past generations by selection
or by node.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud, llm, nosql, schemas
from app.database import get_db
from app.exceptions import NotFoundError, ValidationError

router = APIRouter(tags=["Generation"])


@router.post("/selections/{selection_id}/generate", response_model=schemas.GenerationOut, status_code=201)
def generate_test_cases(selection_id: int, db: Session = Depends(get_db)):
    selection = crud.get_selection(db, selection_id)
    if selection is None:
        raise NotFoundError(f"Selection {selection_id} not found")

    content = crud.collect_selection_text(selection)
    if not content.strip():
        raise ValidationError("Selected nodes have no text content to generate from")

    # llm.generate_test_cases raises LLMUnavailableError / LLMResponseError
    # on failure; both are AppErrors, so the handler in main.py maps them
    # to a 502 with a client-safe message without this route needing a
    # try/except of its own.
    test_cases, model_name, provider = llm.generate_test_cases(content)
    node_ids = [n.id for n in selection.nodes]

    record = nosql.save_generation(
        selection_id=selection.id,
        node_ids=node_ids,
        model=model_name,
        provider=provider,
        test_cases=test_cases,
    )
    return record


@router.get("/generations/{generation_id}", response_model=schemas.GenerationOut)
def get_generation(generation_id: str):
    record = nosql.get_generation_by_id(generation_id)
    if record is None:
        raise NotFoundError(f"Generation {generation_id} not found")
    return record


@router.get("/selections/{selection_id}/generations", response_model=list[schemas.GenerationOut])
def get_generations_for_selection(selection_id: int):
    return nosql.get_generations_by_selection(selection_id)


@router.get("/nodes/{node_id}/generations", response_model=list[schemas.GenerationOut])
def get_generations_for_node(node_id: int):
    return nosql.get_generations_by_node(node_id)
