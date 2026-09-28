from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.test import SimpleTestCase

from .metadata import (
    MetadataResolutionError, _extract_first_page_title, _clean_text,
    fetch_doi_bibtex, select_pdf_doi,
)
from .upload_review import _bibtex_preview


class UploadMetadataRepairTests(SimpleTestCase):
    def test_crossref_fallback_and_identity_validation(self):
        record = '@article{x,title={A title},journal={A journal},doi={10.1000/test}}'
        response = MagicMock()
        response.__enter__.return_value.read.return_value = record.encode()
        with patch('apps.box_upload.metadata.urlopen', side_effect=[URLError('offline'), response]) as request:
            self.assertEqual(fetch_doi_bibtex('10.1000/test'), record)
            self.assertIn('/transform/application/x-bibtex', request.call_args.args[0].full_url)
        with self.assertRaises(MetadataResolutionError):
            _bibtex_preview('10.1000/other', raw_bibtex=record)
        with patch('apps.box_upload.metadata.urlopen', side_effect=URLError('offline')):
            with self.assertRaises(MetadataResolutionError):
                fetch_doi_bibtex('10.1000/test')

    def test_headers_and_author_lines_are_not_part_of_title(self):
        self.assertEqual(_extract_first_page_title(
            'Letter Vol. 50, No. 17/1 September 2025/ Optics Letters 5446\n'
            'Polarization-multiplexed diffractive neural networks\n'
            'for multi-task classification based on liquid crystals\n'
            'Mengqin Liu,1 Xianglin Ye,1 Yingjie Zhou,1\n1School of Physics'
        ), 'Polarization-multiplexed diffractive neural networks for multi-task classification based on liquid crystals')
        self.assertEqual(_extract_first_page_title(
            'A multilined\npaper title\nCheng, Jialuo; Li, Xu; Zhu, Wenjun\nPublished: 01/03/2026'
        ), 'A multilined paper title')
        self.assertEqual(_clean_text('Laser &amp; Photonics Reviews'), 'Laser & Photonics Reviews')

    def test_strong_first_doi_does_not_fetch_reference_list(self):
        evidence = {'title': 'A matching title', 'doi': '10.1000/paper', 'doi_candidates': [
            {'doi': '10.1000/paper', 'page': 1}, {'doi': '10.1000/reference', 'page': 20},
        ]}
        fetch = MagicMock(return_value='@article{x,title={A matching title},journal={Journal},doi={10.1000/paper}}')
        doi, _ = select_pdf_doi(evidence, bibtex_fetcher=fetch)
        self.assertEqual(doi, '10.1000/paper')
        fetch.assert_called_once_with('10.1000/paper')
