"""Vectorization edit service — adapted from autofigure-edit's 5-step pipeline.

Pipeline:
1. Generate raster figure from method text (or accept uploaded image)
2. Segment icons using SAM3 API (fal.ai / Roboflow)
3. Generate SVG template with placeholders via multimodal LLM
4. Validate and fix SVG syntax
5. Return SVG template + icon crops for frontend SVG editor
"""

import base64
import io
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.llm.load_balancer import LoadBalancer

logger = logging.getLogger(__name__)

# SAM3 API endpoints (from autofigure-edit)
SAM3_FAL_API_URL = "https://fal.run/fal-ai/sam-3/image"
SAM3_TIMEOUT = 300


async def segment_with_sam3_api(
    image_b64: str,
    prompts: List[str],
    sam_api_key: str,
    sam_backend: str = "fal",
    max_masks: int = 32,
    min_score: float = 0.5,
) -> List[Dict]:
    """Segment image using SAM3 API (adapted from autofigure-edit).

    Returns list of detected boxes: [{x1, y1, x2, y2, score, label, prompt}]
    """
    all_boxes = []

    for prompt in prompts:
        try:
            if sam_backend == "fal":
                headers = {"Authorization": f"Key {sam_api_key}", "Content-Type": "application/json"}
                payload = {
                    "image_url": f"data:image/png;base64,{image_b64}",
                    "prompt": prompt,
                    "apply_mask": False,
                    "return_multiple_masks": True,
                    "max_masks": max_masks,
                    "include_scores": True,
                    "include_boxes": True,
                }
                async with httpx.AsyncClient(timeout=SAM3_TIMEOUT) as client:
                    resp = await client.post(SAM3_FAL_API_URL, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                # Extract detections from fal.ai response
                metadata = data.get("metadata", [])
                if isinstance(metadata, list):
                    for item in metadata:
                        if not isinstance(item, dict):
                            continue
                        score = item.get("score", 0)
                        if score and float(score) >= min_score:
                            box = item.get("box", [])
                            if len(box) >= 4:
                                all_boxes.append({
                                    "x1": int(box[0]), "y1": int(box[1]),
                                    "x2": int(box[2]), "y2": int(box[3]),
                                    "score": float(score), "prompt": prompt,
                                })

            elif sam_backend == "roboflow":
                url = f"https://serverless.roboflow.com/sam3/concept_segment?api_key={sam_api_key}"
                payload = {
                    "image": {"type": "base64", "value": image_b64},
                    "prompts": [{"type": "text", "text": prompt}],
                    "format": "polygon",
                    "output_prob_thresh": min_score,
                }
                async with httpx.AsyncClient(timeout=SAM3_TIMEOUT) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                # Extract from Roboflow response
                for pr in data.get("prompt_results", []):
                    for pred in pr.get("predictions", []):
                        conf = pred.get("confidence", 0)
                        for mask in pred.get("masks", []):
                            if isinstance(mask, list) and mask:
                                xs = [p[0] for p in mask if isinstance(p, (list, tuple)) and len(p) >= 2]
                                ys = [p[1] for p in mask if isinstance(p, (list, tuple)) and len(p) >= 2]
                                if xs and ys:
                                    all_boxes.append({
                                        "x1": int(min(xs)), "y1": int(min(ys)),
                                        "x2": int(max(xs)), "y2": int(max(ys)),
                                        "score": float(conf), "prompt": prompt,
                                    })
        except Exception as e:
            logger.error(f"SAM3 API error for prompt '{prompt}': {e}")

    # Merge overlapping boxes (adapted from autofigure-edit's merge_overlapping_boxes)
    all_boxes = _merge_overlapping_boxes(all_boxes, overlap_threshold=0.9)

    # Assign labels (like autofigure-edit's <AF>01, <AF>02, ...)
    for i, box in enumerate(all_boxes):
        box["id"] = i
        box["label"] = f"AF{i+1:02d}"

    return all_boxes


def _calculate_overlap_ratio(box1: Dict, box2: Dict) -> float:
    """Calculate overlap ratio between two boxes (from autofigure-edit)."""
    x1 = max(box1["x1"], box2["x1"])
    y1 = max(box1["y1"], box2["y1"])
    x2 = min(box1["x2"], box2["x2"])
    y2 = min(box1["y2"], box2["y2"])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1["x2"] - box1["x1"]) * (box1["y2"] - box1["y1"])
    area2 = (box2["x2"] - box2["x1"]) * (box2["y2"] - box2["y1"])

    if area1 == 0 or area2 == 0:
        return 0.0

    return intersection / min(area1, area2)


