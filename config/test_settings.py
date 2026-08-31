import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def test_postgresql_requires_all_connection_settings(self):
        environment = os.environ.copy()
        environment.update(
            AGENTSYS_DB_ENGINE="postgresql",
            AGENTSYS_DB_NAME="agentsys",
            AGENTSYS_DB_USER="agentsys_app",
            AGENTSYS_DB_PASSWORD="",
            AGENTSYS_DB_HOST="127.0.0.1",
            AGENTSYS_DB_PORT="5432",
        )

        result = subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PostgreSQL requires these AgentSys database settings: PASSWORD", result.stderr)
