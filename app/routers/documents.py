"""
Optional upload endpoint. The project's default, documented ingestion path
is the startup seed script (see app/main.py + README). This endpoint is a
bonus alternative for re-ingesting a different/updated markdown file
without restarting the server.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingest import ingest_markdown

router = APIRouter(prefix="/documents", tags=["Ingestion"])


@router.post("/upload", status_code=201)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are supported")

    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8")
        node_count = ingest_markdown(db, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"message": "Document ingested", "nodes_created": node_count}