def _merge_overlapping_boxes(boxes: List[Dict], overlap_threshold: float = 0.9) -> List[Dict]:
    """Iteratively merge overlapping boxes (from autofigure-edit)."""
    if overlap_threshold <= 0 or len(boxes) <= 1:
        return boxes

    working = [b.copy() for b in boxes]
    merged = True
    while merged:
        merged = False
        n = len(working)
        for i in range(n):
            if merged:
                break
            for j in range(i + 1, n):
                ratio = _calculate_overlap_ratio(working[i], working[j])
                if ratio >= overlap_threshold:
                    # Merge: take bounding box
                    new_box = {
                        "x1": min(working[i]["x1"], working[j]["x1"]),
                        "y1": min(working[i]["y1"], working[j]["y1"]),
                        "x2": max(working[i]["x2"], working[j]["x2"]),
                        "y2": max(working[i]["y2"], working[j]["y2"]),
                        "score": max(working[i].get("score", 0), working[j].get("score", 0)),
                        "prompt": working[i].get("prompt", working[j].get("prompt", "")),
                    }
                    working = [working[k] for k in range(n) if k != i and k != j]
                    working.append(new_box)
                    merged = True
                    break

    return working


SVG_TEMPLATE_PROMPT = """Write SVG code to pixel-level reproduce this image (except icons use gray rectangle placeholders).

CRITICAL DIMENSION REQUIREMENT:
- Set viewBox="0 0 {width} {height}" and width="{width}" height="{height}"

PLACEHOLDER STYLE:
Each icon area is marked with a gray rectangle (#808080), black border, and centered label.
Example: <g id="AF01"><rect x="100" y="50" width="80" height="80" fill="#808080" stroke="black" stroke-width="2"/><text x="140" y="90" text-anchor="middle" dominant-baseline="middle" fill="white" font-size="14">&lt;AF&gt;01</text></g>

Output ONLY SVG code starting with <svg and ending with </svg>."""


async def generate_svg_template(
    figure_b64: str,
    samed_b64: str,
    boxes: List[Dict],
    image_width: int,
    image_height: int,
    chat_lb: LoadBalancer,
    on_event: Optional[Callable] = None,
) -> Optional[str]:
    """Generate SVG template from figure + segmented image (like autofigure-edit step 4)."""

    if on_event:
        await on_event("stage", {"name": "svg_template", "status": "running", "progress": 0.6})

    prompt = SVG_TEMPLATE_PROMPT.format(width=image_width, height=image_height)

    contents = [
        prompt,
        {"type": "image_base64", "data": figure_b64, "media_type": "image/png"},
        {"type": "image_base64", "data": samed_b64, "media_type": "image/png"},
    ]

    try:
        response = await chat_lb.chat_with_images(contents=contents, temperature=0.7, max_tokens=50000)
    except Exception as e:
        logger.error(f"SVG template generation failed: {e}")
        return None

    from app.services.svg_service import extract_svg_code, validate_svg
    svg_code = extract_svg_code(response)
    if not svg_code:
        return None

    # Validate and fix
    is_valid, error = validate_svg(svg_code)
    if not is_valid:
        try:
            fix_resp = await chat_lb.chat(
                messages=[{"role": "user", "content": f"Fix SVG syntax error: {error}\n\n{svg_code}\n\nOutput ONLY fixed SVG:"}],
                temperature=0.3,
            )
            fixed = extract_svg_code(fix_resp)
            if fixed:
                svg_code = fixed
        except Exception:
            pass

    if on_event:
        await on_event("stage", {"name": "svg_template", "status": "done", "progress": 0.8})

    return svg_code


