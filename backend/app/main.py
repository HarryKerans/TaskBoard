import os
import sqlite3
from pathlib import Path
from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from aiohttp import ClientSession
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routes import router, set_state

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

BUILD_DIR = Path(__file__).parent.parent / "build"

@asynccontextmanager
async def lifespan(app: FastAPI):
    session = ClientSession()
    set_state(session, None, None)
    yield
    await session.close()


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/data/tasks.db"))
app = FastAPI(title="Task Dashboard", lifespan=lifespan)
app.include_router(router)

class TaskCreate(BaseModel):
    title: str
    priority: str = 'medium'


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'medium',
                source_type TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


@app.on_event("startup")
def on_startup() -> None:
    initialise_database()


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
            SELECT id, title, status, priority, source_type, created_at, updated_at
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
            SELECT id, title, status, priority, source_type, created_at, updated_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

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