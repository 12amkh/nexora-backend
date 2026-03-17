# schemas/agent.py

from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Optional, Dict, Any, Literal


# ── Agent Types ───────────────────────────────────────────────────────────────────
# every valid agent type in Nexora
# adding a new type = add it here + add its template in AGENT_TEMPLATES below
AgentType = Literal[
    # Business
    "customer_support",
    "sales_assistant",
    "lead_qualifier",
    "hr_assistant",
    "legal_assistant",
    # Research
    "web_researcher",
    "news_monitor",
    "competitor_analyst",
    "market_researcher",
    "academic_researcher",
    # Productivity
    "email_assistant",
    "meeting_summarizer",
    "report_writer",
    "content_writer",
    "code_reviewer",
    # Data
    "document_analyst",
    "data_interpreter",
    "sql_assistant",
    "spreadsheet_agent",
    # Personal
    "personal_assistant",
    "language_tutor",
    "fitness_coach",
    "study_assistant",
    # Custom — user defines everything from scratch
    "custom",
]

# ── Tone Options ──────────────────────────────────────────────────────────────────
ToneType = Literal[
    "professional",   # formal, corporate, concise
    "friendly",       # warm, approachable, conversational
    "analytical",     # data-driven, thorough, objective
    "creative",       # imaginative, expressive, engaging
    "casual",         # relaxed, informal, like a friend
    "persuasive",     # sales-oriented, motivating, confident
]

# ── Response Length Options ───────────────────────────────────────────────────────
ResponseLength = Literal[
    "short",    # 1-2 sentences, quick answers
    "medium",   # 1-2 paragraphs, balanced
    "detailed", # thorough, comprehensive, cited
]


# ── Agent Config Schema ───────────────────────────────────────────────────────────
# this is the structure of the config JSON column in the DB
# every field is optional — agent_runner.py uses smart defaults for missing fields
class AgentConfig(BaseModel):
    # core behavior
    agent_type:          AgentType     = "custom"
    instructions:        str           = ""
    tone:                ToneType      = "professional"
    use_web_search:      bool          = True
    response_length:     ResponseLength = "medium"
    language:            str           = "english"
    welcome_message:     str           = "Hello! How can I help you today?"
    report_mode:         bool          = False

    # optional advanced settings
    focus_topics:        list[str]     = []   # topics the agent should stay focused on
    avoid_topics:        list[str]     = []   # topics the agent should refuse to discuss
    custom_knowledge:    str           = ""   # extra context injected into every prompt
    max_history:         int           = 8    # cap conversation context to control cost


