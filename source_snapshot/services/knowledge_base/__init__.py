"""Independent, versioned, read-only knowledge database infrastructure."""

from services.knowledge_base.errors import (
    KnowledgeBaseError,
    KnowledgeBuildError,
    KnowledgeResourceError,
    KnowledgeSnapshotError,
)
from services.knowledge_base.reader import KnowledgeQueryV0, open_packaged_knowledge_base
from services.knowledge_base.snapshot import KnowledgeReferenceSnapshot

__all__ = [
    "KnowledgeBaseError",
    "KnowledgeBuildError",
    "KnowledgeQueryV0",
    "KnowledgeReferenceSnapshot",
    "KnowledgeResourceError",
    "KnowledgeSnapshotError",
    "open_packaged_knowledge_base",
]
