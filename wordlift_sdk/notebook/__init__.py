from .._lazy_exports import resolve_attr

__all__ = ["install_if_missing"]


_EXPORTS = {
    "install_if_missing": (
        "wordlift_sdk.notebook.install_if_missing",
        "install_if_missing",
    )
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.notebook",
        exports=_EXPORTS,
    )
