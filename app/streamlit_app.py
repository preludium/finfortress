import logging
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FinFortress — Polski asystent finansowy",
    page_icon="🏦",
    layout="centered",
)


st.title("🏦 FinFortress")
st.caption("Asystent finansowy oparty na polskich źródłach — IKE, IKZE, obligacje, kredyty, podatki")

# ---------------------------------------------------------------------------
# Agent — loaded once, cached across reruns
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Ładowanie modelu i indeksu…")
def load_agent():
    from agent.graph import build_graph
    return build_graph()


app = load_agent()

# ---------------------------------------------------------------------------
# Sidebar — user profile
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Twój profil")

    from agent.profile import load_profile, PROFILE_PATH
    profile_text = load_profile()

    if profile_text is None:
        st.info(
            "Brak profilu — odpowiedzi są ogólne.\n\n"
            "Skopiuj `data/user_profile.example.md` jako `data/user_profile.md` "
            "i opisz swoją sytuację finansową. Uruchom aplikację ponownie."
        )
    else:
        st.success("Profil wczytany")
        with st.expander("Pokaż profil"):
            st.markdown(profile_text)
        st.caption(f"`{PROFILE_PATH.relative_to(PROFILE_PATH.parent.parent)}`")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_citations(citations: list[dict]) -> None:
    if not citations:
        return
    with st.expander(f"Źródła ({len(citations)})"):
        for cite in citations:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"**{cite['source']}** — {cite['author']} ({cite['date']})")
                if cite.get("title"):
                    st.caption(f"_{cite['title']}_")
            with col2:
                if cite.get("url") and cite["url"].startswith("http"):
                    st.markdown(f"[Otwórz ↗]({cite['url']})")


def _confidence_badge(confidence: str) -> str:
    return {"high": "🟢 wysoka", "medium": "🟡 średnia", "low": "🔴 niska"}.get(confidence, confidence)


# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            _render_citations(msg["citations"])
        if msg.get("disclaimer"):
            st.warning(msg["disclaimer"])
        if msg.get("meta"):
            st.caption(msg["meta"])


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if question := st.chat_input("Zadaj pytanie o polskie finanse osobiste…"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Szukam odpowiedzi…"):
            from agent.state import INITIAL_STATE
            result = app.invoke({**INITIAL_STATE, "question": question})

        answer     = result.get("answer", "")
        citations  = result.get("citations") or []
        confidence = result.get("confidence", "low")
        disclaimer = result.get("disclaimer")
        avg_grade  = result.get("avg_grade", 0.0)
        rewrites   = result.get("rewrite_count", 0)
        give_up    = result.get("give_up", False)

        st.markdown(answer)
        _render_citations(citations)

        if disclaimer:
            st.warning(disclaimer)

        meta_parts = [f"Pewność: {_confidence_badge(confidence)}", f"Ocena: {avg_grade:.2f}"]
        if rewrites:
            meta_parts.append(f"Przepisania zapytania: {rewrites}")
        if give_up:
            meta_parts.append("⚠️ Nie znaleziono wystarczających danych")
        st.caption(" · ".join(meta_parts))

    st.session_state.messages.append({
        "role":       "assistant",
        "content":    answer,
        "citations":  citations,
        "disclaimer": disclaimer,
        "meta":       " · ".join(meta_parts),
    })
