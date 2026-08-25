from typing import Callable, Protocol


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class FakeLLMClient:
    def __init__(self, responder: Callable[[str, str], str]):
        self.responder = responder
        self.calls = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.responder(system_prompt, user_prompt)
