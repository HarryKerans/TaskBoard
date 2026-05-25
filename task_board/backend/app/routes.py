import logging
import time
from http import HTTPMethod
from typing import Any

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate, CannotConnect, CannotRetrieveData
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.helpers import amazon_request, make_echo_api, get_settings, get_connection

logger = logging.getLogger("alexa_api")

router = APIRouter()

# Shared state — set by main.py at startup and after login
_session = None
_login_data = None
_credentials = None

# In-memory TTL cache for Alexa API responses (keyed by route)
_CACHE_TTL = 3600  # seconds (1 hour)
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, data: Any) -> None:
    _cache[key] = (time.monotonic(), data)


def _cache_clear() -> None:
    _cache.clear()


def _sync_alexa_items_to_db(list_id: str, items: list[dict]) -> list[dict]:
    """Upsert Alexa items into the local DB, storing Alexa metadata for rename support.

    Also marks any open Alexa-sourced tasks as done if they no longer appear in the
    live list — meaning they were completed from another device (phone, Echo, etc.).

    Returns a list of {item_id, list_id, version} dicts for items that are locally
    'done' but still active in Alexa, so the caller can reconcile them.
    """
    live_item_ids = {item.get("itemId") for item in items if item.get("itemId")}

    with get_connection() as conn:
        # Index existing alexa tasks by alexa_item_id, including their status
        existing_by_alexa_id: dict[str, dict] = {
            row["alexa_item_id"]: dict(row)
            for row in conn.execute(
                "SELECT id, alexa_item_id, status, alexa_version FROM tasks "
                "WHERE source_type = 'alexa' AND alexa_item_id IS NOT NULL"
            ).fetchall()
        }
        # Also track all titles for dedup on insert
        existing_titles = {
            row[0].lower()
            for row in conn.execute("SELECT title FROM tasks").fetchall()
        }
        new_count = 0
        needs_alexa_completion: list[dict] = []

        for item in items:
            raw_title = item.get("itemName", "").strip()
            item_id = item.get("itemId", "")
            version = item.get("version")
            if not raw_title or not item_id:
                continue
            title = raw_title[:1].upper() + raw_title[1:]

            if item_id in existing_by_alexa_id:
                local = existing_by_alexa_id[item_id]
                if local["status"] == "done":
                    # Task was completed locally (offline) but is still active in Alexa
                    needs_alexa_completion.append(
                        {"item_id": item_id, "list_id": list_id, "version": version}
                    )
                else:
                    # Update version and title in case they changed on the Alexa side
                    conn.execute(
                        "UPDATE tasks SET title = ?, alexa_version = ?, alexa_list_id = ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE alexa_item_id = ?",
                        (title, version, list_id, item_id),
                    )
            elif title.lower() in existing_titles:
                # Pre-metadata row — backfill alexa columns
                conn.execute(
                    "UPDATE tasks SET alexa_item_id = ?, alexa_list_id = ?, alexa_version = ? "
                    "WHERE lower(title) = lower(?) AND source_type = 'alexa'",
                    (item_id, list_id, version, title),
                )
            else:
                conn.execute(
                    "INSERT INTO tasks (title, status, priority, source_type, alexa_item_id, alexa_list_id, alexa_version) "
                    "VALUES (?, 'open', 'medium', 'alexa', ?, ?, ?)",
                    (title, item_id, list_id, version),
                )
                existing_titles.add(title.lower())
                new_count += 1

        # Mark done any open Alexa tasks that are no longer in the live list —
        # they were completed from another device since the last sync.
        closed = conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = CURRENT_TIMESTAMP "
            "WHERE source_type = 'alexa' AND status = 'open' "
            "AND alexa_item_id IS NOT NULL AND alexa_item_id NOT IN ({}) "
            "RETURNING alexa_item_id".format(",".join("?" * len(live_item_ids))),
            list(live_item_ids),
        ).fetchall() if live_item_ids else []

        conn.commit()

    if closed:
        logger.debug("Marked %d Alexa task(s) done (completed elsewhere): %s",
                     len(closed), [r[0] for r in closed])
    logger.debug("Synced %d new Alexa items to local DB", new_count)
    return needs_alexa_completion


def set_state(session, login_data, credentials):
    global _session, _login_data, _credentials
    _session = session
    _login_data = login_data
    _credentials = credentials


def _echo_api() -> AmazonEchoApi:
    return make_echo_api(_session, _login_data, _credentials)


