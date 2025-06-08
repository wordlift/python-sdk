import importlib.util
import os


class ConfigurationProvider:
    _config: dict

    @staticmethod
    def create(filepath: str = "config/default.py") -> "ConfigurationProvider":
        return ConfigurationProvider(filepath=filepath)

    def __init__(self, filepath: str):
        if not os.path.exists(filepath):
            self._config = {}
        spec = importlib.util.spec_from_file_location("local_config", filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._config = {k: getattr(module, k) for k in dir(module) if not k.startswith("_")}

    def get_value(self, key: str, default=None):
        # 1. Check globals
        if key in globals():
            return globals()[key]

        # 2. Check config.py
        if key in self._config:
            return self._config[key]

        # 3. Check environment variables
        import os
        if key in os.environ:
            return os.environ[key]

        # 4. Check Google Colab userdata
        try:
            from google.colab import userdata
            secret = userdata.get(key)
            if secret is not None:
                return secret
        except ImportError:
            pass  # Not running in Google Colab

        # 5. Return default if provided
        return default
