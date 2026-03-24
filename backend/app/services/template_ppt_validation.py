"""Validate uploaded PowerPoint template bytes before persisting."""

from __future__ import annotations

from io import BytesIO


class TemplatePptValidationError(ValueError):
    """Raised when bytes are not a usable .pptx template deck."""


def validate_template_deck_bytes(content: bytes, *, suffix: str) -> None:
    """
    Ensure bytes are a readable OOXML .pptx with at least one slide.

    Legacy .ppt is not supported by python-pptx.
    """
    suf = (suffix or "").lower().lstrip(".")
    if suf == "ppt":
        raise TemplatePptValidationError(
            "PowerPoint templates must be saved as .pptx. Legacy .ppt files are not supported."
        )
    if suf != "pptx":
        raise TemplatePptValidationError("Template upload must be a .pptx file.")

    from pptx import Presentation

    try:
        prs = Presentation(BytesIO(content))
    except Exception as exc:
        raise TemplatePptValidationError(
            "The file is not a valid .pptx (could not open as a presentation). "
            "Export or save as PowerPoint .pptx and try again."
        ) from exc

    if len(prs.slides) < 1:
        raise TemplatePptValidationError("Template must contain at least one slide.")
