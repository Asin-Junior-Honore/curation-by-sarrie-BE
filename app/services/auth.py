from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from fastapi import HTTPException, status

from ..database import users_collection
from ..models.user import UserInDB, UserCreate, UserUpdate, UserResponse
from ..config import settings
from .security import hash_password, verify_password
from .email import send_email


def _doc_to_user_response(doc: dict) -> UserResponse:
    return UserResponse(
        id=str(doc["_id"]),
        email=doc["email"],
        full_name=doc["full_name"],
        role=doc["role"],
        is_active=doc.get("is_active", True),
        created_at=doc.get("created_at", datetime.utcnow()),
        updated_at=doc.get("updated_at", datetime.utcnow()),
    )


async def seed_super_admin():
    """Create the super admin on first startup if none exists."""
    existing = await users_collection().find_one({"role": "super_admin"})
    if existing:
        print(f"👤 Super admin exists: {existing['email']}")
        return

    doc = {
        "email": settings.super_admin_email.lower(),
        "full_name": settings.super_admin_name,
        "role": "super_admin",
        "is_active": True,
        "hashed_password": hash_password(settings.super_admin_password),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": None,
    }
    await users_collection().insert_one(doc)
    print(f"✅ Super admin created: {settings.super_admin_email}")


async def get_user_by_email(email: str) -> Optional[dict]:
    return await users_collection().find_one({"email": email.lower()})


async def get_user_by_id(user_id: str) -> Optional[dict]:
    try:
        return await users_collection().find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


async def authenticate(email: str, password: str) -> Optional[dict]:
    user = await get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return user


async def create_user(data: UserCreate, created_by_id: str) -> UserResponse:
    existing = await get_user_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    doc = {
        "email": data.email.lower(),
        "full_name": data.full_name,
        "role": data.role,
        "is_active": data.is_active,
        "hashed_password": hash_password(data.password),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": created_by_id,
    }
    result = await users_collection().insert_one(doc)
    doc["_id"] = result.inserted_id

    # Fire welcome email (non-blocking — don't fail the request if it errors)
    role_labels = {
        "super_admin": "Super Admin",
        "admin": "Admin",
        "staff": "Staff",
    }
    await send_email(
        to_email=doc["email"],
        subject="You've been granted admin access — Curation by Sarrie",
        template_name="admin_invite.html",
        context={
            "full_name": doc["full_name"],
            "email": doc["email"],
            "password": data.password,  # plaintext — sent once
            "role_label": role_labels.get(doc["role"], doc["role"]),
            "login_url": f"{settings.admin_panel_url}",
        },
    )

    return _doc_to_user_response(doc)


async def list_users() -> List[UserResponse]:
    cursor = users_collection().find().sort("created_at", -1)
    users = []
    async for doc in cursor:
        users.append(_doc_to_user_response(doc))
    return users


async def update_user(user_id: str, data: UserUpdate) -> UserResponse:
    update = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    if "password" in update:
        update["hashed_password"] = hash_password(update.pop("password"))
    if "email" in update:
        update["email"] = update["email"].lower()
    update["updated_at"] = datetime.utcnow()

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await users_collection().update_one(
        {"_id": ObjectId(user_id)}, {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    doc = await get_user_by_id(user_id)
    return _doc_to_user_response(doc)


async def delete_user(user_id: str, requester_id: str):
    if user_id == requester_id:
        raise HTTPException(
            status_code=400, detail="Cannot delete your own account"
        )
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("role") == "super_admin":
        raise HTTPException(
            status_code=400, detail="Cannot delete the super admin"
        )
    await users_collection().delete_one({"_id": ObjectId(user_id)})