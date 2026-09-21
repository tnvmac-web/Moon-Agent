"""
Memory system with SQLite for structured storage and vector embeddings for semantic search.
"""

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass
class MemoryEntry:
    """A single memory entry"""

    id: str
    type: str  # 'short_term', 'long_term', 'episodic', 'semantic'
    content: str
    metadata: dict[str, Any]
    embedding: list[float] | None = None
    created_at: str = ""
    updated_at: str = ""
    importance: float = 1.0
    tags: list[str] = None

    def __post_init__(self):
        if self.created_at == "":
            self.created_at = datetime.utcnow().isoformat()
        if self.updated_at == "":
            self.updated_at = datetime.utcnow().isoformat()
        if self.tags is None:
            self.tags = []
        if self.id == "":
            self.id = str(uuid.uuid4())


class VectorStore(ABC):
    """Abstract vector store interface"""

    @abstractmethod
    def add(self, id: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        pass

    @abstractmethod
    def delete(self, id: str) -> None:
        pass

    @abstractmethod
    def persist(self) -> None:
        pass


class SimpleVectorStore(VectorStore):
    """Simple in-memory vector store with cosine similarity (for development)"""

    def __init__(self, persist_path: str = "vector_store"):
        self.persist_path = persist_path
        self.vectors: dict[str, list[float]] = {}
        self.metadata: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Load from disk"""
        path = Path(self.persist_path)
        if path.exists():
            try:
                import pickle

                with open(path, "rb") as f:
                    data = pickle.load(f)
                    self.vectors = data.get("vectors", {})
                    self.metadata = data.get("metadata", {})
            except Exception:
                pass

    def add(self, id: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        self.vectors[id] = embedding
        self.metadata[id] = metadata

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        import numpy as np

        query = np.array(query_embedding)
        results = []

        for id, vec in self.vectors.items():
            if filter_metadata:
                meta = self.metadata.get(id, {})
                if not all(meta.get(k) == v for k, v in filter_metadata.items()):
                    continue

            vec_arr = np.array(vec)
            # Cosine similarity
            sim = np.dot(query, vec_arr) / (np.linalg.norm(query) * np.linalg.norm(vec_arr))
            results.append((id, float(sim), self.metadata.get(id, {})))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def delete(self, id: str) -> None:
        self.vectors.pop(id, None)
        self.metadata.pop(id, None)

    def persist(self) -> None:
        import pickle

        Path(self.persist_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "wb") as f:
            pickle.dump({"vectors": self.vectors, "metadata": self.metadata}, f)


class MemoryStore:
    """SQLite-based memory store with vector search"""

    def __init__(self, db_path: str = "memory.db", vector_store: VectorStore | None = None):
        self.db_path = db_path
        self.vector_store = vector_store or SimpleVectorStore()
        self._embedding_model = None
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                importance REAL DEFAULT 1.0,
                tags TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_type ON memories(type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance)
        """)
        conn.commit()
        conn.close()

    def _get_embedding_model(self):
        """Lazy load embedding model"""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._embedding_model = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2"
                )
            except Exception:
                # Fallback: simple hash-based embedding (catch all exceptions including DLL issues)
                self._embedding_model = None
        return self._embedding_model

    def _embed(self, text: str) -> list[float]:
        """Generate embedding for text"""
        model = self._get_embedding_model()
        if model:
            return model.encode(text).tolist()
        else:
            # Simple fallback: hash-based pseudo-embedding
            import hashlib

            # Convert to 384-dim vector (same as MiniLM)
            vec = []
            for i in range(384):
                h = hashlib.md5(f"{text}{i}".encode()).hexdigest()
                vec.append(int(h[:8], 16) / 0xFFFFFFFF - 0.5)
            return vec

    async def add_async(self, entry: MemoryEntry) -> str:
        """Add memory entry asynchronously"""
        if not entry.embedding:
            entry.embedding = self._embed(entry.content)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO memories (id, type, content, metadata, created_at, updated_at, importance, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.id,
                    entry.type,
                    entry.content,
                    json.dumps(entry.metadata),
                    entry.created_at,
                    entry.updated_at,
                    entry.importance,
                    json.dumps(entry.tags),
                ),
            )
            await db.commit()

        # Add to vector store
        self.vector_store.add(
            entry.id,
            entry.embedding,
            {
                "type": entry.type,
                "content": entry.content[:200],
                "tags": entry.tags,
                "importance": entry.importance,
            },
        )

        return entry.id

    def add(self, entry: MemoryEntry) -> str:
        """Add memory entry (sync)"""
        if not entry.embedding:
            entry.embedding = self._embed(entry.content)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO memories (id, type, content, metadata, created_at, updated_at, importance, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                entry.id,
                entry.type,
                entry.content,
                json.dumps(entry.metadata),
                entry.created_at,
                entry.updated_at,
                entry.importance,
                json.dumps(entry.tags),
            ),
        )
        conn.commit()
        conn.close()

        # Add to vector store
        self.vector_store.add(
            entry.id,
            entry.embedding,
            {
                "type": entry.type,
                "content": entry.content[:200],
                "tags": entry.tags,
                "importance": entry.importance,
            },
        )

        return entry.id

    def get(self, id: str) -> MemoryEntry | None:
        """Get memory by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return MemoryEntry(
                id=row["id"],
                type=row["type"],
                content=row["content"],
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                importance=row["importance"],
                tags=json.loads(row["tags"]) if row["tags"] else [],
            )
        return None

    def search(
        self,
        query: str,
        top_k: int = 10,
        memory_type: str | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Search memories by semantic similarity"""
        query_embedding = self._embed(query)

        filter_meta = {}
        if memory_type:
            filter_meta["type"] = memory_type

        vector_results = self.vector_store.search(query_embedding, top_k * 2, filter_meta)

        results = []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        for id, _score, _ in vector_results:
            cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                entry = MemoryEntry(
                    id=row["id"],
                    type=row["type"],
                    content=row["content"],
                    metadata=json.loads(row["metadata"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    importance=row["importance"],
                    tags=json.loads(row["tags"]) if row["tags"] else [],
                )
                # Filter by tags if specified
                if tags and not any(t in entry.tags for t in tags):
                    continue
                results.append(entry)
                if len(results) >= top_k:
                    break

        conn.close()
        return results

    def search_by_type(self, memory_type: str, limit: int = 50) -> list[MemoryEntry]:
        """Get memories by type"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM memories WHERE type = ? ORDER BY created_at DESC LIMIT ?",
            (memory_type, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            MemoryEntry(
                id=row["id"],
                type=row["type"],
                content=row["content"],
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                importance=row["importance"],
                tags=json.loads(row["tags"]) if row["tags"] else [],
            )
            for row in rows
        ]

    def update(self, entry: MemoryEntry) -> bool:
        """Update memory entry"""
        entry.updated_at = datetime.utcnow().isoformat()
        if not entry.embedding:
            entry.embedding = self._embed(entry.content)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            UPDATE memories SET content = ?, metadata = ?, updated_at = ?,
            importance = ?, tags = ? WHERE id = ?
        """,
            (
                entry.content,
                json.dumps(entry.metadata),
                entry.updated_at,
                entry.importance,
                json.dumps(entry.tags),
                entry.id,
            ),
        )
        conn.commit()
        conn.close()

        # Update vector store
        self.vector_store.add(
            entry.id,
            entry.embedding,
            {
                "type": entry.type,
                "content": entry.content[:200],
                "tags": entry.tags,
                "importance": entry.importance,
            },
        )

        return cursor.rowcount > 0

    def delete(self, id: str) -> bool:
        """Delete memory entry"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (id,))
        conn.commit()
        conn.close()

        self.vector_store.delete(id)
        return cursor.rowcount > 0

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT type, COUNT(*) as count, AVG(importance) as avg_importance
            FROM memories GROUP BY type
        """)
        type_stats = cursor.fetchall()
        cursor = conn.execute("SELECT COUNT(*) FROM memories")
        total = cursor.fetchone()[0]
        conn.close()

        return {
            "total": total,
            "by_type": {row[0]: {"count": row[1], "avg_importance": row[2]} for row in type_stats},
        }

    def persist(self):
        """Persist vector store"""
        self.vector_store.persist()


