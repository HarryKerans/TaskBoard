import logging
from http import HTTPMethod

from aioamazondevices.api import AmazonEchoApi
from fastapi import HTTPException

logger = logging.getLogger("alexa_api")


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
