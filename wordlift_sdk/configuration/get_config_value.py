import os
import importlib.util


def load_config_py(filepath="config.py"):
    if not os.path.exists(filepath):
        return {}
    spec = importlib.util.spec_from_file_location("local_config", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {k: getattr(module, k) for k in dir(module) if not k.startswith("_")}


def get_config_value(key, config_py_path=None, default=None):
    # 1. Check globals
    if key in globals():
        return globals()[key]

    # 2. Check config.py
    config = load_config_py(config_py_path)
    if key in config:
        return config[key]

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
