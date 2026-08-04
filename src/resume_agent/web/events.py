"""Durable per-Run events with replayable SSE subscriptions."""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from resume_agent.web.schemas import EventPublic


class EventStore:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                node TEXT,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                details TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def append(
        self,
        event_type: str,
        status: str,
        summary: str,
        node: str | None = None,
        details: dict[str, object] | None = None,
    ) -> EventPublic:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe_details = details or {}
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO events(timestamp,type,node,status,summary,details) VALUES(?,?,?,?,?,?)",
                (timestamp, event_type, node, status, summary, json.dumps(safe_details)),
            )
            event_id = int(cursor.lastrowid)
        return EventPublic(
            id=event_id,
            run_id=self.run_id,
            timestamp=timestamp,
            type=event_type,
            node=node,
            status=status,
            summary=summary,
            details=safe_details,
        )

    def after(self, event_id: int) -> list[EventPublic]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,timestamp,type,node,status,summary,details FROM events "
                "WHERE id > ? ORDER BY id",
                (event_id,),
            ).fetchall()
        return [
            EventPublic(
                id=row[0], run_id=self.run_id, timestamp=row[1], type=row[2],
                node=row[3], status=row[4], summary=row[5], details=json.loads(row[6]),
            )
            for row in rows
        ]

    async def subscribe(self, last_event_id: int = 0) -> AsyncIterator[EventPublic]:
        cursor = last_event_id
        while True:
            events = self.after(cursor)
            for event in events:
                cursor = event.id
                yield event
            await asyncio.sleep(0.35)
