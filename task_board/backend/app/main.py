import sqlite3
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv, find_dotenv
from aiohttp import ClientSession
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routes import router, set_state
from app.helpers import DATABASE_PATH, get_connection

# find_dotenv() walks up the directory tree to find a .env file, so local dev
# works regardless of where .env lives. override=False (default) means real
# env vars set by HA's run.sh always take precedence over the file.
load_dotenv(find_dotenv(usecwd=True), override=False)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

BUILD_DIR = Path(__file__).parent.parent / "build"

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise_database()
    session = ClientSession()
    set_state(session, None, None)
    yield
    await session.close()


app = FastAPI(title="Task Dashboard", lifespan=lifespan)
app.include_router(router)

class TaskCreate(BaseModel):
    title: str
    priority: str = 'medium'



def initialise_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'medium',
                source_type TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migrate existing databases that predate the description column
        try:
            connection.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        connection.commit()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "database_path": str(DATABASE_PATH),
        "database_parent_exists": DATABASE_PATH.parent.exists(),
        "database_exists": DATABASE_PATH.exists(),
        "database_size_bytes": DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0,
    }

@app.get("/api/tasks")
def list_tasks() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, description, status, priority, source_type, created_at, updated_at
            FROM tasks
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


@app.post("/api/tasks")
def create_task(task: TaskCreate) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tasks (title, status, priority, source_type)
            VALUES (?, 'open', ?, 'manual')
            """,
            (task.title, task.priority.lower()),
        )

        task_id = cursor.lastrowid

        row = connection.execute(
            """
            SELECT id, title, description, status, priority, source_type, created_at, updated_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

    return dict(row)


@app.patch("/api/tasks/{task_id}")
def update_task_status(task_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id, title, description, status, priority, source_type, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)


class TaskUpdate(BaseModel):
    title: str
    description: str = ''
    priority: str = 'medium'


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate) -> dict[str, Any]:
    with get_connection() as connection:
        connection.execute(
            "UPDATE tasks SET title = ?, description = ?, priority = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (update.title, update.description, update.priority.lower(), task_id),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id, title, description, status, priority, source_type, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"

if FRONTEND_DIST.exists():
    static_dir = FRONTEND_DIST / "static"

    if static_dir.exists():
        app.mount(
            "/static",
            StaticFiles(directory=static_dir),
            name="static",
        )

    @app.get("/{full_path:path}")
    def serve_react_app(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "message": "Task Dashboard API is running",
            "frontend": "not built yet",
            "expected_frontend_path": str(FRONTEND_DIST),
        }