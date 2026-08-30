import requests


class GeminiLLMClient:
    """Real LLMClient backed by Google's Gemini API.

    This is the local stand-in for the AIP Logic agent. It implements the
    same ``complete(system_prompt, user_prompt) -> str`` seam that
    ``riskagent.agent.judgment`` calls, so replacing it with a real AIP
    Logic SDK client later is a one-line change at the call site.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com",
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        resp = requests.post(
            url,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
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
