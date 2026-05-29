# database/models.py
#
# WHY THIS FILE EXISTS:
# This file defines what your database tables look like, as Python classes.
# SQLAlchemy maps these classes to actual SQL tables — you never write
# raw CREATE TABLE SQL. The class IS the schema.
#
# WHY SEPARATE MODELS FROM SESSION:
# models.py = what the tables look like (schema)
# session.py = how to connect to the database (connection)
# Keeping them separate means you can import the schema without
# triggering a database connection. Useful in tests and migrations.

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, DateTime,
    Integer, Index, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------
# DeclarativeBase is the modern SQLAlchemy 2.0 way to define models.
# All your table classes inherit from this Base.
# SQLAlchemy uses it to track which classes map to which tables.
# ---------------------------------------------------------------
class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    """
    Represents a single conversation session.

    WHY THIS TABLE EXISTS:
    We need to track metadata about sessions — when they were created,
    which user owns them, what document collection they're associated with.
    Without this table, we'd have orphan messages with no context.

    Relationships:
        One user   → many sessions
        One session → many messages
    """

    __tablename__ = "chat_sessions"

    # ---------------------------------------------------------------
    # Primary key — UUID string instead of auto-increment integer.
    #
    # WHY UUID:
    # Auto-increment IDs are sequential: 1, 2, 3...
    # A malicious user can enumerate other users' sessions by guessing IDs.
    # UUIDs (e.g. "a3f8c2d1-...") are not guessable.
    # ---------------------------------------------------------------
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID primary key — not guessable unlike auto-increment"
    )

    # Which user owns this session.
    # In a real app this would be a ForeignKey to a users table.
    # We keep it simple here — just a string identifier.
    user_id = Column(
        String(255),
        nullable=False,
        index=True,     # Indexed because we frequently query "all sessions for user X"
        comment="Identifier of the user who owns this session"
    )

    # Human-readable name, set by the user or auto-generated.
    title = Column(
        String(500),
        nullable=True,
        default="New Conversation",
        comment="Human-readable session title"
    )

    # Which ChromaDB collection this session pulls documents from.
    # When a user uploads documents, they go into a named collection.
    # This field links the session to those documents for retrieval.
    collection_name = Column(
        String(255),
        nullable=True,
        comment="ChromaDB collection used for document retrieval"
    )

    # Timestamps — always include these on every table.
    # You will always want to know when rows were created and last touched.
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When the session was created (UTC)"
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="When the session was last active (UTC)"
    )

    # ---------------------------------------------------------------
    # SQLAlchemy relationship.
    # Lets you write session.messages to get all related messages
    # without writing a JOIN query manually.
    #
    # cascade="all, delete-orphan" means:
    # If you delete a ChatSession, all its ChatMessages are also deleted.
    # No orphan rows accumulate in the messages table.
    # ---------------------------------------------------------------
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id!r} user={self.user_id!r}>"


class ChatMessage(Base):
    """
    Represents a single message in a conversation.

    WHY NOT STORE MESSAGES AS JSON IN THE SESSION ROW:
    - Can't query individual messages
    - Entire array must be loaded and rewritten on every new message
    - Can't paginate long conversations efficiently
    - Concurrent writes to the same row cause conflicts

    One row per message is the correct relational design.

    message_type values:
        "human" — message sent by the user
        "ai"    — message sent by the assistant
    LangChain's SQLChatMessageHistory uses exactly these strings
    when serializing and deserializing messages.
    """

    __tablename__ = "chat_messages"

    # Auto-increment integer is fine here — messages are ordered,
    # and users never directly address a message by its ID.
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment message ID"
    )

    # ---------------------------------------------------------------
    # ForeignKey to chat_sessions.id with CASCADE delete.
    # This means:
    # - You cannot insert a message with a non-existent session_id
    # - Deleting a session automatically deletes its messages at the DB level
    #   (in addition to SQLAlchemy's cascade above — belt and suspenders)
    # ---------------------------------------------------------------
    session_id = Column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Session this message belongs to"
    )

    # "human" or "ai" — matches LangChain's message type serialization
    message_type = Column(
        String(20),
        nullable=False,
        comment="'human' for user messages, 'ai' for assistant messages"
    )

    # Use Text (unlimited length), NOT String(255).
    # AI responses routinely exceed 255 characters.
    content = Column(
        Text,
        nullable=False,
        comment="Full text content of the message"
    )

    # JSON string of source documents used to generate this AI response.
    # Example: '[{"source": "bert_paper.pdf", "page": 3, "chunk": "..."}]'
    # Powers the citation feature in the frontend.
    # Nullable because human messages have no sources.
    sources = Column(
        Text,
        nullable=True,
        comment="JSON-encoded list of source documents (AI messages only)"
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When the message was created (UTC)"
    )

    # Relationship back to the parent session
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<ChatMessage type={self.message_type!r} content={preview!r}>"


# ---------------------------------------------------------------
# Composite index for the most common query pattern:
#
#   SELECT * FROM chat_messages
#   WHERE session_id = 'xyz'
#   ORDER BY created_at
#   LIMIT 10
#
# With this index, SQLite can satisfy the WHERE + ORDER BY
# entirely from the index without touching the table rows.
# Without it, SQLite does a full table scan — fine at 1,000 rows,
# catastrophic at 1,000,000 rows.
# ---------------------------------------------------------------
Index(
    "ix_chat_messages_session_created",
    ChatMessage.session_id,
    ChatMessage.created_at
)