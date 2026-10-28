from unittest import IsolatedAsyncioTestCase

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from yarl import URL

from app.helpers import create_echo_api


class LoginUrlResolutionTest(IsolatedAsyncioTestCase):
    async def test_relative_login_action_is_resolved_against_page_url(self):
        async with ClientSession() as session:
            echo_api = create_echo_api(
                session,
                "user@example.invalid",
                "not-used",
            )
            form = BeautifulSoup(
                '<form method="post" action="/ax/claim?token=test"></form>',
                "html.parser",
            )
            method, action = echo_api.login._get_request_from_soup(
                form,
                URL("https://www.amazon.com/ap/signin"),
            )

        self.assertEqual(method, "post")
        self.assertEqual(str(action), "https://www.amazon.com/ax/claim?token=test")