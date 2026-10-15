"""Moscow hourly collector schedule, separate from 09:00 digest publishing."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def next_collect_at(now: datetime, tz: ZoneInfo) -> datetime:
    if now.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    local=now.astimezone(tz)
    return local.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
