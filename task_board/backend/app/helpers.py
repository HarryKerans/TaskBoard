import os
import sqlite3
import logging
from dataclasses import dataclass
from http import HTTPMethod
from pathlib import Path

from aioamazondevices.api import AmazonEchoApi
from fastapi import HTTPException

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "tasks.db")))


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

logger = logging.getLogger("alexa_api")


@dataclass(frozen=True)
class Settings:
    database_path: str
    amazon_email: str | None
    amazon_password: str | None
    amazon_country: str | None


def get_settings() -> Settings:
    return Settings(
        database_path=os.getenv("DATABASE_PATH") or str(Path(__file__).parent.parent / "data" / "tasks.db"),
        amazon_email=os.getenv("REACT_APP_AMAZON_EMAIL"),
        amazon_password=os.getenv("REACT_APP_AMAZON_PASSWORD"),
        amazon_country=os.getenv("REACT_APP_AMAZON_COUNTRY"),
    )


def make_echo_api(session, login_data, credentials) -> AmazonEchoApi:
    if not session or not login_data or not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated. Call /auth/login first.")
    return AmazonEchoApi(
        session,
        credentials["email"],
        credentials["password"],
        login_data,
    )


async def amazon_request(echo_api: AmazonEchoApi, method: HTTPMethod, url: str, body: dict = {}):
    _, response = await echo_api._http_wrapper.session_request(
        method=method,
        url=url,
        input_data=body,
        json_data=True,
    )
    return response
