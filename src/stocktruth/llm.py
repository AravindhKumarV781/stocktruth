"""Azure OpenAI client (models deployed in Azure AI Foundry) with usage and cost tracking.
LLM_MODE=mock disables model calls so the rest of the pipeline can run offline."""


class LLM:
    def __init__(self, settings):
        self.s = settings
        self.mock = settings.llm_mode != "azure"
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0
        self.client = None
        if not self.mock:
            from openai import AzureOpenAI
            self.client = AzureOpenAI(azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
                                      api_version=settings.aoai_api_version)

    def chat(self, messages, tools=None, json_mode=False):
        kw = dict(model=self.s.deployment, messages=messages)
        if tools:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"
        if json_mode:
            kw["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kw)
        self.calls += 1
        if resp.usage:
            self.tokens_in += resp.usage.prompt_tokens or 0
            self.tokens_out += resp.usage.completion_tokens or 0
        return resp.choices[0].message

    def snapshot(self):
        return (self.tokens_in, self.tokens_out, self.calls)

    def cost_since(self, snap):
        i, o, c = self.tokens_in - snap[0], self.tokens_out - snap[1], self.calls - snap[2]
        usd = i / 1e6 * self.s.price_in + o / 1e6 * self.s.price_out
        return dict(tokens_in=i, tokens_out=o, llm_calls=c, cost_usd=round(usd, 5))
