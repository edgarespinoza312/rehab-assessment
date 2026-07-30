"""
anatomy_renderer.py

Transforms NeuroMotion muscle metadata into a renderable
anatomy representation.

The renderer is intentionally independent of Flask,
HTML, and JavaScript. Its responsibility is to convert
MuscleGroup objects into visualization data.
"""

from dataclasses import dataclass

from dashboard.anatomy.muscle_groups import MuscleGroup
from dashboard.anatomy.anatomy_regions import svg_region
from dashboard.anatomy import muscle_colors


# ==========================================================
# Anatomy Region
# ==========================================================

@dataclass(frozen=True)
class AnatomyRegion:
    """
    A single SVG region and the color it should be rendered.
    """

    region_id: str
    color: str


# ==========================================================
# Render Result
# ==========================================================

@dataclass(frozen=True)
class AnatomyRender:
    """
    Collection of highlighted anatomy regions.
    """

    highlighted_regions: tuple[AnatomyRegion, ...]


# ==========================================================
# Renderer
# ==========================================================

def render(muscles: MuscleGroup) -> AnatomyRender:
    """
    Converts a MuscleGroup into anatomy visualization data.
    """

    regions = []

    # Primary muscles

    for muscle in muscles.primary:

        regions.append(

            AnatomyRegion(

                region_id=svg_region(muscle),

                color=muscle_colors.ACTIVE_PRIMARY,

            )

        )

    # Secondary muscles

    for muscle in muscles.secondary:

        regions.append(

            AnatomyRegion(

                region_id=svg_region(muscle),

                color=muscle_colors.ACTIVE_SECONDARY,

            )

        )

    return AnatomyRender(

        highlighted_regions=tuple(regions)

    )