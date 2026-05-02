import os
import sys
sys.stdout.reconfigure(encoding="utf-8")

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url, key = _load_credentials()
        _client = create_client(url, key)
    return _client


def _load_credentials() -> tuple[str, str]:
    # When running inside Streamlit, prefer st.secrets so the correct
    # key is used regardless of what load_dotenv() resolved.
    try:
        import streamlit as st
        return st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    except Exception:
        pass
    return os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
