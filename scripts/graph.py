"""Generate a visual diagram of the agent graph and save to /tmp/finfortress_graph.png."""

from pathlib import Path

ROOT = Path(__file__).parent.parent

import asyncio
from agent.graph import build_graph

app = asyncio.run(build_graph())
png = app.get_graph().draw_mermaid_png(max_retries=5, retry_delay=2.0)

for path in [Path("/tmp/finfortress_graph.png"), ROOT / "docs/assets/agent_graph.png"]:
    path.write_bytes(png)
    print(f"Saved: {path}")
