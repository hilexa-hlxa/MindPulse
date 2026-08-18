from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(description="Browser's public key for this subscription.")
    auth: str = Field(description="Browser's auth secret for this subscription.")


class SubscriptionCreate(BaseModel):
    """Mirrors the shape of a browser PushSubscription.toJSON() object."""

    endpoint: str = Field(min_length=1, examples=["https://fcm.googleapis.com/fcm/send/abc123..."])
    keys: SubscriptionKeys


class SubscriptionDelete(BaseModel):
    endpoint: str = Field(min_length=1)


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint: str
    is_active: bool
    created_at: datetime