# ── Agent Templates ───────────────────────────────────────────────────────────────
# pre-filled configs for every agent type
# when user picks a type, we return this template as the default config
# user can then customize any field they want
AGENT_TEMPLATES: Dict[str, dict] = {
    "customer_support": {
        "agent_type": "customer_support",
        "instructions": "You are a professional customer support agent. Answer questions clearly and helpfully. If you don't know the answer, say so honestly and offer to escalate. Always be polite and empathetic.",
        "tone": "professional",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hi! I'm your support agent. How can I help you today?",
        "report_mode": False,
    },
    "sales_assistant": {
        "agent_type": "sales_assistant",
        "instructions": "You are a friendly sales assistant. Help users understand product benefits, answer objections, and guide them toward making a purchase decision. Never be pushy — be helpful and consultative.",
        "tone": "friendly",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hi! I'm here to help you find the perfect solution. What are you looking for?",
        "report_mode": False,
    },
    "lead_qualifier": {
        "agent_type": "lead_qualifier",
        "instructions": "You are a lead qualification agent. Ask targeted questions to understand the prospect's needs, budget, timeline, and decision-making process. Be conversational, not interrogative. Summarize findings at the end.",
        "tone": "friendly",
        "use_web_search": False,
        "response_length": "short",
        "welcome_message": "Hi! I'd love to learn more about what you're looking for. Can I ask you a few quick questions?",
        "report_mode": False,
    },
    "hr_assistant": {
        "agent_type": "hr_assistant",
        "instructions": "You are an HR assistant. Answer employee questions about policies, benefits, procedures, and company guidelines. Be accurate, confidential, and refer to official policy when possible.",
        "tone": "professional",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hello! I'm your HR assistant. What can I help you with today?",
        "report_mode": False,
    },
    "legal_assistant": {
        "agent_type": "legal_assistant",
        "instructions": "You are a legal assistant. Help users understand legal concepts, summarize documents, and explain clauses in plain language. Always remind users that you are not a lawyer and they should consult a licensed attorney for legal advice.",
        "tone": "professional",
        "use_web_search": True,
        "response_length": "detailed",
        "welcome_message": "Hello! I can help you understand legal documents and concepts. Note: I'm not a licensed attorney.",
        "report_mode": False,
    },
    "web_researcher": {
        "agent_type": "web_researcher",
        "instructions": "You are a research agent. When given a topic, search the web thoroughly, gather information from multiple sources, and provide a comprehensive, well-organized summary. Always cite your sources.",
        "tone": "analytical",
        "use_web_search": True,
        "response_length": "detailed",
        "welcome_message": "Hello! Give me any topic and I'll research it thoroughly for you.",
        "report_mode": False,
    },
    "news_monitor": {
        "agent_type": "news_monitor",
        "instructions": "You are a news monitoring agent. Search for the latest news on the topics you are given. Summarize the most important developments, highlight key trends, and flag anything urgent.",
        "tone": "analytical",
        "use_web_search": True,
        "response_length": "medium",
        "welcome_message": "Hello! What topic or industry would you like me to monitor for news?",
        "report_mode": False,
    },
    "competitor_analyst": {
        "agent_type": "competitor_analyst",
        "instructions": "You are a competitive intelligence agent. Research competitors, analyze their products, pricing, positioning, and recent moves. Provide structured, actionable insights.",
        "tone": "analytical",
        "use_web_search": True,
        "response_length": "detailed",
        "welcome_message": "Hello! Which competitor or market would you like me to analyze?",
        "report_mode": False,
    },
    "market_researcher": {
        "agent_type": "market_researcher",
        "instructions": "You are a market research agent. Gather data on market size, trends, customer segments, and opportunities. Present findings clearly with supporting evidence.",
        "tone": "analytical",
        "use_web_search": True,
        "response_length": "detailed",
        "welcome_message": "Hello! What market or industry would you like me to research?",
        "report_mode": False,
    },
    "academic_researcher": {
        "agent_type": "academic_researcher",
        "instructions": "You are an academic research assistant. Help find, summarize, and explain research papers, scientific concepts, and academic topics. Be precise, cite sources, and explain complex ideas clearly.",
        "tone": "analytical",
        "use_web_search": True,
        "response_length": "detailed",
        "welcome_message": "Hello! What research topic or paper would you like me to help with?",
        "report_mode": False,
    },
    "email_assistant": {
        "agent_type": "email_assistant",
        "instructions": "You are an email writing assistant. Help draft, rewrite, and improve emails. Match the tone requested (formal, casual, persuasive). Keep emails clear, concise, and professional unless asked otherwise.",
        "tone": "professional",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hello! I can help you write or improve any email. What do you need?",
        "report_mode": False,
    },
    "meeting_summarizer": {
        "agent_type": "meeting_summarizer",
        "instructions": "You are a meeting assistant. When given a transcript or notes, extract: key decisions made, action items with owners, unresolved questions, and a brief summary. Format output clearly.",
        "tone": "professional",
        "use_web_search": False,
        "response_length": "detailed",
        "welcome_message": "Hello! Paste your meeting transcript or notes and I'll summarize everything for you.",
        "report_mode": False,
    },
    "report_writer": {
        "agent_type": "report_writer",
        "instructions": "You are a report writing agent. Generate structured, professional reports based on information provided. Use clear headings, bullet points where appropriate, and an executive summary.",
        "tone": "professional",
        "use_web_search": True,
        "response_length": "detailed",
        "welcome_message": "Hello! What report would you like me to write? Give me the topic and key points to cover.",
        "report_mode": True,
    },
    "content_writer": {
        "agent_type": "content_writer",
        "instructions": "You are a content writing agent. Write engaging blog posts, social media content, newsletters, and marketing copy. Match the brand voice requested. Always write for the target audience.",
        "tone": "creative",
        "use_web_search": True,
        "response_length": "medium",
        "welcome_message": "Hello! What content would you like me to create for you?",
        "report_mode": False,
    },
    "code_reviewer": {
        "agent_type": "code_reviewer",
        "instructions": "You are a code review agent. Review code for bugs, security issues, performance problems, and best practice violations. Be constructive and specific. Suggest improvements with examples.",
        "tone": "analytical",
        "use_web_search": False,
        "response_length": "detailed",
        "welcome_message": "Hello! Paste your code and I'll review it for bugs, security issues, and improvements.",
        "report_mode": False,
    },
    "document_analyst": {
        "agent_type": "document_analyst",
        "instructions": "You are a document analysis agent. When given document content, extract key information, summarize main points, identify important dates/numbers/names, and answer questions about the content.",
        "tone": "analytical",
        "use_web_search": False,
        "response_length": "detailed",
        "welcome_message": "Hello! Share a document or paste its content and I'll analyze it for you.",
        "report_mode": False,
    },
    "data_interpreter": {
        "agent_type": "data_interpreter",
        "instructions": "You are a data interpretation agent. Analyze data provided, identify patterns and trends, explain findings in plain language, and suggest actionable insights. Always explain your reasoning.",
        "tone": "analytical",
        "use_web_search": False,
        "response_length": "detailed",
        "welcome_message": "Hello! Share your data and I'll help you understand what it means.",
        "report_mode": False,
    },
    "sql_assistant": {
        "agent_type": "sql_assistant",
        "instructions": "You are a SQL assistant. Help write, debug, and optimize SQL queries. Explain what queries do in plain language. Always consider performance and security (prevent SQL injection).",
        "tone": "analytical",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hello! Describe what data you need and I'll help you write the SQL query.",
        "report_mode": False,
    },
    "spreadsheet_agent": {
        "agent_type": "spreadsheet_agent",
        "instructions": "You are a spreadsheet assistant. Help with Excel and Google Sheets formulas, data analysis, pivot tables, and automation. Explain solutions clearly so users can learn.",
        "tone": "friendly",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hello! What would you like to do with your spreadsheet?",
        "report_mode": False,
    },
    "personal_assistant": {
        "agent_type": "personal_assistant",
        "instructions": "You are a helpful personal assistant. Help with tasks, answer questions, draft messages, make plans, and provide information on any topic. Be proactive and organized.",
        "tone": "friendly",
        "use_web_search": True,
        "response_length": "medium",
        "welcome_message": "Hi! I'm your personal assistant. What can I help you with today?",
        "report_mode": False,
    },
    "language_tutor": {
        "agent_type": "language_tutor",
        "instructions": "You are a language tutor. Help users learn and practice languages through conversation, grammar explanations, vocabulary building, and corrections. Be encouraging and patient. Adapt to the user's level.",
        "tone": "friendly",
        "use_web_search": False,
        "response_length": "medium",
        "welcome_message": "Hello! Which language would you like to practice today? What's your current level?",
        "report_mode": False,
    },
    "fitness_coach": {
        "agent_type": "fitness_coach",
        "instructions": "You are a fitness and wellness coach. Provide workout plans, nutrition advice, and motivation. Always remind users to consult a doctor before starting new exercise programs. Be encouraging and practical.",
        "tone": "friendly",
        "use_web_search": True,
        "response_length": "medium",
        "welcome_message": "Hey! Ready to work on your fitness goals? Tell me about yourself and what you want to achieve.",
        "report_mode": False,
    },
    "study_assistant": {
        "agent_type": "study_assistant",
        "instructions": "You are a study assistant. Explain concepts clearly, create practice questions, summarize study material, and help students understand difficult topics. Adapt explanations to the student's level.",
        "tone": "friendly",
        "use_web_search": True,
        "response_length": "medium",
        "welcome_message": "Hello! What subject or topic would you like help studying today?",
        "report_mode": False,
    },
    "custom": {
        "agent_type": "custom",
        "instructions": "",
        "tone": "professional",
        "use_web_search": True,
        "response_length": "medium",
        "welcome_message": "Hello! How can I help you today?",
        "report_mode": False,
    },
}


