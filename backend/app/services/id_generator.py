import uuid
from typing import Protocol


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


class UuidIdGenerator:
    def new_id(self) -> str:
        return str(uuid.uuid4())
