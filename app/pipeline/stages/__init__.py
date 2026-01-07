"""
Pipeline Stages

Each stage processes a hearing through one step of the pipeline.

Pipeline flow:
  discover -> download -> transcribe -> [llm_polish] -> analyze -> smart_extract -> review -> extract

Note: Link and Match stages were merged into Analyze for simplicity.
      Entity linking and docket matching now happen automatically after LLM analysis.
      All extracted entities are flagged for human review.

Optional stages:
  - llm_polish: Targeted LLM correction for suspicious transcript segments
"""

from app.pipeline.stages.base import BaseStage, StageResult
from app.pipeline.stages.download import DownloadStage
from app.pipeline.stages.transcribe import TranscribeStage
from app.pipeline.stages.analyze import AnalyzeStage
from app.pipeline.stages.extract import ExtractStage
from app.pipeline.stages.docket_discovery import DocketDiscoveryStage
from app.pipeline.stages.smart_extract import SmartExtractStage
from app.pipeline.stages.llm_polish import LLMPolishStage

__all__ = [
    "BaseStage",
    "StageResult",
    "DownloadStage",
    "TranscribeStage",
    "LLMPolishStage",
    "AnalyzeStage",
    "SmartExtractStage",
    "ExtractStage",
    "DocketDiscoveryStage",
]
