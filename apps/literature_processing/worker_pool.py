from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import os
from threading import Event, Lock

from django.db import close_old_connections, connection

from .models import DocumentProcessingJob
from .worker import run_worker


class WorkerPoolConfigurationError(ValueError):
    pass


class WorkerPoolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerChannel:
    name: str
    queue_lane: str
    api_token: str = field(repr=False)


def load_worker_channels(environ=None):
    environ = os.environ if environ is None else environ
    realtime = (
        environ.get("MINERU_REALTIME_API_TOKEN", "").strip()
        or environ.get("MINERU_API_TOKEN", "").strip()
    )
    backfill = [
        environ.get(f"MINERU_BACKFILL_API_TOKEN_{index}", "").strip()
        for index in range(1, 5)
    ]
    if not realtime or any(not token for token in backfill):
        raise WorkerPoolConfigurationError(
            "Literature worker pool requires one realtime and four backfill MinerU tokens."
        )
    tokens = [realtime, *backfill]
    if len(tokens) != len(set(tokens)):
        raise WorkerPoolConfigurationError("Literature worker pool tokens must be distinct.")
    return (
        WorkerChannel("realtime", DocumentProcessingJob.QueueLane.REALTIME, realtime),
        *(
            WorkerChannel(
                f"backfill-{index}",
                DocumentProcessingJob.QueueLane.BACKFILL,
                token,
            )
            for index, token in enumerate(backfill, start=1)
        ),
    )


def resolve_worker_token(queue_lane, token_slot, *, environ=None):
    environ = os.environ if environ is None else environ
    if queue_lane == DocumentProcessingJob.QueueLane.REALTIME:
        token = (
            environ.get("MINERU_REALTIME_API_TOKEN", "").strip()
            or environ.get("MINERU_API_TOKEN", "").strip()
        )
        channel = "realtime"
    elif queue_lane == DocumentProcessingJob.QueueLane.BACKFILL:
        if token_slot not in {1, 2, 3, 4}:
            raise WorkerPoolConfigurationError("Backfill worker token slot must be 1-4.")
        token = environ.get(f"MINERU_BACKFILL_API_TOKEN_{token_slot}", "").strip()
        channel = f"backfill-{token_slot}"
    else:
        return None, ""
    if not token:
        raise WorkerPoolConfigurationError(f"MinerU token is not configured for {channel}.")
    return token, channel


def run_worker_pool(
    *,
    poll_interval=2.0,
    channels=None,
    stop_event=None,
    worker_func=run_worker,
    on_job=None,
    require_postgresql=True,
):
    if require_postgresql and connection.vendor != "postgresql":
        raise WorkerPoolConfigurationError("Concurrent literature worker pool requires PostgreSQL.")
    channels = tuple(channels or load_worker_channels())
    if len(channels) != 5:
        raise WorkerPoolConfigurationError("Literature worker pool requires exactly five channels.")
    stop_event = stop_event or Event()
    output_lock = Lock()

    def report(job):
        if on_job is not None:
            with output_lock:
                on_job(job)

    def run_channel(channel):
        close_old_connections()
        try:
            return worker_func(
                poll_interval=poll_interval,
                queue_lane=channel.queue_lane,
                worker_channel=channel.name,
                mineru_api_token=channel.api_token,
                stop_event=stop_event,
                on_job=report,
            )
        finally:
            close_old_connections()

    results = {}
    try:
        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="literature-worker") as executor:
            futures = {executor.submit(run_channel, channel): channel for channel in channels}
            for future in as_completed(futures):
                channel = futures[future]
                try:
                    results[channel.name] = future.result()
                except Exception as exc:
                    stop_event.set()
                    raise WorkerPoolError(f"Literature worker channel {channel.name} stopped.") from exc
    except KeyboardInterrupt:
        stop_event.set()
    return results
