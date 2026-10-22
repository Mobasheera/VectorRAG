import torch
from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL


def get_device():
    """
    Use NVIDIA GPU when CUDA is available.
    Otherwise use CPU.
    """

    if torch.cuda.is_available():
        return "cuda"

    return "cpu"


DEVICE = get_device()

print("=" * 60)
print("EMBEDDING MODEL")
print("=" * 60)
print("Model:", EMBEDDING_MODEL)
print("Device:", DEVICE)

if DEVICE == "cuda":
    print(
        "GPU:",
        torch.cuda.get_device_name(0)
    )

print("=" * 60)


model = SentenceTransformer(
    EMBEDDING_MODEL,
    device=DEVICE
)


def embed_text(text: str):

    vector = model.encode(
        text,
        normalize_embeddings=True
    )

    return vector.tolist()


def embed_texts(texts):

    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    return vectors.tolist()


def get_embedding_dimension():

    return model.get_sentence_embedding_dimension()