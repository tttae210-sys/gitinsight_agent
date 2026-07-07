import chromadb
from app.core.config import CHROMA_MODE, CHROMA_HOST, CHROMA_PORT
_client = None
def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is not None: return _client
    if CHROMA_MODE == "http":
        _client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    else:
        _client = chromadb.PersistentClient(path="./chroma_data")
    return _client
