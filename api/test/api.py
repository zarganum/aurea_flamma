import asyncio
import certifi
import os

from aioplantid_sdk import Configuration, ApiClient, DefaultApi as PlantIdApi
from pprint import pprint

configuration = Configuration(
    host="https://plant.id/api/v3",
    ssl_ca_cert=certifi.where(),
)


async def main():
    async with ApiClient(configuration) as api_client:
        api_client.set_default_header("Content-Type", "application/json")
        api_client.set_default_header("Api-Key", os.getenv("PLANT_ID_API_KEY"))
        api = PlantIdApi(api_client)
        resp = await api.usage_info_get()
        pprint(resp)
        # resp = await api.identification_post()


if __name__ == "__main__":
    asyncio.run(main())
