import os
import threading

import faiss
import numpy as np

import config

_lock = threading.Lock()
_index = None


def _load():
    global _index
    if _index is not None:
        return _index
    if os.path.exists(config.FAISS_INDEX_PATH):
        _index = faiss.read_index(config.FAISS_INDEX_PATH)
    else:
        _index = faiss.IndexIDMap(faiss.IndexFlatL2(config.EMBEDDING_DIM))
    return _index


def add(snap_id, vector):
    with _lock:
        index = _load()
        vec = np.array([vector], dtype="float32")
        ids = np.array([snap_id], dtype="int64")
        index.remove_ids(ids)
        index.add_with_ids(vec, ids)
        os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(index, config.FAISS_INDEX_PATH)


def search(vector, k=10):
    with _lock:
        index = _load()
        if index.ntotal == 0:
            return []
        vec = np.array([vector], dtype="float32")
        distances, ids = index.search(vec, min(k, index.ntotal))
        return [(int(i), float(d)) for i, d in zip(ids[0], distances[0]) if i != -1]


def rebuild_from_rows(rows):
    """rows: list of (snap_id, vector). Used for startup consistency check."""
    global _index
    with _lock:
        new_index = faiss.IndexIDMap(faiss.IndexFlatL2(config.EMBEDDING_DIM))
        if rows:
            ids = np.array([r[0] for r in rows], dtype="int64")
            vecs = np.array([r[1] for r in rows], dtype="float32")
            new_index.add_with_ids(vecs, ids)
        _index = new_index
        os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(_index, config.FAISS_INDEX_PATH)


def count():
    with _lock:
        return _load().ntotal
