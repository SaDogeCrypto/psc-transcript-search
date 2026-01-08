"""
Tests for Florida PSC scrapers.

These tests verify the scraper functionality using mock responses
to avoid hitting the actual API during testing.
"""

import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock

from florida.scrapers import (
    FloridaClerkOfficeScraper,
    FloridaClerkOfficeClient,
    FloridaDocketData,
    FloridaThunderstoneScraper,
    FloridaThunderstoneClient,
    ThunderstoneDocument,
    ThunderstoneProfile,
)
from florida.config import FloridaConfig


# Sample API responses for mocking
MOCK_DOCKET_RESPONSE = {
    'result': [
        {
            'docketnum': '20250001-EI',
            'docketTitle': 'FPL Base Rate Case',
            'companyName': 'Florida Power & Light',
            'docketedDate': '2025-01-15T00:00:00',
            'docketCloseDate': None,
            'industryCode': 'E',
            'caseType': 'Rate Case',
        },
        {
            'docketnum': '20250002-GU',
            'docketTitle': 'Peoples Gas Rate Adjustment',
            'companyName': 'Peoples Gas',
            'docketedDate': '2025-01-16T00:00:00',
            'docketCloseDate': '2025-06-01T00:00:00',
            'industryCode': 'G',
            'caseType': 'Rate Adjustment',
        },
    ]
}

MOCK_THUNDERSTONE_SEARCH_RESPONSE = {
    'result': {
        'Results': [
            {
                'Id': '12345',
                'Title': 'FPL Rate Case Order - Final Decision',
                'FileUrl': '/documents/orders/20250001-EI/order.pdf',
                'DocumentType': 'Order',
                'DocketNumber': '20250001-EI',
                'FiledDate': '2025-03-15T00:00:00',
                'Content': 'The Commission hereby approves the rate increase...',
            },
        ],
        'TotalResults': 1,
    }
}

MOCK_PROFILES_RESPONSE = [
    {'Id': 'library', 'Name': 'All PSC Documents', 'DocumentCount': 500000},
    {'Id': 'orders', 'Name': 'Commission Orders', 'DocumentCount': 25000},
    {'Id': 'filingsCurrent', 'Name': '2025 Filings', 'DocumentCount': 1500},
]


class TestDocketParsing:
    """Test docket number parsing."""

    def test_parse_valid_docket(self):
        """Test parsing a valid Florida docket number."""
        result = FloridaClerkOfficeScraper.parse_docket_number('20250001-EI')
        assert result is not None
        assert result['year'] == 2025
        assert result['sequence'] == 1
        assert result['sector_code'] == 'EI'

    def test_parse_docket_with_larger_sequence(self):
        """Test parsing docket with larger sequence number."""
        result = FloridaClerkOfficeScraper.parse_docket_number('20241234-GU')
        assert result is not None
        assert result['year'] == 2024
        assert result['sequence'] == 1234
        assert result['sector_code'] == 'GU'

    def test_parse_invalid_docket_format(self):
        """Test that invalid docket formats return None."""
        assert FloridaClerkOfficeScraper.parse_docket_number('invalid') is None
        assert FloridaClerkOfficeScraper.parse_docket_number('2025-0001-EI') is None
        assert FloridaClerkOfficeScraper.parse_docket_number('20250001') is None
        assert FloridaClerkOfficeScraper.parse_docket_number('') is None

    def test_parse_various_sector_codes(self):
        """Test parsing dockets with different sector codes."""
        sectors = ['EI', 'EU', 'GU', 'WU', 'WS', 'TX', 'TL']
        for sector in sectors:
            result = FloridaClerkOfficeScraper.parse_docket_number(f'20250001-{sector}')
            assert result is not None
            assert result['sector_code'] == sector


