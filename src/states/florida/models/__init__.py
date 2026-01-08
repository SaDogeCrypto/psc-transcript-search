"""
Florida-specific model extensions.

These tables store Florida-specific fields that extend the core models:
- FLDocketDetails: Rate case data, commissioner assignments
- FLDocumentDetails: Thunderstone metadata
- FLHearingDetails: YouTube/RSS source info
"""

from src.states.florida.models.docket import FLDocketDetails
from src.states.florida.models.document import FLDocumentDetails
from src.states.florida.models.hearing import FLHearingDetails

__all__ = [
    "FLDocketDetails",
    "FLDocumentDetails",
    "FLHearingDetails",
]
