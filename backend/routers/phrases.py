from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.phrase import Phrase
from backend.schemas.phrase import PhraseCreate, PhraseOut, PhraseUpdate

router = APIRouter(prefix="/api/phrases", tags=["phrases"])


@router.get("", response_model=list[PhraseOut])
async def list_phrases(db: AsyncSession = Depends(get_db)):
    """Return all phrases (active + inactive), newest first."""
    result = await db.execute(select(Phrase).order_by(Phrase.created_at.desc()))
    return result.scalars().all()


@router.get("/random", response_model=PhraseOut)
async def random_phrase(db: AsyncSession = Depends(get_db)):
    """Pick one active phrase at random."""
    result = await db.execute(
        select(Phrase).where(Phrase.is_active.is_(True)).order_by(func.random()).limit(1)
    )
    phrase = result.scalar_one_or_none()
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active phrases available")
    return phrase


@router.post("", response_model=PhraseOut, status_code=status.HTTP_201_CREATED)
async def create_phrase(payload: PhraseCreate, db: AsyncSession = Depends(get_db)):
    phrase = Phrase(text=payload.text, author=payload.author)
    db.add(phrase)
    await db.commit()
    await db.refresh(phrase)
    return phrase


@router.patch("/{phrase_id}", response_model=PhraseOut)
async def update_phrase(phrase_id: int, payload: PhraseUpdate, db: AsyncSession = Depends(get_db)):
    phrase = await db.get(Phrase, phrase_id)
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrase not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(phrase, field, value)

    await db.commit()
    await db.refresh(phrase)
    return phrase


@router.delete("/{phrase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phrase(phrase_id: int, db: AsyncSession = Depends(get_db)):
    phrase = await db.get(Phrase, phrase_id)
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrase not found")
    await db.delete(phrase)
    await db.commit()
    return None
