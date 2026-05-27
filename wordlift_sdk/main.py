from .container.application_container import ApplicationContainer


async def run_kg_import_workflow():
    application_container = ApplicationContainer()
    workflow = await application_container.create_kg_import_workflow()
    result = await workflow.run()
    if not result.ok:
        raise SystemExit(f"{len(result.failures)} URL handler failure(s) detected.")
