"""
Standalone monitor for the /tool-use websocket — no MQTT, no helper.py import.

Connects and collects every incoming message until you type 'stop' (and
press Enter) in the terminal, then prints a summary of everything received.

Usage:
    uv run python check_toolcall_ws.py
"""
import asyncio
import os
import sys
import websockets

TOOL_USE_WS = os.getenv("TOOL_USE_WS", "ws://130.149.158.133:30084/tool-use")


async def wait_for_stop(stop_event: asyncio.Event):
    loop = asyncio.get_event_loop()
    while not stop_event.is_set():
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line.strip().lower() == "stop":
            stop_event.set()


async def handle():
    messages = []
    stop_event = asyncio.Event()

    try:
        async with websockets.connect(TOOL_USE_WS) as ws:
            print(f"Connected to {TOOL_USE_WS}")
            print("Listening for tool-call messages. Type 'stop' + Enter to finish.\n")

            stop_task = asyncio.create_task(wait_for_stop(stop_event))
            recv_task = asyncio.create_task(ws.recv())

            while not stop_event.is_set():
                done, pending = await asyncio.wait(
                    {stop_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
                )

                if recv_task in done:
                    try:
                        message = recv_task.result()
                        print("Received message:", message)
                        messages.append(message)
                    except websockets.ConnectionClosed:
                        print("Connection closed by server.")
                        stop_event.set()
                        break
                    recv_task = asyncio.create_task(ws.recv())

                if stop_task in done:
                    break

            for t in (stop_task, recv_task):
                if not t.done():
                    t.cancel()

    except (ConnectionRefusedError, OSError) as exc:
        print(f"Could not connect to {TOOL_USE_WS!r}: {exc}")
        raise ConnectionError(f"Could not connect to {TOOL_USE_WS!r}: {exc}") from exc

    return messages


if __name__ == "__main__":
    collected = asyncio.run(handle())

    print("\n" + "=" * 60)
    print(f"Stopped. Received {len(collected)} message(s):")
    print("=" * 60)
    for i, msg in enumerate(collected, 1):
        print(f"[{i}] {msg}")