from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.category import Category
from backend.schemas.category import CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get(
    "",
    response_model=list[CategoryOut],
    summary="List all categories",
    description=(
        "Every category any phrase has ever been tagged with, alphabetical. "
        "Categories are created implicitly by tagging a phrase (see "
        "`POST /api/phrases`) — there's no separate create endpoint."
    ),
)
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()
