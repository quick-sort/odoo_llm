import json
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LLMProvider(models.Model):
    _name = "llm.provider"
    _inherit = ["mail.thread"]
    _description = "LLM Provider"

    # Connectivity test payloads: kept deliberately tiny, the goal is to reach
    # the endpoint, not to get a useful answer.
    TEST_CHAT_PROMPT = "ping"
    TEST_CHAT_MAX_TOKENS = 16
    TEST_IMAGE_PROMPT = "a small red circle on a white background"

    name = fields.Char(required=True)
    service = fields.Selection(
        selection=lambda self: self._selection_service(),
        required=True,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    api_key = fields.Char()
    api_base = fields.Char()
    model_ids = fields.One2many("llm.model", "provider_id", string="Models")

    @api.constrains("name")
    def _check_unique_name(self):
        other_providers = self.search([("id", "not in", self.ids)])
        existing_names_lower = [p.name.lower() for p in other_providers if p.name]
        for record in self:
            if record.name and record.name.lower() in existing_names_lower:
                raise ValidationError(
                    _("The provider name must be unique (case-insensitive)."),
                )

        return True

    @property
    def client(self):
        """Get client instance using dispatch pattern"""
        return self._dispatch("get_client")

    def _dispatch(self, method, *args, record=None, **kwargs):
        """Dispatch method call to appropriate service implementation on self or a given record."""
        if not self.service:
            raise UserError(_("Provider service not configured"))

        service_method = f"{self.service}_{method}"
        record = record if record else self
        record_name = record._name

        if not hasattr(record, service_method):
            raise NotImplementedError(
                _("Method '%s' not implemented for service '%s' on target '%s'")
                % (method, self.service, record_name),
            )

        return getattr(record, service_method)(*args, **kwargs)

    def _has_service_method(self, method, record=None):
        """Check whether the current service implements ``<service>_<method>``.

        Useful to probe optional capabilities without triggering the
        ``NotImplementedError`` raised by :meth:`_dispatch`.
        """
        if not self.service:
            return False
        record = record if record else self
        return hasattr(record, f"{self.service}_{method}")

    @api.model
    def _selection_service(self):
        """Get all available services from provider implementations"""
        services = []
        for provider in self._get_available_services():
            services.append(provider)
        return services

    @api.model
    def _get_available_services(self):
        """Hook method for registering provider services"""
        return []

    def chat(
        self,
        messages,
        model=None,
        stream=False,
        tools=None,
        prepend_messages=None,
        **kwargs,
    ):
        """Send chat messages using this provider.

        Args:
            messages: mail.message recordset (Odoo records) to send
            model: Optional specific model to use
            stream: Whether to stream the response
            tools: llm.tool recordset of available tools
            prepend_messages: List of pre-formatted message dicts to prepend (e.g., system prompts)
            **kwargs: Additional provider-specific parameters

        Returns:
            Generator yielding response chunks if streaming, else complete response
        """
        # Hook: allow extensions to modify prepend_messages (e.g., add tool consent)
        prepend_messages = self._prepare_prepend_messages(prepend_messages, tools)

        # Normalize prepend_messages for the specific provider format
        prepend_messages = self._dispatch(
            "normalize_prepend_messages",
            prepend_messages,
        )

        return self._dispatch(
            "chat",
            messages,
            model=model,
            stream=stream,
            tools=tools,
            prepend_messages=prepend_messages,
            **kwargs,
        )

    def _prepare_prepend_messages(self, prepend_messages, tools):
        """Hook for extensions to modify prepend messages before sending to provider.

        Override in extension modules (e.g., llm_tool for consent injection).

        Args:
            prepend_messages: List of pre-formatted message dicts (e.g., system prompts)
            tools: llm.tool recordset of available tools

        Returns:
            List of message dicts to prepend to the conversation
        """
        return prepend_messages or []

    def _extract_content_text(self, content):
        """Extract plain text from message content.

        Handles both string and OpenAI list formats:
        - String: "hello" → "hello"
        - List: [{"type": "text", "text": "hello"}] → "hello"

        Args:
            content: Message content (string or list format)

        Returns:
            str: Plain text content
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return ""

    def embedding(self, texts, model=None):
        """Generate embeddings using this provider"""
        return self._dispatch("embedding", texts, model=model)

    def generate(self, input_data, model=None, stream=False, **kwargs):
        """Generate content using this provider

        Args:
            input_data: Input data for generation (could be text, prompt, or structured data)
            model: Optional specific model to use
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters

        Returns:
            tuple: (output_dict, urls_list) where:
                - output_dict: Dictionary containing provider-specific output data
                - urls_list: List of dictionaries with URL metadata
        """
        return self._dispatch(
            "generate",
            input_data,
            model=model,
            stream=stream,
            **kwargs,
        )

    def list_models(self, model_id=None):
        """List available models from the provider"""
        return self._dispatch("models", model_id=model_id)

    # ------------------------------------------------------------------
    # Connectivity tests
    # ------------------------------------------------------------------

    def test_model(self, model):
        """Probe the provider API for ``model`` and report reachability.

        A provider may implement ``<service>_test_model(model)`` to run a
        cheaper or more accurate probe (e.g. a dedicated health endpoint).
        Otherwise the generic probe selected by ``model.model_use`` is used.

        Args:
            model: llm.model record to probe

        Returns:
            dict with keys:
                - state: "success", "warning" or "failed"
                - message: short human readable summary
                - detail: optional longer text (excerpt of the raw response)

        Raises:
            Any provider/API exception. Callers are expected to catch them
            (see ``llm.model._run_connectivity_test``).
        """
        self.ensure_one()
        if self._has_service_method("test_model"):
            return self._dispatch("test_model", model)
        return self._default_test_model(model)

    def _default_test_model(self, model):
        """Service-agnostic connectivity probe, routed on ``model.model_use``."""
        handler = self._get_test_handler_name(model)
        if not handler:
            raise UserError(
                _(
                    "Connectivity test is not available for models used as '%s'.",
                    model.model_use,
                ),
            )
        return getattr(self, handler)(model)

    def _can_test_model(self, model):
        """Return True when a connectivity probe exists for ``model``.

        EXTENSION POINT: override (together with ``<service>_test_model``) when
        a service can probe usages the generic layer does not handle.
        """
        self.ensure_one()
        return bool(self._get_test_handler_name(model))

    def _get_test_handler_name(self, model):
        """Map a model usage to the method probing it.

        EXTENSION POINT: override to support additional usages added through
        ``_get_available_model_usages``. Return ``False`` when the usage
        cannot be tested.
        """
        return {
            "chat": "_test_chat_model",
            "multimodal": "_test_chat_model",
            "image_generation": "_test_generation_model",
            "generation": "_test_generation_model",
        }.get(model.model_use, False)

    def _test_chat_model(self, model):
        """Send a minimal chat request to check the chat endpoint."""
        self.ensure_one()
        response = self.chat(
            self.env["mail.message"],  # no history, the prompt is prepended
            model=model,
            stream=False,
            prepend_messages=[{"role": "user", "content": self.TEST_CHAT_PROMPT}],
            max_tokens=self.TEST_CHAT_MAX_TOKENS,
        )

        if not isinstance(response, dict):
            # Defensive: a provider returning a generator for stream=False
            return {
                "state": "warning",
                "message": _("Chat endpoint answered with an unexpected payload."),
                "detail": str(response),
            }

        if response.get("error"):
            return {
                "state": "failed",
                "message": _("The chat endpoint returned an error."),
                "detail": str(response["error"]),
            }

        content = self._extract_content_text(response.get("content") or "")
        if not content and not response.get("tool_calls"):
            return {
                "state": "warning",
                "message": _("Chat endpoint reached but the answer was empty."),
                "detail": self._test_dump(response),
            }

        return {
            "state": "success",
            "message": _("Chat endpoint reached, the model answered."),
            "detail": content or self._test_dump(response),
        }

    def _test_generation_model(self, model):
        """Run a minimal generation request (image or other binary output).

        When the provider has no ``generate`` implementation, fall back to
        checking that the model can be retrieved from the provider API: that
        still validates credentials, base URL and model name, so the result is
        reported as a partial success.
        """
        self.ensure_one()
        try:
            result = self.generate(self.TEST_IMAGE_PROMPT, model=model, stream=False)
        except NotImplementedError:
            return self._test_generation_fallback(model)

        output, urls = self._test_split_generate_result(result)

        if isinstance(output, dict) and output.get("error"):
            return {
                "state": "failed",
                "message": _("The generation endpoint returned an error."),
                "detail": str(output["error"]),
            }

        if not output and not urls:
            return {
                "state": "warning",
                "message": _("Generation endpoint reached but nothing was returned."),
                "detail": self._test_dump(result),
            }

        return {
            "state": "success",
            "message": _(
                "Generation endpoint reached, %(count)d result(s) returned.",
                count=len(urls) if urls else 1,
            ),
            "detail": self._test_dump({"output": output, "urls": urls}),
        }

    def _test_generation_fallback(self, model):
        """Reachability check used when generation is not implemented."""
        try:
            available = self._test_model_is_listed(model)
        except NotImplementedError:
            return {
                "state": "failed",
                "message": _(
                    "Service '%s' implements neither generation nor model listing, "
                    "connectivity cannot be checked.",
                    self.service,
                ),
                "detail": "",
            }

        if not available:
            return {
                "state": "failed",
                "message": _(
                    "API reached but model '%s' was not returned by the provider.",
                    model.name,
                ),
                "detail": "",
            }

        return {
            "state": "warning",
            "message": _(
                "API credentials valid and model '%s' exists, but service '%s' does not "
                "implement generation, so no image was requested.",
                model.name,
                self.service,
            ),
            "detail": "",
        }

    def _test_model_is_listed(self, model):
        """Return True when the provider API knows about ``model``."""
        for model_data in self.list_models(model_id=model.name):
            details = model_data.get("details") or {}
            if (model_data.get("name") or details.get("id")) == model.name:
                return True
        return False

    @staticmethod
    def _test_split_generate_result(result):
        """Normalize ``generate()`` output into an ``(output, urls)`` tuple."""
        if isinstance(result, tuple) and len(result) == 2:
            output, urls = result
            return output, list(urls or [])
        return result, []

    def _test_dump(self, value):
        """Serialize a probe payload for storage in the test details field."""
        try:
            return json.dumps(value, default=str, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)

    def _sanitize_test_output(self, text):
        """Strip the API key from any text before it is stored or displayed."""
        text = text or ""
        if self.api_key and self.api_key in text:
            text = text.replace(self.api_key, "***")
        return text

    def action_fetch_models(self):
        """Fetch models from provider and open import wizard"""
        self.ensure_one()

        # Create wizard first so it has an ID
        wizard = self.env["llm.fetch.models.wizard"].create(
            {
                "provider_id": self.id,
            },
        )

        # Get existing models for comparison
        existing_models = {
            model.name: model
            for model in self.env["llm.model"].search([("provider_id", "=", self.id)])
        }

        # Fetch models from provider
        model_to_fetch = self.env.context.get("default_model_to_fetch")
        if model_to_fetch:
            models_data = self.list_models(model_id=model_to_fetch)
        else:
            models_data = self.list_models()

        # Track models to prevent duplicates
        wizard_models = set()
        lines_to_create = []

        for model_data in models_data:
            details = model_data.get("details", {})
            name = model_data.get("name") or details.get("id")

            if not name:
                continue

            # Skip duplicates
            if name in wizard_models:
                continue
            wizard_models.add(name)

            # Determine model use and capabilities
            capabilities = details.get("capabilities", ["chat"])
            model_use = self._determine_model_use(name, capabilities)

            # Check against existing models
            existing = existing_models.get(name)
            status = "new"
            if existing:
                status = "modified" if existing.details != details else "existing"

            lines_to_create.append(
                {
                    "wizard_id": wizard.id,
                    "name": name,
                    "model_use": model_use,
                    "status": status,
                    "details": details,
                    "existing_model_id": existing.id if existing else False,
                    "selected": status in ["new", "modified"],
                },
            )

        # Create all lines
        if lines_to_create:
            self.env["llm.fetch.models.line"].create(lines_to_create)

        # Return action to open the wizard
        return {
            "type": "ir.actions.act_window",
            "res_model": "llm.fetch.models.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Import Models"),
        }

    def _determine_model_use(self, name, capabilities):
        """
        Determine the primary model use based on capabilities.

        This method classifies models into Odoo's model_use categories based on their
        capabilities. The classification follows a priority order from most specialized
        to most general.

        EXTENSION POINT: Override this method in your provider class to add custom
        model types or modify classification logic.

        Args:
            name (str): Model name/ID from the provider
            capabilities (list): List of capability strings (usually from API response)

        Returns:
            str: One of the model_use values from _get_available_model_usages()
                 Default options: "chat", "embedding", "multimodal", "completion", etc.

        Priority Order:
            1. embedding - Specialized embedding models
            2. multimodal - Models with vision/image understanding
            3. chat - General conversational models (default)

        Standard Capability Names:
            - "chat": Text-based conversations
            - "embedding"/"text-embedding": Vector embeddings
            - "multimodal"/"vision": Image/vision understanding
            - "completion": Text completion
            - "function_calling": Tool/function support
            Provider-specific: "ocr", "image_generation", etc.

        Example Override:
            ```python
            class MyProvider(models.Model):
                _inherit = "llm.provider"

                def _determine_model_use(self, name, capabilities):
                    # Add custom model type
                    if "ocr" in capabilities:
                        return "ocr"
                    # Fall back to parent logic for standard types
                    return super()._determine_model_use(name, capabilities)
            ```

        See Also:
            - llm_mistral.models.mistral_provider for a working example
            - _<provider>_parse_model() for setting capabilities
        """
        # Priority 1: Embedding models (specialized, distinct use case)
        if (
            any(cap in capabilities for cap in ["embedding", "text-embedding"])
            or "embedding" in name.lower()
        ):
            return "embedding"

        # Priority 2: Multimodal models (advanced capability)
        if any(cap in capabilities for cap in ["multimodal", "vision"]):
            return "multimodal"

        # Priority 3: Chat models (default for most LLMs)
        return "chat"

    def get_model(self, model=None, model_use="chat"):
        """Get a model to use for the given purpose

        Args:
            model: Optional specific model to use
            model_use: Type of model to get if no specific model provided

        Returns:
            llm.model record to use
        """
        if model:
            return model

        # Get models from provider
        models = self.model_ids

        # Filter for default model of requested type
        default_models = models.filtered(
            lambda m: m.is_default and m.model_use == model_use,
        )

        if not default_models:
            # Fallback to any model of requested type
            default_models = models.filtered(lambda m: m.model_use == model_use)

        if not default_models:
            raise ValueError(f"No {model_use} model found for provider {self.name}")

        return default_models[0]

    @staticmethod
    def serialize_datetime(obj):
        """Helper function to serialize datetime objects to ISO format strings."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    @staticmethod
    def serialize_model_data(data: dict) -> dict:
        """
        Recursively process dictionary to serialize datetime objects
        and handle any other non-serializable types.

        Args:
            data (dict): Dictionary potentially containing datetime objects

        Returns:
            dict: Processed dictionary with datetime objects converted to ISO strings
        """
        return {
            key: LLMProvider.serialize_datetime(value)
            if isinstance(value, datetime)
            else LLMProvider.serialize_model_data(value)
            if isinstance(value, dict)
            else [
                LLMProvider.serialize_model_data(item)
                if isinstance(item, dict)
                else LLMProvider.serialize_datetime(item)
                for item in value
            ]
            if isinstance(value, list)
            else value
            for key, value in data.items()
        }

    def format_tools(self, tools):
        """Format tools for the specific provider"""
        return self._dispatch("format_tools", tools)

    def format_messages(self, messages, system_prompt=None, model=None):
        """Format messages for this provider

        Args:
            messages: List of messages to format for specific provider, could be mail.message record set or similar data format
            system_prompt: Optional system prompt to include at the beginning of the messages
            model: llm.model record (to determine if multimodal)

        Returns:
            List of formatted messages in provider-specific format
        """
        return self._dispatch(
            "format_messages",
            messages,
            system_prompt=system_prompt,
            model=model,
        )

    def _get_provider_tool_params(self, tools, kwargs):
        """Hook for provider-specific tool parameters."""
        return {}
