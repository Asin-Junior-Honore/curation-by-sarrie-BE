from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

client: AsyncIOMotorClient = None
db = None


async def connect_to_mongo():
    global client, db
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    print(f"✅ Connected to MongoDB: {settings.mongodb_db_name}")

    # Ensure unique index on user email
    await db["users"].create_index("email", unique=True)


async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("❌ Closed MongoDB connection")


def get_db():
    return db


def products_collection():
    return db["products"]


def sync_log_collection():
    return db["sync_log"]


def orders_collection():
    return db["orders"]


def users_collection():
    return db["users"]


def shipping_zones_collection():
    return db["shipping_zones"]

def refresh_tokens_collection():
    return db["refresh_tokens"]