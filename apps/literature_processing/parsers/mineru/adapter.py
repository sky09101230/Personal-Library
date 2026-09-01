from collections import defaultdict
from hashlib import sha256
from html.parser import HTMLParser
import re

from ..contracts import (
    STRUCTURED_PARSE_SCHEMA_VERSION,
    BlockKind,
    ParsedBlock,
    ParsedBoundingBox,
    ParsedDocument,
    ParsedPage,
)
from .archive import MinerUArtifactError, read_structured_segments


class MinerUAdapter:
    name = "mineru"

    def convert(self, raw_result):
        segments = read_structured_segments(raw_result)
        page_drafts = defaultdict(list)
        warnings = []
        for segment in segments:
            if segment.source_format == "content_list":
                _read_legacy_segment(segment, page_drafts, warnings)
            elif segment.source_format == "content_list_v2":
                warnings.append("mineru_content_list_v2_development")
                _read_v2_segment(segment, page_drafts, warnings)
            else:
                raise MinerUArtifactError("MinerU structured format is unsupported.")

        section_stack = []
        pages = []
        for page_number in range(1, raw_result.page_count + 1):
            blocks = []
            for reading_order, draft in enumerate(page_drafts[page_number]):
                heading_level = draft.get("heading_level")
                if draft["kind"] is BlockKind.HEADING:
                    level = heading_level or 1
                    section_stack = section_stack[: level - 1]
                    section_stack.append(draft["text"].strip())
                block_id = _block_id(page_number, reading_order, draft)
                blocks.append(
                    ParsedBlock(
                        block_id=block_id,
                        page_number=page_number,
                        reading_order=reading_order,
                        kind=draft["kind"],
                        text=draft["text"],
                        structured_content=draft.get("structured_content", {}),
                        bounding_box=draft.get("bounding_box"),
                        heading_level=heading_level,
                        section_path=tuple(section_stack),
                        source=draft["source"],
                    )
                )
            pages.append(
                ParsedPage(
                    number=page_number,
                    text="\n\n".join(block.text for block in blocks if block.text.strip()),
                    blocks=tuple(blocks),
                )
            )
        runtime_info = {
            **raw_result.runtime_info,
            "actual_parser": self.name,
            "model_version": raw_result.model_version,
            "structured_sources": [segment.source_format for segment in segments],
        }
        return ParsedDocument(
            parser_name=self.name,
            parser_version=f"mineru-api-v4-{raw_result.model_version}",
            pages=tuple(pages),
            warnings=tuple(dict.fromkeys(warnings)),
            runtime_info=runtime_info,
            schema_version=STRUCTURED_PARSE_SCHEMA_VERSION,
        )


def _read_legacy_segment(segment, page_drafts, warnings):
    if not isinstance(segment.payload, list):
        raise MinerUArtifactError("MinerU content list must be an array.")
    for source_index, item in enumerate(segment.payload):
        if not isinstance(item, dict):
            raise MinerUArtifactError("MinerU content list item must be an object.")
        page_number = _page_number(item.get("page_idx"), segment)
        drafts = _legacy_item(item, segment, source_index, warnings)
        page_drafts[page_number].extend(drafts)


def _read_v2_segment(segment, page_drafts, warnings):
    if not isinstance(segment.payload, list):
        raise MinerUArtifactError("MinerU content list v2 must be an array.")
    for local_page_index, items in enumerate(segment.payload):
        if not isinstance(items, list):
            raise MinerUArtifactError("MinerU content list v2 page must be an array.")
        page_number = _page_number(local_page_index, segment)
        for source_index, item in enumerate(items):
            if not isinstance(item, dict):
                raise MinerUArtifactError("MinerU content list v2 item must be an object.")
            page_drafts[page_number].extend(
                _v2_item(item, segment, source_index, warnings)
            )


