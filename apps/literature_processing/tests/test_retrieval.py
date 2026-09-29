from unittest.mock import Mock

from django.test import SimpleTestCase

from ..evidence import Evidence, EvidenceCatalog
from ..paper_context import ContextError, build_context_packet, build_skeleton_inventory, build_skeleton_context
from ..retrieval import retrieve


class RetrievalTests(SimpleTestCase):
    def setUp(self):
        parse = Mock(pk=1, artifact_sha256='a' * 64)
        self.items = [
            Evidence('ev-intro', 'text', 1, 'a' * 64, 'We use incoherent illumination to reduce speckle.', (1,), ('Introduction',), locator=('a',)),
            Evidence('ev-result', 'text', 1, 'a' * 64, 'Results show improved accuracy.', (8,), ('Results',), locator=('b',)),
            Evidence('ev-fig', 'figure', 1, 'a' * 64, '', (9,), ('Results',), figure_label='2', locator=('c',)),
        ]
        self.catalog = EvidenceCatalog(parse, self.items)

    def test_retrieval_uses_rewritten_english_terms_and_figures(self):
        hits = retrieve(self.catalog, '为什么使用非相干光？', rewritten_queries=('incoherent illumination',))
        self.assertEqual(hits[0].evidence_id, 'ev-intro')
        self.assertEqual(retrieve(self.catalog, 'What does Fig. 2 show?')[0].evidence_id, 'ev-fig')

    def test_context_packet_is_reproducible_and_allowlisted(self):
        first = build_context_packet(self.catalog, 'accuracy', rewritten_queries=())
        second = build_context_packet(self.catalog, 'accuracy', rewritten_queries=())
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.allowed_evidence_ids, {'ev-result'})

    def test_skeleton_inventory_keeps_figures_and_budget_failure_is_explicit(self):
        inventory = build_skeleton_inventory(self.catalog)
        self.assertEqual(inventory['figures'][0]['label'], '2')
        with self.assertRaisesMessage(ContextError, 'too small'):
            build_context_packet(self.catalog, 'accuracy', budget=20)

    def test_skeleton_reserves_tail_conclusion_and_figures_with_full_text(self):
        import json
        from dataclasses import replace
        items = [replace(self.items[0], evidence_id=f'intro-{i}', text=f'Introduction paragraph {i}. ' * 12) for i in range(30)]
        items += [replace(self.items[1], evidence_id='tail-result', text='The results support improved accuracy. ' * 8),
                  replace(self.items[0], evidence_id='tail-conclusion', pages=(120,), section_path=('Conclusions',), text='Conclusions: the optical method improves performance. ' * 8),
                  replace(self.items[2], pages=(119,)),
                  replace(self.items[0], evidence_id='tail-caption', pages=(119,), text='Figure 2. Final experiment comparing the proposed method and baseline. ' * 4)]
        catalog = EvidenceCatalog(self.catalog.document_parse, items)
        packet = build_skeleton_context(catalog, budget=10000)
        self.assertIn('tail-conclusion', packet['allowed_evidence_ids'])
        self.assertIn('tail-caption', packet['allowed_evidence_ids'])
        self.assertIn('ev-fig', packet['allowed_evidence_ids'])
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False).encode()), 10000)
        for item in packet['items']:
            self.assertEqual(item['text'], catalog.get(item['evidence_id']).text)
        with self.assertRaises(ContextError):
            build_skeleton_context(catalog, budget=1000)
