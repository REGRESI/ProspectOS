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
    # httpx logs full request URLs at INFO; search queries contain contact names.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    from app.agent import autopilot_tick

    last_tick = 0.0
    while not stop:
        if time.monotonic() - last_tick > 600:
            last_tick = time.monotonic()
            try:
                from app.flows import tick_all

                advanced = tick_all()
                if advanced:
                    logging.info("flow_runs_advanced=%s", advanced)
            except Exception:
                logging.error("flow_tick_failed")
            try:
                started = autopilot_tick()
                if started:
                    logging.info("autopilot_runs_started=%s", started)
            except Exception:
                logging.error("autopilot_tick_failed")
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
