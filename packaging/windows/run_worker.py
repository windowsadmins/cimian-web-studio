"""Started by the worker's scheduled task.

Reads the studio address and worker id from worker.conf in the data folder,
keeps the token in worker.token beside it, and writes its output to
logs\\worker.log there. It never exits on its own: if the config is missing or
the studio cannot be reached, it waits and tries again, so the task needs no
restart policy of its own.
"""

import argparse
import sys
import time
import tomllib
import traceback
from pathlib import Path

RETRY_SECONDS = 30
LOG_LIMIT = 10 * 1024 * 1024


def _open_log(data: Path) -> None:
    logs = data / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / "worker.log"
    if log.exists() and log.stat().st_size > LOG_LIMIT:
        log.replace(logs / "worker.log.1")
    stream = log.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def _settings(data: Path) -> tuple[str, str] | None:
    conf = data / "worker.conf"
    token = data / "worker.token"
    if not conf.is_file():
        print(f"{conf} is missing; copy worker.conf.example and fill it in", flush=True)
        return None
    try:
        values = tomllib.loads(conf.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"{conf} cannot be read: {error}", flush=True)
        return None
    url, worker_id = values.get("url"), values.get("id")
    if not isinstance(url, str) or not url or not isinstance(worker_id, str) or not worker_id:
        print(f"{conf} needs url and id", flush=True)
        return None
    if not token.is_file() or not token.read_text(encoding="utf-8").strip():
        print(f"{token} is missing or empty; write the worker token into it", flush=True)
        return None
    return url, worker_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="The worker's data folder.")
    data = parser.parse_args().data
    _open_log(data)
    from cimian_web_studio.cli import cli

    while True:
        settings = _settings(data)
        if settings is not None:
            url, worker_id = settings
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} connecting to {url} as {worker_id}")
            try:
                cli(
                    [
                        "worker",
                        "run",
                        "--url",
                        url,
                        "--id",
                        worker_id,
                        "--token-file",
                        str(data / "worker.token"),
                    ]
                )
            except SystemExit as stopped:
                print(f"the worker stopped with status {stopped.code}", flush=True)
            except Exception:
                traceback.print_exc()
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
