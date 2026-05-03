from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    """Identity value object carried by application commands.

    Represents the authenticated actor (user, service, or system) making a request.
    Designed to be immutable and easily passed through the application layer.
    """

    user_id: str
    tenant_id: str | None = None
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    auth_source: str = "unknown"
