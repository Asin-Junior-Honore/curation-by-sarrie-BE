from fastapi import APIRouter, Depends
from typing import List

from ..models.user import UserCreate, UserUpdate, UserResponse
from ..services.auth import create_user, list_users, update_user, delete_user
from ..dependencies.auth import require_super_admin

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_new_user(
    payload: UserCreate,
    user: dict = Depends(require_super_admin),
):
    return await create_user(payload, created_by_id=str(user["_id"]))


@router.get("", response_model=List[UserResponse])
async def get_all_users(user: dict = Depends(require_super_admin)):
    return await list_users()


@router.patch("/{user_id}", response_model=UserResponse)
async def edit_user(
    user_id: str,
    payload: UserUpdate,
    user: dict = Depends(require_super_admin),
):
    return await update_user(user_id, payload)


@router.delete("/{user_id}")
async def remove_user(
    user_id: str,
    user: dict = Depends(require_super_admin),
):
    await delete_user(user_id, requester_id=str(user["_id"]))
    return {"status": "ok"}