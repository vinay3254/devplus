import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
DB_PATH = os.getenv(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "data", "snapstack.db")
)
FAISS_INDEX_PATH = os.getenv(
    "FAISS_INDEX_PATH", os.path.join(os.path.dirname(__file__), "data", "snapstack.faiss")
)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
PORT = int(os.getenv("PORT", "5100"))
