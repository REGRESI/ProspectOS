"""Run with python -m app.worker; SIGTERM finishes bounded in-flight work."""

import logging
import signal
import time

from app.jobs import run_once

stop = False


def shutdown(*_):
    global stop
    stop = True


def main():
    from app.runtime import validate_runtime

    validate_runtime()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    logging.basicConfig(level=logging.INFO)
    while not stop:
        try:
            count = run_once()
            if count:
                logging.info("jobs_processed=%s", count)
        except Exception:
            logging.error("worker_iteration_failed")  # Never log provider secrets or job payloads.
        if not stop:
            time.sleep(2)


if __name__ == "__main__":
    main()
