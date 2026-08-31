import re
import time

import requests


class GeminiLLMClient:
    """Real LLMClient backed by Google's Gemini API.

    This is the local stand-in for the AIP Logic agent. It implements the
    same ``complete(system_prompt, user_prompt) -> str`` seam that
    ``riskagent.agent.judgment`` calls, so replacing it with a real AIP
    Logic SDK client later is a one-line change at the call site.

    On HTTP 429 (free-tier rate limit) it waits the server-advised delay
    and retries, up to ``max_retries`` times, so a run against a
    constrained key makes slow progress instead of aborting.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.6-flash",
        base_url: str = "https://generativelanguage.googleapis.com",
        timeout: int = 120,
        max_retries: int = 4,
        retry_cap: float = 90.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_cap = retry_cap

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code == 429 and attempt < self.max_retries:
                delay = min(self._retry_after_seconds(resp), self.retry_cap)
                time.sleep(delay)
                continue
            if resp.status_code >= 400:
                raise requests.HTTPError(
                    f"{resp.status_code} from Gemini ({self.model}): {str(resp.text)[:500]}",
                    response=resp,
                )
            break

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback", {})
            raise RuntimeError(
                f"Gemini returned no candidates (promptFeedback={feedback!r})"
            )
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)
        return text.strip()

    @staticmethod
    def _retry_after_seconds(resp: requests.Response, default: float = 15.0) -> float:
        """Best-effort parse of how long to wait before retrying a 429."""
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except (TypeError, ValueError):
                pass
        try:
            body = resp.json()
        except ValueError:
            body = {}
        for detail in body.get("error", {}).get("details", []):
            raw = detail.get("retryDelay")
            if isinstance(raw, str) and raw.endswith("s"):
                try:
                    return float(raw[:-1])
                except ValueError:
                    pass
        message = body.get("error", {}).get("message", "")
        match = re.search(r"retry in ([\d.]+)s", message)
        if match:
            return float(match.group(1))
        return default
