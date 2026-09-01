from io import BytesIO
import json
from zipfile import ZipFile

from django.test import SimpleTestCase

from ..parsers import BlockKind
from ..parsers.mineru import MinerUAdapter, MinerUArtifactError, serialize_raw_bundle
from ..parsers.mineru.types import MinerURawResult, MinerUSegmentResult, PageRange


def archive_json(name, payload):
    target = BytesIO()
    with ZipFile(target, "w") as archive:
        archive.writestr(name, json.dumps(payload, ensure_ascii=False))
        archive.writestr("paper_middle.json", json.dumps({"debug": True}))
        archive.writestr("paper.md", "markdown is not the source of truth")
    return target.getvalue()


def raw_result(segments, *, page_count=3):
    return MinerURawResult(
        batch_id="batch-1",
        model_version="vlm",
        page_count=page_count,
        segments=tuple(segments),
        runtime_info={"duration_ms": 1200},
    )


def segment(index, start, end, payload, *, v2=False, result_url="https://result/secret.zip"):
    suffix = "content_list_v2.json" if v2 else "content_list.json"
    return MinerUSegmentResult(
        index=index,
        page_range=PageRange(start, end),
        data_id=f"run-part-{index + 1:03d}",
        archive_bytes=archive_json(f"paper_{suffix}", payload),
        result_url=result_url,
    )


class MinerUAdapterTests(SimpleTestCase):
    def test_legacy_content_list_preserves_structure_page_bbox_and_order(self):
        first = segment(
            0,
            1,
            2,
            [
                {"type": "header", "text": "Journal header", "bbox": [10, 10, 900, 40], "page_idx": 0},
                {
                    "type": "text",
                    "text": "Introduction",
                    "text_level": 1,
                    "bbox": [50, 100, 900, 150],
                    "page_idx": 0,
                },
                {"type": "text", "text": "Opening paragraph.", "bbox": [50, 160, 900, 250], "page_idx": 0},
                {
                    "type": "table",
                    "table_caption": ["Table 1"],
                    "table_body": "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
                    "table_footnote": ["Measured values"],
                    "bbox": [50, 200, 950, 700],
                    "page_idx": 1,
                },
                {
                    "type": "equation",
                    "text": "$$E=mc^2$$",
                    "text_format": "latex",
                    "bbox": [100, 720, 800, 780],
                    "page_idx": 1,
                },
            ],
        )
        second = segment(
            1,
            3,
            3,
            [
                {
                    "type": "list",
                    "sub_type": "ref_text",
                    "list_items": ["[1] First reference", "[2] Second reference"],
                    "bbox": [50, 100, 900, 300],
                    "page_idx": 2,
                },
                {
                    "type": "ref_text",
                    "text": "[3] Direct reference block",
                    "bbox": [50, 300, 900, 315],
                    "page_idx": 2,
                },
                {
                    "type": "image",
                    "img_path": "images/figure.jpg",
                    "image_caption": ["Figure 1. Experimental layout."],
                    "bbox": [50, 320, 900, 800],
                    "page_idx": 2,
                },
            ],
        )

        parsed = MinerUAdapter().convert(raw_result((first, second)))
        repeated = MinerUAdapter().convert(raw_result((first, second)))

        self.assertEqual(parsed.schema_version, "plab.parse.v2")
        self.assertEqual([page.number for page in parsed.pages], [1, 2, 3])
        self.assertEqual([block.kind for block in parsed.pages[0].blocks], [
            BlockKind.HEADER,
            BlockKind.HEADING,
            BlockKind.PARAGRAPH,
        ])
        self.assertEqual(parsed.pages[0].blocks[1].heading_level, 1)
        self.assertEqual(parsed.pages[0].blocks[2].section_path, ("Introduction",))
        table = parsed.pages[1].blocks[0]
        self.assertEqual(table.kind, BlockKind.TABLE)
        self.assertIn("A B", table.text)
        self.assertEqual(table.structured_content["format"], "html")
        self.assertEqual(table.bounding_box.right, 950)
        self.assertEqual(parsed.pages[1].blocks[1].kind, BlockKind.EQUATION)
        self.assertEqual(parsed.pages[2].blocks[0].kind, BlockKind.REFERENCE)
        self.assertEqual(parsed.pages[2].blocks[1].kind, BlockKind.REFERENCE)
        self.assertEqual(parsed.pages[2].blocks[2].kind, BlockKind.FIGURE)
        self.assertEqual(parsed.pages[2].blocks[3].kind, BlockKind.FIGURE_CAPTION)
        self.assertEqual(
            [block.block_id for page in parsed.pages for block in page.blocks],
            [block.block_id for page in repeated.pages for block in page.blocks],
        )

    def test_content_list_v2_is_supported_with_explicit_warning(self):
        payload = [[
            {
                "type": "title",
                "content": {
                    "title_content": [{"type": "text", "content": "Methods"}],
                    "level": 2,
                },
                "bbox": [10, 20, 900, 80],
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [{"type": "text", "content": "Measured result."}]
                },
                "bbox": [10, 100, 900, 180],
            },
            {
                "type": "page_footer",
                "content": {"page_footer_content": [{"type": "text", "content": "Page 1"}]},
            },
        ]]

        parsed = MinerUAdapter().convert(raw_result((segment(0, 1, 1, payload, v2=True),), page_count=1))

        self.assertIn("mineru_content_list_v2_development", parsed.warnings)
        self.assertEqual(parsed.pages[0].blocks[0].kind, BlockKind.HEADING)
        self.assertEqual(parsed.pages[0].blocks[0].heading_level, 2)
        self.assertEqual(parsed.pages[0].blocks[1].text, "Measured result.")
        self.assertEqual(parsed.pages[0].blocks[2].kind, BlockKind.FOOTER)

    def test_segmented_merge_supports_local_page_indexes_through_page_585(self):
        segments = (
            segment(0, 1, 200, [{"type": "text", "text": "p1", "page_idx": 0}]),
            segment(1, 201, 400, [{"type": "text", "text": "p201", "page_idx": 0}]),
            segment(2, 401, 585, [{"type": "text", "text": "p585", "page_idx": 184}]),
        )

        parsed = MinerUAdapter().convert(raw_result(segments, page_count=585))

        self.assertEqual(len(parsed.pages), 585)
        self.assertEqual(parsed.pages[0].blocks[0].text, "p1")
        self.assertEqual(parsed.pages[200].blocks[0].text, "p201")
        self.assertEqual(parsed.pages[584].blocks[0].text, "p585")

    def test_raw_bundle_keeps_segment_zips_but_omits_result_urls(self):
        result = raw_result((
            segment(
                0,
                1,
                1,
                [{"type": "text", "text": "source", "page_idx": 0}],
                result_url="https://result.example/archive.zip?secret=token",
            ),
        ), page_count=1)

        content = serialize_raw_bundle(result)

        with ZipFile(BytesIO(content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertIn("segments/part-001.zip", archive.namelist())
        self.assertNotIn("result_url", str(manifest))
        self.assertNotIn("secret", str(manifest))
        self.assertEqual(manifest["batch_id"], "batch-1")

    def test_missing_structured_json_is_rejected_without_markdown_fallback(self):
        target = BytesIO()
        with ZipFile(target, "w") as archive:
            archive.writestr("paper.md", "markdown only")
        result = raw_result((
            MinerUSegmentResult(
                index=0,
                page_range=PageRange(1, 1),
                data_id="run-part-001",
                archive_bytes=target.getvalue(),
                result_url="https://result/1.zip",
            ),
        ), page_count=1)

        with self.assertRaises(MinerUArtifactError):
            MinerUAdapter().convert(result)
