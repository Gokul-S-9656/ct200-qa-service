"""
Turns the CT-200 markdown manual into a flat list of node dicts, ready to be
inserted into the DB with parent/child links resolved.

Design choice: the parser only understands `#`, `##`, `###` headings (per
the assignment brief, that's all this document uses) and treats every
non-heading line as body text belonging to the nearest preceding heading.
It intentionally does NOT try to handle arbitrary markdown (tables, images,
nested lists, etc.) -- that generality wasn't asked for, and pretending to
support it would just hide bugs.

Algorithm: single pass, maintain a stack of "currently open" headings keyed
by level. When a new heading of level L appears, pop the stack until its
top has level < L, then that becomes the new node's parent.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

HEADING_RE = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


@dataclass
class ParsedNode:
    level: int
    heading: str
    order_index: int
    body_lines: list = field(default_factory=list)
    parent_order_index: Optional[int] = None

    @property
    def body(self) -> str:
        return "\n".join(self.body_lines).strip()


def parse_markdown(text: str) -> list[ParsedNode]:
    lines = text.splitlines()
    nodes: list[ParsedNode] = []
    stack: list[ParsedNode] = []  # open headings, top = most recent
    order_index = 0

    for raw_line in lines:
        match = HEADING_RE.match(raw_line)
        if match:
            hashes, heading_text = match.groups()
            level = len(hashes)

            # Close out any open headings at this level or deeper.
            while stack and stack[-1].level >= level:
                stack.pop()

            node = ParsedNode(
                level=level,
                heading=heading_text,
                order_index=order_index,
                parent_order_index=stack[-1].order_index if stack else None,
            )
            order_index += 1
            nodes.append(node)
            stack.append(node)
        else:
            if stack and raw_line.strip():
                stack[-1].body_lines.append(raw_line)
            # Lines before the first heading, or blank lines, are dropped.

    return nodes
