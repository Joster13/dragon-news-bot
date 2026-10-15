"""Schedule for shadow-only editorial snapshots; never triggers Telegram APIs."""
from __future__ import annotations
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo

MOSCOW=ZoneInfo("Europe/Moscow")

def due_shadow_cutoff(now: datetime, already_built: bool) -> datetime | None:
    """Build the 09:00 Moscow digest during [09:00,12:00) if missing."""
    if now.tzinfo is None:
        raise ValueError("Timezone-aware current timestamp required")
    local=now.astimezone(MOSCOW)
    if already_built or not time(9,0) <= local.time() < time(12,0):
        return None
    return local.replace(hour=9,minute=0,second=0,microsecond=0)
