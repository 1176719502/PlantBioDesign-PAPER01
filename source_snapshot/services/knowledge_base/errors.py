from __future__ import annotations


class KnowledgeBaseError(RuntimeError):
    """Base error for the independent knowledge database."""


class KnowledgeBuildError(KnowledgeBaseError):
    """Raised when an offline release bundle cannot be built safely."""


class KnowledgeResourceError(KnowledgeBaseError):
    """Raised when a packaged knowledge resource cannot be trusted or opened."""


class KnowledgeSnapshotError(KnowledgeBaseError):
    """Raised when a project knowledge-reference snapshot is malformed."""
