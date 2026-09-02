from dataclasses import dataclass

from .jobs import backfill_processing
from .models import DocumentProcessingJob
from .versions import DEFAULT_PARSER_NAME
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
    parser_name=DEFAULT_PARSER_NAME,
    queue_lane=DocumentProcessingJob.QueueLane.BACKFILL,
):
    queued = backfill(
        limit=limit,
        force=force,
        parser_name=parser_name,
        queue_lane=queue_lane,
    )
    worker_result = worker(
        once=True,
        max_jobs=max_jobs,
        on_job=on_job,
        queue_lane=queue_lane,
    )
    return ProcessExistingResult(
        created=queued["created"],
        reused=queued["reused"],
        worker=worker_result,
    )
