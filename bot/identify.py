from typing import Tuple

import os
import certifi
import base64

import logging
from pprint import pformat

from aioplantid_sdk import Configuration, ApiClient, DefaultApi as PlantIdApi

from telegram import PhotoSize, Location
from telegram.ext import ContextTypes

from . import db

PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")


async def identify_images(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    photos: list[Tuple[PhotoSize, ...]],
    location: Location = None,
    message_id: int = None,
) -> dict | None:
    logging.debug(
        f"\nIdentify images:\n{pformat(photos, indent=2)}\n{pformat(location, indent=2)})\n"
    )

    await db.upsert_user(client=context.bot_data["db_client"], user_id=user_id)

    images = []
    for photo in photos:
        largest_photo = photo[-1]
        file = await context.bot.get_file(largest_photo.file_id)
        logging.info(f"\nAppend file: {pformat(file, indent=2)}\n")
        bytes = await file.download_as_bytearray()
        images.append(base64.b64encode(bytes).decode("ascii"))

    (latitude, longitude) = (
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
        body = {"images": images, "latitude": latitude, "longitude": longitude}
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
            return await db.add_identification(
                client=context.bot_data["db_client"],
                plant_id={
                    "namespace": "plant.id",
                    "user_id": user_id,
                    "reference": {"message_id": message_id},
                    **plant_id,
                },
            )
        else:
            return None
