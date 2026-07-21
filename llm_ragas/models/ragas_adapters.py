"""Bridge Odoo ``llm.provider`` / ``llm.model`` records into ragas-compatible
LLM and Embedding objects.

Design principle: whenever the underlying ``llm.provider`` exposes a native
SDK client (e.g. ``openai.OpenAI(...)``) via its ``client`` property AND
ragas has a factory that can use it, hand that client straight to ragas'
own factories (``get_ragas_llm`` / ``get_ragas_embedding_for_metrics``).
This keeps that traffic (auth, base_url, rate limits) going through the
Odoo provider configuration without any custom adapter code. Providers
without such a client fall back to the ``_OdooRagasEmbedding`` /
``_OdooRagasLLM`` adapters, calling ``llm.model.embedding()`` /
``llm.model.chat()`` directly.

Knowledge-graph building (``get_ragas_embeddings_for_graph``) is a special
case: ragas' legacy embedding interface has no useful way to accept a
pre-built client at all (see below), so it *always* goes straight through
``llm.model.embedding()`` via ``_OdooRagasEmbeddingsForGraph`` - there is no
SDK-passthrough fast path to prefer there in the first place.

Two different embedding interfaces exist in ragas and are NOT interchangeable:

* ``ragas.embeddings.base.BaseRagasEmbeddings`` (plural) - legacy,
  langchain-based, batch methods named ``embed_documents``/``aembed_documents``.
  This is what the knowledge-graph-building transforms
  (``default_transforms_for_prechunked``) expect.
* ``ragas.embeddings.base.BaseRagasEmbedding`` (singular) - modern, methods
  named ``embed_text``/``aembed_text``. This is what
  ``ragas.metrics.collections.*`` (used for evaluation) require.

``embedding_factory(provider, model=..., client=...)`` returns the *modern*
(singular) interface whenever a client is given, so it is only suitable for
metrics, not for graph building. ragas' legacy factory also ignores any
``client`` argument (it always builds its own fresh OpenAI client from env
vars), so there is no SDK-passthrough fast path for graph building either
way. Instead, ``get_ragas_embeddings_for_graph`` always uses a small direct
adapter (``_OdooRagasEmbeddingsForGraph``) backed by ``llm.model.embedding()``
- no langchain, no raw openai client, works for any Odoo provider.

NOTE: this module is only imported when llm_ragas is installed, and the
manifest declares ``ragas`` as an external Python dependency, so the
top-level ``ragas`` imports below are safe (same convention as e.g.
llm_openai importing ``openai`` at module load time).
"""

import asyncio
import logging

from ragas.embeddings.base import BaseRagasEmbedding, BaseRagasEmbeddings
from ragas.llms.base import InstructorBaseRagasLLM
from ragas.run_config import RunConfig

_logger = logging.getLogger(__name__)


def get_ragas_llm(llm_model):
    """Return an object implementing ragas' LLM interface for ``llm_model``.

    Suitable both for knowledge-graph transforms/generation (which accept
    ``BaseRagasLLM`` or ``InstructorBaseRagasLLM``) and for
    ``ragas.metrics.collections.*`` (which require ``InstructorBaseRagasLLM``).
    """
    provider = llm_model.provider_id

    try:
        client = provider.client
    except Exception as exc:  # noqa: BLE001 - provider may raise NotImplementedError
        _logger.info(
            "Provider '%s' (%s) has no native SDK client (%s); falling back to "
            "a generic Odoo-backed LLM adapter for ragas.",
            provider.name,
            provider.service,
            exc,
        )
        return _OdooRagasLLM(llm_model)

    from ragas.llms import llm_factory

    try:
        return llm_factory(llm_model.name, provider=provider.service, client=client)
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "ragas.llm_factory could not use the native client of provider "
            "'%s' (%s): %s. Falling back to a generic Odoo-backed LLM adapter.",
            provider.name,
            provider.service,
            exc,
        )
        return _OdooRagasLLM(llm_model)


