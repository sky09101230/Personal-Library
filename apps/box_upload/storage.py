import base64
import http.client
import mimetypes
import os
import re
import secrets
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from .services import LiteratureStorageError


NJU_BOX = "nju_box"  # 历史数据库值；运行时已废弃。
NAS_WEBDAV = "nas_webdav"
_SAFE_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


@dataclass(frozen=True)
class StoredLiteratureObject:
    backend: str
    remote_path: str


class LiteratureStorage(ABC):
    name = ""

    @abstractmethod
    def upload(self, uploaded_file):
        raise NotImplementedError

    @abstractmethod
    def open_stream(self, remote_path, byte_range=None):
        raise NotImplementedError

    @abstractmethod
    def delete(self, remote_path):
        raise NotImplementedError


class NasWebDavLiteratureStorage(LiteratureStorage):
    name = NAS_WEBDAV

    def __init__(self, base_url=None, username=None, password=None, root=None, timeout=120):
        self.base_url = (base_url if base_url is not None else os.environ.get("NAS_WEBDAV_BASE_URL", "")).rstrip("/")
        self.username = username if username is not None else os.environ.get("NAS_WEBDAV_USERNAME", "")
        self.password = password if password is not None else os.environ.get("NAS_WEBDAV_PASSWORD", "")
        self.root = root if root is not None else os.environ.get("NAS_WEBDAV_LITERATURE_ROOT", "")
        self.timeout = timeout
        self._parts = self._validate_configuration()
        credentials = f"{self.username}:{self.password}".encode("utf-8")
        self._authorization = "Basic " + base64.b64encode(credentials).decode("ascii")

    def upload(self, uploaded_file):
        extension = os.path.splitext(uploaded_file.name)[1].lower()
        if not _SAFE_EXTENSION.fullmatch(extension):
            extension = ".bin"
        remote_path = f"{self.root}/{secrets.token_hex(16)}{extension}"
        connection = self._connection()
        try:
            connection.putrequest("PUT", self._request_path(remote_path))
            connection.putheader("Authorization", self._authorization)
            connection.putheader("Content-Length", str(uploaded_file.size))
            connection.putheader(
                "Content-Type",
                getattr(uploaded_file, "content_type", None)
                or mimetypes.guess_type(uploaded_file.name)[0]
                or "application/octet-stream",
            )
            connection.endheaders()
            for chunk in uploaded_file.chunks():
                connection.send(chunk)
            response = connection.getresponse()
            response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise LiteratureStorageError("Could not connect to NAS WebDAV for upload.") from exc
        finally:
            connection.close()
        if response.status not in (200, 201, 204):
            raise LiteratureStorageError(f"NAS WebDAV upload failed (HTTP {response.status}).")
        return remote_path

    def ensure_root(self):
        connection = self._connection()
        try:
            connection.request(
                "PROPFIND",
                self._request_path(self.root),
                headers={"Authorization": self._authorization, "Depth": "0"},
            )
            response = connection.getresponse()
            status = response.status
            response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise LiteratureStorageError("Could not connect to NAS WebDAV to check the storage root.") from exc
        finally:
            connection.close()
        if status in (200, 207):
            return
        if status != 404:
            raise LiteratureStorageError(f"NAS WebDAV root check failed (HTTP {status}).")

        connection = self._connection()
        try:
            connection.request(
                "MKCOL",
                self._request_path(self.root),
                headers={"Authorization": self._authorization},
            )
            response = connection.getresponse()
            status = response.status
            response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise LiteratureStorageError("Could not connect to NAS WebDAV to create the storage root.") from exc
        finally:
            connection.close()
        if status not in (201, 405):
            raise LiteratureStorageError(f"NAS WebDAV root creation failed (HTTP {status}).")

    def open_stream(self, remote_path, byte_range=None):
        request_path = self._request_path(remote_path)
        connection = self._connection()
        headers = {"Authorization": self._authorization, "Accept": "*/*"}
        if byte_range:
            headers["Range"] = byte_range
        try:
            connection.request("GET", request_path, headers=headers)
            response = connection.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            connection.close()
            raise LiteratureStorageError("Could not connect to NAS WebDAV for download.") from exc
        if response.status not in (200, 206):
            try:
                response.read()
            finally:
                response.close()
                connection.close()
            raise LiteratureStorageError(f"NAS WebDAV download failed (HTTP {response.status}).")
        return _WebDavFileStream(response, connection)

    def delete(self, remote_path):
        request_path = self._request_path(remote_path)
        connection = self._connection()
        try:
            connection.request(
                "DELETE",
                request_path,
                headers={"Authorization": self._authorization},
            )
            response = connection.getresponse()
            response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise LiteratureStorageError("Could not connect to NAS WebDAV for deletion.") from exc
        finally:
            connection.close()
        if response.status not in (200, 204):
            raise LiteratureStorageError(f"NAS WebDAV deletion failed (HTTP {response.status}).")

    def _validate_configuration(self):
        parts = urlsplit(self.base_url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in ("", "/")
        ):
            raise LiteratureStorageError("NAS_WEBDAV_BASE_URL must be an HTTPS origin without credentials or a path.")
        if not self.username or not self.password:
            raise LiteratureStorageError("NAS WebDAV username and password are required.")
        root = self.root.rstrip("/")
        if not root.startswith("/") or "\\" in root or any(segment in ("", ".", "..") for segment in root.split("/")[1:]):
            raise LiteratureStorageError("NAS WebDAV root must be a safe absolute path.")
        self.root = root
        return parts

    def _connection(self):
        return http.client.HTTPSConnection(
            self._parts.hostname,
            self._parts.port or 443,
            context=ssl._create_unverified_context(),
            timeout=self.timeout,
        )

    def _request_path(self, remote_path):
        if not remote_path.startswith("/") or "\\" in remote_path:
            raise LiteratureStorageError("NAS WebDAV object path must be absolute.")
        segments = remote_path.split("/")[1:]
        if any(segment in ("", ".", "..") for segment in segments):
            raise LiteratureStorageError("NAS WebDAV object path is invalid.")
        if remote_path != self.root and not remote_path.startswith(f"{self.root}/"):
            raise LiteratureStorageError("NAS WebDAV object path is outside the configured root.")
        return quote(remote_path, safe="/")


def get_literature_storage(backend=None):
    backend = (backend or os.environ.get("LITERATURE_STORAGE_BACKEND") or NAS_WEBDAV).strip().lower()
    if backend == NAS_WEBDAV:
        return NasWebDavLiteratureStorage()
    if backend == NJU_BOX:
        raise LiteratureStorageError("NJU Box storage backend has been retired; use NAS WebDAV.")
    raise LiteratureStorageError(f"Unsupported literature storage backend: {backend}.")


def store_literature(uploaded_file):
    storage = get_literature_storage()
    return StoredLiteratureObject(storage.name, storage.upload(uploaded_file))


def open_literature_stream(document, byte_range=None):
    storage = get_literature_storage(document.storage_backend)
    return storage.open_stream(document.remote_path, byte_range=byte_range)


def delete_literature(document):
    storage = get_literature_storage(document.storage_backend)
    storage.delete(document.remote_path)


class _WebDavFileStream:
    def __init__(self, response, connection):
        self.status = response.status
        self.headers = {name.lower(): value for name, value in response.getheaders()}
        self._response = response
        self._connection = connection

    def get_header(self, name):
        return self.headers.get(name.lower())

    def iter_chunks(self, chunk_size=64 * 1024):
        try:
            while True:
                chunk = self._response.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            self.close()

    def close(self):
        if self._response is not None:
            self._response.close()
            self._response = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None
