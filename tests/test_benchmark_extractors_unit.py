import re

import pytest

from damru.benchmark import _extract_browserscan, _extract_creepjs


class FakePage:
    def __init__(self, text: str):
        self.text = text

    async def wait_for_selector(self, *args, **kwargs):
        return None

    async def wait_for_load_state(self, *args, **kwargs):
        return None

    async def evaluate(self, script: str):
        if "Bot Detection" in script:
            lines = [line.strip() for line in self.text.splitlines() if line.strip()]
            score = "N/A"
            bot_index = next((i for i, line in enumerate(lines) if re.match(r"^Bot Detection:?$", line, re.I)), -1)
            if bot_index >= 0:
                for line in lines[bot_index + 1 : bot_index + 8]:
                    match = re.match(r"^(\d+)\s*%$", line)
                    if match:
                        score = match.group(1) + "%"
                        break
            if score == "N/A":
                match = re.search(r"(\d+)\s*%", self.text)
                score = match.group(1) + "%" if match else "N/A"
            issues = []
            for i, line in enumerate(lines):
                if re.match(r"^-\d+\s*%$", line):
                    issues.append({"name": lines[i - 1] if i else "", "penalty": line, "detail": lines[i + 1] if i + 1 < len(lines) else ""})
            return {"score": score, "issues": issues}

        webrtc_match = re.search(
            r"WebRTC[\s\S]*?(host connection:[\s\S]*?)(?:Timezone|Intl|Headless)",
            self.text,
            re.I,
        )
        webrtc_text = webrtc_match.group(1).strip() if webrtc_match else ""
        like_headless = re.search(r"(\d+)%\s*like headless", self.text, re.I)
        headless = re.search(r"(\d+)%\s*headless:", self.text, re.I)
        stealth = re.search(r"(\d+)%\s*stealth:", self.text, re.I)
        return {
            "likeHeadless": like_headless.group(1) + "%" if like_headless else "N/A",
            "headless": headless.group(1) + "%" if headless else "N/A",
            "stealth": stealth.group(1) + "%" if stealth else "N/A",
            "lies": "N/A",
            "webrtcBlocked": bool(re.search("blocked", webrtc_text, re.I))
            and not bool(re.search(r"(\d{1,3}\.){3}\d{1,3}", webrtc_text)),
        }


@pytest.mark.asyncio
async def test_browserscan_extractor_prefers_bot_detection_score():
    page = FakePage("some unrelated 90%\nBot Detection\n100%\nDevice Model\nPixel")

    assert await _extract_browserscan(page) == {"score": "100%", "issues": []}


@pytest.mark.asyncio
async def test_creepjs_extractor_reports_blocked_webrtc():
    page = FakePage(
        "WebRTC\nhost connection:\nblocked\nfoundation/ip:\nunsupported\nblocked\nTimezone\n"
        "38% like headless\n0% headless:\n0% stealth:"
    )

    result = await _extract_creepjs(page)

    assert result["webrtcBlocked"] is True
