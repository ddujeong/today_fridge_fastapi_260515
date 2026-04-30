import requests


class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma2"):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()