"""
Test Florida-specific models.
"""

import pytest

from src.states.florida.models.docket import FLDocketDetails


def test_parse_docket_number_valid():
    """Test parsing valid Florida docket number."""
    result = FLDocketDetails.parse_docket_number("20240001-EI")
    assert result["year"] == 2024
    assert result["sequence_number"] == 1
    assert result["sector_code"] == "EI"


def test_parse_docket_number_another_valid():
    """Test parsing another valid docket number."""
    result = FLDocketDetails.parse_docket_number("20230156-GU")
    assert result["year"] == 2023
    assert result["sequence_number"] == 156
    assert result["sector_code"] == "GU"


def test_parse_docket_number_invalid():
    """Test parsing invalid docket number."""
    result = FLDocketDetails.parse_docket_number("invalid-format")
    assert result == {}


def test_parse_docket_number_wrong_format():
    """Test parsing wrong format docket number."""
    result = FLDocketDetails.parse_docket_number("2024-0001-EI")
    assert result == {}


def test_format_docket_number():
    """Test formatting docket number."""
    result = FLDocketDetails.format_docket_number(2024, 1, "EI")
    assert result == "20240001-EI"


def test_format_docket_number_padding():
    """Test docket number formatting with zero padding."""
    result = FLDocketDetails.format_docket_number(2023, 42, "WU")
    assert result == "20230042-WU"
