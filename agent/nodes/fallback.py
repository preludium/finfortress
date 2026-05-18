from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent.state import AgentState

log = logging.getLogger(__name__)

_FALLBACK_TEMPLATE = """\
Nie znalazłem wystarczająco pewnych informacji, żeby odpowiedzieć na to pytanie.

Sprawdź bezpośrednio:
- **KNF / inwestoredukacja.pl** — pytania o IKE, IKZE, fundusze inwestycyjne
- **podatki.gov.pl** — pytania podatkowe (PIT, podatek Belki)
- **nbp.pl** — aktualne stopy procentowe (WIBOR, WIRON, stopa referencyjna)
- **obligacjeskarbowe.pl** — aktualne oprocentowanie obligacji skarbowych

Twoje pytanie: *{question}*
"""


def fallback(state: AgentState) -> dict:
    question = state["question"]
    log.info("Fallback triggered after %d rewrites", state.get("rewrite_count", 0))
    return {
        "answer":     _FALLBACK_TEMPLATE.format(question=question),
        "citations":  [],
        "confidence": "low",
        "disclaimer": None,
        "give_up":    True,
    }
