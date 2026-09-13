"""
engine/llm_router.py — free-tier LLM fallback chain

Chains: Groq → Gemini Flash → Cloudflare Workers AI → OpenRouter → Ollama local → extractive fallback

Usage:
  from engine.llm_router import LLMRouter
  router = LLMRouter()
  result = router.complete("Summarize this public document...")
  # result = {"method": "llm", "provider": "groq", "text": "..."} or extractive

Env / secrets:
  GROQ_API_KEY, GEMINI_API_KEY, CF_AI_TOKEN (or CF_ACCOUNT_ID + CF_API_TOKEN), OPENROUTER_API_KEY
  All via GitHub repo secrets or Colab userdata.

Already wired to engine/analyze.py: Summarizer(llm_fn=LLMRouter().complete_fn)

Free tiers (2026):
  Groq ~1000 req/day (Llama 3.3 70B fast)
  Gemini Flash ~1500 req/day
  Cloudflare Workers AI 10k neurons/day ≈ 1300 responses/day (Llama 3.1 8B)
  OpenRouter free models (varies)
  Ollama local (unlimited)
"""
from __future__ import annotations
import os, json, time, urllib.request, urllib.parse

def _get_secret(name):
    v = os.environ.get(name)
    if v:
        return v
    try:
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        return None

def _http_post_json(url, headers, payload, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8","replace"))

class LLMRouter:
    def __init__(self):
        self.groq_key = _get_secret("GROQ_API_KEY")
        self.gemini_key = _get_secret("GEMINI_API_KEY")
        self.cf_token = _get_secret("CF_AI_TOKEN") or _get_secret("CF_API_TOKEN")
        self.cf_account = _get_secret("CF_ACCOUNT_ID")
        self.openrouter_key = _get_secret("OPENROUTER_API_KEY")

    def groq(self, prompt: str) -> str:
        if not self.groq_key:
            raise RuntimeError("no groq key")
        # Groq OpenAI-compatible
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1200,
        }
        headers = {"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"}
        resp = _http_post_json("https://api.groq.com/openai/v1/chat/completions", headers, payload)
        return resp["choices"][0]["message"]["content"]

    def gemini(self, prompt: str) -> str:
        if not self.gemini_key:
            raise RuntimeError("no gemini key")
        # Gemini 1.5 Flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200}}
        headers = {"Content-Type": "application/json"}
        resp = _http_post_json(url, headers, payload)
        return resp["candidates"][0]["content"]["parts"][0]["text"]

    def cf_workers_ai(self, prompt: str) -> str:
        if not (self.cf_token and self.cf_account):
            raise RuntimeError("no cf keys")
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account}/ai/run/@cf/meta/llama-3.1-8b-instruct"
        headers = {"Authorization": f"Bearer {self.cf_token}", "Content-Type": "application/json"}
        payload = {"prompt": prompt, "max_tokens": 1200}
        resp = _http_post_json(url, headers, payload)
        # CF returns {"result": {"response": "..."}}
        return resp.get("result", {}).get("response") or resp.get("result", {}).get("text") or json.dumps(resp)[:2000]

    def openrouter(self, prompt: str) -> str:
        if not self.openrouter_key:
            raise RuntimeError("no openrouter key")
        payload = {
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.openrouter_key}", "Content-Type": "application/json", "HTTP-Referer": "https://therealwindycity.com", "X-Title": "The Real Windy City"}
        resp = _http_post_json("https://openrouter.ai/api/v1/chat/completions", headers, payload)
        return resp["choices"][0]["message"]["content"]

    def ollama(self, prompt: str) -> str:
        # local ollama at localhost:11434
        payload = {"model": "llama3.1:8b", "prompt": prompt, "stream": False}
        headers = {"Content-Type": "application/json"}
        try:
            resp = _http_post_json("http://localhost:11434/api/generate", headers, payload, timeout=120)
            return resp.get("response","")
        except Exception as e:
            raise RuntimeError(f"ollama not available {e}")

    def extractive(self, prompt: str) -> str:
        # fallback uses existing engine/analyze.py logic
        from .analyze import extractive_summary
        return "\n".join("• " + s for s in extractive_summary(prompt, max_sentences=5))

    def complete(self, prompt: str) -> str:
        """Try chain, return text (for Summarizer llm_fn)"""
        for fn in [self.groq, self.gemini, self.cf_workers_ai, self.openrouter, self.ollama]:
            try:
                txt = fn(prompt)
                if txt and len(txt.strip())>20:
                    return txt.strip()
            except Exception:
                continue
        return self.extractive(prompt)

    def complete_fn(self, prompt: str) -> str:
        """Alias for Summarizer(llm_fn=...)"""
        return self.complete(prompt)

    def complete_with_meta(self, prompt: str) -> dict:
        for name, fn in [("groq", self.groq), ("gemini", self.gemini), ("cf_workers_ai", self.cf_workers_ai), ("openrouter", self.openrouter), ("ollama", self.ollama)]:
            try:
                txt = fn(prompt)
                if txt and len(txt.strip())>20:
                    return {"method": "llm", "provider": name, "text": txt.strip()}
            except Exception as e:
                continue
        return {"method": "extractive-offline", "provider": "extractive", "text": self.extractive(prompt)}
