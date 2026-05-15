"""RAG service — embeddings (OpenAI) + vector store (Qdrant). Onda 5."""
from services.rag.embedder import Embedder, embed_texts
from services.rag.qdrant_client import QdrantStore
from services.rag.service import RAGService

__all__ = ["Embedder", "embed_texts", "QdrantStore", "RAGService"]
