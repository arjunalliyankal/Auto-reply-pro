"""
ingestion/image_extractor.py
─────────────────────────────
Extracts embedded images from PDF business documents, saves them to
disk, and captures the surrounding page text as "context" — used later
to semantically match a user's query to the right image.
"""

import os
import hashlib
from pathlib import Path

import fitz  # PyMuPDF

IMAGE_DIR         = "data/images"
MIN_IMAGE_SIZE    = 100    # skip tiny icons/logos under 100×100 px
MAX_CONTEXT_CHARS = 300    # how much page text to store as context

os.makedirs(IMAGE_DIR, exist_ok=True)


def _doc_id(file_path: str) -> str:
    """Short stable hash for a source PDF, used to namespace image filenames."""
    return hashlib.md5(file_path.encode()).hexdigest()[:8]


def extract_images_from_pdf(file_path: str) -> list[dict]:
    """
    Extract every embedded image from a PDF.

    Returns a list of metadata dicts:
    [{
        "image_id":     "a1b2c3d4_p3_i0",
        "source_file":  "brochure.pdf",
        "page_number":  3,
        "file_path":    "data/images/a1b2c3d4_p3_i0.png",
        "context_text": "...surrounding page text used for matching...",
        "width":        800,
        "height":       600,
    }, ...]
    """
    doc    = fitz.open(file_path)
    doc_id = _doc_id(file_path)
    results: list[dict] = []

    for page_index in range(len(doc)):
        page      = doc[page_index]
        page_text = page.get_text("text")[:MAX_CONTEXT_CHARS]
        images    = page.get_images(full=True)

        for img_idx, img in enumerate(images):
            xref       = img[0]
            base_image = doc.extract_image(xref)
            width      = base_image.get("width", 0)
            height     = base_image.get("height", 0)

            if width < MIN_IMAGE_SIZE or height < MIN_IMAGE_SIZE:
                continue  # skip small logos/icons — not useful to send

            image_bytes = base_image["image"]
            ext         = base_image.get("ext", "png")
            image_id    = f"{doc_id}_p{page_index + 1}_i{img_idx}"
            file_name   = f"{image_id}.{ext}"
            out_path    = os.path.join(IMAGE_DIR, file_name)

            with open(out_path, "wb") as f:
                f.write(image_bytes)

            results.append({
                "image_id":     image_id,
                "source_file":  Path(file_path).name,
                "page_number":  page_index + 1,
                "file_path":    out_path,
                "context_text": page_text.strip(),
                "width":        width,
                "height":       height,
            })

    doc.close()
    return results
