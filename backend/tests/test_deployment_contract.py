"""Regression checks for production templates consumed directly by systemd."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentContractTests(unittest.TestCase):
    def test_frontend_unit_passes_next_arguments_without_separator(self) -> None:
        unit = (ROOT / "deploy" / "edu-frontend.service").read_text(encoding="utf-8")
        self.assertIn(
            "ExecStart=/usr/bin/env pnpm --dir /opt/edu-agent/frontend "
            "exec next start -H 127.0.0.1 -p 3030",
            unit,
        )
        self.assertNotIn("next start -- -H", unit)

    def test_env_example_has_no_inline_assignment_comments(self) -> None:
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        offenders = [
            line.split("=", 1)[0]
            for line in env_example.splitlines()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*\s+#", line)
        ]
        self.assertEqual([], offenders)

    def test_manual_uses_current_frontend_command(self) -> None:
        manual = (ROOT / "docs" / "The_Website_deployment_plan.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("pnpm exec next start -H 127.0.0.1 -p 3030", manual)
        self.assertNotIn("next start -- -H", manual)
        self.assertIn(
            "/var/www/edu-agent-acme/.well-known/acme-challenge/health-check",
            manual,
        )
        self.assertNotIn(
            "tee /var/www/edu-agent-acme/health-check",
            manual,
        )


if __name__ == "__main__":
    unittest.main()
