import os
import sys
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from typing import Type, TypeVar

T = TypeVar("T")


def load_override_class(name: str, class_name: str, default_class: Type[T], **kwargs) -> T:
    # Get override directory from environment variable or use default
    override_dir = os.environ.get("WORDLIFT_OVERRIDE_DIR", "app/overrides")
    override_path = Path(f"{override_dir}/{name}.py")

    if override_path.exists():
        spec = spec_from_file_location(name, override_path)
        mod = module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)

        cls = getattr(mod, class_name)
        return cls(**kwargs)

    return default_class(**kwargs)
