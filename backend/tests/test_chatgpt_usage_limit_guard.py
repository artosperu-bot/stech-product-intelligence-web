import unittest

from app.worker_chat_policy import (
    ChatGPTUsageLimitError,
    detect_chatgpt_usage_limit_text,
)


class ChatGPTUsageLimitDetectionTests(unittest.TestCase):
    def test_detects_spanish_pause_banner_and_extracts_reset_time(self):
        text = (
            "Chat en pausa hasta que se restablezca el uso a las 14:25\n"
            "Has alcanzado el límite de chats que incluyen análisis de datos. "
            "Inicia un chat nuevo solo de texto o mejora tu plan para continuar ahora.\n"
            "Nuevo chat"
        )
        state = detect_chatgpt_usage_limit_text(text)
        self.assertIsNotNone(state)
        self.assertEqual(state.reset_hint, "14:25")
        self.assertTrue(state.suggests_new_chat)
        self.assertIn("análisis de datos", state.message)

    def test_does_not_flag_normal_chat_text_that_mentions_limits_generically(self):
        text = "Explícame cuáles son los límites de una base de datos y dame un ejemplo."
        self.assertIsNone(detect_chatgpt_usage_limit_text(text))

    def test_error_message_is_explicit_and_preserves_reset_hint(self):
        error = ChatGPTUsageLimitError(
            message="Chat en pausa por límite de uso",
            reset_hint="14:25",
            suggests_new_chat=True,
        )
        rendered = str(error)
        self.assertIn("CHATGPT_USAGE_LIMIT", rendered)
        self.assertIn("14:25", rendered)


if __name__ == "__main__":
    unittest.main()
