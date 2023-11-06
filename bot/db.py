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


async def upsert_user(client: AsyncIOMotorClient, user: dict) -> None:
    if not isinstance(user, dict) or "id" not in user or "namespace" not in user:
        raise ValueError("user dict is required containing namespace and id")
    users = client.get_default_database()["users"]
    now = datetime.now().astimezone(timezone.utc)
    await users.update_one(
        {"namespace": user["namespace"], "id": user["id"]},
        {
            "$setOnInsert": {
                "created_at": now,
                "count": {"identifications": 0},
                **user,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )


async def add_identification(
    client: AsyncIOMotorClient, user: dict, identification: dict
) -> Dict[str, Any] | None:
    if not isinstance(identification, dict):
        raise ValueError("plant_id must be a dict")
    await upsert_user(client=client, user=user)
    async with await client.start_session() as session:
        async with session.start_transaction():
            await client.get_default_database().identifications.insert_one(
                identification
            )
            await client.get_default_database().users.update_one(
                {"namespace": user["namespace"], "id": user["id"]},
                {
                    "$set": {"updated_at": datetime.now().astimezone(timezone.utc)},
                    "$inc": {"count.identifications": 1},
                },
            )
