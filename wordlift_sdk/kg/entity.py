class Entity:
    _props: dict[str, str]

    def __init__(self, props: dict[str, str]):
        self._props = props

    @property
    def id(self) -> str:
        return self._props['id']

    @property
    def url(self) -> str:
        return self._props['url']

    @staticmethod
    def from_dict(values: dict[str, str]):
        return Entity(values)
