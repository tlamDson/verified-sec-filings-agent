"""Why a retrieval build, search, or snapshot was refused."""


class RetrievalError(Exception):
    """Base class: the index cannot answer, and saying so beats answering wrong."""


class EmbeddingMismatchError(RetrievalError):
    """Vectors from a model, or with a shape, that the embedding space does not hold."""


class EmbedderUnavailableError(RetrievalError):
    """The embedding model cannot be loaded here (package missing)."""


class IndexNotBuiltError(RetrievalError):
    """The embedding space or its BM25 statistics were never built."""


class IncompleteIndexError(RetrievalError):
    """Some chunks of the version have no vector or no lexical row, or statistics are stale."""


class SnapshotNotFoundError(RetrievalError):
    """No snapshot by that name."""


class SnapshotMismatchError(RetrievalError):
    """The database no longer holds the content a snapshot recorded."""
