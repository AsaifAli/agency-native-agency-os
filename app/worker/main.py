
import logging
import signal
import socket
import threading
import uuid

from app.db import engine
from app.worker.runner import run_worker

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    stop_event = threading.Event()

    def request_shutdown(signum, frame) -> None:
        logger.info("Shutdown signal received: signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    hostname = socket.gethostname()[:100]
    worker_id = f"{hostname}:{uuid.uuid4().hex}"

    logger.info("Starting worker process: worker_id=%s", worker_id)

    try:
        run_worker(
            stop_event=stop_event,
            worker_id=worker_id,
        )
    except Exception:
        logger.exception("Worker process terminated due to an error")
        raise
    finally:
        logger.info("Disposing worker database engine")
        engine.dispose()


if __name__ == "__main__":
    main()
