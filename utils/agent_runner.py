# utils/agent_runner.py

import os
import ssl
import logging
import certifi
import httpx
from typing import AsyncGenerator
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_tavily import TavilySearch
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

load_dotenv()

logger = logging.getLogger(__name__)

os.environ["TAVILY_API_KEY"] = os.getenv("TAVILY_API_KEY", "")

ssl._create_default_https_context = ssl.create_default_context
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

TONE_TEMPERATURE = {
    "professional": 0.3,
    "analytical":   0.2,
    "friendly":     0.7,
    "casual":       0.8,
    "creative":     0.9,
    "persuasive":   0.6,
}

RESPONSE_LENGTH_INSTRUCTIONS = {
    "short":    "Keep your responses brief — 1 to 3 sentences maximum.",
    "medium":   "Keep your responses concise — 1 to 2 paragraphs.",
    "detailed": "Provide thorough, comprehensive responses with supporting details.",
}

PRIMARY_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SCHEDULE_GROQ_MODEL = os.getenv("GROQ_SCHEDULE_MODEL", PRIMARY_GROQ_MODEL)


def read_env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default


def get_fallback_providers() -> list[dict]:
    providers = []

    generic_base_url = read_env("FALLBACK_LLM_BASE_URL").rstrip("/")
    generic_api_key = read_env("FALLBACK_LLM_API_KEY")
    generic_model = read_env("FALLBACK_LLM_MODEL")
    generic_name = read_env("FALLBACK_LLM_PROVIDER", "openai-compatible")

    if generic_base_url and generic_api_key and generic_model:
        providers.append(
            {
                "name": generic_name,
                "base_url": generic_base_url,
                "api_key": generic_api_key,
                "model": generic_model,
            }
        )

    gemini_api_key = read_env("GEMINI_API_KEY")
    gemini_model = read_env("GEMINI_MODEL", "gemini-3-flash-preview")
    gemini_schedule_model = read_env("GEMINI_SCHEDULE_MODEL", gemini_model)
    if gemini_api_key:
        providers.append(
            {
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": gemini_api_key,
                "model": gemini_model,
                "schedule_model": gemini_schedule_model,
            }
        )

    openai_api_key = read_env("OPENAI_API_KEY")
    openai_model = read_env("OPENAI_MODEL", "gpt-4o-mini")
    openai_schedule_model = read_env("OPENAI_SCHEDULE_MODEL", openai_model)
    if openai_api_key:
        providers.append(
            {
                "name": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": openai_api_key,
                "model": openai_model,
                "schedule_model": openai_schedule_model,
            }
        )

    # Deduplicate providers that point to the same backend/model combo.
    seen = set()
    unique_providers = []
    for provider in providers:
        key = (provider["name"], provider["base_url"], provider["model"])
        if key in seen:
            continue
        seen.add(key)
        unique_providers.append(provider)

    return unique_providers


def build_llm(config: dict) -> ChatGroq:
    tone        = config.get("tone", "professional")
    temperature = TONE_TEMPERATURE.get(tone, 0.5)
    return ChatGroq(
        model=PRIMARY_GROQ_MODEL,
        temperature=temperature,
        api_key=os.getenv("GROQ_API_KEY"),
    )


def build_groq_llm(config: dict, mode: str) -> ChatGroq:
    tone = config.get("tone", "professional")
    temperature = TONE_TEMPERATURE.get(tone, 0.5)
    model = SCHEDULE_GROQ_MODEL if mode == "scheduled" else PRIMARY_GROQ_MODEL
    return ChatGroq(
        model=model,
        temperature=temperature,
        api_key=read_env("GROQ_API_KEY"),
    )


def build_tools(config: dict) -> list:
    tools = []
    if config.get("use_web_search", True):
        tools.append(TavilySearch(max_results=3))
    return tools


