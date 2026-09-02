from uuid import uuid4

from pypdf import PdfReader

from ..contracts import ParserOutput, ParserRawArtifact
from .adapter import MinerUAdapter
from .archive import RAW_BUNDLE_CONTENT_TYPE, serialize_raw_bundle
from .client import MinerUClient


class MinerUParser:
    name = "mineru"
    parser_version = "mineru-api-v4"

    def __init__(self, *, client=None, adapter=None):
        self._client = client
        self._adapter = adapter or MinerUAdapter()

    def parse(self, file_obj):
        page_count = _pdf_page_count(file_obj)
        client = self._client or MinerUClient()
        data_id = f"plab-{uuid4().hex}"
        raw_result = client.parse_pdf(file_obj, page_count=page_count, data_id=data_id)
        document = self._adapter.convert(raw_result)
        return ParserOutput(
            document=document,
            raw_artifact=ParserRawArtifact(
                filename="mineru-raw-result.zip",
                content=serialize_raw_bundle(raw_result),
                content_type=RAW_BUNDLE_CONTENT_TYPE,
            ),
        )


def _pdf_page_count(file_obj):
    file_obj.seek(0)
    try:
        count = len(PdfReader(file_obj).pages)
    finally:
        file_obj.seek(0)
    if count < 1:
        raise ValueError("Source PDF has no pages.")
    return count
