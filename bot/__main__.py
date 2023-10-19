from typing import Tuple, Dict, List
import certifi
import os
import base64

import asyncio
import contextvars
from fastapi import FastAPI
from uvicorn import Config, Server

from telegram import Update, User
from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    PhotoSize,
    Location,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
)
from telegram.ext import filters

from motor.core import AgnosticClient as MotorAgnosticClient
from motor.motor_asyncio import AsyncIOMotorClient

from aioplantid_sdk import Configuration, ApiClient, DefaultApi as PlantIdApi

import logging
from pprint import pformat, pprint


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")
MONGODB_URL = os.getenv("MONGODB_URL")

GALLERY_TIMEOUT = 1

media_groups: Dict[str, List] = {}
album_message_ids: Dict[str, int] = {}
chat_locations: Dict[int, Location] = {}

app = FastAPI()
cx_bot = contextvars.ContextVar("bot")


@app.get("/")
async def read_root():
    bot = cx_bot.get()
    return {"Hello": "World"}


async def identify_images(
    context: ContextTypes.DEFAULT_TYPE,
    photos: list[Tuple[PhotoSize, ...]],
    location: Location = None,
) -> dict | None:
    logging.debug(
        f"\nIdentify images:\n{pformat(photos, indent=2)}\n{pformat(location, indent=2)})\n"
    )

    images = []
    for photo in photos:
        largest_photo = photo[-1]
        file = await context.bot.get_file(largest_photo.file_id)
        logging.info(f"\nAppend file: {pformat(file, indent=2)}\n")
        bytes = await file.download_as_bytearray()
        images.append(base64.b64encode(bytes).decode("ascii"))

    (lattitude, longitude) = (
        (None, None)
        if not location
        else (
            location.latitude,
            location.longitude,
        )
    )

    async with ApiClient(
        Configuration(
            host="https://plant.id/api/v3",
            ssl_ca_cert=certifi.where(),
        )
    ) as api_client:
        api_client.set_default_header("Content-Type", "application/json")
        api_client.set_default_header("Api-Key", PLANT_ID_API_KEY)
        api = PlantIdApi(api_client)
        body = {"images": images, "latitude": lattitude, "longitude": longitude}
        plant_id = await api.create_identification(
            details=",".join(
                [
                    "common_names",
                    "url",
                    #     "description",
                    #     "taxonomy",
                    #     "rank",
                    #     "gbif_id",
                    #     "inaturalist_id",
                    #     "image",
                    #     "synonyms",
                    #     "edible_parts",
                    #     "watering",
                    #     "propagation_methods",
                ]
            ),
            language=",".join(["en", "ru", "ua"]),
            body=body,
        )
        logging.info(f"Identification access token: {plant_id['access_token']}")

        if isinstance(plant_id, dict):
            identification = {
                **plant_id,
                "namespace": "plant.id",
            }
            client = context.bot_data["db_client"]
            db = client["aurea_flamma"]
            identifications = db["identifications"]
            await identifications.insert_one(identification)
            return identification
        else:
            return None


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user: User = update.message.from_user
    logging.debug(f"from_user:\n{pformat(user, indent=2)}")

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
        chat_locations[update.effective_chat.id] = update.message.location
        # latitude = update.message.location.latitude
        # longitude = update.message.location.longitude
        # await update.message.reply_text(
        #     f"Received location: Latitude {latitude}, Longitude {longitude}"
        # )
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


async def batch_group_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global media_groups, chat_locations, album_message_ids
    logging.debug(f"Batch group: {context.job.data}")
    identification = await identify_images(
        context,
        media_groups[context.job.data],
        location=chat_locations.get(context.job.chat_id, None),
    )
    if isinstance(identification, dict):
        base_suggestion = identification["result"]["classification"]["suggestions"][0]
        text = (
            f"{round(base_suggestion['probability']*100)}% {base_suggestion['name']}\n"
            f"see also:"
        )
        keyboard = []
        for lang in ("global", "en", "ru", "ua"):
            if isinstance(base_suggestion["details"]["url"][lang], str):
                keyboard.append(
                    InlineKeyboardButton(
                        lang, url=base_suggestion["details"]["url"][lang]
                    )
                )
        reply_markup = InlineKeyboardMarkup([keyboard])
        await context.bot.send_message(
            chat_id=context.job.chat_id,
            text=text,
            reply_markup=reply_markup,
            # parse_mode="MarkdownV2",
            reply_to_message_id=album_message_ids[context.job.data],
            # disable_web_page_preview=True,
        )
    media_groups[context.job.data] = None
    album_message_ids[context.job.data] = None


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global media_groups
    if update.message.photo:
        logging.debug(f"\nReceived photo:\n{pformat(update.message.photo, indent=2)}\n")
        # logging.info(f"job_queue: {pformat(context.job_queue, indent=2)}")
        if update.message.media_group_id:
            group_id = update.message.media_group_id
            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            logging.debug(f"Media group: {group_id}")
            if group_id not in media_groups:
                media_groups[group_id] = []
                album_message_ids[group_id] = message_id
            media_groups[group_id].append(update.message.photo)
            job_name = f"gal:{chat_id}"
            jobs = context.job_queue.get_jobs_by_name(job_name)
            if jobs:
                for job in jobs:
                    job.schedule_removal()
            context.job_queue.run_once(
                batch_group_job,
                GALLERY_TIMEOUT,
                name=job_name,
                chat_id=chat_id,
                data=group_id,
            )
        else:
            logging.debug(f"Single photo")
            await identify_images(
                context,
                [update.message.photo],
                location=chat_locations.get(update.effective_chat.id, None),
            )


async def post_init(application: Application) -> None:
    client = AsyncIOMotorClient(MONGODB_URL)
    application.bot_data["db_client"] = client
    db = client["aurea_flamma"]
    collection_names = await db.list_collection_names()
    if "identifications" not in collection_names:
        await db.create_collection("identifications")
    identifications = db["identifications"]

    identifications_indices = [
        ("namespace", False),
        ("access_token", True),
        ("completed", False),
        ("created", False),
        ("status", False),
        ("result.classification.suggestions.details.entity_id", False),
        ("result.classification.suggestions.details.language", False),
        ("result.classification.suggestions.id", False),
        ("result.classification.suggestions.name", False),
        ("result.classification.suggestions.probability", False),
        ("result.is_plant.probability", False),
    ]

    for index, unique in identifications_indices:
        await identifications.create_index(index, unique=unique)

    async def start_server() -> None:
        # asyncio.set_event_loop(asyncio.new_event_loop())
        # asyncio.get_event_loop().run_until_complete(server.serve())
        config = Config(app=app, host="0.0.0.0", port=5000, loop="asyncio")
        server = Server(config)
        await server.serve()

    cx_bot.set(application.bot)
    asyncio.create_task(start_server())


async def post_shutdown(application: Application) -> None:
    application.bot_data["db_client"].close()


if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT | filters.LOCATION, handle_location)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    application.run_polling()
