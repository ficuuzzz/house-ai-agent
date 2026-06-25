from functools import lru_cache

from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def get_embedding(text: str) -> list[float]:
    model = get_embedding_model()
    vector = model.encode(text)

    return vector.tolist()


def get_embedding_size() -> int:
    model = get_embedding_model()

    return model.get_sentence_embedding_dimension()