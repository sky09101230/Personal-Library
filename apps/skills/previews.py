import html
import tempfile
import zipfile
from pathlib import PurePosixPath

from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename
from pygments.util import ClassNotFound

from apps.box_upload.services import LiteratureStorageError

from .storage import open_skill_stream


MAX_PREVIEW_BYTES = 256 * 1024
MAX_PREVIEW_FILES = 200
MAX_IN_MEMORY_ARCHIVE_SIZE = 10 * 1024 * 1024
_HIGHLIGHT_FORMATTER = HtmlFormatter(nowrap=True, cssclass="skill-code", style="monokai")
SYNTAX_CSS = mark_safe(_HIGHLIGHT_FORMATTER.get_style_defs(".skill-code"))


def build_release_preview(release, selected_path=""):
    if release is None:
        return {"available": False, "files": [], "error": "该 Skill 尚未发布文件。"}
    try:
        upstream = open_skill_stream(release)
        with tempfile.SpooledTemporaryFile(max_size=MAX_IN_MEMORY_ARCHIVE_SIZE) as archive_file:
            for chunk in upstream.iter_chunks():
                archive_file.write(chunk)
            archive_file.seek(0)
            with zipfile.ZipFile(archive_file) as archive:
                members = _file_members(archive)
                files = [{"path": path, "size": member.file_size} for path, member in members]
                selected = _select_member(members, selected_path)
                selected_preview = _preview_member(archive, selected) if selected else None
    except (LiteratureStorageError, OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return {"available": False, "files": [], "error": "暂时无法读取该 Skill 的文件预览。"}
    return {
        "available": True,
        "files": files,
        "selected_path": selected_preview["path"] if selected_preview else "",
        "selected": selected_preview,
        "syntax_css": SYNTAX_CSS,
    }


def _file_members(archive):
    members = []
    for member in archive.infolist():
        if member.is_dir():
            continue
        path = _safe_path(member.filename)
        if path:
            members.append((path, member))
    return sorted(members, key=lambda item: item[0].casefold())[:MAX_PREVIEW_FILES]


def _safe_path(name):
    if not name or "\\" in name or any(part in ("", ".", "..") for part in name.split("/")):
        return None
    path = PurePosixPath(name)
    if path.is_absolute():
        return None
    return path.as_posix()


def _select_member(members, selected_path):
    by_path = {path: member for path, member in members}
    if selected_path in by_path:
        return selected_path, by_path[selected_path]
    skill_document = next((item for item in members if PurePosixPath(item[0]).name.casefold() == "skill.md"), None)
    if skill_document:
        return skill_document
    return members[0] if members else None


def _preview_member(archive, selected):
    path, member = selected
    try:
        with archive.open(member) as stream:
            raw = stream.read(MAX_PREVIEW_BYTES + 1)
        if len(raw) > MAX_PREVIEW_BYTES:
            return {"path": path, "size": member.file_size, "can_preview": False, "reason": "文件超过 256 KiB 预览上限。"}
        if b"\0" in raw:
            return {"path": path, "size": member.file_size, "can_preview": False, "reason": "二进制文件不支持在线预览。"}
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"path": path, "size": member.file_size, "can_preview": False, "reason": "文件不是 UTF-8 文本。"}
    try:
        lexer = get_lexer_for_filename(path)
    except ClassNotFound:
        lexer = None
    if lexer is None:
        highlighted = html.escape(text)
        language = "text"
    else:
        highlighted = highlight(text, lexer, _HIGHLIGHT_FORMATTER)
        language = lexer.name
    return {
        "path": path,
        "size": member.file_size,
        "can_preview": True,
        "language": language,
        "content": mark_safe(highlighted),
    }
