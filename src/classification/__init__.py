"""Page classification module.

Classifies each page of a PDF based on its content characteristics.
"""

from src.classification.classifier import classify_pages

__all__ = ["classify_pages"]
