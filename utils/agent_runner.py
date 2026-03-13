# utils/agent_runner.py

import os
import ssl
import logging
import certifi
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


def build_llm(config: dict) -> ChatGroq:
    tone        = config.get("tone", "professional")
    temperature = TONE_TEMPERATURE.get(tone, 0.5)
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        api_key=os.getenv("GROQ_API_KEY"),
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


# ── Standard (Non-Streaming) Agent ───────────────────────────────────────────────
async def run_agent(
    user_message: str,
    conversation_history: list,
    agent_config: dict = None,
) -> str:
    config        = agent_config or {}
    llm           = build_llm(config)
    tools         = build_tools(config)
    system_prompt = build_system_prompt(config)
    history       = format_history(conversation_history)

    all_messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_message)]

    logger.info(f"run_agent: type={config.get('agent_type','custom')} tone={config.get('tone','professional')} web_search={config.get('use_web_search', True)}")

    agent  = create_react_agent(model=llm, tools=tools)
    result = await agent.ainvoke({"messages": all_messages})

    response = result["messages"][-1].content
    logger.info(f"run_agent: response generated ({len(response)} chars)")
    return response


# ── Streaming Agent ───────────────────────────────────────────────────────────────
async def stream_agent(
    user_message: str,
    conversation_history: list,
    agent_config: dict = None,
) -> AsyncGenerator[str, None]:
    config        = agent_config or {}
    llm           = build_llm(config)
    tools         = build_tools(config)
    system_prompt = build_system_prompt(config)
    history       = format_history(conversation_history)

    all_messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_message)]

    logger.info(f"stream_agent: type={config.get('agent_type','custom')} web_search={config.get('use_web_search', True)}")

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

    logger.info("stream_agent: stream complete")