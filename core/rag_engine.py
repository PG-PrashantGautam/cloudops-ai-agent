import argparse
import os
from pathlib import Path

import boto3
import chromadb
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT_DIR / ".env")

DB_DIR = ROOT_DIR / "chroma_db"
RUNBOOKS_DIR = ROOT_DIR / "knowledge_base" / "runbooks"


class RAGEngine:
    """Dual-mode RAG Engine: Local (ChromaDB + Ollama) or Cloud (AWS Bedrock KB)."""

    def __init__(self, collection_name: str = "cloudops_runbooks", provider: str = None):
        self.provider = (provider or os.getenv("RAG_PROVIDER", "local")).lower()
        self.region = os.getenv("AWS_REGION", "ap-south-1")

        if self.provider == "bedrock":
            self.kb_id = os.getenv("BEDROCK_KB_ID", "").strip()
            self.ds_id = os.getenv("BEDROCK_DATA_SOURCE_ID", "").strip()
            self.bucket = os.getenv("BEDROCK_RUNBOOK_BUCKET", "").strip()
            if not self.kb_id:
                raise ValueError("BEDROCK_KB_ID is not set in .env")
            self.agent_runtime = boto3.client("bedrock-agent-runtime", region_name=self.region)
            self.bedrock_agent = boto3.client("bedrock-agent", region_name=self.region)
            self.s3 = boto3.client("s3", region_name=self.region)
        else:
            self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            self.embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
            self.client = chromadb.PersistentClient(path=str(DB_DIR))
            self.collection = self.client.get_or_create_collection(name=collection_name)

    def get_embedding(self, text: str) -> list[float]:
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": self.embed_model, "input": text},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start += chunk_size - overlap
        return [c for c in chunks if c]

    def ingest_runbooks(self, folder: Path = RUNBOOKS_DIR) -> int:
        files = list(folder.glob("*.md")) + list(folder.glob("*.txt"))
        if not files:
            print(f"[⚠️] No .md or .txt files found in {folder}")
            return 0

        if self.provider == "bedrock":
            for file_path in files:
                key = f"runbooks/{file_path.name}"
                self.s3.upload_file(str(file_path), self.bucket, key)
                print(f"[☁️] Uploaded '{file_path.name}' -> s3://{self.bucket}/{key}")

            job = self.bedrock_agent.start_ingestion_job(
                knowledgeBaseId=self.kb_id,
                dataSourceId=self.ds_id,
            )
            job_id = job["ingestionJob"]["ingestionJobId"]
            print(f"[🚀] Started Bedrock Knowledge Base sync job: {job_id}")
            return len(files)

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
        if self.provider == "bedrock":
            resp = self.agent_runtime.retrieve(
                knowledgeBaseId=self.kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "managedSearchConfiguration": {"numberOfResults": top_k}
                },
            )
            results = resp.get("retrievalResults", [])
            if not results:
                return ""
            formatted = []
            for item in results:
                uri = item.get("location", {}).get("s3Location", {}).get("uri", "s3-runbook")
                text = item.get("content", {}).get("text", "").strip()
                formatted.append(f"\n{text}")
            return "\n\n---\n\n".join(formatted)

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
        return "\n\n---\n\n".join(
            f"\n{doc}"
            for doc, meta in zip(docs, metas)
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PG-AI Dual-Mode RAG Engine")
    parser.add_argument("--ingest", action="store_true", help="Ingest runbooks into ChromaDB or Bedrock KB")
    parser.add_argument("--query", "-q", help="Test semantic search")
    parser.add_argument("--provider", choices=["local", "bedrock"], default=None, help="RAG backend")
    parser.add_argument("--top-k", type=int, default=2, help="Number of chunks to retrieve")
    args = parser.parse_args()

    rag = RAGEngine(provider=args.provider)
    if args.ingest:
        count = rag.ingest_runbooks()
        print(f"[✅] Done ({rag.provider}). Processed: {count}")
    if args.query:
        print(rag.search(args.query, top_k=args.top_k) or "No matching runbooks found.")
