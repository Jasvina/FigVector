from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisProfile:
    name: str
    background_threshold: int
    min_area: int
    color_quantization: int


PROFILES: dict[str, AnalysisProfile] = {
    "synthetic": AnalysisProfile(
        name="synthetic",
        background_threshold=38,
        min_area=32,
        color_quantization=24,
    ),
    "real": AnalysisProfile(
        name="real",
        background_threshold=28,
        min_area=20,
        color_quantization=16,
    ),
}


def resolve_profile(
    profile: str = "real",
    *,
    background_threshold: int | None = None,
    min_area: int | None = None,
    color_quantization: int | None = None,
) -> AnalysisProfile:
    base = PROFILES.get(profile, PROFILES["real"])
    return AnalysisProfile(
        name=base.name,
        background_threshold=base.background_threshold if background_threshold is None else background_threshold,
        min_area=base.min_area if min_area is None else min_area,
        color_quantization=base.color_quantization if color_quantization is None else color_quantization,
    )
