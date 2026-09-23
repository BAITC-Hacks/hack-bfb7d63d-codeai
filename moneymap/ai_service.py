"""One explicit, budgeted request; verified results cached only in caller memory."""

from copy import deepcopy
import hashlib
import json

from moneymap.ai_provider import AIProviderError, call_provider
from moneymap.ai_response import (
    AIResponseError, PROMPT_VERSION, SYSTEM_PROMPT, render_report,
    response_schema, validate_response,
)


def cache_key(settings, bundle):
    return hashlib.sha256(json.dumps([
        PROMPT_VERSION, SYSTEM_PROMPT, response_schema(bundle), settings.provider,
        settings.model, settings.max_output_tokens, bundle.fingerprint,
    ], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def request_analysis(settings, bundle, *, cache, ledger):
    if not settings.ready:
        raise AIProviderError("disabled", "API өшірулі немесе кілт енгізілмеген. Жергілікті есеп қолжетімді.")
    key = cache_key(settings, bundle)
    if key in cache:
        result = deepcopy(cache[key])
        result["from_cache"] = True
        return result
    payload = bundle.public_payload()
    schema = response_schema(bundle)
    # UTF-8 bytes + protocol allowance conservatively bound tokenizer input.
    request_bytes = len((SYSTEM_PROMPT + json.dumps(payload, ensure_ascii=False)
                         + json.dumps(schema, ensure_ascii=False)).encode("utf-8"))
    if request_bytes > 120000:
        raise AIResponseError("Фактілер көлемі сұрау шегінен асты. Клиенттер санын азайтыңыз.")
    reservation = ledger.reserve(settings, request_bytes + 2048)
    try:
        reply = call_provider(settings, SYSTEM_PROMPT, payload, schema)
    except AIProviderError as exc:
        ledger.settle(reservation, getattr(exc, "input_tokens", None),
                      getattr(exc, "output_tokens", None), status="error")
        raise
    try:
        result = validate_response(reply.text, bundle)
    except AIResponseError:
        ledger.settle(reservation, reply.input_tokens, reply.output_tokens, status="invalid_response")
        raise
    ledger.settle(reservation, reply.input_tokens, reply.output_tokens, status="success")
    response = {
        "data": result, "report": render_report(result, bundle, provider=settings.provider, model=settings.model),
        "provider": settings.provider, "model": settings.model, "from_cache": False,
        "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
    }
    if len(cache) >= 30:
        cache.pop(next(iter(cache)))
    cache[key] = deepcopy(response)
    return response
