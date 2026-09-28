import os

from apps.box_upload.services import LiteratureStorageError
from apps.box_upload.storage import LOCAL, NAS_WEBDAV, NasWebDavLiteratureStorage
from apps.box_upload.local_storage import LocalLiteratureStorage


def get_nas_skill_storage():
    if os.environ.get("LITERATURE_STORAGE_BACKEND", "").strip().lower() == LOCAL:
        return LocalLiteratureStorage(category="skills")
    return NasWebDavLiteratureStorage(
        root=os.environ.get("NAS_WEBDAV_SKILLS_ROOT", "/public/PLAB_KnowledgeBase/Skills")
    )


def get_nas_skill_candidate_storage():
    if os.environ.get("LITERATURE_STORAGE_BACKEND", "").strip().lower() == LOCAL:
        return LocalLiteratureStorage(category="skill_candidates")
    return NasWebDavLiteratureStorage(
        root=os.environ.get(
            "NAS_WEBDAV_SKILL_CANDIDATES_ROOT",
            "/public/PLAB_KnowledgeBase/SkillCandidates",
        )
    )


def open_skill_stream(release):
    if release.storage_backend == LOCAL:
        return LocalLiteratureStorage(category="skills").open_stream(release.archive_remote_path)
    if release.storage_backend == NAS_WEBDAV:
        return NasWebDavLiteratureStorage(
            root=os.environ.get("NAS_WEBDAV_SKILLS_ROOT", "/public/PLAB_KnowledgeBase/Skills")
        ).open_stream(release.archive_remote_path)
    if release.storage_backend == "nju_box":
        raise LiteratureStorageError("NJU Box Skill storage has been retired; use NAS WebDAV.")
    raise LiteratureStorageError(f"Unsupported Skill storage backend: {release.storage_backend}.")
