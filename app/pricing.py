def billable_token_counts(input_tokens: int, cached_input_tokens: int, output_tokens: int, reasoning_tokens: int) -> tuple[int, int, int]:
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")
    return input_tokens - cached_input_tokens, cached_input_tokens, output_tokens + reasoning_tokens

def estimate_cost_cents(api_calls: int, input_tokens: int, cached_input_tokens: int, output_tokens: int, reasoning_tokens: int, *, api_call_cents: int = 1, input_microcents: int = 10, cached_microcents: int = 2, output_microcents: int = 20) -> int:
    fresh, cached, output = billable_token_counts(input_tokens, cached_input_tokens, output_tokens, reasoning_tokens)
    microcents = api_calls * api_call_cents * 10000 + fresh * input_microcents + cached * cached_microcents + output * output_microcents
    return microcents // 10000
