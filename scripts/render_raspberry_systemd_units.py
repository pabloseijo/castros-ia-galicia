#!/usr/bin/env python3
"""Render systemd units for Raspberry worker agents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/raspberry_agents.json"


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def service_text(agent_id: str, project_dir: Path) -> str:
    return f"""[Unit]
Description=Castros IA Raspberry agent: {agent_id}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={project_dir}
ExecStart=/usr/bin/env python3 scripts/run_raspberry_agents.py --agent {agent_id}
Nice=10
IOSchedulingClass=best-effort
"""


def timer_text(agent_id: str, on_calendar: str) -> str:
    return f"""[Unit]
Description=Schedule Castros IA Raspberry agent: {agent_id}

[Timer]
OnCalendar={on_calendar}
Persistent=true
Unit=castros-ia-{agent_id}.service

[Install]
WantedBy=timers.target
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render systemd service/timer units for Castros IA agents.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, help="Directory where .service/.timer files will be written.")
    parser.add_argument("--project-dir", type=Path, default=PROJECT_ROOT, help="Project directory path on the Raspberry.")
    parser.add_argument("--include-disabled", action="store_true", help="Render disabled agents too.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    rendered: list[tuple[str, str]] = []
    for agent in config.get("agents", []):
        if not args.include_disabled and not agent.get("enabled"):
            continue
        agent_id = agent["id"]
        on_calendar = agent.get("systemd_on_calendar", "daily")
        rendered.append((f"castros-ia-{agent_id}.service", service_text(agent_id, args.project_dir)))
        rendered.append((f"castros-ia-{agent_id}.timer", timer_text(agent_id, on_calendar)))

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for filename, text in rendered:
            (args.out_dir / filename).write_text(text, encoding="utf-8")
            print(args.out_dir / filename)
    else:
        for filename, text in rendered:
            print(f"# {filename}")
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