def build_system_prompt(config: dict) -> str:
    instructions     = config.get("instructions",     "")
    tone             = config.get("tone",             "professional")
    response_length  = config.get("response_length",  "medium")
    language         = config.get("language",         "english")
    focus_topics     = config.get("focus_topics",     [])
    avoid_topics     = config.get("avoid_topics",     [])
    custom_knowledge = config.get("custom_knowledge", "")
    use_web_search   = config.get("use_web_search",   True)

    tone_instructions = {
        "professional": "Maintain a professional, formal tone at all times.",
        "analytical":   "Be analytical and data-driven. Back up claims with evidence.",
        "friendly":     "Be warm, approachable, and conversational.",
        "casual":       "Be relaxed and informal, like talking to a friend.",
        "creative":     "Be creative, engaging, and expressive in your responses.",
        "persuasive":   "Be confident and persuasive. Highlight benefits and value.",
    }

    prompt_parts = []
    prompt_parts.append(instructions if instructions else "You are Nexora, a helpful and intelligent AI assistant.")
    prompt_parts.append(tone_instructions.get(tone, ""))

    length_instruction = RESPONSE_LENGTH_INSTRUCTIONS.get(response_length, "")
    if length_instruction:
        prompt_parts.append(length_instruction)

    if language.lower() != "english":
        prompt_parts.append(f"Always respond in {language}.")

    if focus_topics:
        prompt_parts.append(f"Stay focused on these topics: {', '.join(focus_topics)}. If asked about something outside these topics, politely redirect.")

    if avoid_topics:
        prompt_parts.append(f"Do not discuss or provide information about: {', '.join(avoid_topics)}. If asked, politely decline.")

    if custom_knowledge:
        prompt_parts.append(f"Additional context you should know: {custom_knowledge}")

    if use_web_search:
        prompt_parts.append("You have access to a web search tool. Use it when the user asks about current events, real-time data, or anything that requires up-to-date information.")
    else:
        prompt_parts.append("Answer based on your knowledge. If you don't know something, say so honestly.")

    return " ".join(filter(None, prompt_parts))


def format_history(conversation_history: list) -> list:
    formatted = []
    for entry in conversation_history:
        # support both ORM objects (entry.role) and plain dicts (entry["role"])
        role    = entry["role"]    if isinstance(entry, dict) else entry.role
        message = entry["message"] if isinstance(entry, dict) else entry.message
        if role == "user":
            formatted.append(HumanMessage(content=message))
        elif role == "assistant":
            formatted.append(AIMessage(content=message))
    return formatted


def get_max_history(config: dict, mode: str) -> int:
    configured = config.get("max_history")
    if isinstance(configured, int) and configured >= 0:
        return configured
    return 4 if mode == "scheduled" else 8


def trim_history(conversation_history: list, config: dict, mode: str) -> list:
    max_history = get_max_history(config, mode)
    if max_history <= 0:
        return []
    return conversation_history[-max_history:]


# casual phrases that don't need web search — respond naturally from LLM knowledge
CASUAL_PHRASES = {
    "hi", "hello", "hey", "hiya", "howdy",
    "how are you", "how are you doing", "how's it going", "what's up", "sup",
    "good morning", "good afternoon", "good evening", "good night",
    "thanks", "thank you", "thank you so much", "thx", "ty",
    "bye", "goodbye", "see you", "see ya", "later",
    "ok", "okay", "sure", "great", "awesome", "nice", "cool",
    "yes", "no", "maybe", "got it", "understood",
    "who are you", "what are you", "what can you do",
    "help", "what is your name", "your name",
}

def is_casual_message(message: str) -> bool:
    """Return True if the message is casual conversation that doesn't need web search."""
    cleaned = message.lower().strip().rstrip("!?.,'\"")
    # exact match against known casual phrases
    if cleaned in CASUAL_PHRASES:
        return True
    # very short messages (1-2 words) are almost always casual
    if len(cleaned.split()) <= 2 and len(cleaned) <= 20:
        return True
    return False


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "rate_limit_exceeded" in text
        or "rate limit" in text
        or "too many requests" in text
        or exc.__class__.__name__ == "RateLimitError"
    )


def has_fallback_llm() -> bool:
    return len(get_fallback_providers()) > 0


def build_fallback_messages(system_prompt: str, history: list, user_message: str) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]

    for entry in history:
        if isinstance(entry, HumanMessage):
            messages.append({"role": "user", "content": entry.content})
        elif isinstance(entry, AIMessage):
            messages.append({"role": "assistant", "content": entry.content})

    messages.append({"role": "user", "content": user_message})
    return messages


def get_provider_sequence(mode: str) -> list[str]:
    # Scheduled work is cheaper-first; interactive chat stays quality-first.
    if mode == "scheduled":
        return ["gemini", "groq", "openai", "openai-compatible"]
    return ["groq", "gemini", "openai", "openai-compatible"]


def get_openai_compatible_candidates(mode: str) -> list[dict]:
    candidates = []
    provider_order = {name: i for i, name in enumerate(get_provider_sequence(mode))}

    for provider in get_fallback_providers():
        provider = provider.copy()
        provider["model"] = provider.get("schedule_model", provider["model"]) if mode == "scheduled" else provider["model"]
        candidates.append(provider)

    candidates.sort(key=lambda provider: provider_order.get(provider["name"], 999))
    return candidates


