from typing import Dict, List, Tuple

import os
import certifi

import logging
from pprint import pformat

from aioplantid_sdk import Configuration, ApiClient, DefaultApi as PlantIdApi

PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")


async def create_identification(
    images: List[bytearray],
    location: Tuple = None,
) -> dict | None:
    (latitude, longitude) = location if location else (None, None)

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
            return {
                "namespace": "plant.id",
                **plant_id,
            }

        else:
            return None
