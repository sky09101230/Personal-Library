from dataclasses import dataclass
import time

from .models import DocumentProcessingJob
from .parsers.mineru import use_mineru_api_token
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
    queue_lane=None,
    worker_channel="",
    stop_event=None,
    mineru_api_token=None,
):
    processed = 0
    succeeded = 0
    failed = 0
    max_jobs = max(0, int(max_jobs))
    with use_mineru_api_token(mineru_api_token):
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            process_options = {}
            if queue_lane:
                process_options["queue_lane"] = queue_lane
            if worker_channel:
                process_options["worker_channel"] = worker_channel
            job = process_func(**process_options) if process_options else process_func()
            if job is None:
                if once or (max_jobs and processed >= max_jobs):
                    break
                wait_seconds = max(0.2, poll_interval)
                if stop_event is not None:
                    stop_event.wait(wait_seconds)
                else:
                    sleep_func(wait_seconds)
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