class ConversationMemory:
    """High-level conversation memory management"""

    def __init__(self, store: MemoryStore):
        self.store = store
        self.session_id = str(uuid.uuid4())
        self.short_term_buffer: list[MemoryEntry] = []
        self.max_short_term = 50

    def add_user_message(self, content: str, metadata: dict[str, Any] = None) -> str:
        """Add user message to memory"""
        entry = MemoryEntry(
            id="",
            type="short_term",
            content=f"User: {content}",
            metadata=metadata or {},
            tags=["user", "conversation", self.session_id],
        )
        self._add_to_buffer(entry)
        return self.store.add(entry)

    def add_assistant_message(self, content: str, metadata: dict[str, Any] = None) -> str:
        """Add assistant message to memory"""
        entry = MemoryEntry(
            id="",
            type="short_term",
            content=f"Assistant: {content}",
            metadata=metadata or {},
            tags=["assistant", "conversation", self.session_id],
        )
        self._add_to_buffer(entry)
        return self.store.add(entry)

    def add_tool_call(self, tool_name: str, args: dict[str, Any], result: str) -> str:
        """Add tool call to memory"""
        entry = MemoryEntry(
            id="",
            type="short_term",
            content=f"Tool: {tool_name}({args}) -> {result[:200]}",
            metadata={"tool": tool_name, "args": args, "result": result},
            tags=["tool", "conversation", self.session_id],
        )
        self._add_to_buffer(entry)
        return self.store.add(entry)

    def _add_to_buffer(self, entry: MemoryEntry):
        """Add to short-term buffer with eviction"""
        self.short_term_buffer.append(entry)
        if len(self.short_term_buffer) > self.max_short_term:
            # Move oldest to long-term
            oldest = self.short_term_buffer.pop(0)
            oldest.type = "long_term"
            oldest.importance = 0.8
            self.store.add(oldest)

    def get_recent_context(self, limit: int = 10) -> list[MemoryEntry]:
        """Get recent conversation context"""
        return self.short_term_buffer[-limit:]

    def search_relevant(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Search for relevant memories"""
        return self.store.search(query, top_k=top_k, tags=[self.session_id])

    def promote_to_long_term(self, entry_id: str, importance: float = 1.0):
        """Promote a short-term memory to long-term"""
        entry = self.store.get(entry_id)
        if entry and entry.type == "short_term":
            entry.type = "long_term"
            entry.importance = importance
            self.store.update(entry)


def create_memory_store(config) -> MemoryStore:
    """Factory function to create memory store from config"""
    # Handle both SettingsManager and Settings objects
    settings = config.settings if hasattr(config, "settings") else config
    vector_store = SimpleVectorStore(settings.memory.vector_store_path)
    return MemoryStore(settings.memory.db_path, vector_store)
