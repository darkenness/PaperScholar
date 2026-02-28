"""Paper methodology extractor service — adapted from AutoFigure's extractor.py.

Extracts methodology descriptions from academic papers (PDF or Markdown/text)
using LLM analysis. Useful for auto-filling the "method description" field
in the figure generation pipeline.
"""

import logging
from pathlib import Path
from typing import Optional

from app.llm.load_balancer import LoadBalancer

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a highly discerning AI assistant for academic literature analysis. Your task is to extract ONLY the core theoretical and algorithmic methodology of a scientific paper.

**Core Objective:**
Isolate and extract the section(s) that describe the central innovation of the paper. This section answers the question, "What is the authors' core proposed method, model, or framework?" It should NOT describe how this method was tested or evaluated.

**Guiding Principles & Identification Criteria (What to INCLUDE):**
You must identify and extract the section(s) based on their semantic content. A section should be extracted if it primarily describes:
- The mathematical formulation or theoretical underpinnings of the work.
- The architecture of a novel model or system.
- The steps of a new algorithm.
- The conceptual framework being proposed.
- Common headings include "Method", "Our Approach", "Proposed Model/Framework", "Algorithm".

**Strict Exclusion Criteria (What to EXCLUDE):**
You MUST actively identify and exclude sections that, while related, are not part of the core methodology. DO NOT extract sections primarily describing:
- **Datasets:** Descriptions of data sources, collection methods, or statistics.
- **Experimental Setup:** Details about hardware, software environments, hyperparameters, or implementation specifics.
- **Evaluation Metrics:** Definitions of metrics like Accuracy, F1-Score, PSNR, etc.
- **Results or Ablation Studies:** Any reporting of experimental outcomes.
- Common headings to exclude are "Experiments", "Evaluation", "Dataset", "Implementation Details", "Results".

**Execution Rules:**
1.  **Verbatim Extraction:** Extract the qualifying section(s) verbatim, with original headings. Do not alter the text.
2.  **Boundary Detection:** Start the extraction at the section's heading and stop before a section that should be excluded (e.g., stop before `## Experiments` or `## Results`).
3.  **Output Format:** Produce only the raw Markdown content. Add no commentary.

--- PAPER CONTENT START ---
{content}
--- PAPER CONTENT END ---"""


def read_pdf(file_bytes: bytes) -> Optional[str]:
    """Read PDF content from bytes using PyMuPDF (fitz).

    Returns extracted text or None on failure.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = "\n".join(text_parts)
        if text.strip():
            logger.info(f"Read PDF with PyMuPDF: {len(text)} chars, {doc.page_count} pages")
            return text
    except ImportError:
        logger.error("PyMuPDF not installed. Install with: pip install PyMuPDF")
    except Exception as e:
        logger.error(f"PyMuPDF failed: {e}")

    return None


def read_text_file(file_bytes: bytes) -> Optional[str]:
    """Read plain text / markdown file from bytes."""
    for encoding in ("utf-8", "latin-1", "gbk"):
        try:
            return file_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


async def extract_methodology(
    file_bytes: bytes,
    filename: str,
    chat_lb: LoadBalancer,
    max_content_chars: int = 50000,
) -> Optional[str]:
    """Extract methodology from a paper file (PDF, Markdown, or text).

    Args:
        file_bytes: Raw file content bytes.
        filename: Original filename (used to determine file type).
        chat_lb: LoadBalancer for LLM calls.
        max_content_chars: Maximum characters to send to LLM.

    Returns:
        Extracted methodology text, or None on failure.
    """
    suffix = Path(filename).suffix.lower()

    # Read content based on file type
    if suffix == ".pdf":
        content = read_pdf(file_bytes)
    elif suffix in (".md", ".markdown", ".txt", ".tex"):
        content = read_text_file(file_bytes)
    else:
        logger.warning(f"Unsupported file type: {suffix}")
        return None

    if not content or len(content.strip()) < 100:
        logger.warning("File content too short or empty")
        return None

    # Truncate if too long
    if len(content) > max_content_chars:
        logger.info(f"Truncating content from {len(content)} to {max_content_chars} chars")
        content = content[:max_content_chars]

    prompt = EXTRACTION_PROMPT.format(content=content)

    logger.info("Extracting methodology with LLM...")
    try:
        result = await chat_lb.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=8000,
        )
        if result:
            logger.info(f"Extracted {len(result)} chars of methodology")
            return result.strip()
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")

    return None
