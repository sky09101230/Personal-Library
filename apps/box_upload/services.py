import http.client
import json
import mimetypes
import os
import secrets
import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class LiteratureStorageError(Exception):
    pass


class NjuBoxUploadError(LiteratureStorageError):
    pass


def upload_to_nju_box(uploaded_file, api_token=None, library_password=None, target_directory=None, repository_id=None):
    api_url = os.environ.get("NJU_BOX_API_URL", "https://box.nju.edu.cn").rstrip("/")
    repository_id = repository_id or os.environ.get("NJU_BOX_REPOSITORY_ID")
    target_directory = target_directory or os.environ.get("NJU_BOX_TARGET_DIRECTORY", "/")
    api_token = api_token or os.environ.get("NJU_BOX_API_TOKEN")
    library_password = library_password or os.environ.get("NJU_BOX_LIBRARY_PASSWORD")
    if not repository_id:
        raise NjuBoxUploadError("NJU Box repository ID is not configured.")
    if not api_token or not library_password:
        raise NjuBoxUploadError("Enter the NJU Box API Token and library password, or configure them in .env.")

    _require_https(api_url)
    repository_url = f"{api_url}/api2/repos/{repository_id}/"
    headers = {"Authorization": f"Token {api_token}"}
    unlock_headers = {
        **headers,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = _request(repository_url, "POST", unlock_headers, urlencode({"password": library_password}).encode())
    if response.status != 200:
        raise NjuBoxUploadError(_message_for_status(response.status, "unlock"))

    upload_link_url = f"{repository_url}upload-link/?{urlencode({'p': target_directory})}"
    response = _request(upload_link_url, "GET", headers)
    if response.status != 200:
        raise NjuBoxUploadError(_message_for_status(response.status, "get upload link"))
    upload_url = json.loads(response.body.decode("utf-8"))
    _require_https(upload_url)
    upload_url = _with_query_parameter(upload_url, "ret-json", "1")

    response = _upload_file(upload_url, uploaded_file, target_directory)
    if response.status != 200:
        raise NjuBoxUploadError(_message_for_status(response.status, "upload"))
    uploaded_name = _uploaded_name(response.body)
    return f"{target_directory.rstrip('/')}/{uploaded_name}"


def get_download_link(remote_path, api_token=None, library_password=None, repository_id=None):
    api_url = os.environ.get("NJU_BOX_API_URL", "https://box.nju.edu.cn").rstrip("/")
    repository_id = repository_id or os.environ.get("NJU_BOX_REPOSITORY_ID")
    api_token = api_token or os.environ.get("NJU_BOX_API_TOKEN")
    library_password = library_password or os.environ.get("NJU_BOX_LIBRARY_PASSWORD")
    if not repository_id or not api_token or not library_password:
        raise NjuBoxUploadError("Enter the NJU Box API Token and library password, or configure them in .env.")

    _require_https(api_url)
    repository_url = f"{api_url}/api2/repos/{repository_id}/"
    headers = {"Authorization": f"Token {api_token}"}
    unlock_headers = {**headers, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    response = _request(repository_url, "POST", unlock_headers, urlencode({"password": library_password}).encode())
    if response.status != 200:
        raise NjuBoxUploadError(_message_for_status(response.status, "unlock"))

    query = urlencode({"p": remote_path, "reuse": "1"})
    response = _request(f"{repository_url}file/?{query}", "GET", headers)
    if response.status != 200:
        raise NjuBoxUploadError(_message_for_status(response.status, "get download link"))
    try:
        link = json.loads(response.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise NjuBoxUploadError("NJU Box returned an invalid download link.") from exc
    _require_https(link)
    return link


def stream_from_nju_box(remote_path, byte_range=None, api_token=None, library_password=None, repository_id=None):
    """Open an NJU Box file as a closable HTTP stream without exposing its temporary URL."""
    link = get_download_link(
        remote_path,
        api_token=api_token,
        library_password=library_password,
        repository_id=repository_id,
    )
    parts = urlsplit(link)
    connection = http.client.HTTPSConnection(
        parts.hostname,
        parts.port or 443,
        context=ssl.create_default_context(),
        timeout=120,
    )
    headers = {"Accept": "application/pdf"}
    if byte_range:
        headers["Range"] = byte_range
    try:
        connection.request("GET", _path_with_query(parts), headers=headers)
        response = connection.getresponse()
    except OSError as exc:
        connection.close()
        raise NjuBoxUploadError("Could not connect to the NJU Box file service.") from exc
    if response.status not in (200, 206):
        try:
            response.read()
        finally:
            response.close()
            connection.close()
        raise NjuBoxUploadError(_message_for_status(response.status, "open PDF"))
    return _NjuBoxFileStream(response, connection)


def delete_from_nju_box(remote_path, api_token=None, library_password=None):
    """Delete one file from the encrypted NJU Box repository."""
    api_url = os.environ.get("NJU_BOX_API_URL", "https://box.nju.edu.cn").rstrip("/")
    repository_id = os.environ.get("NJU_BOX_REPOSITORY_ID")
    api_token = api_token or os.environ.get("NJU_BOX_API_TOKEN")
    library_password = library_password or os.environ.get("NJU_BOX_LIBRARY_PASSWORD")
    if not repository_id or not api_token or not library_password:
        raise NjuBoxUploadError("Enter the NJU Box API Token and library password, or configure them in .env.")

    _require_https(api_url)
    repository_url = f"{api_url}/api2/repos/{repository_id}/"
    headers = {"Authorization": f"Token {api_token}"}
    unlock_headers = {
        **headers,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = _request(repository_url, "POST", unlock_headers, urlencode({"password": library_password}).encode())
    if response.status not in (200, 409):
        raise NjuBoxUploadError(_message_for_status(response.status, "unlock"))

    query = urlencode({"p": remote_path})
    response = _request(f"{repository_url}file/detail/?{query}", "GET", {**headers, "Accept": "application/json"})
    if response.status != 200:
        raise NjuBoxUploadError(_message_for_status(response.status, "find file to delete"))
    response = _request(f"{repository_url}file/?{query}", "DELETE", {**headers, "Accept": "application/json"})
    if response.status not in (200, 204):
        raise NjuBoxUploadError(_message_for_status(response.status, "delete"))


def ensure_nju_box_directory(directory, api_token=None, library_password=None, repository_id=None):
    """Create one NJU Box directory path when it does not already exist."""
    if not directory.startswith("/") or ".." in directory.split("/"):
        raise NjuBoxUploadError("NJU Box directory must be an absolute path.")
    api_url = os.environ.get("NJU_BOX_API_URL", "https://box.nju.edu.cn").rstrip("/")
    repository_id = repository_id or os.environ.get("NJU_BOX_REPOSITORY_ID")
    api_token = api_token or os.environ.get("NJU_BOX_API_TOKEN")
    library_password = library_password or os.environ.get("NJU_BOX_LIBRARY_PASSWORD")
    if not repository_id or not api_token or not library_password:
        raise NjuBoxUploadError("Enter the NJU Box API Token and library password, or configure them in .env.")

    _require_https(api_url)
    repository_url = f"{api_url}/api2/repos/{repository_id}/"
    headers = {"Authorization": f"Token {api_token}", "Accept": "application/json"}
    response = _request(
        repository_url,
        "POST",
        {**headers, "Content-Type": "application/x-www-form-urlencoded"},
        urlencode({"password": library_password}).encode(),
    )
    if response.status not in (200, 409):
        raise NjuBoxUploadError(_message_for_status(response.status, "unlock"))

    normalized = directory.rstrip("/") or "/"
    response = _request(f"{repository_url}dir/?{urlencode({'p': normalized})}", "GET", headers)
    if response.status == 200:
        return
    if response.status != 404:
        raise NjuBoxUploadError(_message_for_status(response.status, "find directory"))

    response = _request(
        f"{repository_url}dir/?{urlencode({'p': normalized})}",
        "POST",
        {**headers, "Content-Type": "application/x-www-form-urlencoded"},
        urlencode({"operation": "mkdir", "create_parents": "true"}).encode(),
    )
    if response.status != 201:
        raise NjuBoxUploadError(_message_for_status(response.status, "create directory"))


def _request(url, method, headers, body=None):
    parts = urlsplit(url)
    connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, context=ssl.create_default_context(), timeout=120)
    try:
        connection.request(method, _path_with_query(parts), body=body, headers=headers)
        response = connection.getresponse()
        return _Response(response.status, response.read())
    except OSError as exc:
        raise NjuBoxUploadError("Could not connect to NJU Box.") from exc
    finally:
        connection.close()


def _upload_file(url, uploaded_file, target_directory):
    parts = urlsplit(url)
    boundary = f"----PLAB{secrets.token_hex(16)}"
    filename = uploaded_file.name.replace('"', "")
    content_type = getattr(uploaded_file, "content_type", None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    fields = _multipart_field(boundary, "filename", filename) + _multipart_field(boundary, "parent_dir", target_directory)
    ending = f"--{boundary}--\r\n".encode()
    content_length = len(file_header) + uploaded_file.size + 2 + len(fields) + len(ending)
    connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, context=ssl.create_default_context(), timeout=120)
    try:
        connection.putrequest("POST", _path_with_query(parts))
        connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        connection.putheader("Content-Length", str(content_length))
        connection.endheaders()
        connection.send(file_header)
        for chunk in uploaded_file.chunks():
            connection.send(chunk)
        connection.send(b"\r\n")
        connection.send(fields)
        connection.send(ending)
        response = connection.getresponse()
        return _Response(response.status, response.read())
    except OSError as exc:
        raise NjuBoxUploadError("Could not connect to NJU Box upload service.") from exc
    finally:
        connection.close()


def _multipart_field(boundary, name, value):
    return f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()


def _path_with_query(parts):
    return parts.path + (f"?{parts.query}" if parts.query else "")


def _with_query_parameter(url, name, value):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[name] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _uploaded_name(body):
    try:
        payload = json.loads(body.decode("utf-8"))
        name = payload[0]["name"]
    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise NjuBoxUploadError("NJU Box returned an invalid upload result.") from exc
    if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise NjuBoxUploadError("NJU Box returned an invalid uploaded filename.")
    return name


def _require_https(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise NjuBoxUploadError("NJU Box API URL must be a valid HTTPS URL.")


def _message_for_status(status, operation):
    messages = {
        400: "The API Token or library password was rejected.",
        401: "The API Token was rejected.",
        403: "Your NJU Box account does not have upload permission for this library.",
        404: "The NJU Box file was not found." if operation in ("find file to delete", "get download link", "open PDF") else "The configured NJU Box repository or target directory was not found.",
        409: "The library is already unlocked or is not encrypted.",
        440: "The encrypted library was not unlocked.",
        441: "A file with the same name already exists in the target directory.",
    }
    return messages.get(status, f"NJU Box {operation} failed (HTTP {status}).")


class _Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body


class _NjuBoxFileStream:
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