def _is_authenticated() -> bool:
    return _session is not None and _login_data is not None and _credentials is not None


@router.get("/auth/status")
async def auth_status():
    """Check whether a valid session already exists."""
    return {"authenticated": _is_authenticated()}

class LoginRequest(BaseModel):
    otp: str
    
@router.post("/auth/login")
async def login(body: LoginRequest):
    """Authenticate with Amazon using email, password, and OTP."""
    global _login_data, _credentials

    logger.debug("Login attempt - otp provided: %s", bool(body.otp))

    settings = get_settings()
    email = settings.amazon_email
    password = settings.amazon_password
    country_code = settings.amazon_country or "com"

    logger.debug("Attempting login - email: %s, country: %s", email, country_code)

    if not email or not password:
        raise HTTPException(status_code=400, detail="Missing email or password (provide in .env)")

    api = AmazonEchoApi(_session, email, password)
    try:
        login_data = await api.login.login_mode_interactive(body.otp)
    except CannotAuthenticate as e:
        logger.error("CannotAuthenticate: %s", e)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    except CannotConnect as e:
        logger.error("CannotConnect: %s", e)
        raise HTTPException(status_code=503, detail=f"Could not connect to Amazon: {e}")
    except Exception as e:
        logger.exception("Unexpected error during login")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    set_state(_session, login_data, {
        "email": email,
        "password": password,
        "country_code": country_code,
    })
    _cache_clear()

    logger.info("Login successful for %s", email)
    return {"status": "ok"}


@router.get("/lists")
async def get_lists():
    """Return all Alexa shopping/todo lists (cached for 1 hour)."""
    cached = _cache_get("lists")
    if cached is not None:
        logger.debug("Returning cached lists")
        return cached

    echo_api = _echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"
    response = await amazon_request(echo_api, HTTPMethod.POST, f"{base_url}/alexashoppinglists/api/v2/lists/fetch")
    data = await response.json()
    _cache_set("lists", data)
    return data


@router.get("/lists/{list_id}/items")
async def get_list_items(list_id: str):
    """Return all items in a given list, handling pagination (cached for 1 hour)."""
    cache_key = f"items:{list_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Returning cached items for list %s", list_id)
        return cached

    echo_api = _echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"

    all_items = []
    next_token: str | None = None

    while True:
        body = {"nextToken": next_token} if next_token else {}
        try:
            response = await amazon_request(
                echo_api,
                HTTPMethod.POST,
                f"{base_url}/alexashoppinglists/api/v2/lists/{list_id}/items/fetch?limit=100",
                body,
            )
        except CannotRetrieveData as e:
            raise HTTPException(status_code=400, detail=str(e))

        data = await response.json()
        all_items.extend(data.get("itemInfoList", []))
        next_token = data.get("nextToken")
        if not next_token:
            break

    needs_completion = _sync_alexa_items_to_db(list_id, all_items)

    # Reconcile offline completions: push to Alexa any tasks marked done locally
    # while we didn't have an active session.
    if needs_completion:
        echo_api = _echo_api()
        base_url = f"https://www.amazon.{echo_api.domain}"
        for pending in needs_completion:
            try:
                await amazon_request(
                    echo_api,
                    HTTPMethod.PUT,
                    f"{base_url}/alexashoppinglists/api/v2/lists/{pending['list_id']}/items/{pending['item_id']}?version={pending['version']}",
                    {"itemAttributesToUpdate": [{"type": "itemStatus", "value": "COMPLETE"}], "itemAttributesToRemove": []},
                )
                logger.info("Reconciled offline completion of Alexa item %s", pending["item_id"])
            except Exception as exc:
                logger.warning("Could not reconcile Alexa completion for %s: %s", pending["item_id"], exc)

    _cache_set(cache_key, all_items)
    return all_items


@router.patch("/lists/{list_id}/items/{item_id}")
async def mark_alexa_item_done(list_id: str, item_id: str, body: dict):
    """Mark an Alexa list item as complete."""
    version = body.get("version")
    if version is None:
        raise HTTPException(status_code=400, detail="version is required")
    echo_api = _echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"
    response = await amazon_request(
        echo_api,
        HTTPMethod.PUT,
        f"{base_url}/alexashoppinglists/api/v2/lists/{list_id}/items/{item_id}?version={version}",
        {
            "itemAttributesToUpdate": [{"type": "itemStatus", "value": "COMPLETE"}],
            "itemAttributesToRemove": [],
        },
    )
    if response.status >= 300:
        body = await response.text()
        logger.error("Amazon mark-done failed: status=%s body=%s", response.status, body)
        raise HTTPException(status_code=response.status, detail="Failed to mark Alexa item as done")

    # Mirror the completion in the local DB so the record doesn't stay stale
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE alexa_item_id = ?",
            (item_id,),
        )
        conn.commit()

    logger.info("Marked Alexa item %s in list %s as done (status %s)", item_id, list_id, response.status)
    return {"status": "ok"}


