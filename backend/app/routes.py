import logging
from http import HTTPMethod

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate, CannotConnect, CannotRetrieveData
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.helpers import amazon_request, make_echo_api, get_settings

logger = logging.getLogger("alexa_api")

router = APIRouter()

# Shared state — set by main.py at startup and after login
_session = None
_login_data = None
_credentials = None


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

    logger.info("Login successful for %s", email)
    return {"status": "ok"}


@router.get("/lists")
async def get_lists():
    """Return all Alexa shopping/todo lists."""
    echo_api = _echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"
    response = await amazon_request(echo_api, HTTPMethod.POST, f"{base_url}/alexashoppinglists/api/v2/lists/fetch")
    return await response.json()


@router.get("/lists/{list_id}/items")
async def get_list_items(list_id: str):
    """Return all items in a given list, handling pagination."""
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

    return all_items
