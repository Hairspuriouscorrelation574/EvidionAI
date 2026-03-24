"""
Chats and messages API.

GET    /chats                           list root chats (or filter by project)
POST   /chats                           create a chat
GET    /chats/search?q=...              full-text search
PUT    /chats/{id}                      rename
DELETE /chats/{id}                      delete (cascades to messages)
GET    /chats/{id}/messages             list messages
POST   /chats/{id}/messages             append a message
PATCH  /chats/{id}/messages/{msg_id}    update content / status / history
DELETE /chats/{id}/messages/{msg_id}    delete a message
"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.database import get_db, now_iso

router = APIRouter()


class ChatIn(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=500)
    project_id: Optional[str] = None


class ChatRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(default="")
    full_history: Optional[list] = None
    status: str = Field(default="done", pattern="^(done|pending|error)$")


class MessagePatch(BaseModel):
    content: Optional[str] = None
    full_history: Optional[list] = None
    status: Optional[str] = Field(default=None, pattern="^(done|pending|error)$")


def _chat_row(row) -> dict:
    return dict(row) if row else None


def _msg_row(row) -> dict:
    if not row:
        return None
    data = dict(row)
    if data.get("full_history") and isinstance(data["full_history"], str):
        try:
            data["full_history"] = json.loads(data["full_history"])
        except Exception:
            data["full_history"] = []
    return data


def _require_chat(db, chat_id: str):
    row = db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Chat not found")
    return row


@router.get("", summary="List chats")
def list_chats(
    project_id: Optional[str] = Query(None, description="Filter by project. Omit for root chats."),
):
    with get_db() as db:
        if project_id:
            rows = db.execute(
                "SELECT c.*, "
                "(SELECT content FROM messages WHERE chat_id=c.id AND role='user' ORDER BY id LIMIT 1)"
                " AS first_query "
                "FROM chats c WHERE c.project_id = ? ORDER BY c.updated_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT c.*, "
                "(SELECT content FROM messages WHERE chat_id=c.id AND role='user' ORDER BY id LIMIT 1)"
                " AS first_query "
                "FROM chats c WHERE c.project_id IS NULL ORDER BY c.updated_at DESC"
            ).fetchall()
    return [_chat_row(r) for r in rows]


@router.post("", summary="Create a chat", status_code=201)
def create_chat(body: ChatIn):
    cid = body.id or str(uuid.uuid4())
    ts = now_iso()
    with get_db() as db:
        if body.project_id:
            proj = db.execute(
                "SELECT id FROM projects WHERE id = ?", (body.project_id,)
            ).fetchone()
            if not proj:
                raise HTTPException(404, "Project not found")
        db.execute(
            "INSERT OR IGNORE INTO chats (id, title, project_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (cid, body.title, body.project_id, ts, ts),
        )
        row = db.execute("SELECT * FROM chats WHERE id = ?", (cid,)).fetchone()
    return _chat_row(row)


@router.get("/search", summary="Search chats by title or message content")
def search_chats(q: str = Query(..., min_length=1)):
    pattern = f"%{q}%"
    with get_db() as db:
        rows = db.execute(
            """
            SELECT DISTINCT c.*,
              (SELECT content FROM messages WHERE chat_id=c.id AND role='user' ORDER BY id LIMIT 1)
              AS first_query
            FROM chats c
            LEFT JOIN messages m ON m.chat_id = c.id
            WHERE c.title LIKE ? OR m.content LIKE ?
            ORDER BY c.updated_at DESC
            LIMIT 50
            """,
            (pattern, pattern),
        ).fetchall()
    return [_chat_row(r) for r in rows]


@router.put("/{chat_id}", summary="Rename a chat")
def rename_chat(chat_id: str, body: ChatRename):
    with get_db() as db:
        _require_chat(db, chat_id)
        db.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (body.title, now_iso(), chat_id),
        )
        row = db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    return _chat_row(row)


@router.delete("/{chat_id}", summary="Delete a chat", status_code=204)
def delete_chat(chat_id: str):
    with get_db() as db:
        db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


@router.get("/{chat_id}/messages", summary="List messages for a chat")
def get_messages(chat_id: str):
    with get_db() as db:
        _require_chat(db, chat_id)
        rows = db.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    return [_msg_row(r) for r in rows]


@router.post("/{chat_id}/messages", summary="Append a message", status_code=201)
def add_message(chat_id: str, body: MessageIn):
    with get_db() as db:
        _require_chat(db, chat_id)
        history_json = json.dumps(body.full_history) if body.full_history is not None else None
        cursor = db.execute(
            "INSERT INTO messages (chat_id, role, content, full_history, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, body.role, body.content, history_json, body.status, now_iso()),
        )
        msg_id = cursor.lastrowid
        db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now_iso(), chat_id))
        row = db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    return _msg_row(row)


@router.patch("/{chat_id}/messages/{message_id}", summary="Update a message")
def patch_message(chat_id: str, message_id: int, body: MessagePatch):
    with get_db() as db:
        _require_chat(db, chat_id)
        msg = db.execute(
            "SELECT * FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)
        ).fetchone()
        if not msg:
            raise HTTPException(404, "Message not found")

        updates = {}
        if body.content is not None:
            updates["content"] = body.content
        if body.status is not None:
            updates["status"] = body.status
        if body.full_history is not None:
            updates["full_history"] = json.dumps(body.full_history)

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            db.execute(
                f"UPDATE messages SET {set_clause} WHERE id = ?",
                (*updates.values(), message_id),
            )
            db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now_iso(), chat_id))

        row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    return _msg_row(row)


@router.delete("/{chat_id}/messages/{message_id}", summary="Delete a message", status_code=204)
def delete_message(chat_id: str, message_id: int):
    with get_db() as db:
        db.execute("DELETE FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id))
