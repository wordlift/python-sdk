import re
import unicodedata
from urllib.parse import urljoin

from wordlift_sdk.id_generator.id_generator_interface import IdGeneratorInterface


class IdGenerator(IdGeneratorInterface):

    def slugify(self, input_string: str) -> str:
        if not isinstance(input_string, str):
            return ''

        # Insert dash between camelCase or PascalCase transitions: e.g. "ProfilePage" -> "Profile-Page"
        input_string = re.sub(r'(?<=[a-z])(?=[A-Z])', '-', input_string)

        # Normalize diacritics
        slug = unicodedata.normalize('NFD', input_string)
        slug = ''.join(c for c in slug if unicodedata.category(c) != 'Mn')

        # Remove punctuation, convert to lowercase, format dashes
        slug = re.sub(r'[^\w\s-]', '', slug)  # remove punctuation
        slug = re.sub(r'\s+', '-', slug)  # replace spaces with dashes
        slug = re.sub(r'-+', '-', slug)  # collapse multiple dashes
        slug = slug.strip('-')  # trim leading/trailing dashes
        slug = slug.lower()

        return slug

    def create(self, base_uri: str, *args):
        full_url = base_uri
        for arg in args:
            full_url = full_url + '/' + self.slugify(arg)

        return full_url
