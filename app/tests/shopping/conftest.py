"""
테스트 환경에 google.generativeai / ollama 등 외부 의존성이 없어도
import 가 성공하도록 최소 stub 을 sys.modules 에 등록합니다.
"""
from __future__ import annotations

import sys
import types


def _stub_google_generativeai() -> None:
    if "google.generativeai" in sys.modules:
        return

    # google 네임스페이스 패키지
    google_pkg = sys.modules.setdefault("google", types.ModuleType("google"))

    genai_mod = types.ModuleType("google.generativeai")

    class _FakeGenerativeModel:
        def __init__(self, *a, **kw):
            pass
        def generate_content(self, prompt: str):
            raise RuntimeError("stub: google.generativeai not installed")

    genai_mod.configure = lambda **kw: None
    genai_mod.GenerativeModel = _FakeGenerativeModel

    google_pkg.generativeai = genai_mod
    sys.modules["google.generativeai"] = genai_mod


_stub_google_generativeai()
