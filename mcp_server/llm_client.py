# Thin wrapper around OpenRouter's chat-completions API.
# One job: send a system prompt + user prompt, get text back.

import httpx

from mcp_server.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def ask(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }

    # Analysis prompts are large, so allow a generous timeout.
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json=payload,
        )
        # OpenRouter puts the useful reason (no credits, rate limited, bad model)
        # in the response body, so surface that instead of a bare status code.
        if resp.status_code != 200:
            detail = resp.json().get("error", {}).get("message", resp.text[:300])
            raise RuntimeError(
                f"OpenRouter {resp.status_code} for model '{OPENROUTER_MODEL}': {detail}"
            )
        return resp.json()["choices"][0]["message"]["content"]
