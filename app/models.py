"""
Relational data model.

DocumentNode
    One row per markdown heading (#, ##, or ###). Self-referential
    parent_id builds the tree. `order_index` preserves the original
    top-to-bottom order of the document, since a `SELECT ... ORDER BY id`
    isn't guaranteed to reflect document order once nodes are edited/added
    later (e.g. via the upload endpoint re-ingesting a new version).

Selection
    A named, persisted set of node IDs a client picked (e.g. "sections 1.2
    and 3.3"). Many-to-many with DocumentNode via SelectionNode.

SelectionNode
    Plain association table. Kept explicit (not `secondary=`) so we retain
    the option to add per-row metadata later (e.g. the order the user
    picked nodes in) without a migration that changes table shape.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentNode(Base):
    __tablename__ = "document_nodes"

    id = Column(Integer, primary_key=True, index=True)
    heading = Column(String(500), nullable=False)
    level = Column(Integer, nullable=False)  # 1 = '#', 2 = '##', 3 = '###'
    body = Column(Text, nullable=False, default="")
    order_index = Column(Integer, nullable=False)  # document reading order

    parent_id = Column(Integer, ForeignKey("document_nodes.id"), nullable=True)
    parent = relationship("DocumentNode", remote_side=[id], back_populates="children")
    children = relationship(
        "DocumentNode",
        back_populates="parent",
        order_by="DocumentNode.order_index",
        cascade="all, delete-orphan",
    )

    created_at = Column(DateTime, default=_utcnow)


class Selection(Base):
    __tablename__ = "selections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    nodes = relationship("DocumentNode", secondary="selection_nodes")


class SelectionNode(Base):
    __tablename__ = "selection_nodes"

    selection_id = Column(Integer, ForeignKey("selections.id"), primary_key=True)
    node_id = Column(Integer, ForeignKey("document_nodes.id"), primary_key=True)
