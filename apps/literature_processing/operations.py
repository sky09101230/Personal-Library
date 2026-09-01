from dataclasses import dataclass

from .jobs import backfill_processing
from .worker import WorkerResult, run_worker


@dataclass(frozen=True, slots=True)
class ProcessExistingResult:
    created: int
    reused: int
    worker: WorkerResult


def process_existing(
    *,
    limit=100,
    force=False,
    max_jobs=0,
    backfill=backfill_processing,
    worker=run_worker,
    on_job=None,
):
    queued = backfill(limit=limit, force=force)
    worker_result = worker(once=True, max_jobs=max_jobs, on_job=on_job)
    return ProcessExistingResult(
        created=queued["created"],
        reused=queued["reused"],
        worker=worker_result,
    )

