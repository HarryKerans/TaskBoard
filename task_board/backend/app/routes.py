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


def _sync_alexa_items_to_db(list_id: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Upsert Alexa items into the local DB, storing Alexa metadata for rename support.

    Also marks any open Alexa-sourced tasks as done if they no longer appear in the
    live list — meaning they were completed from another device (phone, Echo, etc.).

    Returns a tuple of:
      - needs_completion: [{item_id, list_id, version}] locally-done items still active in Alexa
      - needs_rename:     [{item_id, list_id, version, new_title}] locally-renamed items to push
    """
    live_item_ids = {item.get("itemId") for item in items if item.get("itemId")}

    with get_connection() as conn:
        # Index existing alexa tasks by alexa_item_id, including their status and title
        existing_by_alexa_id: dict[str, dict] = {
            row["alexa_item_id"]: dict(row)
            for row in conn.execute(
                "SELECT id, title, alexa_item_id, status, alexa_version FROM tasks "
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
        needs_alexa_rename: list[dict] = []

        for item in items:
            raw_title = item.get("itemName", "").strip()
            item_id = item.get("itemId", "")
            version = item.get("version")
            if not raw_title or not item_id:
                continue
            alexa_title = raw_title[:1].upper() + raw_title[1:]

            if item_id in existing_by_alexa_id:
                local = existing_by_alexa_id[item_id]
                if local["status"] == "done":
                    # Task was completed locally (offline) but is still active in Alexa
                    needs_alexa_completion.append(
                        {"item_id": item_id, "list_id": list_id, "version": version}
                    )
                elif local["title"] != alexa_title:
                    # Title differs — local edit takes priority; push rename to Alexa
                    needs_alexa_rename.append(
                        {"item_id": item_id, "list_id": list_id, "version": version, "new_title": local["title"]}
                    )
                    # Only update version metadata, not the title
                    conn.execute(
                        "UPDATE tasks SET alexa_version = ?, alexa_list_id = ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE alexa_item_id = ?",
                        (version, list_id, item_id),
                    )
                else:
                    # In sync — update version in case it incremented on Alexa side
                    conn.execute(
                        "UPDATE tasks SET alexa_version = ?, alexa_list_id = ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE alexa_item_id = ?",
                        (version, list_id, item_id),
                    )
            elif alexa_title.lower() in existing_titles:
                # Pre-metadata row — backfill alexa columns
                conn.execute(
                    "UPDATE tasks SET alexa_item_id = ?, alexa_list_id = ?, alexa_version = ? "
                    "WHERE lower(title) = lower(?) AND source_type = 'alexa'",
                    (item_id, list_id, version, alexa_title),
                )
            else:
                conn.execute(
                    "INSERT INTO tasks (title, status, priority, source_type, alexa_item_id, alexa_list_id, alexa_version) "
                    "VALUES (?, 'open', 'medium', 'alexa', ?, ?, ?)",
                    (alexa_title, item_id, list_id, version),
                )
                existing_titles.add(alexa_title.lower())
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
    if needs_alexa_rename:
        logger.debug("%d offline rename(s) queued to push to Alexa", len(needs_alexa_rename))
    logger.debug("Synced %d new Alexa items to local DB", new_count)
    return needs_alexa_completion, needs_alexa_rename


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


@router.post("/api/sync")
async def sync_alexa():
    """Fetch the Alexa TODO list and sync all items into the local DB.
    Returns a summary of how many open tasks are now in the DB."""
    if not _is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated. Call /auth/login first.")

    echo_api = _echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"

    # Fetch lists (use cache if available)
    cached_lists = _cache_get("lists")
    if cached_lists is not None:
        lists_data = cached_lists
    else:
        response = await amazon_request(echo_api, HTTPMethod.POST, f"{base_url}/alexashoppinglists/api/v2/lists/fetch")
        lists_data = await response.json()
        _cache_set("lists", lists_data)

    todo_list = next(
        (l for l in lists_data.get("listInfoList", []) if l.get("listType") == "TODO"),
        None,
    )
    if not todo_list:
        return {"synced": 0, "message": "No TODO list found"}

    list_id = todo_list["listId"]

    # Fetch all items, bypassing cache so we always get fresh data on an explicit sync
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

    # Only sync active (non-complete) items
    active_items = [i for i in all_items if i.get("itemStatus") != "COMPLETE"]
    needs_completion, needs_rename = _sync_alexa_items_to_db(list_id, active_items)
    _cache_set(f"items:{list_id}", active_items)

    # Reconcile any tasks marked done locally while offline
    if needs_completion:
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

    # Reconcile any tasks renamed locally while offline — push new title to Alexa
    for pending in needs_rename:
        try:
            await amazon_request(
                echo_api,
                HTTPMethod.PUT,
                f"{base_url}/alexashoppinglists/api/v2/lists/{pending['list_id']}/items/{pending['item_id']}?version={pending['version']}",
                {"itemAttributesToUpdate": [{"type": "itemName", "value": pending["new_title"]}], "itemAttributesToRemove": []},
            )
            logger.info("Reconciled offline rename of Alexa item %s → '%s'", pending["item_id"], pending["new_title"])
        except Exception as exc:
            logger.warning("Could not reconcile rename for Alexa item %s: %s", pending["item_id"], exc)

    logger.info("Sync complete: %d active Alexa items", len(active_items))
    return {"synced": len(active_items)}

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

    needs_completion, needs_rename = _sync_alexa_items_to_db(list_id, all_items)

    # Reconcile offline completions: push to Alexa any tasks marked done locally
    # while we didn't have an active session.
    if needs_completion or needs_rename:
        echo_api_reconcile = _echo_api()
        base_url_reconcile = f"https://www.amazon.{echo_api_reconcile.domain}"
        for pending in needs_completion:
            try:
                await amazon_request(
                    echo_api_reconcile,
                    HTTPMethod.PUT,
                    f"{base_url_reconcile}/alexashoppinglists/api/v2/lists/{pending['list_id']}/items/{pending['item_id']}?version={pending['version']}",
                    {"itemAttributesToUpdate": [{"type": "itemStatus", "value": "COMPLETE"}], "itemAttributesToRemove": []},
                )
                logger.info("Reconciled offline completion of Alexa item %s", pending["item_id"])
            except Exception as exc:
                logger.warning("Could not reconcile Alexa completion for %s: %s", pending["item_id"], exc)
        for pending in needs_rename:
            try:
                await amazon_request(
                    echo_api_reconcile,
                    HTTPMethod.PUT,
                    f"{base_url_reconcile}/alexashoppinglists/api/v2/lists/{pending['list_id']}/items/{pending['item_id']}?version={pending['version']}",
                    {"itemAttributesToUpdate": [{"type": "itemName", "value": pending["new_title"]}], "itemAttributesToRemove": []},
                )
                logger.info("Reconciled offline rename of Alexa item %s → '%s'", pending["item_id"], pending["new_title"])
            except Exception as exc:
                logger.warning("Could not reconcile rename for Alexa item %s: %s", pending["item_id"], exc)

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
    created_at: str | None = None  # ISO datetime string; only updated if provided


@router.put("/api/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate) -> dict[str, Any]:
    """Update a task's title, description, priority, and optionally created_at.
    If the task is Alexa-sourced and the title changed, attempt to rename it in Alexa
    immediately (requires an active session). If not authenticated the local DB is
    updated anyway — the next sync will push the rename to Alexa."""
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

        if _is_authenticated() and alexa_item_id and alexa_list_id and alexa_version is not None:
            # Online: push rename to Alexa immediately
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
            _cache.pop(f"items:{alexa_list_id}", None)
        else:
            # Offline: save locally — sync on next login will push the rename to Alexa
            logger.info(
                "Offline edit: renamed Alexa task %d locally to %r — will sync to Alexa on next login",
                task_id, update.title,
            )

    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET title = ?, description = ?, priority = ?, alexa_version = ?,"
            " created_at = COALESCE(?, created_at), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (update.title, update.description, update.priority.lower(), new_alexa_version, update.created_at, task_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT id, title, description, status, priority, source_type, created_at, updated_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    return dict(updated)
