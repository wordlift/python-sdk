from .main import run_kg_import_workflow

__all__ = ["run_kg_import_workflow", "kg_build"]


def __getattr__(name: str):
    if name == "kg_build":
        import wordlift_sdk.kg_build as kg_build

        return kg_build
    raise AttributeError(f"module 'wordlift_sdk' has no attribute '{name}'")
