import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings


def launch_scan_job(job_id, source_id=None, source_path=None, expected_commit=None, license_path=None, license_spdx=None):
    arguments = []
    for option, value in (
        ("--source-path", source_path),
        ("--expected-commit", expected_commit),
        ("--license-path", license_path),
        ("--license-spdx", license_spdx),
    ):
        if value:
            arguments.append(f"{option}={value}")
    _launch_job("scan_skill_candidates_job", job_id, source_id, arguments)


def launch_enrichment_job(job_id, source_id=None):
    _launch_job("enrich_skills_job", job_id, source_id)


def launch_academic_recommendations_job(job_id):
    _launch_job("refresh_academic_skill_recommendations_job", job_id, None)


def _launch_job(command_name, job_id, source_id, arguments=()):
    command = [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), command_name, str(job_id)]
    if source_id is not None:
        command.extend(["--source-id", str(source_id)])
    command.extend(arguments)
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
