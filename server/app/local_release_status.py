"""Read-only local release registry and storage diagnostics for the launcher."""

from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import Database
from app.releases.registry import ManagedReleaseService
from app.releases.service import ReleaseUnavailable
from app.releases.storage import StorageStatus, inspect_storage, prepare_storage


def store_status(root: Path | None) -> str:
    status = inspect_storage(root)
    if not status.available:
        return f"Release store: {status.reason}."
    if not status.writable:
        return "Release store: directory is not writable."
    if not status.staging_ready:
        return "Release staging: incoming directory is unavailable or not writable."
    return "Release store and staging directory: available and writable."


def management_readiness(storage: StorageStatus, *, registry_compatible: bool) -> str:
    if storage.available and storage.writable and storage.staging_ready and registry_compatible:
        return "ready"
    return "unavailable"


def run() -> None:
    settings = Settings()
    root = settings.release_store_root
    prepare_storage(root, development_default=settings.release_store_is_default)
    print(f"Release storage root: {root if root is not None else 'not configured'}")
    storage = inspect_storage(root)
    print(store_status(root))
    database = Database(settings)
    registry_compatible = False
    try:
        service = ManagedReleaseService(
            database,
            root,
            settings.agent_server_url or settings.public_base_url,
        )
        try:
            service.list()
            registry_compatible = True
            print("Release registry/schema: compatible.")
            artifact = service.active_artifact()
        except ReleaseUnavailable as exc:
            print(f"Active installation release: unavailable ({exc}).")
        except SQLAlchemyError:
            print("Release registry/schema: unavailable; inspect schema and database service.")
        else:
            print(f"Active installation release: {artifact.version}; stored bytes verified.")
        readiness = management_readiness(storage, registry_compatible=registry_compatible)
        print(f"Release management: {readiness}.")
    finally:
        database.dispose()


if __name__ == "__main__":
    run()
