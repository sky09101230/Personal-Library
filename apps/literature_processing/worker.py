from dataclasses import dataclass
import time

from .models import DocumentProcessingJob
from .pipeline import process_next_job


@dataclass(frozen=True, slots=True)
class WorkerResult:
    processed: int
    succeeded: int
    failed: int


def run_worker(
    *,
    once=False,
    max_jobs=0,
    poll_interval=2.0,
    process_func=process_next_job,
    sleep_func=time.sleep,
    on_job=None,
):
    processed = 0
    succeeded = 0
    failed = 0
    max_jobs = max(0, int(max_jobs))
    while True:
        job = process_func()
        if job is None:
            if once or (max_jobs and processed >= max_jobs):
                break
            sleep_func(max(0.2, poll_interval))
            continue
        processed += 1
        if job.status == DocumentProcessingJob.Status.SUCCEEDED:
            succeeded += 1
        elif job.status == DocumentProcessingJob.Status.FAILED:
            failed += 1
        if on_job is not None:
            on_job(job)
        if max_jobs and processed >= max_jobs:
            break
    return WorkerResult(processed=processed, succeeded=succeeded, failed=failed)

