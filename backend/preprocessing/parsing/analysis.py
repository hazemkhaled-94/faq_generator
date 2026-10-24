"""Reading a converted document: body text, title, language and content hash."""

from __future__ import annotations

import hashlib

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from nlp.analysis import normalised
from nlp.language import detect, document_language
from nlp.pipelines import languages
from preprocessing.parsing.models import Conversion, ParsedDocument

#: Labels that carry a document's own title, in the order they are searched.
_TITLE_LABELS = (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER)


class Unconvincing(Exception):
    """Raised when a conversion is too unsure of itself to build on."""


class AlreadyHeld(Exception):
    """Raised when another document holds the same text as this one."""


class EmptyDocument(Exception):
    """Raised when a conversion produced no body text to work with."""


class UnconfiguredLanguage(Exception):
    """Raised when a document is in a language NLP_MODELS does not configure."""


class DocumentAnalyser:
    """Turns a converted document into the values the database holds.

    Format-independent, and so separate from the pipelines.
    """

    def analyse(self, conversion: Conversion) -> ParsedDocument:
        """Reads everything the database needs from a converted document.

        Args:
            conversion: What a pipeline produced.

        Returns:
            The values `documents` holds for this document.

        Raises:
            EmptyDocument: If the conversion produced no body text.
            UnconfiguredLanguage: If the body reads as a language NLP_MODELS
                does not name, which every later stage would read as another.
        """
        document = conversion.document
        body = self.body(document)
        if not body:
            raise EmptyDocument("the document has no extractable body text")
        self._configured(body)

        return ParsedDocument(
            title=self.title(document),
            language=detect(body),
            content_sha256=self.content_hash(body),
            page_count=len(document.pages),
            confidence=conversion.confidence,
            confidence_low=conversion.confidence_low,
        )

    @staticmethod
    def _configured(body: str) -> None:
        """Refuses a body in a language no pipeline is configured for."""
        found = document_language(body)
        if found is not None and found[0] not in languages():
            raise UnconfiguredLanguage(
                f"the document is in {found[1]} ({found[0]}), which NLP_MODELS "
                f"does not configure ({', '.join(languages())}): add its "
                "pipeline and table rows, or leave it out"
            )

    @staticmethod
    def body(document: DoclingDocument) -> str:
        """Renders the document's body content as text, table values included.

        Running headers and footers are left out.
        """
        return document.export_to_text().strip()

    @staticmethod
    def title(document: DoclingDocument) -> str | None:
        """Finds the document's title, or None if it carries none."""
        for label in _TITLE_LABELS:
            for item in document.texts:
                if item.label == label and (item.text or "").strip():
                    return item.text.strip()
        return None

    @staticmethod
    def content_hash(body: str) -> str:
        """Hashes the body with whitespace collapsed and case folded.

        Punctuation and digits are kept. The same fold as every other text
        comparison in the project.
        """
        return hashlib.sha256(normalised(body).encode()).hexdigest()
