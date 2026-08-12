import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings


def launch_sync_job(job_id, source_id=None):
    _launch_job("sync_skills_job", job_id, source_id)


def launch_scan_job(job_id, source_id=None):
    _launch_job("scan_skill_candidates_job", job_id, source_id)


def launch_enrichment_job(job_id, source_id=None):
    _launch_job("enrich_skills_job", job_id, source_id)


def _launch_job(command_name, job_id, source_id):
    command = [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), command_name, str(job_id)]
    if source_id is not None:
        command.extend(["--source-id", str(source_id)])
    options = {
        "cwd": settings.BASE_DIR,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    subprocess.Popen(command, **options)
