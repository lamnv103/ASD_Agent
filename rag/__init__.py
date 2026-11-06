"""PostgreSQL whole-document retrieval, without generation or corpus mutation."""
from .retriever import PostgresRetriever, RetrievalError
__all__ = ["PostgresRetriever", "RetrievalError"]