async def run_edit_pipeline(
    image_bytes: bytes,
    sam_api_key: Optional[str],
    sam_backend: str,
    sam_prompts: str,
    chat_lb: LoadBalancer,
    on_event: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Run the full autofigure-edit vectorization pipeline.

    Returns: {figure_b64, boxes, svg_template, icon_crops}
    """
    result: Dict[str, Any] = {"figure_b64": None, "boxes": [], "svg_template": None, "icon_crops": []}

    # Encode image
    figure_b64 = base64.b64encode(image_bytes).decode()
    result["figure_b64"] = figure_b64

    # Get image dimensions
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size

    if on_event:
        await on_event("stage", {"name": "edit_pipeline", "status": "running", "progress": 0.1})

    # Step 2: SAM3 segmentation
    if sam_api_key:
        if on_event:
            await on_event("stage", {"name": "sam3_segment", "status": "running", "progress": 0.2})

        prompts = [p.strip() for p in sam_prompts.split(",") if p.strip()]
        if not prompts:
            prompts = ["icon", "diagram", "arrow"]

        boxes = await segment_with_sam3_api(
            image_b64=figure_b64,
            prompts=prompts,
            sam_api_key=sam_api_key,
            sam_backend=sam_backend,
        )
        result["boxes"] = boxes

        if on_event:
            await on_event("intermediate", {
                "type": "text", "stage": "sam3_segment",
                "content": f"Detected {len(boxes)} icon regions",
            })
            await on_event("stage", {"name": "sam3_segment", "status": "done", "progress": 0.4})

        # Create samed image (draw gray boxes with labels)
        from PIL import ImageDraw, ImageFont
        samed = img.copy()
        draw = ImageDraw.Draw(samed)
        for box in boxes:
            x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
            draw.rectangle([x1, y1, x2, y2], fill="#808080", outline="black", width=3)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            draw.text((cx, cy), f"<AF>{box['label'][-2:]}", fill="white", anchor="mm")

        buf = io.BytesIO()
        samed.save(buf, format="PNG")
        samed_b64 = base64.b64encode(buf.getvalue()).decode()

        # Crop icons
        icon_crops = []
        for box in boxes:
            crop = img.crop((box["x1"], box["y1"], box["x2"], box["y2"]))
            crop_buf = io.BytesIO()
            crop.save(crop_buf, format="PNG")
            icon_crops.append({
                "label": box["label"],
                "b64": base64.b64encode(crop_buf.getvalue()).decode(),
                "x1": box["x1"], "y1": box["y1"],
                "width": box["x2"] - box["x1"], "height": box["y2"] - box["y1"],
            })
        result["icon_crops"] = icon_crops
    else:
        samed_b64 = figure_b64
        if on_event:
            await on_event("intermediate", {"type": "text", "stage": "sam3_segment", "content": "No SAM3 API key, skipping segmentation"})

    # Step 3-4: Generate SVG template
    svg_template = await generate_svg_template(
        figure_b64=figure_b64,
        samed_b64=samed_b64,
        boxes=result["boxes"],
        image_width=width,
        image_height=height,
        chat_lb=chat_lb,
        on_event=on_event,
    )
    result["svg_template"] = svg_template

    if on_event:
        await on_event("stage", {"name": "edit_pipeline", "status": "done", "progress": 1.0})

    return result


async def save_icon_crops(task_dir: str, icon_crops: List[Dict]) -> List[str]:
    """Save icon crops to disk for later assembly.

    Returns list of saved file paths.
    """
    import os
    icons_dir = os.path.join(task_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)

    saved = []
    for ic in icon_crops:
        label = ic["label"]
        icon_bytes = base64.b64decode(ic["b64"])
        path = os.path.join(icons_dir, f"{label}.png")
        with open(path, "wb") as f:
            f.write(icon_bytes)
        saved.append(path)

    return saved


def remove_background_simple(image_bytes: bytes) -> bytes:
    """Simple background removal: make white/near-white pixels transparent.

    For production use, RMBG-2.0 or similar model would be better,
    but this provides a usable fallback without extra dependencies.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    pixels = img.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            # Remove near-white backgrounds (threshold: RGB all > 240)
            if r > 240 and g > 240 and b > 240:
                pixels[x, y] = (r, g, b, 0)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def assemble_final_svg(
    template_svg: str,
    task_dir: str,
    chat_lb: Optional[LoadBalancer] = None,
) -> Optional[str]:
    """Assemble final SVG by replacing gray placeholder rectangles with actual icon images.

    Adapted from autofigure-edit's final assembly step:
    1. Find all <g id="AFxx"> groups in the template SVG
    2. For each placeholder, load the corresponding icon crop
    3. Remove background from icon
    4. Replace the gray rect + label text with an embedded <image> element

    Args:
        template_svg: The SVG template string with placeholders.
        task_dir: Directory containing the task's icon crops.
        chat_lb: Optional LLM client (unused for now, reserved for future LLM-assisted assembly).

    Returns:
        Assembled SVG string with icons embedded, or None on failure.
    """
    import os
    import xml.etree.ElementTree as ET

    icons_dir = os.path.join(task_dir, "icons")

    # If no icons directory, try to re-extract from figure
    if not os.path.isdir(icons_dir):
        logger.warning(f"No icons directory found at {icons_dir}")
        # Fall back: return template as-is (no icons to replace)
        return template_svg

    try:
        # Register SVG namespace to avoid ns0: prefix
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

        root = ET.fromstring(template_svg)
        ns = {"svg": "http://www.w3.org/2000/svg", "xlink": "http://www.w3.org/1999/xlink"}

        # Find all placeholder groups (id="AF01", "AF02", etc.)
        replacements = 0
        for g_elem in root.iter():
            elem_id = g_elem.get("id", "")
            if not re.match(r"AF\d+", elem_id):
                continue

            label = elem_id  # e.g., "AF01"
            icon_path = os.path.join(icons_dir, f"{label}.png")

            if not os.path.exists(icon_path):
                logger.warning(f"Icon file not found for {label}: {icon_path}")
                continue

            # Read and process icon
            with open(icon_path, "rb") as f:
                icon_bytes = f.read()

            # Remove background
            try:
                icon_bytes = remove_background_simple(icon_bytes)
            except Exception as e:
                logger.warning(f"Background removal failed for {label}: {e}")

            icon_b64 = base64.b64encode(icon_bytes).decode()

            # Find the rect element inside this group to get position/size
            rect = None
            for child in list(g_elem):
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "rect":
                    rect = child
                    break

            if rect is None:
                continue

            x = rect.get("x", "0")
            y = rect.get("y", "0")
            width = rect.get("width", "80")
            height = rect.get("height", "80")

            # Clear the group's children (remove rect + text label)
            for child in list(g_elem):
                g_elem.remove(child)

            # Add embedded image element
            image_elem = ET.SubElement(g_elem, "image")
            image_elem.set("x", x)
            image_elem.set("y", y)
            image_elem.set("width", width)
            image_elem.set("height", height)
            image_elem.set("href", f"data:image/png;base64,{icon_b64}")
            image_elem.set("preserveAspectRatio", "xMidYMid meet")

            replacements += 1
            logger.info(f"Replaced placeholder {label} with icon image")

        logger.info(f"Assembled final SVG: {replacements} placeholders replaced")

        return ET.tostring(root, encoding="unicode", xml_declaration=False)

    except ET.ParseError as e:
        logger.error(f"Failed to parse SVG template: {e}")
        return None
    except Exception as e:
        logger.error(f"SVG assembly failed: {e}")
        return None
