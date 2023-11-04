from typing import Any, Dict
from datetime import datetime, timezone
from pymongo import IndexModel, ASCENDING, DESCENDING

from motor.motor_asyncio import AsyncIOMotorClient


async def init(client: AsyncIOMotorClient) -> None:
    db = client.get_default_database()
    collection_names = await db.list_collection_names()

    if "identifications" not in collection_names:
        await db.create_collection("identifications")

    await db.identifications.create_indexes(
        [
            IndexModel(
                [("namespace", ASCENDING), ("access_token", ASCENDING)], unique=True
            ),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel(
                [("reference.message_id", ASCENDING)],
                partialFilterExpression={"reference.message_id": {"$exists": True}},
            ),
            IndexModel([("completed", ASCENDING)]),
            IndexModel([("created", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel(
                [
                    (
                        "result.classification.suggestions.details.entity_id",
                        ASCENDING,
                    )
                ]
            ),
            IndexModel(
                [("result.classification.suggestions.details.language", ASCENDING)]
            ),
            IndexModel([("result.classification.suggestions.id", ASCENDING)]),
            IndexModel([("result.classification.suggestions.name", ASCENDING)]),
            IndexModel([("result.classification.suggestions.probability", ASCENDING)]),
            IndexModel([("result.is_plant.probability", ASCENDING)]),
        ]
    )

    if "users" not in collection_names:
        await db.create_collection("users")

    await db.users.create_indexes(
        [
            IndexModel([("namespace", ASCENDING), ("id", ASCENDING)], unique=True),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("updated_at", DESCENDING)]),
        ]
    )


async def upsert_user(client: AsyncIOMotorClient, user_id: int) -> None:
    users = client.get_default_database()["users"]
    now = datetime.now().astimezone(timezone.utc)
    await users.update_one(
        {"namespace": "tg", "id": user_id},
        {
            "$setOnInsert": {
                "namespace": "tg",
                "id": user_id,
                "created_at": now,
                "count": {"identifications": 0},
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )


async def add_identification(
    client: AsyncIOMotorClient, plant_id: dict
) -> Dict[str, Any] | None:
    if not isinstance(plant_id, dict) or "user_id" not in plant_id:
        return None
    async with await client.start_session() as session:
        async with session.start_transaction():
            await client.get_default_database().identifications.insert_one(plant_id)
            await client.get_default_database().users.update_one(
                {"namespace": "tg", "id": plant_id["user_id"]},
                {
                    "$set": {"updated_at": datetime.now().astimezone(timezone.utc)},
                    "$inc": {"count.identifications": 1},
                },
            )
            return plant_id
