"""
Optional upload endpoint. The project's default, documented ingestion path
is the startup seed script (see app/main.py + README). This endpoint is a
bonus alternative for re-ingesting a different/updated markdown file
without restarting the server.
"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.exceptions import PayloadTooLargeError, ValidationError
from app.ingest import ingest_markdown

router = APIRouter(prefix="/documents", tags=["Ingestion"])


@router.post("/upload", status_code=201)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise ValidationError("Only .md files are supported")

    # Read in bounded chunks and bail out as soon as the limit is
    # crossed, rather than `await file.read()` -- an unbounded read
    # buffers the entire upload into memory before any validation runs,
    # which makes the endpoint a trivial memory-exhaustion vector for
    # anyone who can reach it (it's unauthenticated, per the documented
    # scope in APPROACH.md).
    chunks: list[bytes] = []
    total_size = 0
    chunk_size = 1024 * 1024  # 1 MB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > settings.max_upload_size_bytes:
            raise PayloadTooLargeError(
                f"File exceeds the {settings.max_upload_size_bytes // (1024 * 1024)} MB upload limit."
            )
        chunks.append(chunk)

    raw_bytes = b"".join(chunks)
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("File must be UTF-8 encoded text.") from exc

    node_count = ingest_markdown(db, text)
    return {"message": "Document ingested", "nodes_created": node_count}
