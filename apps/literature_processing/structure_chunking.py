from collections import defaultdict
import hashlib

from .chunking import ChunkDraft
from .parsers import BlockKind, ParsedDocument, STRUCTURED_PARSE_SCHEMA_VERSION


STRUCTURE_CHUNKER_VERSION = "structure-blocks-v1"
DEFAULT_TARGET_CHARS = 2000
_EXCLUDED_KINDS = {BlockKind.HEADER, BlockKind.FOOTER}


def chunk_structured_document(document: ParsedDocument, *, target_chars=DEFAULT_TARGET_CHARS):
    if document.schema_version != STRUCTURED_PARSE_SCHEMA_VERSION:
        raise ValueError("Structure-aware chunking requires PLAB parse v2.")
    if target_chars < 1:
        raise ValueError("Chunk target size must be positive.")

    drafts = []
    current = []
    page_sequences = defaultdict(int)

    def flush():
        nonlocal current
        if current:
            drafts.append(_build_draft(current, len(drafts), page_sequences))
            current = []

    for page in document.pages:
        for block in page.blocks:
            if block.kind in _EXCLUDED_KINDS or not block.text.strip():
                continue
            for block_start, block_end, text in _split_block(
                block,
                target_chars=target_chars,
            ):
                is_table = block.kind is BlockKind.TABLE
                section_changed = current and current[-1][0].section_path != block.section_path
                projected = sum(len(item[3]) for item in current) + 2 * len(current) + len(text)
                if is_table or section_changed or projected > target_chars:
                    flush()
                current.append((block, block_start, block_end, text))
                if is_table or len(text) >= target_chars:
                    flush()
    flush()
    return tuple(drafts)


def _build_draft(pieces, sequence, page_sequences):
    text_parts = []
    source_spans = []
    cursor = 0
    for block, block_start, block_end, text in pieces:
        if text_parts:
            text_parts.append("\n\n")
            cursor += 2
        text_parts.append(text)
        source_spans.append({
            "block_id": block.block_id,
            "page": block.page_number,
            "chunk_start": cursor,
            "chunk_end": cursor + len(text),
            "block_start": block_start,
            "block_end": block_end,
        })
        cursor += len(text)
    text = "".join(text_parts)
    first_page = min(item[0].page_number for item in pieces)
    last_page = max(item[0].page_number for item in pieces)
    page_sequence = page_sequences[first_page]
    page_sequences[first_page] += 1
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ChunkDraft(
        chunk_key=(
            f"p{first_page:04d}-p{last_page:04d}-c{page_sequence:04d}-{digest[:16]}"
        ),
        sequence=sequence,
        page_number=first_page,
        end_page_number=last_page,
        page_sequence=page_sequence,
        start_offset=0,
        end_offset=len(text),
        text=text,
        content_sha256=digest,
        section_path=pieces[-1][0].section_path,
        source_spans=tuple(source_spans),
    )


def _split_block(block, *, target_chars):
    if block.kind is BlockKind.TABLE or len(block.text) <= target_chars:
        text = block.text.strip()
        start = block.text.find(text)
        return ((start, start + len(text), text),) if text else ()

    pieces = []
    cursor = 0
    while cursor < len(block.text):
        while cursor < len(block.text) and block.text[cursor].isspace():
            cursor += 1
        if cursor >= len(block.text):
            break
        target = min(cursor + target_chars, len(block.text))
        end = target if target == len(block.text) else _find_break(block.text, cursor, target)
        while end > cursor and block.text[end - 1].isspace():
            end -= 1
        if end <= cursor:
            end = target
        pieces.append((cursor, end, block.text[cursor:end]))
        cursor = end
    return tuple(pieces)


def _find_break(text, start, target):
    search_start = max(start + 1, target - min(400, target - start))
    positions = []
    for marker in ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", "; "):
        marker_index = text.rfind(marker, search_start, target)
        if marker_index >= 0:
            positions.append(marker_index + len(marker))
    marked_end = max(positions, default=-1)
    if marked_end > start:
        return marked_end
    end = target
    while end > start + 1 and text[end - 1].isalnum() and text[end].isalnum():
        end -= 1
    return end if end > start + 1 else target
