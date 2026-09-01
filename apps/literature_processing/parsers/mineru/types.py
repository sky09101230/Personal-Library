from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageRange:
    start: int
    end: int

    def __post_init__(self):
        if self.start < 1 or self.end < self.start:
            raise ValueError("MinerU page range is invalid.")

    @property
    def expression(self):
        return f"{self.start}-{self.end}"


@dataclass(frozen=True, slots=True)
class MinerUSegmentResult:
    index: int
    page_range: PageRange
    data_id: str
    archive_bytes: bytes
    result_url: str


@dataclass(frozen=True, slots=True)
class MinerURawResult:
    batch_id: str
    model_version: str
    page_count: int
    segments: tuple[MinerUSegmentResult, ...]
    runtime_info: dict[str, object]


@dataclass(frozen=True, slots=True)
class MinerUStructuredSegment:
    index: int
    page_range: PageRange
    data_id: str
    source_format: str
    source_name: str
    payload: object


def segment_page_ranges(page_count, *, segment_pages=200):
    page_count = int(page_count)
    segment_pages = int(segment_pages)
    if page_count < 1:
        raise ValueError("PDF page count must be positive.")
    if segment_pages < 1 or segment_pages > 200:
        raise ValueError("MinerU segment size must be between 1 and 200 pages.")
    return tuple(
        PageRange(start=start, end=min(start + segment_pages - 1, page_count))
        for start in range(1, page_count + 1, segment_pages)
    )
