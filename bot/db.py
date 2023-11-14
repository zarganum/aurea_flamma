from typing import Any, Dict, List
from datetime import datetime, timezone
from pymongo import IndexModel, ReturnDocument, ASCENDING, DESCENDING

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
            # IndexModel([("user_id", ASCENDING)]),
            # IndexModel(
            #     [("reference.message_id", ASCENDING)],
            #     partialFilterExpression={"reference.message_id": {"$exists": True}},
            # ),
            IndexModel(
                [("reference.user.id", ASCENDING)],
                partialFilterExpression={"reference.user": {"$exists": True}},
            ),
            IndexModel(
                [("reference.user.namespace", ASCENDING)],
                partialFilterExpression={"reference.user": {"$exists": True}},
            ),
            IndexModel(
                [("reference.message.id", ASCENDING)],
                partialFilterExpression={"reference.message": {"$exists": True}},
            ),
            IndexModel(
                [("reference.message.namespace", ASCENDING)],
                partialFilterExpression={"reference.message": {"$exists": True}},
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


async def list_identifications(
    client: AsyncIOMotorClient, user: dict
) -> List[Dict[str, Any]] | None:
    return [
        doc
        async for doc in client.get_default_database()
        .identifications.find(
            filter={
                "reference.user.id": user["id"],
                "reference.user.namespace": user["namespace"],
            },
            projection={"_id": False},
        )
        .sort("created", ASCENDING)
    ]


async def get_identification(
    client: AsyncIOMotorClient, user: dict, id: dict
) -> List[Dict[str, Any]] | None:
    identification = await client.get_default_database().identifications.find_one(
        filter={
            "reference.user.id": user["id"],
            "reference.user.namespace": user["namespace"],
            "access_token": id["access_token"],
            "namespace": id["namespace"],
        },
        projection={"_id": False},
    )
    return identification if identification else None


async def approve_identification(
    client: AsyncIOMotorClient, user: dict, id: dict, approval: dict
) -> None:
    # TODO approval history
    async with await client.start_session() as session:
        async with session.start_transaction():
            identification = await client.get_default_database().identifications.find_one_and_update(
                filter={
                    "reference.user.id": user["id"],
                    "reference.user.namespace": user["namespace"],
                    "access_token": id["access_token"],
                    "namespace": id["namespace"],
                },
                update={
                    "$set": {
                        "result.classification.suggestions.$[approved].approved": {
                            "updated_at": datetime.now().astimezone(timezone.utc)
                        }
                    },
                    "$unset": {
                        "result.classification.suggestions.$[unapproved].approved": ""
                    },
                },
                array_filters=[
                    {"approved.id": approval["id"]},
                    {"unapproved.id": {"$ne": approval["id"]}},
                ],
                return_document=ReturnDocument.AFTER,
            )
            return identification if identification else None
