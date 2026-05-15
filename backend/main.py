import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger("alexa_api")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager
from http import HTTPMethod

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate, CannotConnect, CannotRetrieveData
from aiohttp import ClientSession
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# In-memory session store  (single-user, for local use)
# ---------------------------------------------------------------------------
_session: ClientSession | None = None
_login_data: dict | None = None
_credentials: dict | None = None  # {email, password, country_code}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session
    _session = ClientSession()
    yield
    if _session:
        await _session.close()


app = FastAPI(title="Alexa To-Do API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_echo_api() -> AmazonEchoApi:
    if not _session or not _login_data or not _credentials:
        raise HTTPException(status_code=401, detail="Not authenticated. Call /auth/login first.")
    return AmazonEchoApi(
        _session,
        _credentials["email"],
        _credentials["password"],
        _login_data,
    )


async def _amazon_request(echo_api: AmazonEchoApi, method: HTTPMethod, url: str, body: dict = {}):
    _, response = await echo_api._http_wrapper.session_request(
        method=method,
        url=url,
        input_data=body,
        json_data=True,
    )
    return response


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    otp: str
    country_code: str | None = None  # e.g. "com", "co.uk", "de"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------



@app.post("/auth/login")
async def login(body: LoginRequest):
    """Authenticate with Amazon using email, password, and OTP."""
    global _login_data, _credentials

    # Load from .env if not provided in request
    logger.debug("Body received - email: '%s', country: '%s', otp: '%s'", body.email, body.country_code, body.otp)
    logger.debug("Env vars - REACT_APP_AMAZON_EMAIL: '%s', REACT_APP_AMAZON_COUNTRY: '%s'", os.environ.get('REACT_APP_AMAZON_EMAIL'), os.environ.get('REACT_APP_AMAZON_COUNTRY'))
    email = os.environ.get("REACT_APP_AMAZON_EMAIL")
    password = os.environ.get("REACT_APP_AMAZON_PASSWORD")
    country_code = os.environ.get("REACT_APP_AMAZON_COUNTRY", "com")

    logger.debug("Attempting login - email: %s, country: %s", email, country_code)
    # Do NOT log password for security reasons

    if not email or not password:
        raise HTTPException(status_code=400, detail="Missing email or password (provide in .env or request body)")

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

    _login_data = login_data
    _credentials = {
        "email": email,
        "password": password,
        "country_code": country_code,
    }

    logger.info("Login successful for %s", email)
    return {"status": "ok"}


@app.get("/lists")
async def get_lists():
    """Return all Alexa shopping/todo lists."""
    echo_api = _make_echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"
    response = await _amazon_request(echo_api, HTTPMethod.POST, f"{base_url}/alexashoppinglists/api/v2/lists/fetch")
    return await response.json()


@app.get("/lists/{list_id}/items")
async def get_list_items(list_id: str):
    """Return all items in a given list, handling pagination."""
    echo_api = _make_echo_api()
    base_url = f"https://www.amazon.{echo_api.domain}"

    all_items = []
    next_token: str | None = None

    while True:
        body = {"nextToken": next_token} if next_token else {}
        try:
            response = await _amazon_request(
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



