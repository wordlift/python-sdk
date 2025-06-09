from queue import Queue
from typing import Optional

from .entity_patch import EntityPatch


class EntityPatchQueue:
    queue: Queue[EntityPatch]
    hashes: set[str]

    def __init__(self):
        self.queue = Queue()
        self.hashes = set()

    def put(self, entity_patch: EntityPatch) -> None:
        self.queue.put(entity_patch)

    def get(self) -> Optional[EntityPatch]:
        if not self.queue.empty():
            return self.queue.get()

        return None

    def __len__(self) -> int:
        return self.queue.qsize()