def get_ragas_embedding_for_metrics(embedding_model):
    """Return a *modern* ragas embedding object (``BaseRagasEmbedding``),
    suitable for ``ragas.metrics.collections`` metrics such as
    ``answer_relevancy``.
    """
    provider = embedding_model.provider_id

    try:
        client = provider.client
    except Exception as exc:  # noqa: BLE001
        _logger.info(
            "Provider '%s' (%s) has no native SDK client (%s); falling back to "
            "a generic Odoo-backed embedding adapter for ragas.",
            provider.name,
            provider.service,
            exc,
        )
        return _OdooRagasEmbedding(embedding_model)

    from ragas.embeddings import embedding_factory

    try:
        return embedding_factory(
            provider.service, model=embedding_model.name, client=client
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "ragas.embedding_factory could not use the native client of "
            "provider '%s' (%s): %s. Falling back to a generic Odoo-backed "
            "embedding adapter.",
            provider.name,
            provider.service,
            exc,
        )
        return _OdooRagasEmbedding(embedding_model)


def get_ragas_embeddings_for_graph(embedding_model):
    """Return a ``BaseRagasEmbeddings`` (legacy, langchain-shaped interface)
    adapter for ``embedding_model``, required by ragas' knowledge-graph-
    building transforms (``default_transforms_for_prechunked``).

    Always backed directly by ``llm.model.embedding()`` - no langchain
    client, no raw openai client, works for any Odoo provider that has an
    embedding implementation.
    """
    return _OdooRagasEmbeddingsForGraph(embedding_model)


# ---------------------------------------------------------------------------
# Adapters backed directly by Odoo's llm.model.embedding() / llm.model.chat()
# ---------------------------------------------------------------------------


class _OdooRagasEmbeddingsForGraph(BaseRagasEmbeddings):
    """Legacy-interface embedding adapter for knowledge-graph building.

    ``BaseRagasEmbeddings`` inherits from langchain_core's ``Embeddings``
    ABC, so a ``page_content``-in/vector-out subclass like this one is the
    minimum needed to satisfy it - no actual langchain client required.
    """

    def __init__(self, embedding_model):
        super().__init__()
        self._embedding_model = embedding_model
        self.set_run_config(RunConfig())

    def embed_documents(self, texts):
        return self._embedding_model.embedding(list(texts))

    def embed_query(self, text):
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts):
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text):
        return await asyncio.to_thread(self.embed_query, text)


class _OdooRagasEmbedding(BaseRagasEmbedding):
    """Fallback modern-interface embedding adapter backed by
    ``llm.model.embedding()``. Fully implemented: embeddings only need
    plain text in / vectors out, no message formatting involved.
    """

    def __init__(self, embedding_model):
        super().__init__()
        self._embedding_model = embedding_model

    def embed_text(self, text, **kwargs):
        return self._embedding_model.embedding([text])[0]

    async def aembed_text(self, text, **kwargs):
        return await asyncio.to_thread(self.embed_text, text)

    def embed_texts(self, texts, **kwargs):
        return self._embedding_model.embedding(list(texts))

    async def aembed_texts(self, texts, **kwargs):
        return await asyncio.to_thread(self.embed_texts, texts)


class _OdooRagasLLM(InstructorBaseRagasLLM):
    """Fallback structured-output adapter backed by ``llm.model.chat()``.

    NOT IMPLEMENTED YET: ``llm.provider.chat()`` expects an Odoo
    ``mail.message`` recordset, not a plain prompt string, and there is no
    generic JSON-schema-constrained generation path for arbitrary providers
    in the base ``llm`` module yet. Configure an OpenAI or
    Anthropic-compatible provider (handled by ``get_ragas_llm`` above
    without hitting this fallback) until this is implemented.
    """

    def __init__(self, llm_model):
        self._llm_model = llm_model

    def generate(self, prompt, response_model):
        raise NotImplementedError(
            "Structured generation fallback is not implemented for provider "
            f"'{self._llm_model.provider_id.name}' (service "
            f"'{self._llm_model.provider_id.service}'). Configure an OpenAI "
            "or Anthropic-compatible provider for llm_ragas, or contribute "
            "an implementation in ragas_adapters.py::_OdooRagasLLM."
        )

    async def agenerate(self, prompt, response_model):
        return await asyncio.to_thread(self.generate, prompt, response_model)
