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


def _sync_alexa_items_to_db(items: list[dict]) -> None:
    """Insert Alexa items into the local DB, skipping titles that already exist."""
    with get_connection() as conn:
        existing = {
            row[0].lower()
            for row in conn.execute("SELECT title FROM tasks").fetchall()
        }
        new_count = 0
        for item in items:
            raw_title = item.get("itemName", "").strip()
            if not raw_title:
                continue
            title = raw_title[:1].upper() + raw_title[1:]
            if title.lower() in existing:
                continue
            conn.execute(
                "INSERT INTO tasks (title, status, priority, source_type) VALUES (?, 'open', 'medium', 'alexa')",
                (title,),
            )
            existing.add(title.lower())
            new_count += 1
        conn.commit()
    logger.debug("Synced %d new Alexa items to local DB", new_count)


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

    _sync_alexa_items_to_db(all_items)
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
    logger.info("Marked Alexa item %s in list %s as done (status %s)", item_id, list_id, response.status)
    return {"status": "ok"}
