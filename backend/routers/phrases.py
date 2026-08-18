from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.phrase import Phrase
from backend.rate_limit import limiter
from backend.schemas.phrase import PhraseCreate, PhraseOut, PhraseUpdate
from backend.services.category_repo import get_or_create_categories
from backend.services.phrase_repo import pick_random_active_phrase

router = APIRouter(prefix="/api/phrases", tags=["phrases"])


@router.get(
    "",
    response_model=list[PhraseOut],
    summary="List all phrases",
    description="Every phrase, active and inactive, newest first.",
)
async def list_phrases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Phrase).order_by(Phrase.created_at.desc()))
    return result.scalars().all()


@router.get(
    "/random",
    response_model=PhraseOut,
    summary="Pick one random active phrase",
    description="Respects the active category filter (see PATCH /api/settings) — "
    "this previews exactly what the scheduler would actually send right now.",
    responses={404: {"description": "No active phrase matches the current filter."}},
)
async def random_phrase(db: AsyncSession = Depends(get_db)):
    """Used by the frontend's Dashboard preview button."""
    phrase = await pick_random_active_phrase(db)
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active phrases available")
    return phrase


@router.post(
    "",
    response_model=PhraseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a phrase",
    description="Rate-limited to 20 requests/minute per client to keep a public deployment from being spammed.",
)
@limiter.limit("20/minute")
async def create_phrase(request: Request, payload: PhraseCreate, db: AsyncSession = Depends(get_db)):
    phrase = Phrase(text=payload.text, author=payload.author)
    if payload.categories is not None:
        phrase.categories = await get_or_create_categories(db, payload.categories)
    db.add(phrase)
    await db.commit()
    await db.refresh(phrase)
    return phrase


@router.patch(
    "/{phrase_id}",
    response_model=PhraseOut,
    summary="Edit a phrase",
    description="Only fields present in the body are changed (PATCH semantics). "
    "Sending `categories` replaces the full tag set, it doesn't merge.",
    responses={404: {"description": "No phrase with that ID."}},
)
async def update_phrase(phrase_id: int, payload: PhraseUpdate, db: AsyncSession = Depends(get_db)):
    phrase = await db.get(Phrase, phrase_id)
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrase not found")

    updates = payload.model_dump(exclude_unset=True, exclude={"categories"})
    for field, value in updates.items():
        setattr(phrase, field, value)

    if payload.categories is not None:
        phrase.categories = await get_or_create_categories(db, payload.categories)

    await db.commit()
    await db.refresh(phrase)
    return phrase


@router.delete(
    "/{phrase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a phrase",
    description="Hard delete — there's no undo. Delivery log rows for this phrase are cascade-deleted with it.",
    responses={404: {"description": "No phrase with that ID."}},
)
async def delete_phrase(phrase_id: int, db: AsyncSession = Depends(get_db)):
    phrase = await db.get(Phrase, phrase_id)
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrase not found")
    await db.delete(phrase)
    await db.commit()
    return None
