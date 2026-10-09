"""Infer coding conventions from an existing codebase. Deterministic: no LLM, no network.

    from discovery import discover
    candidates = discover(Path("~/code/app").expanduser())

Evidence sources, strongest first:
  1. tooling config   .editorconfig, manifests (composer/npm/pip/go/cargo/maven/...), linter configs
  2. code statistics  indentation, quotes, semicolons, line length, file naming
  3. language markers framework-independent conventions        -> languages/<lang>.py
  4. framework markers conventions of frameworks in use        -> frameworks/<name>.py

A candidate is emitted only when the evidence is lopsided (default >= 90% over >= 5 files) and
always carries that evidence. To teach it something new, add a Marker (markers.py) to the right
language/framework module; no other file needs to change.
"""
from __future__ import annotations

from pathlib import Path

from .core import Candidate, Project, Thresholds
from .detectors import (Detector, EditorConfigDetector, FrameworkMarkerDetector, LanguageMarkerDetector,
                        ManifestDetector, NamingDetector, StyleDetector)
from .markers import (AbsentMarker, ChoiceMarker, FileMarker, Marker, OccurrenceMarker, Option,
                      marker_from_dict)

__all__ = ["Discoverer", "discover", "Candidate", "Project", "Thresholds", "Marker", "FileMarker",
           "OccurrenceMarker", "AbsentMarker", "ChoiceMarker", "Option", "marker_from_dict"]


class Discoverer:
    """Runs detectors over a project, in order, and concatenates their candidates."""

    def __init__(self, thresholds: Thresholds | None = None, extra_markers: list[Marker] | None = None,
                 detectors: list[Detector] | None = None):
        self.thresholds = thresholds or Thresholds()
        self.detectors = detectors or [
            EditorConfigDetector(),          # must precede StyleDetector (it sets project.has_editorconfig)
            ManifestDetector(),
            StyleDetector(),
            NamingDetector(),
            LanguageMarkerDetector(extra_markers or []),
            FrameworkMarkerDetector(),
        ]

    def run(self, root: Path) -> list[Candidate]:
        project = Project(root, self.thresholds)
        return [c for d in self.detectors for c in d.detect(project)]


def discover(root: Path, min_ratio: float = 0.9, min_files: int = 5,
             extra_markers: list[dict] | None = None) -> list[Candidate]:
    markers = [marker_from_dict(m) for m in extra_markers or []]
    return Discoverer(Thresholds(min_ratio=min_ratio, min_files=min_files), markers).run(Path(root))
