from typing import Tuple
import certifi
import os

from telegram import Update, User
from telegram import ReplyKeyboardMarkup, KeyboardButton, PhotoSize, Location
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
)
from telegram.ext import filters

from aioplantid_sdk import Configuration, ApiClient, DefaultApi as PlantIdApi

import logging
import json
from pprint import pformat


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")

GALLERY_TIMEOUT = 1
media_groups = {}
chat_locations = {}
configuration = Configuration(
    host="https://plant.id/api/v3",
    ssl_ca_cert=certifi.where(),
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user: User = update.message.from_user
    logging.info(f"from_user:\n{pformat(user, indent=2)}")
    user_info = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "language_code": user.language_code,
    }

    logging.info(f"job_queue: {pformat(context.job_queue, indent=2)}")

    formatted_user_info = json.dumps(user_info, indent=2)
    response_text = f"User Info:\n```\n{formatted_user_info}\n```"

    location_keyboard = [
        [
            KeyboardButton(text="Send Location", request_location=True),
            KeyboardButton(text="No Location"),
        ]
    ]
    reply_markup = ReplyKeyboardMarkup(
        location_keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=response_text, parse_mode="Markdown"
    )

    await update.message.reply_text(
        text="For accuracy I need your location:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def handle_location(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    global chat_locations
    if update.message.location:
        # Handle location
        logging.info(
            f"Received location:\n{pformat(update.message.location, indent=2)}"
        )
        latitude = update.message.location.latitude
        longitude = update.message.location.longitude
        chat_locations[update.effective_chat.id] = update.message.location
        await update.message.reply_text(
            f"Received location: Latitude {latitude}, Longitude {longitude}"
        )
    elif update.message.text == "No Location":
        # Handle refusal to send location
        chat_locations[update.effective_chat.id] = None
        await update.message.reply_text(
            "That's okay! However the quality might suffer."
        )
    # else:
    #     # Handle any other message
    #     await update.message.reply_text(
    #         "Please send your location or let me know if you don't want to."
    #     )


async def identify_images(photos: Tuple[PhotoSize, ...], location: Location = None):
    logging.info(
        f"\nIdentify images:\n{pformat(photos, indent=2)}\n{pformat(location, indent=2)})\n"
    )
    async with ApiClient(configuration) as api_client:
        api_client.set_default_header("Content-Type", "application/json")
        api_client.set_default_header("Api-Key", PLANT_ID_API_KEY)
        api = PlantIdApi(api_client)


async def batch_group(context: ContextTypes.DEFAULT_TYPE) -> None:
    global media_groups, chat_locations
    logging.debug(f"Batch group: {context.job.data}")
    await identify_images(
        media_groups[context.job.data],
        location=chat_locations.get(context.job.chat_id, None),
    )
    media_groups[context.job.data] = None


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global media_groups
    if update.message.photo:
        logging.debug(f"\nReceived photo:\n{pformat(update.message.photo, indent=2)}\n")
        # logging.info(f"job_queue: {pformat(context.job_queue, indent=2)}")
        if update.message.media_group_id:
            group_id = update.message.media_group_id
            chat_id = update.effective_chat.id
            logging.debug(f"Media group: {group_id}")
            if group_id not in media_groups:
                media_groups[group_id] = []
            media_groups[group_id].append(update.message.photo)
            job_name = f"gal:{chat_id}"
            jobs = context.job_queue.get_jobs_by_name(job_name)
            if jobs:
                for job in jobs:
                    job.schedule_removal()
            context.job_queue.run_once(
                batch_group,
                GALLERY_TIMEOUT,
                name=job_name,
                chat_id=chat_id,
                data=group_id,
            )
        else:
            logging.debug(f"Single photo")
            await identify_images(
                [update.message.photo],
                location=chat_locations.get(update.effective_chat.id, None),
            )


if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT | filters.LOCATION, handle_location)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    application.run_polling()
