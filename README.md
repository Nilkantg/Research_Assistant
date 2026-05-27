# AI Research Assistant

A production-style AI Research Assistant built using FastAPI, LangChain, ChromaDB, and RAG architecture.

---

# Project Structure

```text
ai_research_assistant/
│
├── app/                    ← startup, server init, app factory
│   └── main.py
│
├── api/                    ← FastAPI route handlers (thin layer, no logic)
│   ├── routes/
│   │   ├── chat.py         ← POST /chat, GET /sessions
│   │   └── documents.py    ← POST /upload, GET /documents
│   └── middleware.py       ← CORS, rate limiting, logging
│
├── chains/                 ← LCEL pipeline definitions (core logic lives here)
│   ├── rag_chain.py        ← The main RAG Q&A chain
│   ├── ingestion_chain.py  ← Document loading → splitting → embedding
│   └── rewrite_chain.py    ← History-aware question rewriting
│
├── retrievers/             ← Custom retriever logic
│   └── contextual.py       ← Contextual compression + MMR retriever
│
├── memory/                 ← Session + history management
│   └── history.py          ← SQLChatMessageHistory wiring per session
│
├── vectorstore/            ← Vector DB connection + management
│   └── chroma_store.py     ← ChromaDB client, collection management
│
├── prompts/                ← All prompt templates in one place
│   ├── rag_prompt.py       ← System prompt for RAG answers
│   └── rewrite_prompt.py   ← Prompt for question rewriting
│
├── models/                 ← Pydantic schemas (not ML models)
│   ├── chat.py             ← ChatRequest, ChatResponse, Source
│   └── document.py         ← UploadRequest, DocumentMetadata
│
├── database/               ← DB connection, migrations
│   ├── session.py          ← SQLite connection setup
│   └── models.py           ← SQLAlchemy table definitions
│
├── config/                 ← All configuration in one place
│   └── settings.py         ← Pydantic settings, reads from .env
│
├── utils/                  ← Shared utilities
│   ├── logging.py          ← Structured logging setup
│   └── helpers.py          ← Token counting, text utils
│
├── tests/                  ← Tests mirror the app structure
│   ├── test_chains/
│   ├── test_api/
│   └── conftest.py
│
├── logs/                   ← Log files (gitignored)
│
├── data/                   ← Uploaded documents (gitignored)
│   └── uploads/
│
├── .env                    ← Secrets (NEVER commit this)
├── .env.example            ← Template showing what vars are needed
├── requirements.txt
└── README.md
```

---

# Tech Stack

- FastAPI
- LangChain
- ChromaDB
- SQLAlchemy
- SQLite
- Pydantic
- Python
- LCEL (LangChain Expression Language)

---

# Features

- RAG-based Question Answering
- Contextual Retrieval
- Session-based Chat Memory
- Document Upload & Processing
- Question Rewriting
- Vector Search using ChromaDB
- Structured Logging
- Modular Production-Ready Architecture

---

# Setup Instructions

## Clone Repository

```bash
git clone <your-repository-url>
cd ai_research_assistant
```

---

## Create Virtual Environment

### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate
```

### Linux / Mac

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Run FastAPI Server

```bash
uvicorn app.main:app --reload
```

---

# Environment Variables

Create a `.env` file and add:

```env
OPENAI_API_KEY=your_api_key
DATABASE_URL=sqlite:///./chat_history.db
CHROMA_DB_PATH=./chroma_db
```

---

# Future Improvements

- Authentication & Authorization
- Redis Caching
- Streaming Responses
- Async Processing
- Docker Support
- CI/CD Pipeline
- PostgreSQL Integration
- Deployment on AWS/GCP/Azure

---

# License

MIT License