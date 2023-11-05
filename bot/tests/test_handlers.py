import unittest
from unittest.mock import AsyncMock, ANY, patch
from .. import handlers
from pprint import pprint

from telegram import Location


class TestHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        handlers.chat_locations.clear()

    @patch("telegram.Update", new_callable=AsyncMock)
    @patch("telegram.ext.CallbackContext", new_callable=AsyncMock)
    async def test_start(self, mock_context: AsyncMock, mock_update: AsyncMock) -> None:
        mock_update.message.text = "/start"
        mock_update.message.reply_text = AsyncMock()
        await handlers.handle_start(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_once_with(
            text=ANY, parse_mode=ANY, reply_markup=ANY
        )

    @patch("telegram.Update", new_callable=AsyncMock)
    @patch("telegram.ext.CallbackContext", new_callable=AsyncMock)
    async def test_location(
        self, mock_context: AsyncMock, mock_update: AsyncMock
    ) -> None:
        mock_update.message.location = Location(1.0, 1.0)
        mock_update.effective_chat.id = 1
        await handlers.handle_location(mock_update, mock_context)
        self.assertDictEqual(handlers.chat_locations, {1: Location(1.0, 1.0)})


if __name__ == "__main__":
    unittest.main()
