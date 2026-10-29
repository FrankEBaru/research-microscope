"""SPECTER2 query vectors for the S2 specter_v2 paper index.

Semantic Scholar embeddings-specter_v2 stores one 768-d vector per paper.
Those are candidate-paper embeddings. The Hugging Face card for the adhoc
query adapter says to encode a short text query with allenai/specter2_adhoc_query
on top of allenai/specter2_base, and to encode candidate papers with the
proximity adapter (allenai/specter2, formerly allenai/specter2_proximity):

https://huggingface.co/allenai/specter2_adhoc_query

The vector is the CLS token, last_hidden_state[:, 0, :]. The card compares
query and paper with Euclidean distance, so the FAISS index is L2, not cosine.
Runs on CPU. Loaded only when encode() is called.
"""

BASE = "allenai/specter2_base"
ADAPTER = "allenai/specter2_adhoc_query"


class QueryEncoder:
    def __init__(self):
        self._model = None
        self._tokenizer = None

    def load(self):
        if self._model is not None:
            return
        import torch
        from adapters import AutoAdapterModel
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(BASE)
        model = AutoAdapterModel.from_pretrained(BASE)
        model.load_adapter(ADAPTER, source="hf", load_as="adhoc_query", set_active=True)
        model.eval()
        self._tokenizer = tok
        self._torch = torch
        self._model = model

    def encode(self, texts):
        """Return float32 array (len(texts), 768)."""
        import numpy as np

        self.load()
        if not texts:
            return np.zeros((0, 768), dtype=np.float32)
        inputs = self._tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
            return_token_type_ids=False,
        )
        with self._torch.no_grad():
            hidden = self._model(**inputs).last_hidden_state[:, 0, :]
        return hidden.numpy().astype(np.float32, copy=False)
