from typing import Tuple, Dict, List

import certifi
import os
import base64
from datetime import datetime, timezone

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
import pymongo

from aioplantid_sdk import Configuration, ApiClient, DefaultApi as PlantIdApi

import logging
from pprint import pformat, pprint


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")
MONGODB_URL = os.getenv("MONGODB_URL")
MONGODB_NAME = "aurea_flamma"

GALLERY_TIMEOUT = 1

media_groups: Dict[str, list[Tuple[PhotoSize, ...]]] = {}
album_message_ids: Dict[str, int] = {}
chat_locations: Dict[int, Location] = {}


async def db_init(client: AsyncIOMotorClient) -> None:
    db = client[MONGODB_NAME]
    collection_names = await db.list_collection_names()

    if "identifications" not in collection_names:
        await db.create_collection("identifications")
    identifications = db["identifications"]

    identifications_indices = [
        ([("namespace", pymongo.ASCENDING), ("access_token", pymongo.ASCENDING)], True),
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

    if "users" not in collection_names:
        await db.create_collection("users")
    users = db["users"]

    users_indexes = [
        ([("namespace", pymongo.ASCENDING), ("id", pymongo.ASCENDING)], True),
        ("created_at", False),
        ("updated_at", False),
    ]

    for index, unique in users_indexes:
        await users.create_index(index, unique=unique)


async def upsert_user(client: AsyncIOMotorClient, user_id: int) -> None:
    users = client[MONGODB_NAME]["users"]
    now = datetime.now().astimezone(timezone.utc)
    await users.update_one(
        {"_id": user_id},
        {
            "$setOnInsert": {
                "_id": user_id,
                "created_at": now,
                "count": {"identifications": 0},
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )


async def identify_images(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    photos: list[Tuple[PhotoSize, ...]],
    location: Location = None,
) -> dict | None:
    logging.debug(
        f"\nIdentify images:\n{pformat(photos, indent=2)}\n{pformat(location, indent=2)})\n"
    )

    await upsert_user(client=context.bot_data["db_client"], user_id=user_id)

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
            client: AsyncIOMotorClient = context.bot_data["db_client"]
            async with await client.start_session() as session:
                async with session.start_transaction():
                    identification = {
                        "namespace": "plant.id",
                        "user_id": user_id,
                        **plant_id,
                    }
                    await client[MONGODB_NAME].identifications.insert_one(
                        identification
                    )
                    await client[MONGODB_NAME].users.update_one(
                        {"_id": user_id},
                        {
                            "$set": {
                                "updated_at": datetime.now().astimezone(timezone.utc)
                            }
                        },
                        {"$inc": {"count.identifications": 1}},
                    )
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
        user_id=context.job.user_id,
        photos=media_groups[context.job.data],
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
                user_id=update.effective_user.id,
                data=group_id,
            )
        else:
            logging.debug(f"Single photo")
            await identify_images(
                context=context,
                user_id=update.effective_user.id,
                photos=[update.message.photo],
                location=chat_locations.get(update.effective_chat.id, None),
            )


async def app_post_init(application: Application) -> None:
    client = AsyncIOMotorClient(MONGODB_URL)
    application.bot_data["db_client"] = client
    await db_init(client)


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

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT | filters.LOCATION, handle_location)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    application.run_polling()
