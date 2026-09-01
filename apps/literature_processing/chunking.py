from dataclasses import dataclass
import hashlib

from .parsers import ParsedDocument


CHUNKER_VERSION = "page-chars-v2"
DEFAULT_MAX_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200
_BREAK_MARKERS = ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", "; ")


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    chunk_key: str
    sequence: int
    page_number: int
    page_sequence: int
    start_offset: int
    end_offset: int
    text: str
    content_sha256: str


def chunk_document(
    document: ParsedDocument,
    *,
    max_chars=DEFAULT_MAX_CHARS,
    overlap_chars=DEFAULT_OVERLAP_CHARS,
):
    if max_chars < 1 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("Chunk size must be positive and larger than overlap.")

    chunks = []
    sequence = 0
    for page in document.pages:
        page_chunks = _chunk_page(page.text, max_chars=max_chars, overlap_chars=overlap_chars)
        for page_sequence, (start, end, text) in enumerate(page_chunks):
            content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                ChunkDraft(
                    chunk_key=f"p{page.number:04d}-c{page_sequence:04d}-{content_sha256[:16]}",
                    sequence=sequence,
                    page_number=page.number,
                    page_sequence=page_sequence,
                    start_offset=start,
                    end_offset=end,
                    text=text,
                    content_sha256=content_sha256,
                )
            )
            sequence += 1
    return tuple(chunks)


def _chunk_page(text, *, max_chars, overlap_chars):
    chunks = []
    cursor = _skip_whitespace(text, 0)
    while cursor < len(text):
        target_end = min(cursor + max_chars, len(text))
        reached_page_end = target_end == len(text)
        end = target_end if reached_page_end else _find_break(text, cursor, target_end)
        end = _trim_trailing_whitespace(text, cursor, end)
        if end <= cursor:
            end = target_end
        chunks.append((cursor, end, text[cursor:end]))
        if reached_page_end:
            break
        next_cursor = max(cursor + 1, end - overlap_chars)
        cursor = _skip_whitespace(text, next_cursor)
    return chunks


def _find_break(text, start, target_end):
    search_start = max(start + 1, target_end - min(400, target_end - start))
    best_end = -1
    for marker in _BREAK_MARKERS:
        marker_index = text.rfind(marker, search_start, target_end)
        if marker_index >= 0:
            best_end = max(best_end, marker_index + len(marker))
    return best_end if best_end > start else target_end


def _skip_whitespace(text, offset):
    while offset < len(text) and text[offset].isspace():
        offset += 1
    return offset


def _trim_trailing_whitespace(text, start, end):
    while end > start and text[end - 1].isspace():
        end -= 1
    return end
