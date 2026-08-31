import os

from apps.box_upload.services import LiteratureStorageError
from apps.box_upload.storage import NAS_WEBDAV, NasWebDavLiteratureStorage


def get_nas_skill_storage():
    return NasWebDavLiteratureStorage(
        root=os.environ.get("NAS_WEBDAV_SKILLS_ROOT", "/public/PLAB_KnowledgeBase/Skills")
    )


def get_nas_skill_candidate_storage():
    return NasWebDavLiteratureStorage(
        root=os.environ.get(
            "NAS_WEBDAV_SKILL_CANDIDATES_ROOT",
            "/public/PLAB_KnowledgeBase/SkillCandidates",
        )
    )


def open_skill_stream(release):
    if release.storage_backend == NAS_WEBDAV:
        return get_nas_skill_storage().open_stream(release.archive_remote_path)
    if release.storage_backend == "nju_box":
        raise LiteratureStorageError("NJU Box Skill storage has been retired; use NAS WebDAV.")
    raise LiteratureStorageError(f"Unsupported Skill storage backend: {release.storage_backend}.")