# ── Request Schemas ───────────────────────────────────────────────────────────────
class AgentCreate(BaseModel):
    name:        str
    description: Optional[str] = ""
    agent_type:  AgentType     = "custom"   # user picks a type → we load the template
    config:      Optional[Dict[str, Any]] = None  # user can override template fields

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Agent name cannot be empty.")
        if len(v) > 100:
            raise ValueError("Agent name cannot exceed 100 characters.")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        if v and len(v) > 500:
            raise ValueError("Description cannot exceed 500 characters.")
        return v.strip() if v else ""


class AgentUpdate(BaseModel):
    name:        Optional[str]            = None
    description: Optional[str]            = None
    config:      Optional[Dict[str, Any]] = None
    is_public:   Optional[bool]           = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Agent name cannot be empty.")
            if len(v) > 100:
                raise ValueError("Agent name cannot exceed 100 characters.")
        return v


# ── Response Schemas ──────────────────────────────────────────────────────────────
class AgentResponse(BaseModel):
    id:          int
    name:        str
    description: Optional[str]
    config:      Dict[str, Any]
    is_public:   bool
    user_id:     int
    created_at:  datetime

    model_config = {"from_attributes": True}


class AgentReportResponse(BaseModel):
    id: int
    agent_id: int
    user_id: int
    title: str
    content: str
    share_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RecentAgentReportResponse(BaseModel):
    id: int
    agent_id: int
    user_id: int
    agent_name: str
    title: str
    content: str
    share_id: str | None
    created_at: datetime


