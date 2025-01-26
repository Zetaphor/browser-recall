import asyncio
import websockets
import json
from page_info import PageInfo
from datetime import datetime

async def handle_websocket(websocket, path):
    try:
        async for message in websocket:
            data = json.loads(message)
            page_info = PageInfo(
                url=data['url'],
                html=data['html'],
                timestamp=datetime.fromisoformat(data['timestamp'])
            )
            print(f"Received page content from: {page_info.url}")
            # Here you can process the page_info object as needed

    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error handling message: {e}")

async def start_server():
    server = await websockets.serve(handle_websocket, "localhost", 8765)
    print("WebSocket server started on ws://localhost:8765")
    await server.wait_closed()

def run_server():
    asyncio.run(start_server())

if __name__ == "__main__":
    run_server()