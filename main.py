"""Interactive CLI for the LangGraph operations supervisor."""

import argparse
import uuid

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the operations supervisor.")
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Conversation thread ID (defaults to a new ID for this run).",
    )
    args = parser.parse_args()
    thread_id = args.thread_id or str(uuid.uuid4())
    graph = build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": thread_id}}

    print(f"Operations supervisor ready (thread: {thread_id}). Type 'exit' to quit.")
    while True:
        try:
            request = input("\nYou: ").strip()
        except EOFError:
            print()
            break
        if request.lower() in {"exit", "quit"}:
            break
        if not request:
            continue

        result = graph.invoke(
            {"messages": [HumanMessage(content=request)]},
            config=config,
        )
        print(f"\nAssistant: {result['response']}")


if __name__ == "__main__":
    main()
