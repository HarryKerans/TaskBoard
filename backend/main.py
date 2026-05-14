import json
from contextlib import asynccontextmanager

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate, CannotConnect, CannotRetrieveData
from aiohttp import ClientSession
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pyalexatodo.alexa_api import AlexaToDoAPI
from pyalexatodo.api import AlexaToDoAPI as FullAlexaToDoAPI

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


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str
    otp: str
    country_code: str = "com"  # e.g. "com", "co.uk", "de"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/auth/login")
async def login(body: LoginRequest):
    """Authenticate with Amazon using email, password, and OTP."""
    global _login_data, _credentials

    api = AmazonEchoApi(_session, body.email, body.password)
    try:
        login_data = await api.login.login_mode_interactive(body.otp)
    except CannotAuthenticate as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    except CannotConnect as e:
        raise HTTPException(status_code=503, detail=f"Could not connect to Amazon: {e}")

    _login_data = login_data
    _credentials = {
        "email": body.email,
        "password": body.password,
        "country_code": body.country_code,
    }

    return {"status": "ok"}


@app.get("/lists")
async def get_lists():
    """Return all Alexa shopping/todo lists."""
    echo_api = _make_echo_api()
    api = FullAlexaToDoAPI(echo_api)
    lists = await api.get_lists()
    return [{"listId": lst.id, "name": lst.name} for lst in lists]


@app.get("/lists/{list_id}/items")
async def get_list_items(list_id: str):
    """Return all items in a given list."""
    echo_api = _make_echo_api()
    api = AlexaToDoAPI(echo_api, list_id)
    try:
        items = await api.get_all()
    except CannotRetrieveData as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [{"itemId": item.id, "value": item.name, "status": item.status.value, "version": item.version} for item in items]
