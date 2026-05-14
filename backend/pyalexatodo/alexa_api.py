from http import HTTPMethod
from typing import TYPE_CHECKING

from aioamazondevices.api import AmazonEchoApi

from pyalexatodo.models.list_items_response import ListItem, ListItemsResponse

if TYPE_CHECKING:
    from aiohttp import ClientResponse


class AlexaToDoAPI:
    """A minimal Alexa API client for fetching todo list items."""

    def __init__(self, alexa_echo_api: AmazonEchoApi, list_id: str, base_url: str | None = None):
        """Initialize the Alexa To-Do API client.

        Args:
            alexa_echo_api: An authenticated AmazonEchoApi instance.
            list_id: The ID of the todo list to fetch items from.
            base_url: Base URL for API requests (for testing). If None, uses Amazon's URL.
        """
        self.alexa_echo_api = alexa_echo_api
        self.list_id = list_id
        self._base_url = base_url or f"https://www.amazon.{alexa_echo_api.domain}"

    async def _http_request(self, method: HTTPMethod, url: str, data: dict) -> "ClientResponse":
        _, response = await self.alexa_echo_api._http_wrapper.session_request(
            method=method, url=url, input_data=data, json_data=True,
        )
        return response

    async def get_all(self, limit: int = 100) -> list[ListItem]:
        """Fetch all items from the todo list. Call this whenever you need a fresh list.

        Args:
            limit: Max number of items to fetch per request (max 100).

        Returns:
            A list of all todo items.

        Raises:
            Exception: If the API request fails.
        """
        all_items: list[ListItem] = []
        next_token: str | None = None

        while True:
            url = f"{self._base_url}/alexashoppinglists/api/v2/lists/{self.list_id}/items/fetch?limit={limit}"
            body = {"nextToken": next_token} if next_token else {}

            result = await self._http_request(HTTPMethod.POST, url, body)

            if not result or result.status != 200:
                raise Exception(f"Failed to fetch list items for list: {self.list_id}")

            result_json = await result.json()
            response = ListItemsResponse(**result_json)
            all_items.extend(response.itemInfoList)

            next_token = response.nextToken
            if not next_token:
                break

        return all_items
