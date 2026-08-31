from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .metadata import resolve_pdf_metadata_safely
from .models import CanonicalDocument


class MetadataResilienceTests(TestCase):
    @patch("apps.box_upload.metadata._enriched_bibtex", side_effect=ValueError("unsupported BibTeX value"))
    def test_bibtex_evidence_enrichment_failure_keeps_resolved_metadata(self, _enrich):
        canonical = CanonicalDocument.objects.create(sha256="a" * 64)
        uploaded = SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.7\nhttps://doi.org/10.1000/TEST.1\n",
            content_type="application/pdf",
        )

        resolve_pdf_metadata_safely(
            canonical,
            uploaded,
            bibtex_fetcher=lambda _doi: """@article{paper,
                title={Resolved title},
                author={Lovelace, Ada},
                journal={Journal of Tests},
                year={2026},
                doi={10.1000/test.1}
            }""",
            crossref_fetcher=lambda doi: {"DOI": doi},
        )

        canonical.refresh_from_db()
        self.assertEqual(canonical.title, "Resolved title")
        self.assertEqual(canonical.authors, [{"name": "Ada Lovelace"}])
        self.assertEqual(canonical.journal, "Journal of Tests")
        self.assertEqual(canonical.publication_year, 2026)
        self.assertEqual(canonical.metadata_source, "bibtex")
        self.assertEqual(canonical.metadata_evidence["bibtex"]["enriched"].lstrip()[:8], "@article")
        self.assertEqual(
            canonical.metadata_evidence["provider_errors"]["bibtex_enrichment"],
            "BibTeX evidence enrichment failed.",
        )
