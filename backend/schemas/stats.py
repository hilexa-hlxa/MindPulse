from pydantic import BaseModel, ConfigDict


class MostSentPhrase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    author: str | None
    times_sent: int


class StatsOut(BaseModel):
    total_phrases: int
    active_phrases: int
    total_subscribers: int
    notifications_sent_today: int
    most_sent_phrase: MostSentPhrase | None
