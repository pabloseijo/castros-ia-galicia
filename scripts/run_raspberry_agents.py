#!/usr/bin/env python3
"""Run Raspberry-friendly Castros IA worker agents.

These are deterministic workers, not autonomous archaeological decision makers.
They run existing repo commands, keep logs/state, and avoid concurrent runs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/raspberry_agents.json"
DEFAULT_STATE_DIR = PROJECT_ROOT / "data/agent-state"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs/agents"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_event(log_dir: Path, event: dict[str, Any]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def agents_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {agent["id"]: agent for agent in config.get("agents", [])}


def lock_path(state_dir: Path, agent_id: str) -> Path:
    return state_dir / "locks" / f"{agent_id}.lock"


def acquire_lock(state_dir: Path, agent_id: str, stale_after_seconds: int) -> Path:
    path = lock_path(state_dir, agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if path.exists() and now - path.stat().st_mtime > stale_after_seconds:
        path.unlink()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"{agent_id} is already running: {path}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"{os.getpid()}\n{utc_now()}\n")
    return path


def release_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def run_agent(agent: dict[str, Any], state_dir: Path, log_dir: Path, dry_run: bool) -> int:
    agent_id = agent["id"]
    command = agent.get("command", [])
    if not isinstance(command, list) or not command:
        raise RuntimeError(f"{agent_id}: command must be a non-empty list")

    timeout = int(agent.get("timeout_seconds", 600))
    started_at = utc_now()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = started_at.replace(":", "").replace("-", "")
    log_path = log_dir / f"{stamp}_{agent_id}.log"
    state_path = state_dir / f"{agent_id}.json"

    if dry_run:
        print(f"[dry-run] {agent_id}: {' '.join(command)}")
        return 0

    lock = acquire_lock(state_dir, agent_id, timeout + 600)
    status = "failed"
    returncode = 1
    try:
        env = os.environ.copy()
        env["CASTROS_AGENT_ID"] = agent_id
        env["CASTROS_AGENT_STARTED_AT"] = started_at
        before = time.time()
        proc = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration = round(time.time() - before, 3)
        returncode = proc.returncode
        status = "ok" if returncode == 0 else "failed"
        log_path.write_text(
            "\n".join(
                [
                    f"agent={agent_id}",
                    f"started_at={started_at}",
                    f"finished_at={utc_now()}",
                    f"returncode={returncode}",
                    f"command={' '.join(command)}",
                    "",
                    "## stdout",
                    proc.stdout,
                    "",
                    "## stderr",
                    proc.stderr,
                ]
            ),
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired as exc:
        duration = timeout
        status = "timeout"
        returncode = 124
        log_path.write_text(
            "\n".join(
                [
                    f"agent={agent_id}",
                    f"started_at={started_at}",
                    f"finished_at={utc_now()}",
                    f"returncode={returncode}",
                    f"command={' '.join(command)}",
                    "",
                    "## stdout",
                    exc.stdout or "",
                    "",
                    "## stderr",
                    exc.stderr or "",
                ]
            ),
            encoding="utf-8",
        )
    finally:
        release_lock(lock)

    payload = {
        "agent_id": agent_id,
        "description": agent.get("description", ""),
        "status": status,
        "returncode": returncode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": duration,
        "command": command,
        "log_path": str(log_path.relative_to(PROJECT_ROOT)),
        "writes": agent.get("writes", []),
        "risk_level": agent.get("risk_level", ""),
    }
    write_json(state_path, payload)
    append_event(log_dir, payload)
    print(f"{agent_id}: {status} returncode={returncode} log={log_path.relative_to(PROJECT_ROOT)}")
    return returncode


def list_agents(config: dict[str, Any]) -> None:
    for agent in config.get("agents", []):
        enabled = "enabled" if agent.get("enabled") else "disabled"
        schedule = agent.get("systemd_on_calendar", "-")
        print(f"{agent['id']}\t{enabled}\t{schedule}\t{agent.get('risk_level', '')}\t{agent.get('description', '')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Castros IA Raspberry worker agents.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--list", action="store_true", help="List configured agents.")
    parser.add_argument("--agent", help="Run a single agent by id.")
    parser.add_argument("--run-enabled", action="store_true", help="Run all enabled agents in config order.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    if args.list:
        list_agents(config)
        return 0

    by_id = agents_by_id(config)
    if args.agent:
        if args.agent not in by_id:
            print(f"Unknown agent: {args.agent}", file=sys.stderr)
            return 2
        return run_agent(by_id[args.agent], args.state_dir, args.log_dir, args.dry_run)

    if args.run_enabled:
        failures = 0
        for agent in config.get("agents", []):
            if not agent.get("enabled"):
                continue
            rc = run_agent(agent, args.state_dir, args.log_dir, args.dry_run)
            if rc != 0:
                failures += 1
        return 1 if failures else 0

    print("Choose --list, --agent ID, or --run-enabled.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
