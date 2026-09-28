import json
from unittest.mock import patch

from django.test import SimpleTestCase

from ..llm import LLMConfig, LLMError, complete, load_config
from ..overview_provider import generate_deepseek_overview


class LLMProviderTests(SimpleTestCase):
    def config(self, **overrides):
        values = {
            "PAPER_LLM_BASE_URL": "http://localhost:53347/v1",
            "PAPER_LLM_API_KEY": "secret",
            "PAPER_CHAT_MODEL": "chat-model",
            "PAPER_OVERVIEW_MODEL": "overview-model",
            "PAPER_VISION_MODEL": "vision-model",
            "PAPER_LLM_VISION_ENABLED": "true",
        }
        values.update(overrides)
        return load_config(environ=values)

    def response(self, content='{"ok":true}', model='chat-model', finish='stop'):
        return {"model": model, "choices": [{"message": {"content": content}, "finish_reason": finish}], "usage": {"total_tokens": 3}}

    @patch('apps.literature_processing.llm.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 53347))])
    def test_roles_and_json_result(self, _resolve):
        config = self.config()
        calls = []
        result = complete('overview', [{"role": "user", "content": "source"}], output_mode='json', config=config,
                           request_func=lambda url, body, cfg, timeout: (calls.append((url, body)) or self.response(model='overview-model')))
        self.assertEqual(result.requested_model, 'overview-model')
        self.assertEqual(result.returned_model, 'overview-model')
        self.assertEqual(calls[0][0], 'http://localhost:53347/v1/chat/completions')
        self.assertEqual(calls[0][1]['response_format'], {'type': 'json_object'})

    @patch('apps.literature_processing.llm.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 53347))])
    def test_invalid_public_http_and_partial_profile(self, _resolve):
        with self.assertRaisesMessage(LLMError, 'incomplete'):
            load_config(environ={'PAPER_LLM_BASE_URL': 'http://localhost:53347/v1', 'PAPER_LLM_API_KEY': 'x'})
        with self.assertRaises(LLMError):
            load_config(environ={'PAPER_LLM_BASE_URL': 'http://example.com/v1', 'PAPER_CHAT_MODEL': 'x', 'PAPER_OVERVIEW_MODEL': 'y'})

    @patch('apps.literature_processing.llm.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 53347))])
    def test_unknown_role_and_malformed_json_are_safe(self, _resolve):
        config = self.config(PAPER_VISION_MODEL='')
        with self.assertRaisesMessage(LLMError, 'not configured'):
            complete('vision', [], config=config)
        with self.assertRaisesMessage(LLMError, 'malformed'):
            complete('chat', [], output_mode='json', config=config,
                     request_func=lambda *args: self.response('not-json'))

    @patch('apps.literature_processing.llm.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 53347))])
    def test_vision_uses_bounded_data_url(self, _resolve):
        config = self.config()
        calls = []
        result = complete('vision', [{"role": "user", "content": "inspect"}], images=[{"mime": "image/png", "data": b'png'}], config=config,
                           request_func=lambda url, body, cfg, timeout: (calls.append(body) or self.response('{}', model='vision-model')))
        self.assertEqual(result.returned_model, 'vision-model')
        content = calls[0]['messages'][-1]['content']
        self.assertTrue(content[-1]['image_url']['url'].startswith('data:image/png;base64,'))

    def test_legacy_config_keeps_deepseek_defaults(self):
        config = load_config(environ={'DEEPSEEK_API_KEY': 'x'})
        self.assertEqual(config.profile, 'deepseek-legacy')
        self.assertEqual(config.overview_model, 'deepseek-chat')

    @patch.dict('os.environ', {
        'PAPER_LLM_BASE_URL': 'http://localhost:53347/v1',
        'PAPER_LLM_API_KEY': 'secret',
        'PAPER_CHAT_MODEL': 'chat-model',
        'PAPER_OVERVIEW_MODEL': 'overview-model',
    }, clear=False)
    @patch('apps.literature_processing.llm.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 53347))])
    def test_existing_overview_entry_uses_unified_profile(self, _resolve):
        generated = generate_deepseek_overview(
            {'chunks': []},
            request_func=lambda url, body, config, timeout: self.response('{"summary_short":"ok"}', model='overview-model'),
        )
        self.assertEqual(generated['provider'], 'paper')
        self.assertEqual(generated['model'], 'overview-model')
