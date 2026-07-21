"""
log.py — Raft replicated log.

Maintains an ordered list of ``LogEntry`` items.  The leader appends new
entries and replicates them to followers via AppendEntries RPCs.  An entry
is *committed* once a majority of nodes have acknowledged it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LogEntry:
    """A single entry in the Raft replicated log.

    Attributes:
        index:     1-based sequential position in the log.
        term:      The Raft term when this entry was created.
        command:   The command string (e.g. ``"MOVE 120 340"``).
        committed: Whether this entry has been committed (majority ack).
    """

    index: int
    term: int
    command: str
    committed: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "term": self.term,
            "command": self.command,
            "committed": self.committed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> LogEntry:
        return cls(
            index=d["index"],
            term=d["term"],
            command=d["command"],
            committed=d.get("committed", False),
        )


class RaftLog:
    """Ordered, 1-indexed replicated log.

    The log is empty on startup (index 0 is a sentinel — never stored).
    """

    def __init__(self) -> None:
        self._entries: list[LogEntry] = []

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def last_index(self) -> int:
        """Return the index of the last entry, or 0 if empty."""
        return self._entries[-1].index if self._entries else 0

    def last_term(self) -> int:
        """Return the term of the last entry, or 0 if empty."""
        return self._entries[-1].term if self._entries else 0

    def get(self, index: int) -> LogEntry | None:
        """Return the entry at *index* (1-based), or ``None``."""
        if index < 1 or index > len(self._entries):
            return None
        return self._entries[index - 1]

    def get_term_at(self, index: int) -> int:
        """Return the term of the entry at *index*, or 0 if absent."""
        entry = self.get(index)
        return entry.term if entry else 0

    def entries_from(self, start_index: int) -> list[LogEntry]:
        """Return all entries from *start_index* onward (inclusive)."""
        if start_index < 1:
            start_index = 1
        return list(self._entries[start_index - 1 :])

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def append(self, term: int, command: str) -> LogEntry:
        """Append a new entry and return it."""
        entry = LogEntry(
            index=self.last_index() + 1,
            term=term,
            command=command,
        )
        self._entries.append(entry)
        return entry

    def append_entry(self, entry: LogEntry) -> None:
        """Append a pre-built ``LogEntry`` (used during replication)."""
        self._entries.append(entry)

    def truncate_from(self, index: int) -> None:
        """Remove all entries at *index* and beyond (conflict resolution)."""
        if index < 1:
            return
        self._entries = self._entries[: index - 1]

    def mark_committed(self, up_to_index: int) -> None:
        """Mark all entries up to and including *up_to_index* as committed."""
        for entry in self._entries:
            if entry.index <= up_to_index:
                entry.committed = True

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dicts(self) -> list[dict]:
        """Serialize all entries to a list of dicts (for JSON transport)."""
        return [e.to_dict() for e in self._entries]

    def entries_to_dicts(self, entries: list[LogEntry]) -> list[dict]:
        """Serialize a subset of entries to dicts."""
        return [e.to_dict() for e in entries]
