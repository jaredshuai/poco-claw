"""Shared worker identity for executor_manager.

Provides a single source of truth for the worker_id used when claiming runs,
starting runs, failing runs, and forwarding callbacks. This ensures callback
worker_id matches the worker_id used to claim/start/fail runs.
"""

import os
import socket


def get_worker_id() -> str:
    """Get the worker identity for this executor_manager process.

    The worker_id is composed of hostname and process ID, uniquely identifying
    this manager instance for run claiming and callback attribution.
    """
    return f"{socket.gethostname()}:{os.getpid()}"
