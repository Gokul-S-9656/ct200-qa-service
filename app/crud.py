"""
Database access functions. Kept as plain functions (not a repository class)
since the project is small enough that a class layer would just add
indirection without adding value.
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app import models


# ---------- Ingestion ----------

def clear_all_nodes(db: Session) -> None:
    """Wipe existing tree before re-ingesting (used by seed + upload)."""
    db.query(models.SelectionNode).delete()
    db.query(models.Selection).delete()
    db.query(models.DocumentNode).delete()
    db.commit()


def bulk_insert_nodes(db: Session, parsed_nodes: list) -> dict[int, int]:
    """
    Insert parser output into the DB.

    `parsed_nodes` items have a `parent_order_index` pointing at another
    parsed node's `order_index`, not a real DB id yet (DB ids don't exist
    until after insert). We insert root-to-leaf so that by the time a
    child is inserted, its parent already has a real id, then look the
    real id up via `order_index_to_db_id`.

    Returns the order_index -> db_id mapping, useful for callers (e.g. the
    seed script) that want to log/verify the ingested tree.
    """
    order_index_to_db_id: dict[int, int] = {}

    for parsed in parsed_nodes:  # parser emits nodes in document order,
        parent_db_id = (
            order_index_to_db_id[parsed.parent_order_index]
            if parsed.parent_order_index is not None
            else None
        )
        db_node = models.DocumentNode(
            heading=parsed.heading,
            level=parsed.level,
            body=parsed.body,
            order_index=parsed.order_index,
            parent_id=parent_db_id,
        )
        db.add(db_node)
        db.flush()  # assigns db_node.id without committing the transaction
        order_index_to_db_id[parsed.order_index] = db_node.id

    db.commit()
    return order_index_to_db_id


# ---------- Browse ----------

def get_top_level_nodes(db: Session) -> list[models.DocumentNode]:
    """
    'Top level sections' = children of the document's root node (the H1),
    not the H1 itself. The H1 is the document title, not a section a user
    would pick test cases from.
    """
    root = db.query(models.DocumentNode).filter(models.DocumentNode.parent_id.is_(None)).first()
    if root is None:
        return []
    return (
        db.query(models.DocumentNode)
        .filter(models.DocumentNode.parent_id == root.id)
        .order_by(models.DocumentNode.order_index)
        .all()
    )


def get_node(db: Session, node_id: int) -> models.DocumentNode | None:
    return db.query(models.DocumentNode).filter(models.DocumentNode.id == node_id).first()


def search_nodes(db: Session, query: str) -> list[models.DocumentNode]:
    pattern = f"%{query}%"
    return (
        db.query(models.DocumentNode)
        .filter(or_(models.DocumentNode.heading.ilike(pattern), models.DocumentNode.body.ilike(pattern)))
        .order_by(models.DocumentNode.order_index)
        .all()
    )


# ---------- Selections ----------

def create_selection(db: Session, node_ids: list[int], name: str | None) -> models.Selection:
    nodes = db.query(models.DocumentNode).filter(models.DocumentNode.id.in_(node_ids)).all()
    found_ids = {n.id for n in nodes}
    missing = set(node_ids) - found_ids
    if missing:
        raise ValueError(f"Unknown node id(s): {sorted(missing)}")

    selection = models.Selection(name=name, nodes=nodes)
    db.add(selection)
    db.commit()
    db.refresh(selection)
    return selection


def get_selection(db: Session, selection_id: int) -> models.Selection | None:
    return db.query(models.Selection).filter(models.Selection.id == selection_id).first()


def collect_selection_text(selection: models.Selection) -> str:
    """
    Reconstruct the text of a selection for the LLM prompt: each selected
    node's heading + body, in the order the nodes were originally
    selected (matches `SelectionCreate.node_ids` order via `nodes`
    relationship, which SQLAlchemy returns in insertion order here).
    """
    parts = []
    for node in selection.nodes:
        parts.append(f"### {node.heading}\n{node.body}".strip())
    return "\n\n".join(parts)
