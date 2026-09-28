class GeminiUsageTracker:
    def __init__(
        self,
        max_calls=0,
        log_usage=True,
        input_price_per_million=0.75,
        output_price_per_million=3.75,
    ):
        self.max_calls = max(0, int(max_calls))
        self.log_usage = bool(log_usage)
        self.input_price_per_million = float(input_price_per_million)
        self.output_price_per_million = float(output_price_per_million)

        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.thought_tokens = 0

    def can_call(self):
        return self.max_calls == 0 or self.calls < self.max_calls

    def record(self, interaction):
        self.calls += 1
        usage = getattr(interaction, "usage", None)
        if usage is None:
            return

        input_tokens = int(getattr(usage, "total_input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "total_output_tokens", 0) or 0)
        thought_tokens = int(getattr(usage, "total_thought_tokens", 0) or 0)

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.thought_tokens += thought_tokens

        if self.log_usage:
            print(
                "  Gemini usage: "
                f"input={input_tokens}, "
                f"output={output_tokens}, "
                f"thought={thought_tokens}"
            )

    def estimated_cost_usd(self):
        input_cost = (
            self.input_tokens / 1_000_000
        ) * self.input_price_per_million
        billable_output = self.output_tokens + self.thought_tokens
        output_cost = (
            billable_output / 1_000_000
        ) * self.output_price_per_million
        return input_cost + output_cost

    def summary(self):
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "thought_tokens": self.thought_tokens,
            "estimated_cost_usd": self.estimated_cost_usd(),
        }
