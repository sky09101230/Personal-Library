"""Local objects served through the existing authenticated download endpoints."""
import mimetypes
import os
import re
import secrets
from pathlib import Path

from django.conf import settings

from .services import LiteratureStorageError
from .storage import LiteratureStorage, _SAFE_EXTENSION


class LocalLiteratureStorage(LiteratureStorage):
    name = "local"

    def __init__(self, category="literature", root=None):
        base = Path(
            root
            or os.environ.get("LOCAL_STORAGE_ROOT")
            or r"E:\Personal-Library\data"
        )
        if not base.is_absolute():
            base = settings.BASE_DIR / base
        self.root = (base / category).resolve()

    def _path(self, key, allow_root=False):
        if not isinstance(key, str) or (not key and not allow_root):
            raise LiteratureStorageError("Local object path is invalid.")
        if key and any(
            not part or part in (".", "..") or part.endswith((".", " "))
            or any(c in '<>:"\\|?*' or ord(c) < 32 for c in part)
            or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}
            for part in key.split("/")
        ):
            raise LiteratureStorageError("Local object path must be a safe relative path.")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise LiteratureStorageError("Local object path is outside the configured root.")
        return path

    def ensure_root(self):
        return self.ensure_namespace("")

    def ensure_namespace(self, namespace):
        path = self._path(namespace, allow_root=True)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LiteratureStorageError("Could not create local storage directory.") from exc
        return str(path)

    def path_for(self, namespace, basename):
        if not basename or "/" in basename:
            raise LiteratureStorageError("Local object basename is invalid.")
        self._path(namespace, allow_root=True)
        key = f"{namespace}/{basename}" if namespace else basename
        self._path(key)
        return key

    def upload(self, uploaded_file, namespace=""):
        extension = os.path.splitext(uploaded_file.name)[1].lower()
        if not _SAFE_EXTENSION.fullmatch(extension):
            extension = ".bin"
        self.ensure_namespace(namespace)
        key = self.path_for(namespace, f"{secrets.token_hex(16)}{extension}")
        path = self._path(key)
        created = False
        try:
            with path.open("xb") as target:
                created = True
                for chunk in uploaded_file.chunks():
                    target.write(chunk)
        except Exception as exc:
            if created:
                path.unlink(missing_ok=True)
            raise LiteratureStorageError("Could not write local object.") from exc
        return key

    def exists(self, remote_path):
        return self._path(remote_path).is_file()

    def move(self, source_path, destination_path):
        source, destination = self._path(source_path), self._path(destination_path)
        self.ensure_namespace(destination_path.rpartition("/")[0])
        try:
            # A hard link fails if the destination exists, preserving original files.
            os.link(source, destination)
            source.unlink()
        except OSError as exc:
            raise LiteratureStorageError("Could not move local object without overwriting.") from exc

    def open_stream(self, remote_path, byte_range=None):
        path = self._path(remote_path)
        try:
            return _LocalFileStream(path, byte_range)
        except OSError as exc:
            raise LiteratureStorageError("Could not read local object.") from exc

    def delete(self, remote_path):
        try:
            self._path(remote_path).unlink()
        except OSError as exc:
            raise LiteratureStorageError("Could not delete local object.") from exc


class _LocalFileStream:
    def __init__(self, path, byte_range):
        self._file = path.open("rb")
        try:
            size = os.fstat(self._file.fileno()).st_size
            start, end = 0, size - 1
            self.status = 200
            self.headers = {"accept-ranges": "bytes", "content-type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}
            if byte_range:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
                if not match or not any(match.groups()):
                    raise LiteratureStorageError("Invalid local byte range.")
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    start = max(0, size - int(last))
                if start > end or start >= size:
                    self.status = 416
                    self.headers["content-range"] = f"bytes */{size}"
                    start, end = 0, -1
                else:
                    self.status = 206
                    self.headers["content-range"] = f"bytes {start}-{end}/{size}"
            self._remaining = max(0, end - start + 1)
            self.headers["content-length"] = str(self._remaining)
            self._file.seek(start)
        except Exception:
            self.close()
            raise

    def get_header(self, name):
        return self.headers.get(name.lower())

    def iter_chunks(self, chunk_size=64 * 1024):
        try:
            while self._remaining:
                chunk = self._file.read(min(chunk_size, self._remaining))
                if not chunk:
                    break
                self._remaining -= len(chunk)
                yield chunk
        finally:
            self.close()

    def close(self):
        self._file.close()
