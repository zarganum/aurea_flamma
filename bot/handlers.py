from typing import Tuple, Dict

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

from .identify import identify_images

GALLERY_TIMEOUT = 1

media_groups: Dict[str, list[Tuple[PhotoSize, ...]]] = {}
album_message_ids: Dict[str, int] = {}
chat_locations: Dict[int, Location] = {}


async def batch_group_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global media_groups, chat_locations, album_message_ids
    logging.debug(f"Batch group: {context.job.data}")
    plant_id = await identify_images(
        context,
        user_id=context.job.user_id,
        photos=media_groups[context.job.data],
        location=chat_locations.get(context.job.chat_id, None),
        message_id=album_message_ids[context.job.data],
    )
    logging.debug(f"Identification:\n{pformat(plant_id, indent=2)}")
    if isinstance(plant_id, dict):
        base_suggestion = plant_id["result"]["classification"]["suggestions"][0]
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
                message_id=update.message.message_id,
            )
