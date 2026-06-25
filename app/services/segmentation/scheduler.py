from apscheduler.schedulers.background import BackgroundScheduler
from app.services.payment_gateway.subscription_reconcile import reconcile_pending_subscriptions
from app.services.payment_gateway.access_sync import sync_access_status
from app.services.segmentation.classify import run_classification
from app.utils.logger_config import logger

_scheduler = BackgroundScheduler()


def _run_daily_jobs():
    # reconcile_pending_subscriptions()
    sync_access_status()
    run_classification()


def start_scheduler():
    _scheduler.add_job(_run_daily_jobs, "cron", hour=3, id="daily_user_status_sync")
    _scheduler.start()
    logger.info("Daily user status sync scheduler started")


def stop_scheduler():
    _scheduler.shutdown()
