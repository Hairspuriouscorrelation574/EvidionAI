"""
Projects API.

GET    /projects               list all projects
POST   /projects               create
PUT    /projects/{id}          rename
DELETE /projects/{id}          delete (cascades to chats and messages)
GET    /projects/{id}/chats    list chats inside a project
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.database import get_db, now_iso

router = APIRouter()


class ProjectIn(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=200)


class ProjectRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.get("", summary="List all projects")
def list_projects():
    with get_db() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("", summary="Create a project", status_code=201)
def create_project(body: ProjectIn):
    pid = body.id or str(uuid.uuid4())
    ts = now_iso()
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO projects (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (pid, body.title, ts, ts),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    return dict(row)


@router.put("/{project_id}", summary="Rename a project")
def rename_project(project_id: str, body: ProjectRename):
    with get_db() as db:
        db.execute(
            "UPDATE projects SET title = ?, updated_at = ? WHERE id = ?",
            (body.title, now_iso(), project_id),
        )
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


@router.delete("/{project_id}", summary="Delete a project", status_code=204)
def delete_project(project_id: str):
    with get_db() as db:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))


@router.get("/{project_id}/chats", summary="List chats inside a project")
def list_project_chats(project_id: str):
    with get_db() as db:
        if not db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        rows = db.execute(
            "SELECT c.*, "
            "(SELECT content FROM messages WHERE chat_id=c.id AND role='user' ORDER BY id LIMIT 1)"
            " AS first_query "
            "FROM chats c WHERE c.project_id = ? ORDER BY c.updated_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]
