"""
svg_renderer.py

Applies NeuroMotion anatomy rendering instructions
to an SVG anatomy model.

This module knows nothing about rehabilitation
exercises or muscle groups. It simply colors SVG
regions according to a render specification.
"""

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

from dashboard.anatomy.anatomy_renderer import AnatomyRender


SVG_FILE = (
    Path(__file__).parent
    / "assets"
    / "muscular_system.svg"
)


def render_svg(render: AnatomyRender) -> str:
    """
    Produces a highlighted SVG string.
    """

    tree = ET.parse(SVG_FILE)

    root = tree.getroot()

    # Color requested regions

    for region in render.highlighted_regions:

        element = root.find(f".//*[@id='{region.region_id}']")

        if element is None:
            continue

        element.set("fill", region.color)

    return ET.tostring(
        root,
        encoding="unicode",
    )