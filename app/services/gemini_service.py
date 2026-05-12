import os
import google.generativeai as genai


class GeminiService:

    def __init__(self):
        genai.configure(
            api_key=os.getenv("GEMINI_API_KEY")
        )

        self.model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

    def generate(self, prompt: str) -> str:
        response = self.model.generate_content(prompt)
        return response.text.strip()

    def generate_health_report(self, prompt: str) -> str:
        # Use gemini-2.5-flash and force JSON output
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(

            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        return response.text.strip()