class Entity:
    _props: dict[str, str]

    def __init__(self, props: dict[str, str]):
        self._props = props

    @property
    def iri(self):
        return self._props['iri']

    @property
    def url(self):
        return self._props['url']

    @staticmethod
    def from_dict(values: dict[str, str]):
        return Entity(values)
