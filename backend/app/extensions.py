"""Shared singletons: SQLAlchemy engine/session factory and Supabase client."""

import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool
from supabase import Client, create_client

from .config import Config

_engine = None
_session_factory: Optional[scoped_session] = None
_supabase: Optional[Client] = None

# On serverless platforms (Vercel) every invocation may be a fresh process, so
# connection pooling only leaks connections. Open/close per request instead and
# let the Supabase pooler do the pooling.
IS_SERVERLESS = os.environ.get("VERCEL") == "1"


def get_engine():
    global _engine
    if _engine is None:
        if IS_SERVERLESS:
            _engine = create_engine(
                Config.DATABASE_URL,
                poolclass=NullPool,
                pool_pre_ping=True,
            )
        else:
            _engine = create_engine(
                Config.DATABASE_URL,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                pool_recycle=1800,
            )
    return _engine


def get_session_factory() -> scoped_session:
    global _session_factory
    if _session_factory is None:
        _session_factory = scoped_session(
            sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
        )
    return _session_factory


def get_supabase_admin() -> Client:
    """Service-role Supabase client (bypasses RLS) for admin operations
    such as disabling auth users."""
    global _supabase
    if _supabase is None:
        _supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase
