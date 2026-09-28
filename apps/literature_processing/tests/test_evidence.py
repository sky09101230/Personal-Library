from unittest.mock import Mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from ..evidence import Evidence, EvidenceCatalog, EvidenceError, validate_claims
from ..evidence_assets import _resolve_member


class EvidenceContractTests(SimpleTestCase):
    def setUp(self):
        self.parse = Mock(pk=4, artifact_sha256='a' * 64)
        self.item = Evidence('ev1:4:abc', 'text', 4, 'a' * 64, 'source', (2,), locator=('chunk', 1))
        self.catalog = EvidenceCatalog(self.parse, [self.item])

    def test_allowlist_and_claim_validation(self):
        claims = [{"text": "Supported finding", "evidence_ids": [self.item.evidence_id], "kind": "finding"}]
        self.assertEqual(validate_claims(self.catalog, claims, [self.item.evidence_id]), claims)
        with self.assertRaises(ValidationError):
            validate_claims(self.catalog, [{"text": "hallucination", "evidence_ids": [], "kind": "finding"}], [self.item.evidence_id])

    def test_unknown_evidence_is_rejected(self):
        with self.assertRaisesMessage(EvidenceError, 'unknown ID'):
            self.catalog.allowlist(['ev1:4:missing'])

    def test_asset_paths_are_exact_and_traversal_safe(self):
        names = ('paper/images/figure.png', 'paper/images/other.png')
        self.assertEqual(_resolve_member(names, 'paper/images/figure.png'), names[0])
        with self.assertRaises(EvidenceError):
            _resolve_member(names, '../figure.png')
        with self.assertRaises(EvidenceError):
            _resolve_member(names, 'figure.png')
