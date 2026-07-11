"""
Single ingestion routine shared by:
  1. Startup seeding (reads MANUAL_PATH from disk) -- the primary,
     documented way this project loads data. See README.
  2. POST /documents/upload (bonus) -- lets a client re-ingest a new
     markdown file at runtime without restarting the server.

Both call `ingest_markdown` so there's exactly one code path that turns
markdown text into DB rows.
"""
from sqlalchemy.orm import Session

from app import crud
from app.exceptions import ValidationError
from app.parser import parse_markdown


def ingest_markdown(db: Session, text: str) -> int:
    """Wipes the existing tree and inserts a fresh one. Returns node count."""
    parsed_nodes = parse_markdown(text)
    if not parsed_nodes:
        raise ValidationError("No headings found -- document must use #, ##, or ### headings")
    crud.clear_all_nodes(db)
    order_map = crud.bulk_insert_nodes(db, parsed_nodes)
    return len(order_map)
