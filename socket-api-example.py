#!/usr/bin/env python3
"""
Socket.io API Example for apiUI

This script demonstrates how to connect to and interact with
your generated APIs using Socket.io for real-time communication.

Requirements:
- pip install socketio requests

Usage:
1. Replace 'your-api-id' with your actual API ID
2. Update the backend URL if needed
3. Run: python socket-api-example.py
"""

import socketio
import requests
import json
import time
import sys

class ApiUISocketClient:
    def __init__(self, api_id, backend_url="https://apiui-backend-44565368406.us-central1.run.app"):
        self.api_id = api_id
        self.backend_url = backend_url
        self.sio = socketio.Client()

        # Set up event handlers
        self.setup_event_handlers()

    def setup_event_handlers(self):
        """Set up Socket.io event handlers"""

        @self.sio.event
        def connect():
            print("✅ Connected to API socket")
            print(f"📡 Namespace: /api/{self.api_id}")

        @self.sio.event
        def disconnect():
            print("❌ Disconnected from API socket")

        @self.sio.on('chat_response')
        def on_chat_response(data):
            print("\n🤖 API Response:")
            if data['type'] == 'success':
                print(f"   {data['message']}")
            else:
                print(f"   Error: {data['message']}")
            print()  # Empty line for readability

        @self.sio.on('query_result')
        def on_query_result(data):
            print("\n📊 Query Results:")
            if data['type'] == 'success':
                print(f"   Total records: {data['total_count']}")
                print(f"   Returned records: {len(data['data'])}")

                if data['data']:
                    print("   Sample data:")
                    # Show first 2 records as formatted JSON
                    sample = data['data'][:2]
                    for i, record in enumerate(sample):
                        print(f"     Record {i+1}: {json.dumps(record, indent=8)}")
                        if i >= 1:  # Only show first 2 records
                            break

                    if len(data['data']) > 2:
                        print(f"     ... and {len(data['data']) - 2} more records")
            else:
                print(f"   Error: {data['message']}")
            print()

        @self.sio.on('stream_chunk')
        def on_stream_chunk(chunk):
            progress = chunk.get('progress', 0)
            chunk_num = chunk.get('chunk_number', 0)
            total_chunks = chunk.get('total_chunks', 0)
            records = len(chunk.get('data', []))

            print(f"📥 Streaming chunk {chunk_num + 1}/{total_chunks + 1} "
                  f"({progress:.1f}%) - {records} records")

        @self.sio.on('stream_complete')
        def on_stream_complete(data):
            print(f"\n✅ Streaming complete! Total records: {data['total_rows']}\n")

        @self.sio.on('error')
        def on_error(error):
            print(f"❌ Socket error: {error['message']}")

    def connect(self):
        """Initialize socket connection and connect"""
        try:
            # First, initialize the socket endpoint
            print(f"🔌 Initializing socket for API: {self.api_id}")
            init_url = f"{self.backend_url}/v1/apis/{self.api_id}/socket/init"
            response = requests.post(init_url)

            if response.status_code == 200:
                init_data = response.json()
                print(f"✅ Socket initialized: {init_data['message']}")
            else:
                print(f"❌ Failed to initialize socket: {response.status_code}")
                return False

            # Connect to the socket
            socket_url = f"{self.backend_url}/api/{self.api_id}"
            print(f"🔗 Connecting to: {socket_url}")
            self.sio.connect(socket_url)

            return True

        except Exception as e:
            print(f"❌ Connection failed: {str(e)}")
            return False

    def chat(self, message):
        """Send a chat message to the API"""
        print(f"💬 Sending: {message}")
        self.sio.emit('chat_message', {
            'message': message,
            'user_id': 'python-example-client',
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        })

    def query_data(self, query_params=None):
        """Send a structured data query"""
        if query_params is None:
            query_params = {'limit': 5}

        print(f"🔍 Querying data with params: {query_params}")
        self.sio.emit('query_data', {
            'query': query_params,
            'user_id': 'python-example-client'
        })

    def stream_data(self, chunk_size=50, delay=0.2):
        """Request data streaming"""
        print(f"🌊 Starting data stream (chunk_size={chunk_size}, delay={delay}s)")
        self.sio.emit('stream_data', {
            'params': {
                'chunk_size': chunk_size,
                'delay': delay
            },
            'user_id': 'python-example-client'
        })

    def disconnect(self):
        """Disconnect from the socket"""
        self.sio.disconnect()
        print("👋 Disconnected")

def main():
    # Configuration
    API_ID = "your-api-id"  # Replace with your actual API ID
    BACKEND_URL = "https://apiui-backend-44565368406.us-central1.run.app"

    if API_ID == "your-api-id":
        print("⚠️  Please update the API_ID variable with your actual API ID")
        print("   You can find your API ID in the apiUI dashboard or API docs")
        sys.exit(1)

    # Create client
    client = ApiUISocketClient(API_ID, BACKEND_URL)

    # Connect
    if not client.connect():
        sys.exit(1)

    try:
        print("\n🎯 Running example queries...\n")

        # Example 1: Chat with natural language
        print("Example 1: Natural language chat")
        client.chat("How many records are in the dataset?")
        time.sleep(2)  # Wait for response

        client.chat("What columns are available?")
        time.sleep(2)

        client.chat("Show me a sample of the data")
        time.sleep(3)

        # Example 2: Structured queries
        print("Example 2: Structured data queries")
        client.query_data({'limit': 3})
        time.sleep(2)

        # Example 3: Data streaming (commented out as it can be long)
        # print("Example 3: Data streaming")
        # client.stream_data(chunk_size=10, delay=0.5)
        # time.sleep(10)  # Wait for streaming to complete

        print("✨ Examples completed! You can now try your own queries.")
        print("💡 Type 'help' for available commands or 'quit' to exit")

        # Interactive mode
        while True:
            try:
                command = input("\n🎤 Enter a command (chat/query/stream/help/quit): ").strip()

                if command.lower() in ['quit', 'exit', 'q']:
                    break
                elif command.lower() == 'help':
                    print("""
Available commands:
- chat <message>    : Send a natural language message
- query [limit=N]   : Query data with optional limit
- stream            : Start data streaming
- help              : Show this help
- quit              : Exit the program

Examples:
- chat How many records are there?
- chat What columns do I have?
- query limit=10
- stream
                    """)
                elif command.lower().startswith('chat '):
                    message = command[5:].strip()
                    if message:
                        client.chat(message)
                    else:
                        print("❌ Please provide a message after 'chat'")
                elif command.lower().startswith('query'):
                    # Parse limit parameter
                    limit = 5  # default
                    if '=' in command:
                        try:
                            limit_str = command.split('=')[1].strip()
                            limit = int(limit_str)
                        except ValueError:
                            print("❌ Invalid limit value")

                    client.query_data({'limit': limit})
                elif command.lower() == 'stream':
                    client.stream_data()
                else:
                    print("❌ Unknown command. Type 'help' for available commands.")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {str(e)}")

    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