class TestFloridaClerkOfficeScraper:
    """Test ClerkOffice API scraper."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        return FloridaConfig(
            clerk_office_base_url='https://test.floridapsc.com/api/ClerkOffice',
            api_rate_limit=10.0,
        )

    @pytest.fixture
    def scraper(self, mock_config):
        """Create scraper with mock config."""
        return FloridaClerkOfficeScraper(config=mock_config)

    def test_scraper_attributes(self, scraper):
        """Test scraper has correct attributes."""
        assert scraper.state_code == 'FL'
        assert scraper.state_name == 'Florida'
        assert 'psc.state.fl.us' in scraper.base_url

    @patch.object(FloridaClerkOfficeClient, 'get_dockets_by_type')
    def test_scrape_docket_list(self, mock_get, scraper):
        """Test scraping docket list."""
        mock_get.return_value = MOCK_DOCKET_RESPONSE['result']

        dockets = list(scraper.scrape_docket_list(year=2025, limit=10))

        assert len(dockets) == 2
        assert dockets[0].docket_number == '20250001-EI'
        assert dockets[0].utility_name == 'Florida Power & Light'
        assert dockets[0].status == 'open'

    @patch.object(FloridaClerkOfficeClient, 'get_dockets_by_type')
    def test_scrape_florida_dockets(self, mock_get, scraper):
        """Test scraping with full Florida metadata."""
        mock_get.return_value = MOCK_DOCKET_RESPONSE['result']

        dockets = list(scraper.scrape_florida_dockets(year=2025, limit=10))

        assert len(dockets) == 2
        assert isinstance(dockets[0], FloridaDocketData)
        assert dockets[0].year == 2025
        assert dockets[0].sequence == 1
        assert dockets[0].sector_code == 'EI'
        assert dockets[0].filed_date == date(2025, 1, 15)
        assert dockets[0].closed_date is None
        assert dockets[1].closed_date == date(2025, 6, 1)

    @patch.object(FloridaClerkOfficeClient, 'get_open_dockets')
    def test_connection_test_success(self, mock_get, scraper):
        """Test successful connection test."""
        mock_get.return_value = MOCK_DOCKET_RESPONSE['result']
        assert scraper.test_connection() is True

    @patch.object(FloridaClerkOfficeClient, 'get_open_dockets')
    def test_connection_test_failure(self, mock_get, scraper):
        """Test failed connection test."""
        mock_get.side_effect = Exception("Connection refused")
        assert scraper.test_connection() is False


class TestFloridaThunderstoneScraper:
    """Test Thunderstone document search scraper."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        return FloridaConfig(
            thunderstone_base_url='https://test.floridapsc.com/api/thunderstone',
            api_rate_limit=10.0,
        )

    @pytest.fixture
    def scraper(self, mock_config):
        """Create scraper with mock config."""
        return FloridaThunderstoneScraper(config=mock_config)

    @patch.object(FloridaThunderstoneClient, 'get_profiles')
    def test_get_profiles(self, mock_get, scraper):
        """Test getting search profiles."""
        mock_get.return_value = MOCK_PROFILES_RESPONSE

        profiles = scraper.get_profiles()

        assert len(profiles) == 3
        assert isinstance(profiles[0], ThunderstoneProfile)
        assert profiles[0].id == 'library'
        assert profiles[0].name == 'All PSC Documents'

    @patch.object(FloridaThunderstoneClient, 'search')
    def test_search_documents(self, mock_search, scraper):
        """Test searching documents."""
        mock_search.return_value = MOCK_THUNDERSTONE_SEARCH_RESPONSE

        docs = list(scraper.search('rate case', profile='orders', limit=10))

        assert len(docs) == 1
        assert isinstance(docs[0], ThunderstoneDocument)
        assert docs[0].title == 'FPL Rate Case Order - Final Decision'
        assert docs[0].document_type == 'Order'
        assert docs[0].docket_number == '20250001-EI'
        assert docs[0].file_type == 'PDF'

    @patch.object(FloridaThunderstoneClient, 'search')
    def test_search_by_docket(self, mock_search, scraper):
        """Test searching by docket number."""
        mock_search.return_value = MOCK_THUNDERSTONE_SEARCH_RESPONSE

        docs = list(scraper.search_by_docket('20250001-EI', limit=10))

        assert len(docs) == 1
        # Verify the search was called with docket number
        call_args = mock_search.call_args
        assert '20250001' in call_args[1]['search_text']

    @patch.object(FloridaThunderstoneClient, 'get_profiles')
    def test_connection_test_success(self, mock_get, scraper):
        """Test successful connection test."""
        mock_get.return_value = MOCK_PROFILES_RESPONSE
        assert scraper.test_connection() is True

    @patch.object(FloridaThunderstoneClient, 'get_profiles')
    def test_connection_test_failure(self, mock_get, scraper):
        """Test failed connection test."""
        mock_get.side_effect = Exception("Connection refused")
        assert scraper.test_connection() is False


class TestFloridaDocketData:
    """Test FloridaDocketData dataclass."""

    def test_to_docket_record(self):
        """Test conversion to standard DocketRecord."""
        data = FloridaDocketData(
            docket_number='20250001-EI',
            year=2025,
            sequence=1,
            sector_code='EI',
            title='Test Rate Case',
            utility_name='Test Utility',
            status='open',
            case_type='Rate Case',
            filed_date=date(2025, 1, 15),
            psc_docket_url='https://example.com/docket',
        )

        record = data.to_docket_record()

        assert record.docket_number == '20250001-EI'
        assert record.title == 'Test Rate Case'
        assert record.utility_name == 'Test Utility'
        assert record.status == 'open'
        assert record.case_type == 'Rate Case'
        assert record.filing_date == '2025-01-15'
        assert record.source_url == 'https://example.com/docket'


class TestThunderstoneDocument:
    """Test ThunderstoneDocument dataclass."""

    def test_document_defaults(self):
        """Test default values."""
        doc = ThunderstoneDocument()
        assert doc.title == ''
        assert doc.thunderstone_id is None
        assert doc.docket_number is None

    def test_document_with_values(self):
        """Test document with all values set."""
        doc = ThunderstoneDocument(
            thunderstone_id='12345',
            title='Test Order',
            document_type='Order',
            docket_number='20250001-EI',
            file_url='https://example.com/doc.pdf',
            file_type='PDF',
            filed_date=date(2025, 1, 15),
        )

        assert doc.thunderstone_id == '12345'
        assert doc.title == 'Test Order'
        assert doc.file_type == 'PDF'
        assert doc.filed_date == date(2025, 1, 15)
