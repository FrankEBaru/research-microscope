"""SPECTER2 query vectors for the S2 specter_v2 paper index.

Direct Use table, https://huggingface.co/allenai/specter2_adhoc_query :
short text uses allenai/specter2_adhoc_query; a paper (title + abstract, or
any paste longer than 40 words) uses the proximity adapter allenai/specter2
(formerly allenai/specter2_proximity), which is the candidate embedding stored
in embeddings-specter_v2. The vector is last_hidden_state[:, 0, :]. The card
compares with Euclidean distance, so the FAISS index is L2. CPU only.
"""

BASE = "allenai/specter2_base"
ADHOC = "allenai/specter2_adhoc_query"
PROXIMITY = "allenai/specter2"


def use_proximity(text):
    """Paper text uses proximity. Short queries and subtopics stay on adhoc_query.

    Title and abstract are joined with a newline (that is how the eval builds
    its query). A single block of more than 40 words is a long paste.
    """
    if not text:
        return False
    if "\n" in text:
        return True
    return len(text.split()) > 40


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
        model.load_adapter(ADHOC, source="hf", load_as="adhoc_query", set_active=True)
        model.load_adapter(PROXIMITY, source="hf", load_as="proximity")
        model.eval()
        self._tokenizer = tok
        self._torch = torch
        self._model = model

    def encode(self, texts):
        """Return float32 array (len(texts), 768). Adapter follows use_proximity."""
        import numpy as np

        texts = list(texts)
        self.load()
        if not texts:
            return np.zeros((0, 768), dtype=np.float32)
        prox = [use_proximity(text) for text in texts]
        if all(prox) or not any(prox):
            return self._forward(texts, "proximity" if prox[0] else "adhoc_query")
        out = np.zeros((len(texts), 768), dtype=np.float32)
        for flag, name in ((False, "adhoc_query"), (True, "proximity")):
            idx = [i for i, flag_i in enumerate(prox) if flag_i is flag]
            if idx:
                out[idx] = self._forward([texts[i] for i in idx], name)
        return out

    def _forward(self, texts, adapter):
        self._model.set_active_adapters(adapter)
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
        return hidden.numpy().astype("float32", copy=False)
