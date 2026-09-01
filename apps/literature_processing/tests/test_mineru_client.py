from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase

from ..parsers.mineru.client import (
    MinerUAPIError,
    MinerUClient,
    MinerUConfig,
    MinerUConfigurationError,
    MinerUTimeoutError,
    _put_bytes,
    use_mineru_api_token,
)
from ..parsers.mineru.types import segment_page_ranges


def config(**overrides):
    values = {
        "base_url": "https://mineru.example/api/v4",
        "token": "test-token",
        "model_version": "vlm",
        "request_timeout": 30,
        "poll_interval": 0,
        "poll_timeout": 10,
        "segment_pages": 200,
        "result_max_bytes": 1024,
    }
    values.update(overrides)
    return MinerUConfig(**values)


class MinerUConfigurationTests(SimpleTestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_token_is_a_lazy_configuration_error(self):
        with self.assertRaises(MinerUConfigurationError) as context:
            MinerUClient()

        self.assertEqual(context.exception.code, "mineru_configuration")

    def test_585_pages_are_split_into_three_contiguous_ranges(self):
        ranges = segment_page_ranges(585)

        self.assertEqual([item.expression for item in ranges], ["1-200", "201-400", "401-585"])

    def test_config_repr_never_contains_token(self):
        self.assertNotIn("test-token", repr(config()))

    @patch.dict("os.environ", {"MINERU_API_TOKEN": "generic-token"}, clear=True)
    def test_worker_token_context_overrides_generic_token(self):
        with use_mineru_api_token("channel-token"):
            resolved = MinerUConfig.from_environment()

        self.assertEqual(resolved.token, "channel-token")
        self.assertEqual(MinerUConfig.from_environment().token, "generic-token")

    @patch.dict("os.environ", {"MINERU_API_TOKEN": "test-token"}, clear=True)
    def test_default_result_limit_is_800_mib(self):
        self.assertEqual(MinerUConfig.from_environment().result_max_bytes, 800 * 1024 * 1024)


class MinerUClientTests(SimpleTestCase):
    @patch("apps.literature_processing.parsers.mineru.client.HTTPSConnection")
    def test_presigned_put_sends_only_content_length(self, connection_class):
        connection = connection_class.return_value
        connection.getresponse.return_value.status = 200

        _put_bytes("https://upload.example/path?signature=secret", b"pdf", 30)

        connection_class.assert_called_once_with("upload.example", port=None, timeout=30)
        connection.request.assert_called_once_with(
            "PUT",
            "/path?signature=secret",
            body=b"pdf",
            headers={"Content-Length": "3"},
        )
        connection.close.assert_called_once_with()

    def test_upload_poll_and_download_use_official_batch_flow(self):
        json_calls = []
        uploads = []
        downloads = []
        progress_events = []
        poll_count = 0

        def request_json(method, url, headers, body, timeout):
            nonlocal poll_count
            json_calls.append((method, url, headers, body, timeout))
            if method == "POST":
                return {
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "file_urls": ["https://upload.example/1", "https://upload.example/2"],
                    },
                }
            poll_count += 1
            state = "running" if poll_count == 1 else "done"
            return {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "data_id": "run-1-part-001",
                            "state": state,
                            "full_zip_url": "https://result.example/1.zip" if state == "done" else "",
                        },
                        {
                            "data_id": "run-1-part-002",
                            "state": state,
                            "full_zip_url": "https://result.example/2.zip" if state == "done" else "",
                        },
                    ]
                },
            }

        client = MinerUClient(
            config(segment_pages=2),
            request_json=request_json,
            put_bytes=lambda url, content, timeout: uploads.append((url, content, timeout)),
            request_bytes=lambda url, timeout, limit: downloads.append((url, timeout, limit))
            or b"zip",
            sleep_func=lambda seconds: None,
            monotonic_func=iter(range(20)).__next__,
            progress_callback=progress_events.append,
        )

        result = client.parse_pdf(BytesIO(b"%PDF-source"), page_count=3, data_id="run-1")

        allocation = json_calls[0]
        self.assertEqual(allocation[0:2], ("POST", "https://mineru.example/api/v4/file-urls/batch"))
        self.assertEqual(allocation[2]["Authorization"], "Bearer test-token")
        self.assertEqual(
            [item["page_ranges"] for item in allocation[3]["files"]],
            ["1-2", "3-3"],
        )
        self.assertTrue(allocation[3]["enable_formula"])
        self.assertTrue(allocation[3]["enable_table"])
        self.assertEqual([item[0] for item in uploads], [
            "https://upload.example/1",
            "https://upload.example/2",
        ])
        self.assertTrue(all(item[1] == b"%PDF-source" for item in uploads))
        self.assertEqual(len(downloads), 2)
        self.assertEqual(result.batch_id, "batch-1")
        self.assertEqual([item.page_range.expression for item in result.segments], ["1-2", "3-3"])
        self.assertEqual(progress_events[0], {
            "state": "allocating",
            "current": 0,
            "total": 3,
            "unit": "pages",
            "batch_id": "",
        })
        self.assertIn("uploading", [event["state"] for event in progress_events])
        self.assertIn("running", [event["state"] for event in progress_events])
        self.assertEqual(progress_events[-1]["state"], "normalizing")

    def test_failed_segment_is_normalized_without_provider_detail(self):
        def request_json(method, url, headers, body, timeout):
            if method == "POST":
                return {"code": 0, "data": {"batch_id": "batch", "file_urls": ["https://up/1"]}}
            return {
                "code": 0,
                "data": {
                    "extract_result": {
                        "data_id": "run-part-001",
                        "state": "failed",
                        "err_msg": "provider secret detail",
                    }
                },
            }

        client = MinerUClient(
            config(),
            request_json=request_json,
            put_bytes=lambda url, content, timeout: None,
        )

        with self.assertRaises(MinerUAPIError) as context:
            client.parse_pdf(BytesIO(b"pdf"), page_count=1, data_id="run")

        self.assertNotIn("secret", str(context.exception))

    def test_poll_timeout_is_bounded(self):
        def request_json(method, url, headers, body, timeout):
            if method == "POST":
                return {"code": 0, "data": {"batch_id": "batch", "file_urls": ["https://up/1"]}}
            return {
                "code": 0,
                "data": {"extract_result": {"data_id": "run-part-001", "state": "running"}},
            }

        clock = iter((0, 0, 2, 4, 6)).__next__
        client = MinerUClient(
            config(poll_timeout=3),
            request_json=request_json,
            put_bytes=lambda url, content, timeout: None,
            sleep_func=lambda seconds: None,
            monotonic_func=clock,
        )

        with self.assertRaises(MinerUTimeoutError):
            client.parse_pdf(BytesIO(b"pdf"), page_count=1, data_id="run")

    def test_result_archive_size_is_checked_even_for_fake_transport(self):
        def request_json(method, url, headers, body, timeout):
            if method == "POST":
                return {"code": 0, "data": {"batch_id": "batch", "file_urls": ["https://up/1"]}}
            return {
                "code": 0,
                "data": {
                    "extract_result": {
                        "data_id": "run-part-001",
                        "state": "done",
                        "full_zip_url": "https://result/1.zip",
                    }
                },
            }

        client = MinerUClient(
            config(result_max_bytes=3),
            request_json=request_json,
            put_bytes=lambda url, content, timeout: None,
            request_bytes=lambda url, timeout, limit: b"large",
        )

        with self.assertRaises(MinerUAPIError):
            client.parse_pdf(BytesIO(b"pdf"), page_count=1, data_id="run")
