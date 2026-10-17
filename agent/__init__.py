"""windycity-agent — a portable, local, multi-agent runtime.

Same capability shape as a hosted "agent mode" (plan, use real tools, verify,
report) but running on hardware you own, on every device you own:

    python3 -m agent doctor      # what works here, and the workaround for what doesn't
    python3 -m agent serve       # installable web console for phone/Chromebook/tablet
    python3 -m agent run "..."   # one-shot task
    python3 -m agent selftest    # offline proof: no keys, no network

Provider-agnostic by design: Anthropic, any OpenAI-compatible endpoint (OpenAI,
OpenRouter, Gemini, Groq, LM Studio, llama.cpp, vLLM), local Ollama, the Claude
CLI, a paste-bridge for chat UIs with no API (Arena.ai), and an offline demo.
"""
__version__ = "1.0.0"
