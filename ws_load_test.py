import asyncio
import json
import random
import string
import websockets

WS_URL = "ws://localhost:8000/ws/chat/"

NUM_CLIENTS = 5
MSGS_PER_CLIENT = 3
HEARTBEAT_TIMEOUT = 35


async def random_message():
    return ''.join(random.choices(string.ascii_letters, k=5))


async def run_client(client_id: int):
    try:
        async with websockets.connect(WS_URL) as ws:
            print(f"[Client {client_id}] Connected")

            for i in range(1, MSGS_PER_CLIENT + 1):
                msg = f"{client_id}:{await random_message()}"
                await ws.send(msg)
                print(f"[Client {client_id}] Sent: {msg}")
                reply = await ws.recv()
                print(f"[Client {client_id}] Received: {reply}")

            try:
                print(f"[Client {client_id}] Waiting for heartbeat...")
                heartbeat = await asyncio.wait_for(ws.recv(), timeout=HEARTBEAT_TIMEOUT)
                print(f"[Client {client_id}] Received heartbeat: {heartbeat}")
            except asyncio.TimeoutError:
                print(f"[Client {client_id}] No heartbeat received within timeout.")

            await ws.close()
            try:
                bye_msg = await ws.recv()
                print(f"[Client {client_id}] Bye message: {bye_msg}")
            except websockets.exceptions.ConnectionClosed:
                print(f"[Client {client_id}] Connection closed by server.")

    except Exception as e:
        print(f"[Client {client_id}] Error: {e}")


async def main():
    tasks = [run_client(i) for i in range(1, NUM_CLIENTS + 1)]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
