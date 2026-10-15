from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, status

from ..database import refresh_tokens_collection
from ..models.user import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from ..services.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ..services.auth import authenticate, get_user_by_id
from ..dependencies.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_to_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        is_active=user.get("is_active", True),
        created_at=user.get("created_at", datetime.utcnow()),
        updated_at=user.get("updated_at", datetime.utcnow()),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    user = await authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user_id = str(user["_id"])
    access = create_access_token({"sub": user_id, "role": user["role"]})
    refresh = create_refresh_token({"sub": user_id})

    # Store refresh token for revocation
    await refresh_tokens_collection().insert_one({
        "token": refresh,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow()
        + timedelta(days=7),
    })

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_to_response(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest):
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    stored = await refresh_tokens_collection().find_one(
        {"token": payload.refresh_token}
    )
    if not stored:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    user = await get_user_by_id(decoded["sub"])
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found or disabled")

    user_id = str(user["_id"])
    access = create_access_token({"sub": user_id, "role": user["role"]})
    new_refresh = create_refresh_token({"sub": user_id})

    # Rotate refresh token
    await refresh_tokens_collection().delete_one(
        {"token": payload.refresh_token}
    )
    await refresh_tokens_collection().insert_one({
        "token": new_refresh,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
    })

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        user=_user_to_response(user),
    )


@router.post("/logout")
async def logout(payload: RefreshRequest):
    await refresh_tokens_collection().delete_one(
        {"token": payload.refresh_token}
    )
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return _user_to_response(user)