@router.patch("/api/tasks/{task_id}")
async def update_task_status(task_id: int) -> dict[str, Any]:
    """Mark a local task as done. If it is Alexa-sourced and we are authenticated,
    also complete it in Alexa immediately so it doesn't reappear on the next sync."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, source_type, alexa_item_id, alexa_list_id, alexa_version FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    row = dict(row)
    if (
        row["source_type"] == "alexa"
        and _is_authenticated()
        and row["alexa_item_id"]
        and row["alexa_list_id"]
        and row["alexa_version"] is not None
    ):
        echo_api = _echo_api()
        base_url = f"https://www.amazon.{echo_api.domain}"
        try:
            response = await amazon_request(
                echo_api,
                HTTPMethod.PUT,
                f"{base_url}/alexashoppinglists/api/v2/lists/{row['alexa_list_id']}/items/{row['alexa_item_id']}?version={row['alexa_version']}",
                {"itemAttributesToUpdate": [{"type": "itemStatus", "value": "COMPLETE"}], "itemAttributesToRemove": []},
            )
            if response.status < 300:
                logger.info("Marked Alexa item %s done from local task %s", row["alexa_item_id"], task_id)
                _cache.pop(f"items:{row['alexa_list_id']}", None)
            else:
                logger.warning("Alexa mark-done returned %s for item %s", response.status, row["alexa_item_id"])
        except Exception as exc:
            logger.warning("Could not mark Alexa item %s done: %s", row["alexa_item_id"], exc)
        # Local DB is always updated regardless of Alexa result

    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT id, title, description, status, priority, source_type, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    return dict(updated)


class TaskUpdate(BaseModel):
    title: str
    description: str = ''
    priority: str = 'medium'


@router.put("/api/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate) -> dict[str, Any]:
    """Update a task's title, description, and priority.
    If the task is Alexa-sourced and the title changed, also rename it in Alexa."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, title, source_type, alexa_item_id, alexa_list_id, alexa_version FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    row = dict(row)
    title_changed = row["title"] != update.title
    new_alexa_version = row["alexa_version"]

    if row["source_type"] == "alexa" and title_changed:
        alexa_item_id = row["alexa_item_id"]
        alexa_list_id = row["alexa_list_id"]
        alexa_version = row["alexa_version"]

        if not alexa_item_id or not alexa_list_id or alexa_version is None:
            raise HTTPException(
                status_code=409,
                detail="Cannot rename Alexa item: missing metadata — open the app to trigger a sync first",
            )
        if not _is_authenticated():
            raise HTTPException(
                status_code=401,
                detail="Not authenticated with Alexa — cannot rename Alexa item",
            )

        echo_api = _echo_api()
        base_url = f"https://www.amazon.{echo_api.domain}"
        response = await amazon_request(
            echo_api,
            HTTPMethod.PUT,
            f"{base_url}/alexashoppinglists/api/v2/lists/{alexa_list_id}/items/{alexa_item_id}?version={alexa_version}",
            {
                "itemAttributesToUpdate": [{"type": "itemName", "value": update.title}],
                "itemAttributesToRemove": [],
            },
        )
        if response.status >= 300:
            err_body = await response.text()
            logger.error("Alexa rename failed: status=%s body=%s", response.status, err_body)
            raise HTTPException(status_code=response.status, detail="Failed to rename item in Alexa")

        logger.info("Renamed Alexa item %s to %r (list %s)", alexa_item_id, update.title, alexa_list_id)
        new_alexa_version = alexa_version + 1
        # Invalidate the list cache so the next fetch returns fresh data
        _cache.pop(f"items:{alexa_list_id}", None)

    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET title = ?, description = ?, priority = ?, alexa_version = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (update.title, update.description, update.priority.lower(), new_alexa_version, task_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT id, title, description, status, priority, source_type, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    return dict(updated)
