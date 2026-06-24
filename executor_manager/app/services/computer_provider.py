"""Provider-neutral port for provisioning execution environments.

This module introduces the target vocabulary from the clean architecture
spec (§5.3): ``ComputerInstance``, ``ComputerCapability`` and
``ComputerProvider``.  It is intentionally additive — the existing
``ContainerPool`` / ``RunDispatchContainerPool`` / ``RunDispatchRuntime``
stack stays fully intact so all current behavior and tests remain green.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class ComputerCapability(str, Enum):
    """Capabilities an execution environment can provide.

    Used for capability-based scheduling instead of vendor-specific flags
    (e.g. ``browser_enabled: bool``).  Start minimal; add ``OFFICE``,
    ``NETWORK``, ``MCP`` etc. as the system grows.
    """

    SHELL = "shell"
    BROWSER = "browser"
    FILESYSTEM = "filesystem"


@dataclass(frozen=True)
class ComputerInstance:
    """A provisioned execution environment, provider-neutral.

    Attributes:
        instance_id: Opaque provider handle (container_id, pod_name, sandbox_id, …).
        executor_endpoint: HTTP URL where the executor worker listens.
        provider: Backend name (``"docker"``, ``"kubernetes"``, ``"e2b"`` …).
        capabilities: Capability set satisfied by this instance.
    """

    instance_id: str
    executor_endpoint: str
    provider: str
    capabilities: set[ComputerCapability] = field(default_factory=set)


class ComputerProvider(Protocol):
    """Provider-neutral port for acquiring and releasing execution environments.

    Implementations (``DockerComputerProvider``, future Kubernetes / E2B /
    Cua adapters) translate the capability-based contract into their own
    backend-specific APIs.  Callers depend only on this protocol.
    """

    async def acquire(
        self,
        *,
        session_id: str,
        user_id: str,
        requires: set[ComputerCapability],
        reuse_id: str | None = None,
    ) -> ComputerInstance:
        """Provision or reuse an environment satisfying ``requires``.

        Args:
            session_id: Logical session owning the environment.
            user_id: Owning user (for workspace isolation / quotas).
            requires: Minimum capability set the environment must satisfy.
            reuse_id: Opaque handle of an existing environment to reuse.

        Returns:
            A ``ComputerInstance`` describing the ready environment.
        """
        ...

    async def release(self, session_id: str) -> None:
        """Release the environment tied to ``session_id``."""
        ...
