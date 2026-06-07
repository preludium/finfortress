"""
Strategy Session — guided 4-step financial review.

Step 1: Review      — summarise what we know from the profile
Step 2: Gaps        — identify missing/suboptimal areas
Step 3: Priorities  — rank by PLN impact
Step 4: Plan        — concrete actions with timing
"""

import logging
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FinFortress — Strategy Session",
    page_icon="🎯",
    layout="centered",
)

# ---------------------------------------------------------------------------
# LLM (cached — one instance per Streamlit process)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _get_llm():
    from langchain_openai import ChatOpenAI
    kwargs = dict(
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        temperature=0.3,
        api_key=os.getenv("OPENAI_API_KEY") or None,
    )
    if base_url := os.getenv("OPENAI_BASE_URL"):
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def _run_step(step: int, profile_block: str, results: dict) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from agent.prompts.strategy import (
        STEP1_SYSTEM, STEP1_USER,
        STEP2_SYSTEM, STEP2_USER,
        STEP3_SYSTEM, STEP3_USER,
        STEP4_SYSTEM, STEP4_USER,
    )

    systems = {1: STEP1_SYSTEM, 2: STEP2_SYSTEM, 3: STEP3_SYSTEM, 4: STEP4_SYSTEM}
    users   = {1: STEP1_USER,   2: STEP2_USER,   3: STEP3_USER,   4: STEP4_USER}

    # Truncate prior step summaries to keep prompt size manageable
    def _trim(text: str, max_chars: int = 1800) -> str:
        return text[:max_chars] + "\n…[skrócono]" if len(text) > max_chars else text

    user_msg = users[step].format(
        profile_block=profile_block,
        step1_summary=_trim(results.get(1, "")),
        step2_summary=_trim(results.get(2, "")),
        step3_summary=_trim(results.get(3, "")),
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=systems[step]),
        HumanMessage(content=user_msg),
    ])
    return response.content.strip()


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _reset():
    for key in ["strategy_step", "strategy_results"]:
        st.session_state.pop(key, None)


def _step() -> int:
    return st.session_state.get("strategy_step", 0)


def _results() -> dict:
    return st.session_state.setdefault("strategy_results", {})


def _advance():
    st.session_state["strategy_step"] = _step() + 1
    st.rerun()


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _progress_bar(current_step: int) -> None:
    from agent.prompts.strategy import STEP_TITLES, STEP_ICONS
    cols = st.columns(4)
    for i, col in enumerate(cols, start=1):
        with col:
            if i < current_step:
                st.success(f"{STEP_ICONS[i]} {STEP_TITLES[i]}", icon=None)
            elif i == current_step:
                st.info(f"{STEP_ICONS[i]} {STEP_TITLES[i]}", icon=None)
            else:
                st.caption(f"{STEP_ICONS[i]} {STEP_TITLES[i]}")


def _render_completed_step(step: int, result: str) -> None:
    from agent.prompts.strategy import STEP_TITLES, STEP_ICONS
    title = f"{STEP_ICONS[step]} Krok {step}: {STEP_TITLES[step]}"
    with st.expander(title, expanded=False):
        st.markdown(result)


def _render_active_step(step: int, profile_block: str) -> None:
    from agent.prompts.strategy import STEP_TITLES, STEP_ICONS, STEP_SPINNERS

    st.subheader(f"{STEP_ICONS[step]} Krok {step}: {STEP_TITLES[step]}")

    results = _results()

    # Run if not cached
    if step not in results:
        with st.spinner(STEP_SPINNERS[step]):
            results[step] = _run_step(step, profile_block, results)
            st.session_state["strategy_results"] = results

    st.markdown(results[step])
    st.divider()

    if step < 4:
        from agent.prompts.strategy import STEP_TITLES as T, STEP_ICONS as IC
        if st.button(f"Dalej: {IC[step+1]} {T[step+1]} →", type="primary"):
            _advance()
    else:
        st.success("Sesja strategiczna zakończona.")
        if st.button("🔄 Zacznij od nowa"):
            _reset()
            st.rerun()


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

st.title("🎯 Sesja Strategiczna")
st.caption(
    "Ustrukturyzowany przegląd Twoich finansów w 4 krokach — "
    "od diagnozy do konkretnego planu działania."
)

# Profile guard
from agent.profile import load_profile, format_profile_block, PROFILE_PATH

profile_text = load_profile()

if profile_text is None:
    st.warning(
        "**Brak profilu użytkownika.**\n\n"
        "Sesja strategiczna wymaga danych o Twojej sytuacji finansowej.\n\n"
        f"Skopiuj `data/user_profile.example.md` do `data/user_profile.md`, "
        "opisz swoją sytuację i uruchom aplikację ponownie.",
        icon="⚠️",
    )
    st.stop()

profile_block = format_profile_block(profile_text)

# Sidebar — profile preview
with st.sidebar:
    st.header("Twój profil")
    st.success("Profil załadowany")
    with st.expander("Pokaż profil"):
        st.markdown(profile_text)
    st.caption(f"`{PROFILE_PATH.relative_to(PROFILE_PATH.parent.parent)}`")

    st.divider()
    st.caption(
        "Sesja strategiczna używa tylko Twojego profilu — "
        "nie przeszukuje bazy wiedzy. Wyniki oparte na danych z profilu."
    )

# Disclaimer
with st.expander("ℹ️ Informacja prawna", expanded=False):
    from agent.prompts.strategy import STRATEGY_DISCLAIMER
    st.caption(STRATEGY_DISCLAIMER)

st.divider()

# Step 0 — landing
current = _step()

if current == 0:
    st.markdown(
        """
        Sesja przeprowadzi Cię przez 4 kroki:

        | Krok | Co robimy |
        |------|-----------|
        | 🔍 Przegląd | Podsumowujemy co wiemy z Twojego profilu |
        | ⚠️ Analiza luk | Identyfikujemy co jest suboptymalne lub brakujące |
        | 📊 Priorytety | Rankingujemy według wpływu finansowego (PLN) |
        | 🎯 Plan | Konkretne działania z terminami |

        Każdy krok jest generowany przez model językowy na podstawie Twojego profilu.
        Możesz przejrzeć wynik każdego kroku przed przejściem do kolejnego.
        """
    )
    if st.button("▶️ Rozpocznij sesję", type="primary"):
        _advance()

# Steps 1–4
else:
    _progress_bar(current)
    st.divider()

    # Completed steps (collapsed)
    for s in range(1, current):
        if s in _results():
            _render_completed_step(s, _results()[s])

    # Active step
    _render_active_step(current, profile_block)
