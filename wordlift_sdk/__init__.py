from .main import run_kg_import_workflow

__all__ = ["run_kg_import_workflow", "kg_build", "ingestion"]


def __getattr__(name: str):
    if name == "kg_build":
        import wordlift_sdk.kg_build as kg_build

        return kg_build
    if name == "ingestion":
        import wordlift_sdk.ingestion as ingestion

        return ingestion
    raise AttributeError(f"module 'wordlift_sdk' has no attribute '{name}'")
