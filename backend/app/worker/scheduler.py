from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler(job_func) -> AsyncIOScheduler:
    sched = get_scheduler()
    sched.add_job(
        job_func,
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_expiry_scan",
        replace_existing=True,
    )
    sched.start()
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
