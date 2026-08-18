"""Re-export models so `Base.metadata` sees all tables when this
package is imported (needed by Alembic autogenerate and init_models)."""
from backend.models.phrase import Phrase
from backend.models.settings import AppSettings
from backend.models.subscription import PushSubscription

__all__ = ["Phrase", "PushSubscription", "AppSettings"]
