import logging
import subprocess
import sys


def install_if_missing(package_spec: str, import_name=None):
    import_name = import_name or package_spec.split()[0]
    try:
        __import__(import_name)
    except ImportError:
        print(f"{import_name} not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_spec])
