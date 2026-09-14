# -*- coding: utf-8 -*-
"""
OCEANIX — AI Model Interface
"""

import os
from typing import Dict, Any


class OilSpillModelInterface:

    def __init__(self, endpoint_url: str = "http://localhost:8080/predict"):
        self.endpoint = endpoint_url
        self.data_mode = os.getenv("OCEANIX_DATA_MODE", "DEMO").upper()

        # DEMO mode = no separate AI server required
        self.is_connected = self.data_mode == "DEMO"

    def check_health(self) -> bool:
        """Check whether AI model service is available."""

        if self.data_mode == "DEMO":
            self.is_connected = True
            return True

        self.is_connected = False
        return False

    def detect_spill(self, scene_path: str) -> Dict[str, Any]:
        """Run oil-spill detection."""

        if not self.check_health():
            raise RuntimeError(
                "OilSpillNet inference service is not available in LIVE mode."
            )

        if self.data_mode == "DEMO":
            return {
                "spill_detected": True,
                "confidence": 0.91,
                "polygons": [],
                "processing_time_ms": 142,
                "mode": "DEMO",
                "model": "OilSpillNet-v0.1",
                "message": "Synthetic demonstration result — not a real detection."
            }

        raise RuntimeError(
            "LIVE inference is not configured. "
            "Connect a trained OilSpillNet model before using LIVE mode."
        )