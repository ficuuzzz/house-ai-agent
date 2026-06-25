import os
from functools import lru_cache

from dotenv import load_dotenv
from gigachat import GigaChat

load_dotenv()


@lru_cache
def get_gigachat_client() -> GigaChat:
    credentials = os.getenv("GIGACHAT_CREDENTIALS")

    if not credentials:
        raise RuntimeError("GIGACHAT_CREDENTIALS is not set in .env")

    return GigaChat(
        credentials=credentials,
        verify_ssl_certs=False,
    )


def generate_answer(prompt: str) -> str:
    giga = get_gigachat_client()
    response = giga.chat(prompt)
    return response.choices[0].message.content