def _legacy_item(item, segment, source_index, warnings):
    source_type = str(item.get("type") or "unknown")
    source = _source(segment, source_index, source_type)
    bbox = _bbox(item.get("bbox"), warnings)
    if source_type == "text":
        level = item.get("text_level")
        heading_level = int(level) if isinstance(level, int) and level > 0 else None
        return [_draft(
            BlockKind.HEADING if heading_level else BlockKind.PARAGRAPH,
            _text(item.get("text")),
            source,
            bbox,
            heading_level=heading_level,
        )]
    if source_type == "equation":
        equation = _text(item.get("text"))
        return [_draft(
            BlockKind.EQUATION,
            equation,
            source,
            bbox,
            structured_content={"format": item.get("text_format") or "latex", "body": equation},
        )]
    if source_type == "table":
        body = _text(item.get("table_body"))
        captions = _string_list(item.get("table_caption"))
        footnotes = _string_list(item.get("table_footnote"))
        text = "\n".join((*captions, _html_text(body), *footnotes)).strip()
        return [_draft(
            BlockKind.TABLE,
            text,
            source,
            bbox,
            structured_content={
                "format": "html",
                "body": body,
                "caption": captions,
                "footnote": footnotes,
            },
        )]
    if source_type in {"image", "chart"}:
        caption_key = "chart_caption" if source_type == "chart" else "image_caption"
        captions = _string_list(item.get(caption_key))
        figure = _draft(
            BlockKind.FIGURE,
            "",
            source,
            bbox,
            structured_content={
                "asset_path": _text(item.get("img_path")),
                "visual_kind": source_type,
            },
        )
        caption_blocks = [
            _draft(BlockKind.FIGURE_CAPTION, caption, source, bbox)
            for caption in captions
            if caption.strip()
        ]
        return [figure, *caption_blocks]
    if source_type == "list":
        items = _string_list(item.get("list_items"))
        is_reference = item.get("sub_type") == "ref_text"
        return [_draft(
            BlockKind.REFERENCE if is_reference else BlockKind.LIST,
            "\n".join(items),
            source,
            bbox,
            structured_content={"items": items},
        )]
    if source_type == "ref_text":
        return [_draft(
            BlockKind.REFERENCE,
            _text(item.get("text") or item.get("content")),
            source,
            bbox,
        )]
    if source_type == "code":
        body = _text(item.get("code_body"))
        captions = _string_list(item.get("code_caption"))
        return [_draft(
            BlockKind.CODE,
            "\n".join((*captions, body)).strip(),
            source,
            bbox,
            structured_content={"body": body, "caption": captions},
        )]
    if source_type in {"header"}:
        return [_draft(BlockKind.HEADER, _text(item.get("text")), source, bbox)]
    if source_type in {"footer", "page_number", "page_footnote"}:
        return [_draft(BlockKind.FOOTER, _text(item.get("text")), source, bbox)]
    warnings.append("mineru_unknown_block_type")
    return [_draft(BlockKind.UNKNOWN, _text(item.get("text") or item.get("content")), source, bbox)]