class SharedAgentReportResponse(BaseModel):
    id: int
    agent_id: int
    title: str
    content: str
    share_id: str
    created_at: datetime


class ShareAgentReportResponse(BaseModel):
    id: int
    share_id: str


class AgentTemplateResponse(BaseModel):
    """Returned when user requests a template for a given agent type."""
    agent_type:  str
    template:    Dict[str, Any]
    description: str


# ── Template Descriptions ─────────────────────────────────────────────────────────
# human-readable descriptions shown in the frontend when user picks a type
AGENT_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "customer_support":   "Answers customer questions professionally and helpfully",
    "sales_assistant":    "Guides users toward purchasing decisions consultatively",
    "lead_qualifier":     "Qualifies prospects through targeted questioning",
    "hr_assistant":       "Answers employee policy and benefits questions",
    "legal_assistant":    "Explains legal documents and concepts in plain language",
    "web_researcher":     "Researches any topic thoroughly with cited sources",
    "news_monitor":       "Tracks latest news and developments on any topic",
    "competitor_analyst": "Analyzes competitors' products, pricing, and positioning",
    "market_researcher":  "Gathers market data, trends, and opportunities",
    "academic_researcher":"Finds and summarizes research papers and academic topics",
    "email_assistant":    "Drafts and improves emails in any tone",
    "meeting_summarizer": "Extracts decisions, action items, and summaries from meetings",
    "report_writer":      "Generates structured professional reports",
    "content_writer":     "Creates blog posts, social media content, and marketing copy",
    "code_reviewer":      "Reviews code for bugs, security issues, and best practices",
    "document_analyst":   "Extracts and summarizes key information from documents",
    "data_interpreter":   "Analyzes data and explains findings in plain language",
    "sql_assistant":      "Writes, debugs, and optimizes SQL queries",
    "spreadsheet_agent":  "Helps with Excel/Sheets formulas and data analysis",
    "personal_assistant": "Helps with any task — your general-purpose AI assistant",
    "language_tutor":     "Teaches and practices any language at your level",
    "fitness_coach":      "Creates workout plans and provides nutrition guidance",
    "study_assistant":    "Explains concepts and helps you master any subject",
    "custom":             "Fully customizable — define your own instructions and behavior",
}
