"""已废弃的 NJU Box 兼容接口。

历史导入路径保留，以便旧脚本得到明确错误；所有入口均禁止网络访问。
"""


class LiteratureStorageError(Exception):
    pass


class NjuBoxUploadError(LiteratureStorageError):
    pass


def _retired(*args, **kwargs):
    raise NjuBoxUploadError("NJU Box backend has been retired; use NAS WebDAV.")


def upload_to_nju_box(*args, **kwargs):
    return _retired(*args, **kwargs)


def get_download_link(*args, **kwargs):
    return _retired(*args, **kwargs)


def stream_from_nju_box(*args, **kwargs):
    return _retired(*args, **kwargs)


def delete_from_nju_box(*args, **kwargs):
    return _retired(*args, **kwargs)


def ensure_nju_box_directory(*args, **kwargs):
    return _retired(*args, **kwargs)