def extract_fallback_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Fallback LLM response did not include choices.")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "text" and isinstance(item.get("content"), str):
                    parts.append(item["content"])
        text = "".join(parts).strip()
        if text:
            return text

    raise ValueError(f"Unsupported fallback LLM response format: {content!r}")


async def run_fallback_llm(system_prompt: str, history: list, user_message: str, config: dict, mode: str) -> str:
    providers = get_openai_compatible_candidates(mode)
    if not providers:
        raise RuntimeError("Fallback LLM is not configured.")

    tone = config.get("tone", "professional")
    temperature = TONE_TEMPERATURE.get(tone, 0.5)
    last_error = None

    for provider in providers:
        payload = {
            "model": provider["model"],
            "messages": build_fallback_messages(system_prompt, history, user_message),
            "temperature": temperature,
        }

        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{provider['base_url']}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            text = extract_fallback_text(data)
            logger.warning(f"run_agent: using fallback provider {provider['name']}")
            return text
        except Exception as exc:
            last_error = exc
            logger.warning(
                f"run_agent: fallback provider {provider['name']} failed, trying next provider",
                exc_info=True,
            )

    if last_error:
        raise last_error
    raise RuntimeError("All fallback providers failed.")


# ── Standard (Non-Streaming) Agent ───────────────────────────────────────────────
async def run_agent(
    user_message: str,
    conversation_history: list,
    agent_config: dict = None,
    mode: str = "interactive",
) -> str:
    config        = agent_config or {}
    llm           = build_groq_llm(config, mode)
    # skip web search for casual messages even if agent has it enabled
    # real life: you don't google "hi" — you just respond naturally
    tools         = [] if is_casual_message(user_message) else build_tools(config)
    system_prompt = build_system_prompt(config)
    history       = format_history(trim_history(conversation_history, config, mode))

    all_messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_message)]

    logger.info(f"run_agent: type={config.get('agent_type','custom')} tone={config.get('tone','professional')} web_search={bool(tools)}")

    try:
        if mode == "scheduled" and not tools and has_fallback_llm():
            # Cheapest path for automations: try low-cost OpenAI-compatible providers first.
            response = await run_fallback_llm(system_prompt, history, user_message, config, mode)
            logger.info(f"run_agent: scheduled fallback-first response generated ({len(response)} chars)")
            return response

        agent  = create_react_agent(model=llm, tools=tools)
        result = await agent.ainvoke({"messages": all_messages})
        response = result["messages"][-1].content
        logger.info(f"run_agent: response generated ({len(response)} chars)")
        return response
    except Exception as exc:
        if not is_rate_limit_error(exc) or not has_fallback_llm():
            raise

        logger.warning("run_agent: Groq rate-limited, attempting configured fallback providers", exc_info=True)
        response = await run_fallback_llm(system_prompt, history, user_message, config, mode)
        logger.info(f"run_agent: fallback response generated ({len(response)} chars)")
        return response


# ── Streaming Agent ───────────────────────────────────────────────────────────────
async def stream_agent(
    user_message: str,
    conversation_history: list,
    agent_config: dict = None,
    mode: str = "interactive",
) -> AsyncGenerator[str, None]:
    config        = agent_config or {}
    llm           = build_groq_llm(config, mode)
    # skip web search for casual messages — respond instantly without searching
    tools         = [] if is_casual_message(user_message) else build_tools(config)
    system_prompt = build_system_prompt(config)
    history       = format_history(trim_history(conversation_history, config, mode))

    all_messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_message)]

    logger.info(f"stream_agent: type={config.get('agent_type','custom')} web_search={bool(tools)}")

    try:
        if tools:
            agent    = create_react_agent(model=llm, tools=tools)
            result   = await agent.ainvoke({"messages": all_messages})
            full_text = result["messages"][-1].content

            chunk_size = 3
            for i in range(0, len(full_text), chunk_size):
                yield full_text[i:i + chunk_size]

        else:
            async for chunk in llm.astream(all_messages):
                if chunk.content:
                    yield chunk.content
    except Exception as exc:
        if not is_rate_limit_error(exc) or not has_fallback_llm():
            raise

        logger.warning("stream_agent: Groq rate-limited, attempting configured fallback providers", exc_info=True)
        fallback_text = await run_fallback_llm(system_prompt, history, user_message, config, mode)
        chunk_size = 12
        for i in range(0, len(fallback_text), chunk_size):
            yield fallback_text[i:i + chunk_size]

    logger.info("stream_agent: stream complete")
