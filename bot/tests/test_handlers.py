import unittest
from unittest.mock import AsyncMock, MagicMock, ANY, patch
from .. import handlers
from pprint import pprint

from telegram import Location, PhotoSize

MOCK_PHOTOS = [
    (
        PhotoSize("1-22", "U1-22", 2, 2),
        PhotoSize("1-44", "U1-44", 4, 4),
        PhotoSize("1-88", "U1-88", 8, 8),
    ),
    (
        PhotoSize("2-22", "U2-22", 2, 2),
        PhotoSize("2-44", "U2-44", 4, 4),
        PhotoSize("2-88", "U2-88", 8, 8),
    ),
    (
        PhotoSize("3-22", "U3-22", 2, 2),
        PhotoSize("3-44", "U3-44", 4, 4),
        PhotoSize("3-88", "U3-88", 8, 8),
    ),
]

MOCK_CHAT_ID = 1
MOCK_USER_ID = 1
MOCK_MEDIA_GROUP_ID = 1
MOCK_MESSAGE_ID = 1
MOCK_PLANT_ID = {
    "result": {
        "classification": {
            "suggestions": [
                {
                    "probability": 0.8,
                    "name": "Squamosus Ridiculus",
                    "details": {
                        "url": {
                            "global": "https://www.gbif.org/species/000000",
                            "en": "https://en.wikipedia.org/wiki/Squamosus_Ridiculus",
                            "ru": None,
                            "ua": None,
                        }
                    },
                }
            ]
        }
    }
}


class TestHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        handlers.chat_locations.clear()

    @patch("telegram.Update", new_callable=AsyncMock)
    @patch("telegram.ext.CallbackContext", new_callable=AsyncMock)
    async def test10_start(
        self, mock_context: AsyncMock, mock_update: AsyncMock
    ) -> None:
        mock_update.message.text = "/start"
        mock_update.message.reply_text = AsyncMock()
        await handlers.handle_start(mock_update, mock_context)
        mock_update.message.reply_text.assert_awaited_once_with(
            text=ANY, parse_mode=ANY, reply_markup=ANY
        )

    @patch("telegram.Update", new_callable=AsyncMock)
    @patch("telegram.ext.CallbackContext", new_callable=AsyncMock)
    async def test20_location(
        self, mock_context: AsyncMock, mock_update: AsyncMock
    ) -> None:
        mock_update.message.location = Location(1.0, 1.0)
        mock_update.effective_chat.id = 1
        await handlers.handle_location(mock_update, mock_context)
        self.assertDictEqual(handlers.chat_locations, {1: Location(1.0, 1.0)})

    @patch("telegram.Update", new_callable=AsyncMock)
    @patch("telegram.ext.CallbackContext", new_callable=AsyncMock)
    async def test30_photo(
        self, mock_context: AsyncMock, mock_update: AsyncMock
    ) -> None:
        mock_update.message.location = Location(1.0, 1.0)
        mock_update.effective_chat.id = MOCK_CHAT_ID
        mock_update.effective_user.id = MOCK_USER_ID
        mock_update.message.media_group_id = MOCK_MEDIA_GROUP_ID
        mock_update.message.message_id = MOCK_MESSAGE_ID

        mock_update.message.photo = MOCK_PHOTOS[0]
        mock_context.job_queue.run_once = MagicMock()
        mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
        await handlers.handle_photo(mock_update, mock_context)
        mock_context.job_queue.run_once.assert_called_once_with(
            ANY,
            when=ANY,
            name=ANY,
            data=ANY,
            chat_id=mock_update.effective_chat.id,
            user_id=mock_update.effective_user.id,
        )
        job_name = mock_context.job_queue.run_once.call_args.kwargs["name"]

        mock_update.message.photo = MOCK_PHOTOS[1]
        mock_update.message.message_id = MOCK_MESSAGE_ID + 1
        job_obj = MagicMock()
        mock_update.message.photo = MOCK_PHOTOS[1]
        mock_context.job_queue.run_once = MagicMock()
        mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[job_obj])
        await handlers.handle_photo(mock_update, mock_context)
        mock_context.job_queue.get_jobs_by_name.assert_called_once_with(job_name)
        job_obj.schedule_removal.assert_called_once()
        mock_context.job_queue.run_once.assert_called_once_with(
            ANY,
            when=ANY,
            name=ANY,
            data=ANY,
            chat_id=mock_update.effective_chat.id,
            user_id=mock_update.effective_user.id,
        )
        job_callback = mock_context.job_queue.run_once.call_args.args[0]

    @patch("bot.handlers.identify_images", new_callable=AsyncMock)
    async def test40_batch_group_job(self, mock_identify_images: AsyncMock) -> None:
        mock_context = MagicMock()
        mock_context.job.user_id = MOCK_USER_ID
        mock_context.job.chat_id = MOCK_CHAT_ID
        mock_context.job.data = MOCK_MEDIA_GROUP_ID
        mock_context.bot.send_message = AsyncMock()
        mock_identify_images.return_value = MOCK_PLANT_ID
        await handlers.batch_group_job(mock_context)
        mock_identify_images.assert_called_once_with(
            mock_context,
            user_id=MOCK_USER_ID,
            photos=ANY,
            location=ANY,
            message_id=MOCK_MESSAGE_ID,
        )
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=MOCK_CHAT_ID,
            text=ANY,
            reply_markup=ANY,
            reply_to_message_id=ANY,
        )


if __name__ == "__main__":
    unittest.main()
