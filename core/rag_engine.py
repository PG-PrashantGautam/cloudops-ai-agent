import argparse
import os
from pathlib import Path

import chromadb
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT_DIR / ".env")

DB_DIR = ROOT_DIR / "chroma_db"
RUNBOOKS_DIR = ROOT_DIR / "knowledge_base" / "runbooks"


class RAGEngine:
    """Local Vector DB (ChromaDB) + Ollama Embedding engine for CloudOps runbooks."""

    def __init__(self, collection_name: str = "cloudops_runbooks"):
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.client = chromadb.PersistentClient(path=str(DB_DIR))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def get_embedding(self, text: str) -> list[float]:
        """Convert text into a vector embedding using local Ollama."""
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": self.embed_model, "input": text},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
        """Split a document into overlapping chunks so context isn't cut in half."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start += chunk_size - overlap
        return [c for c in chunks if c]

    def ingest_runbooks(self, folder: Path = RUNBOOKS_DIR) -> int:
        """Read all .md/.txt files in the runbooks folder, embed, and upsert into ChromaDB."""
        files = list(folder.glob("*.md")) + list(folder.glob("*.txt"))
        if not files:
            print(f"[⚠️] No .md or .txt files found in {folder}")
            return 0

        total_chunks = 0
        for file_path in files:
            content = file_path.read_text(encoding="utf-8")
            chunks = self.chunk_text(content)

            for idx, chunk in enumerate(chunks):
                doc_id = f"{file_path.name}::chunk_{idx}"
                embedding = self.get_embedding(chunk)
                self.collection.upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{"source": file_path.name, "chunk": idx}],
                )
                total_chunks += 1

            print(f"[📚] Ingested '{file_path.name}' ({len(chunks)} chunks)")

        return total_chunks

    def search(self, query: str, top_k: int = 2) -> str:
        """Perform semantic search and return the top matching runbook snippets."""
        if self.collection.count() == 0:
            return ""

        query_embedding = self.get_embedding(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return ""

        formatted = []
        for doc, meta in zip(docs, metas):
            formatted.append(f"[Source: {meta.get('source', 'unknown')}]\n{doc}")
        return "\n\n---\n\n".join(formatted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PG-AI Local RAG Engine (ChromaDB + Ollama)")
    parser.add_argument("--ingest", action="store_true", help="Ingest all runbooks into ChromaDB")
    parser.add_argument("--query", "-q", help="Test semantic search against the Vector DB")
    parser.add_argument("--top-k", type=int, default=2, help="Number of chunks to retrieve")
    args = parser.parse_args()

    rag = RAGEngine()

    if args.ingest:
        count = rag.ingest_runbooks()
        print(f"[✅] Done. Total chunks stored in ChromaDB: {count}")

    if args.query:
        print(f"\n[🔎] Searching Vector DB for: '{args.query}'\n")
        hits = rag.search(args.query, top_k=args.top_k)
        print(hits or "No matching runbooks found.")
