"""Wiring for the parsing service."""

from __future__ import annotations

from blob_store.s3 import DocumentsBucket, ParsedBucket
from preprocessing.parsing.analysis import DocumentAnalyser
from preprocessing.parsing.config import Settings
from preprocessing.parsing.pipelines import PdfPipeline, PipelineRegistry
from preprocessing.parsing.repository import ParseQueue
from preprocessing.parsing.service import ParsingService


def build_service(settings: Settings) -> ParsingService:
    """Wires the service and its collaborators.

    Args:
        settings: The loaded parsing settings.

    Returns:
        The service. Its converter is built on first use, not here.
    """
    return ParsingService(
        repository=ParseQueue(),
        documents=DocumentsBucket(),
        parsed=ParsedBucket(),
        pipelines=PipelineRegistry((pdf_pipeline(settings),)),
        analyser=DocumentAnalyser(),
        ocr_char_threshold=settings.ocr_char_threshold,
        min_confidence=settings.min_confidence,
    )


def pdf_pipeline(settings: Settings) -> PdfPipeline:
    """Builds the PDF pipeline the service converts with.

    Args:
        settings: The loaded parsing settings.

    Returns:
        The pipeline. Its converter is built on first use, not here.
    """
    return PdfPipeline(
        table_mode=settings.table_mode,
        heading_hierarchy=settings.heading_hierarchy,
        document_timeout_seconds=settings.document_timeout_seconds,
        artifacts_path=settings.artifacts_path,
        ocr_char_threshold=settings.ocr_char_threshold,
    )
