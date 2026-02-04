# NexaAgent-AI-ChatBot

# 🌟 Features
### Core Capabilities

*Multi-Tool Agent:* Integrated web search (DuckDuckGo) and calculator functionality

*Persistent Conversations:* SQLite-based checkpoint system for conversation history

*Real-time Streaming:* Server-sent events (SSE) for responsive chat experience

*Multi-Threading:* Manage multiple independent conversation threads

*RESTful API:* Clean FastAPI backend with automatic documentation

# 🏗️ Architecture
┌─────────────────┐
│   Streamlit UI  │  (Frontend - Chat Interface)
└────────┬────────┘
         │
         │ HTTP/SSE
         │
┌────────▼────────┐
│  FastAPI Server │  (Backend - API Layer)
└────────┬────────┘
         │
         │
┌────────▼────────┐
│    LangGraph    │  (Agent Framework)
│  State Machine  │
└────────┬────────┘
         │
    ┌────┴────┬──────────┐
    │         │          │
┌───▼──┐  ┌──▼───┐  ┌───▼────┐
│ LLM  │  │Search│  │Calculator│
└──────┘  └──────┘  └────────┘



# 📁 Project Structure

ai-chatbot-langgraph/
│
├── backend.py              # FastAPI server with LangGraph agent

├── frontend.py             # Streamlit chat interface

├── requirements.txt        # Python dependencies

├── .env                    # Environment variables (create this)

├── chatbot.db             # SQLite database (auto-generated)

└── README.md              # Project documentation
