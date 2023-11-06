from typing import Tuple, Dict

import base64

import logging
from pprint import pformat

from telegram import (
    Update,
    User,
    ReplyKeyboardMarkup,
    KeyboardButton,
    PhotoSize,
    Location,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import ContextTypes

from .identify import create_identification
from . import db

GALLERY_TIMEOUT = 1

LANGUAGES = ["en", "ru", "ua"]

media_groups: Dict[str, list[Tuple[PhotoSize, ...]]] = {}
album_message_ids: Dict[str, int] = {}
chat_locations: Dict[int, Location] = {}


async def identify_photos(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    message_id: int,
    photos: list[Tuple[PhotoSize, ...]],
    location: Location = None,
) -> None:
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

    id = await create_identification(
        images=images,
        location=(location.latitude, location.longitude) if location else None,
    )

    logging.debug(f"\nIdentification: {pformat(id, indent=2)}")

    if isinstance(id, dict):
        # TODO:
        # Pydantic models for User, Message, etc.
        # move reference to db.add_identification
        reference = {
            "user": {"namespace": "tg", "id": user_id},
            "message": {"namespace": "tg", "id": message_id},
        }

        await db.add_identification(
            client=context.bot_data["db_client"],
            user={"namespace": "tg", "id": user_id},
            identification={
                "reference": reference,
                **id,
            },
        )
        if id["namespace"] == "plant.id":
            base_suggestion = id["result"]["classification"]["suggestions"][0]
            text = (
                f"{round(base_suggestion['probability']*100)}% {base_suggestion['name']}\n"
                f"see also:"
            )
            keyboard = []
            for lang in ("global", *LANGUAGES):
                if isinstance(base_suggestion["details"]["url"][lang], str):
                    keyboard.append(
                        InlineKeyboardButton(
                            lang, url=base_suggestion["details"]["url"][lang]
                        )
                    )
            reply_markup = InlineKeyboardMarkup([keyboard])
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                reply_to_message_id=message_id,
            )


async def batch_group_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global media_groups, chat_locations, album_message_ids

    logging.debug(f"Batch job data: {context.job.data}")
    await identify_photos(
        context,
        user_id=context.job.user_id,
        chat_id=context.job.chat_id,
        message_id=album_message_ids[context.job.data],
        photos=media_groups[context.job.data],
        location=chat_locations.get(context.job.chat_id, None),
    )

    media_groups[context.job.data] = None
    album_message_ids[context.job.data] = None


async def handle_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
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
                when=GALLERY_TIMEOUT,
                name=job_name,
                chat_id=chat_id,
                user_id=update.effective_user.id,
                data=group_id,
            )
        else:
            logging.debug(f"Single photo")
            await identify_photos(
                context,
                user_id=update.message.from_user.id,
                chat_id=update.message.chat_id,
                message_id=update.message.id,
                photos=[update.message.photo],
                location=chat_locations.get(context.job.chat_id, None),
            )
