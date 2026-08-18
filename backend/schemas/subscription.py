from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionCreate(BaseModel):
    """Mirrors the shape of a browser PushSubscription.toJSON() object."""

    endpoint: str = Field(min_length=1)
    keys: SubscriptionKeys


class SubscriptionDelete(BaseModel):
    endpoint: str = Field(min_length=1)


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint: str
    is_active: bool
    created_at: datetime
