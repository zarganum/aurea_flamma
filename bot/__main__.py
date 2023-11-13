import os

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
)
from telegram.ext import filters

from motor.motor_asyncio import AsyncIOMotorClient

import logging

from . import db
from . import handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URL = os.getenv("MONGODB_URL")


async def app_post_init(application: Application) -> None:
    client = AsyncIOMotorClient(MONGODB_URL)
    application.bot_data["db_client"] = client
    await db.init(client)


async def app_post_shutdown(application: Application) -> None:
    application.bot_data["db_client"].close()


if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(app_post_init)
        .post_shutdown(app_post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(
        MessageHandler(filters.TEXT | filters.LOCATION, handlers.location)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handlers.photo))

    application.run_polling()
