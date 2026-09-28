from unittest.mock import Mock

from django.test import SimpleTestCase

from ..evidence import Evidence, EvidenceCatalog
from ..paper_context import ContextError, build_context_packet, build_skeleton_inventory
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
