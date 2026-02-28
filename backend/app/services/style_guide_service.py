"""Style Guide Generation Service — auto-generates style guides from reference images.
Ported from PaperBanana's style_guides/generate_category_style_guide.py.

Given a set of reference images from a specific category/venue, this service
uses an LLM to analyze common visual patterns and generate a comprehensive style guide.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STYLE_GUIDE_DIR = Path(__file__).parent.parent / "agents" / "style_guides"

STYLE_GUIDE_GENERATOR_SYSTEM = """You are a Lead Visual Designer and Style Analyst for top-tier AI conferences.

## TASK
You are given a collection of reference diagrams/plots from a specific academic venue and category.
Analyze these images to identify common visual patterns, then generate a comprehensive **Style Guide** document.

## ANALYSIS DIMENSIONS
For each image, analyze:
1. **Color Palettes**: Background fills, functional element colors, highlight colors (provide HEX codes)
2. **Shapes & Containers**: Node shapes, grouping patterns, border styles
3. **Lines & Arrows**: Connector styles, line semantics, integrated math symbols
4. **Typography & Icons**: Font families, label styles, icon usage and semantics
5. **Layout Patterns**: Flow direction, hierarchy, "Macro-Micro" patterns
6. **Domain-Specific Conventions**: Special visual conventions for the paper's domain

## OUTPUT FORMAT
Generate a Markdown document structured like this:
### 1. The "[Venue] Look"
[High-level aesthetic description]

### 2. Detailed Style Options
#### A. Color Palettes
[Specific HEX codes and usage rules]
#### B. Shapes & Containers
[Shape conventions and hierarchy]
#### C. Lines & Arrows
[Connector and flow conventions]
#### D. Typography & Icons
[Font and icon conventions]

### 3. Common Pitfalls
[What to avoid]

### 4. Domain-Specific Styles
[Domain-specific conventions observed]

Be specific with HEX codes, pixel values, and concrete examples from the analyzed images.
"""


async def generate_style_guide(
    chat_lb,
    reference_images: List[Dict[str, str]],
    venue: str = "NeurIPS 2025",
    category: str = "diagram",
    existing_guide_path: Optional[str] = None,
) -> str:
    """Generate a style guide from reference images.

    Args:
        chat_lb: Chat load balancer for LLM calls
        reference_images: List of dicts with keys 'base64' and optional 'caption'
        venue: Target venue name
        category: 'diagram' or 'plot'
        existing_guide_path: Optional path to existing guide for refinement

    Returns:
        Generated style guide as Markdown string
    """
    if not reference_images:
        raise ValueError("At least one reference image is required")

    # Build multimodal content
    contents: list[Any] = []

    intro = f"Analyze the following {len(reference_images)} reference {category}s from {venue} and generate a comprehensive style guide.\n\n"
    contents.append(intro)

    for idx, img in enumerate(reference_images):
        caption = img.get("caption", f"Reference {category} {idx + 1}")
        contents.append(f"Reference {idx + 1} — {caption}:\n")
        contents.append({
            "type": "image_base64",
            "data": img["base64"],
            "media_type": img.get("media_type", "image/jpeg"),
        })
        contents.append("\n")

    # If there's an existing guide, ask to refine it
    if existing_guide_path and os.path.exists(existing_guide_path):
        with open(existing_guide_path, "r", encoding="utf-8") as f:
            existing = f.read()
        contents.append(f"\n\nExisting style guide for reference (refine and expand upon this):\n{existing}\n")

    contents.append(f"\nGenerate the {venue} {category.capitalize()} Style Guide:")

    response = await chat_lb.chat_with_images(
        contents=contents,
        temperature=0.7,
        system_prompt=STYLE_GUIDE_GENERATOR_SYSTEM,
    )

    return response.strip()


async def save_style_guide(
    content: str,
    filename: str,
    output_dir: Optional[str] = None,
) -> str:
    """Save a generated style guide to file.

    Args:
        content: Style guide markdown content
        filename: Output filename (e.g., 'neurips2025_diagram_style_guide.md')
        output_dir: Optional output directory (defaults to agents/style_guides/)

    Returns:
        Path to saved file
    """
    target_dir = Path(output_dir) if output_dir else STYLE_GUIDE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    filepath = target_dir / filename
    filepath.write_text(content, encoding="utf-8")

    logger.info(f"Style guide saved to {filepath}")
    return str(filepath)
