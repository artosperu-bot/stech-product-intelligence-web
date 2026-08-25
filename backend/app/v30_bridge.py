from __future__ import annotations
from pathlib import Path
import sys

CORE_DIR = Path(__file__).resolve().parents[1] / 'legacy_core'
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))


def required_core_modules() -> list[str]:
    return [
        'chatgpt_browser','browser_manager','excel_workflow','research_runner','result_parser','template_engine','prompt_builder',
        'price_prompt_builder','price_parser','price_workflow','price_web_verifier',
        'image_prompt_builder','image_parser','image_relevance','image_catalog','image_web_scanner','image_workflow',
        'video_prompt_builder','video_parser','video_relevance','video_catalog','video_web_scanner','video_workflow','video_downloader',
    ]
