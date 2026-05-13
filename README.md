# AutoReply Pro — 🤖 AI-Powered Business Reply Automation

> **Stack:** Streamlit · Google Gemini 1.5 Pro · RAG (FAISS + Sentence Transformers) · Telegram Bot API · Gmail API · LangChain

---

## Overview

AutoReply Pro is a **multi-channel, RAG-powered business reply automation system**.

Upload your business knowledge base (PDFs, Excel sheets, Word docs, CSVs, JSON, etc.), configure your communication channels (Telegram, Gmail), and let Gemini generate contextually accurate, business-aware replies **automatically**.

### Core Capabilities

- 🧠 **RAG-backed replies** — answers grounded in your uploaded business data
- 📄 **Multi-format ingestion** — PDF, DOCX, TXT, MD, XLSX, XLS, CSV, JSON
- 📡 **Multi-channel delivery** — Telegram Bot (free), Gmail (free)
- 🖥️ **Streamlit control panel** — no-code UI for config, uploads, and live logs
- ✨ **Gemini 1.5 Pro** — powerful generation via Google AI Studio (free tier)

---

## Project Structure

```
reply_tele_email/
├── app.py                        # Streamlit entry point
├── config/
│   └── settings.py               # Pydantic settings loader
├── ingestion/
│   ├── loader.py                 # Multi-format document loader
│   ├── chunker.py                # Text splitter / chunking
│   └── supported_formats.py     # Format registry
├── rag/
│   ├── embedder.py               # HuggingFace embeddings
│   ├── vector_store.py           # FAISS index build & query
│   └── retriever.py              # Top-k context retriever
├── llm/
│   ├── gemini_client.py          # Gemini API wrapper
│   ├── prompt_builder.py         # RAG prompt assembler
│   └── reply_generator.py        # Retrieval → generation orchestrator
├── channels/
│   ├── base.py                   # Abstract channel interface
│   ├── telegram_channel.py       # Telegram Bot integration
│   ├── gmail_channel.py          # Gmail API integration
│   └── channel_registry.py      # Dynamic channel loader
├── ui/
│   ├── sidebar.py                # API keys & channel toggles
│   ├── file_uploader.py          # Knowledge base upload panel
│   ├── live_log.py               # Real-time reply log
│   └── channel_config.py        # Per-channel setup guide
├── data/
│   ├── uploads/                  # Uploaded business documents
│   └── faiss_index/              # Persisted FAISS vector store
├── logs/
│   └── reply_log.jsonl           # Append-only structured reply log
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup & Installation

```bash
# 1. Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in environment variables
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux

# 4. Run the app
streamlit run app.py
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `GMAIL_CREDENTIALS_PATH` | Path to Gmail OAuth2 `credentials.json` |
| `FAISS_INDEX_PATH` | Path to save/load FAISS index |
| `EMBED_MODEL` | Sentence-transformers model name |
| `TOP_K_CHUNKS` | Number of RAG chunks to retrieve |
| `POLL_INTERVAL` | Polling interval in seconds |

---

## Channel Setup

### Telegram (Free ✅)
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the Bot Token → paste in Streamlit sidebar
3. Toggle Telegram ON → Start Automation

### Gmail (Free ✅)
1. [Google Cloud Console](https://console.cloud.google.com) → Enable Gmail API
2. Create OAuth 2.0 credentials (Desktop app) → download `credentials.json`
3. Upload `credentials.json` in Streamlit sidebar
4. Toggle Gmail ON → Start Automation

---

## How It Works

```
Business Docs → FAISS Vector Index
                      ↓
Incoming Message → Embed → Similarity Search → Top-K Chunks
                                                    ↓
                                          Gemini 1.5 Pro (RAG)
                                                    ↓
                                          Reply → Channel → Sent ✓
```

---

*Built with AutoReply Pro System Design. Ready to deploy.*
