import os

from apps.box_upload.services import LiteratureStorageError, stream_from_nju_box
from apps.box_upload.storage import NAS_WEBDAV, NJU_BOX, NasWebDavLiteratureStorage


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
    if release.storage_backend == NJU_BOX:
        return stream_from_nju_box(
            release.archive_remote_path,
            library_password=os.environ.get("NJU_SKILLS_LIBRARY_PASSWORD")
            or os.environ.get("NJU_BOX_LIBRARY_PASSWORD"),
            repository_id=release.repository_id or os.environ.get("NJU_SKILLS_REPOSITORY_ID"),
        )
    raise LiteratureStorageError(f"Unsupported Skill storage backend: {release.storage_backend}.")
