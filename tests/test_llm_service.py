import os
import unittest

from openai import AsyncOpenAI

from app.services.llm_service import LLMService


class LLMServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_text_makes_real_openai_call(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set. Skipping integration test.")
            self.skipTest("OPENAI_API_KEY is not set.")

        service = LLMService(client=AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]))

        text = await service.generate_text(
            system_prompt=(
                "You are a test assistant. Return exactly the phrase "
                "'integration-ok' and nothing else."
            ),
            user_prompt="Return the required phrase.",
            temperature=0.0,
            max_output_tokens=20,
        )

        self.assertEqual(text, "integration-ok")


if __name__ == "__main__":
    unittest.main()
