from fastapi import APIRouter

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.post("")
async def create_checkout():
    """Placeholder — will push orders to Bumpa after payment."""
    return {
        "status": "coming_soon",
        "message": "Order sync to Bumpa will be implemented next.",
    }