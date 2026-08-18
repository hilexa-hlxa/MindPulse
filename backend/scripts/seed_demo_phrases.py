"""
Seeds a handful of demo phrases so a fresh install has something to send
immediately, instead of an empty Dashboard/Phrases list.

Usage (run as a module so `backend.*` imports resolve, from the repo root):
    python -m backend.scripts.seed_demo_phrases
"""
import asyncio

from sqlalchemy import select

from backend.database import AsyncSessionLocal, init_models
from backend.models.phrase import Phrase

DEMO_PHRASES = [
    ("Make it first, make it great later.", "Unknown"),
    ("The obstacle is the way.", "Marcus Aurelius"),
    ("Discipline equals freedom.", "Jocko Willink"),
    ("Small steps every day beat big plans that never start.", None),
    ("You don't have to see the whole staircase, just take the first step.", "Martin Luther King Jr."),
    ("Done is better than perfect.", None),
]


async def seed() -> None:
    await init_models()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Phrase.text))).scalars().all()
        existing_set = set(existing)

        added = 0
        for text, author in DEMO_PHRASES:
            if text in existing_set:
                continue
            db.add(Phrase(text=text, author=author))
            added += 1

        await db.commit()
        print(f"Seeded {added} new phrase(s); {len(existing_set)} already present.")


if __name__ == "__main__":
    asyncio.run(seed())