def _v2_item(item, segment, source_index, warnings):
    source_type = str(item.get("type") or "unknown")
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    source = _source(segment, source_index, source_type)
    bbox = _bbox(item.get("bbox"), warnings)
    if source_type == "title":
        level = content.get("level")
        heading_level = int(level) if isinstance(level, int) and level > 0 else 1
        return [_draft(
            BlockKind.HEADING,
            _inline_text(content.get("title_content")),
            source,
            bbox,
            heading_level=heading_level,
        )]
    if source_type == "paragraph":
        return [_draft(
            BlockKind.PARAGRAPH,
            _inline_text(content.get("paragraph_content")),
            source,
            bbox,
        )]
    if source_type == "equation_interline":
        equation = _inline_text(content.get("math_content"))
        return [_draft(
            BlockKind.EQUATION,
            equation,
            source,
            bbox,
            structured_content={"format": content.get("math_type") or "latex", "body": equation},
        )]
    if source_type in {"list", "index"}:
        items = _inline_items(content.get("list_items"))
        return [_draft(
            BlockKind.REFERENCE if source_type == "index" else BlockKind.LIST,
            "\n".join(items),
            source,
            bbox,
            structured_content={"items": items},
        )]
    if source_type in {"code", "algorithm"}:
        body = _inline_text(
            content.get("code_content") or content.get("algorithm_content")
        )
        return [_draft(
            BlockKind.CODE,
            body,
            source,
            bbox,
            structured_content={"body": body, "language": content.get("code_language") or ""},
        )]
    if source_type == "table":
        body = _inline_text(content.get("table_body") or content.get("table_content"))
        return [_draft(
            BlockKind.TABLE,
            _html_text(body),
            source,
            bbox,
            structured_content={"format": "html", "body": body},
        )]
    if source_type in {"image", "chart"}:
        caption = _inline_text(
            content.get("chart_caption")
            if source_type == "chart"
            else content.get("image_caption")
        ).strip()
        blocks = [_draft(
            BlockKind.FIGURE,
            "",
            source,
            bbox,
            structured_content={
                "asset_path": _inline_text(content.get("image_path")),
                "visual_kind": source_type,
            },
        )]
        if caption:
            blocks.append(_draft(BlockKind.FIGURE_CAPTION, caption, source, bbox))
        return blocks
    if source_type == "page_header":
        return [_draft(BlockKind.HEADER, _inline_text(content), source, bbox)]
    if source_type in {"page_footer", "page_number", "page_footnote"}:
        return [_draft(BlockKind.FOOTER, _inline_text(content), source, bbox)]
    warnings.append("mineru_unknown_block_type")
    return [_draft(BlockKind.UNKNOWN, _inline_text(content), source, bbox)]


def _draft(kind, text, source, bbox, *, structured_content=None, heading_level=None):
    return {
        "kind": kind,
        "text": text,
        "source": source,
        "bounding_box": bbox,
        "structured_content": structured_content or {},
        "heading_level": heading_level,
    }


def _source(segment, source_index, source_type):
    return {
        "provider": "mineru",
        "segment_index": segment.index,
        "source_format": segment.source_format,
        "source_index": source_index,
        "source_type": source_type,
    }


def _page_number(raw_page_index, segment):
    if not isinstance(raw_page_index, int) or isinstance(raw_page_index, bool):
        raise MinerUArtifactError("MinerU block page index is invalid.")
    length = segment.page_range.end - segment.page_range.start + 1
    if 0 <= raw_page_index < length:
        return segment.page_range.start + raw_page_index
    if segment.page_range.start - 1 <= raw_page_index <= segment.page_range.end - 1:
        return raw_page_index + 1
    raise MinerUArtifactError("MinerU block page index is outside its segment.")


def _bbox(value, warnings):
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in value)
    ):
        warnings.append("mineru_invalid_bbox")
        return None
    left, top, right, bottom = (float(item) for item in value)
    if not (0 <= left <= right <= 1000 and 0 <= top <= bottom <= 1000):
        warnings.append("mineru_invalid_bbox")
        return None
    return ParsedBoundingBox(left=left, top=top, right=right, bottom=bottom)


def _block_id(page_number, reading_order, draft):
    fingerprint = repr((
        draft["kind"].value,
        draft["text"],
        draft.get("structured_content", {}),
        draft["source"],
    ))
    digest = sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
    return f"p{page_number:04d}-b{reading_order:04d}-{digest}"


def _text(value):
    return str(value or "").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")


def _string_list(value):
    if not isinstance(value, list):
        return []
    return [_text(item).strip() for item in value if _text(item).strip()]


def _inline_items(value):
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _inline_text(item).strip())]


def _inline_text(value):
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return "".join(_inline_text(item) for item in value)
    if isinstance(value, dict):
        if "children" in value:
            return _inline_text(value["children"])
        if "content" in value:
            return _inline_text(value["content"])
        return "".join(_inline_text(item) for item in value.values())
    return ""


class _TableTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, data):
        self.parts.append(data)


def _html_text(value):
    if not value:
        return ""
    parser = _TableTextParser()
    parser.feed(value)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)
