"""TypeSafe SDK adapter: typed questions in, sanitized JSON out."""

class ProviderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def sanitize(value):
    """Recursively remove credential fields without discarding answer metadata."""
    if isinstance(value, dict):
        sanitized = {}
        private_fields = {"api_key", "authorization", "access_token", "secret", "password", "headers", "request_headers", "response_headers"}
        for key, item in value.items():
            normalized_key = str(key).casefold().replace("-", "_")
            if normalized_key in private_fields:
                continue
            # These are answer option IDs, not metadata field names. A legitimate
            # option named 'password' must retain its numeric probability.
            if key == "probabilities" and isinstance(item, dict) and all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in item.values()):
                sanitized[str(key)] = dict(item)
            else:
                sanitized[str(key)] = sanitize(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def call_jev(state: dict, questions: dict, *, api_key, model, timeout_seconds, max_retries) -> dict:
    if not api_key or not str(api_key).strip():
        raise ProviderError("provider_not_configured", "Live Jev requires a backend TypeSafe API key.", 503)
    try:
        from typesafe_sdk import (
            Choice, Noul, RetryPolicy, TypeSafeAPIConnectionError, TypeSafeAPIError,
            TypeSafeAPIResponseValidationError, TypeSafeAPITimeoutError, TypeSafeClient, TypeSafeError,
        )
    except ImportError as exc:
        raise ProviderError("provider_not_installed", "Install backend dependencies with uv sync --project backend --locked from the repository root to use live Jev.", 503) from exc
    typed = {}
    for question_id, question in questions.items():
        if question["type"] == "noul":
            typed[question_id] = Noul(instructions=question["instructions"])
        else:
            typed[question_id] = Choice(
                instructions=question["instructions"],
                criteria=question["criteria"],
            )
    try:
        retry = RetryPolicy(max_retries=max_retries, timeout=timeout_seconds,
                            http_statuses={429, 500, 502, 503, 504, 529}, backoff_max=5.0)
        with TypeSafeClient(api_key=api_key, model=model, timeout=timeout_seconds, retry=retry) as client:
            result = client.system_one(state=state, questions=typed)
        return sanitize(result.model_dump(mode="json"))
    except TypeSafeAPITimeoutError as exc:
        raise ProviderError("provider_timeout", "Jev timed out. Retry the analysis.", 504) from exc
    except TypeSafeAPIConnectionError as exc:
        raise ProviderError("provider_connection", "Could not reach Jev. Check connectivity and retry.", 503) from exc
    except TypeSafeAPIResponseValidationError as exc:
        raise ProviderError("invalid_provider_response", "Jev returned an invalid response. Retry the analysis.") from exc
    except TypeSafeAPIError as exc:
        status = exc.status
        if status in {401, 403}:
            raise ProviderError("provider_authentication", "Jev rejected the configured credentials. Check the backend API key.", 503) from exc
        if status == 429:
            raise ProviderError("provider_rate_limit", "Jev is rate limited. Wait briefly and retry.", 429) from exc
        if status in {529, 503}:
            raise ProviderError("provider_overloaded", "Jev is temporarily overloaded. Retry shortly.", 503) from exc
        raise ProviderError("provider_request_failed", "Jev could not complete this request. Check the model configuration and retry.") from exc
    except TypeSafeError as exc:
        # SDK exception strings may include the request body. Never expose them.
        raise ProviderError("provider_configuration", "Jev client configuration is invalid. Check the backend settings.", 503) from exc

