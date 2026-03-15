from .._lazy_exports import resolve_attr
from .load_override_class import load_override_class

__all__ = [
    "Context",
    "load_override_class",
    "WebPageImportProtocolInterface",
    "DefaultWebPageImportProtocol",
]


_EXPORTS = {
    "Context": ("wordlift_sdk.protocol.context", "Context"),
    "WebPageImportProtocolInterface": (
        "wordlift_sdk.protocol.web_page_import_protocol",
        "WebPageImportProtocolInterface",
    ),
    "DefaultWebPageImportProtocol": (
        "wordlift_sdk.protocol.web_page_import_protocol",
        "DefaultWebPageImportProtocol",
    ),
}


def __getattr__(name: str):
    if name == "load_override_class":
        return load_override_class
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.protocol",
        exports=_EXPORTS,
        extra="workflow",
    )
