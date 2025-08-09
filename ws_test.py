import asyncio
import json
import websockets

WS_URL = "ws://localhost:8000/ws/chat/"

async def main():
    async with websockets.connect(WS_URL) as ws:
        # first message
        await ws.send("msg1")
        print("Sent: msg1")
        print("Received:", await ws.recv())

        # second message
        await ws.send("msg2")
        print("Sent: msg2")
        print("Received:", await ws.recv())

        print("Waiting for heartbeat...")
        msg = await ws.recv()
        print("Received:", msg)

        await ws.close()

        try:
            bye = await ws.recv()
            print("Received:", bye)
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed by server.")

if __name__ == "__main__":
    asyncio.run(main())
