import json
import asyncio
import threading
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import os
from core.config import settings
from .ai_service import AIService

class SocketService:
    """
    Service for handling real-time socket communications with generated APIs.
    Provides chat-based interactions, data streaming, and real-time updates.
    """

    def __init__(self):
        self.active_connections: Dict[str, Dict[str, Any]] = {}  # job_id -> connection info
        self.chat_history: Dict[str, List[Dict[str, Any]]] = {}  # job_id -> chat messages
        self.data_cache: Dict[str, pd.DataFrame] = {}  # job_id -> cached DataFrame
        self.last_activity: Dict[str, datetime] = {}  # job_id -> last activity timestamp
        self.ai_service = AIService()  # AI service for chat responses
        self.initialized_namespaces: set = set()  # Track which namespaces have handlers
        self.jobs = {}  # Reference to jobs data from main app

    def set_jobs_reference(self, jobs_dict: Dict[str, Any]):
        """Set reference to jobs data from main application"""
        self.jobs = jobs_dict

    def initialize_job_socket(self, job_id: str, socketio_instance):
        """
        Initialize socket handlers for a specific job/API
        Note: This method is kept for compatibility but handlers are now global
        """
        # Handlers are registered globally, not per namespace
        pass

    def register_global_handlers(self, socketio_instance):
        """
        Register global socket handlers that work for any API (job_id passed in data)
        """
        @socketio_instance.on('connect')
        def handle_connect():
            print("Client connected to socket")
            # Job ID will be provided in individual messages

        @socketio_instance.on('disconnect')
        def handle_disconnect():
            print("Client disconnected from socket")

        @socketio_instance.on('chat_message')
        def handle_chat_message(data):
            try:
                job_id = data.get('job_id') or data.get('api_id')
                if not job_id:
                    socketio_instance.emit('error', {'message': 'Missing job_id or api_id in message'})
                    return

                message = data.get('message', '')
                user_id = data.get('user_id', 'anonymous')

                print(f"Chat message for job {job_id}: {message}")

                # Add user message to history
                if job_id not in self.chat_history:
                    self.chat_history[job_id] = []

                self.chat_history[job_id].append({
                    'type': 'user',
                    'message': message,
                    'timestamp': datetime.utcnow().isoformat(),
                    'user_id': user_id
                })

                # Process the message and generate response
                response = self._process_chat_message(job_id, message, user_id)

                # Send response back to client
                socketio_instance.emit('chat_response', response)

                self.last_activity[job_id] = datetime.utcnow()

            except Exception as e:
                print(f"Chat message error: {e}")
                socketio_instance.emit('error', {
                    'message': f'Error processing message: {str(e)}'
                })

        @socketio_instance.on('query_data')
        def handle_query_data(data):
            try:
                job_id = data.get('job_id') or data.get('api_id')
                if not job_id:
                    socketio_instance.emit('error', {'message': 'Missing job_id or api_id in message'})
                    return

                query_params = data.get('query', {})
                user_id = data.get('user_id', 'anonymous')

                # Process the query
                result = self._process_data_query(job_id, query_params)

                # Send result back to client
                socketio_instance.emit('query_result', result)

                self.last_activity[job_id] = datetime.utcnow()

            except Exception as e:
                socketio_instance.emit('error', {
                    'message': f'Error processing query: {str(e)}'
                })

        @socketio_instance.on('stream_data')
        def handle_stream_data(data):
            try:
                job_id = data.get('job_id') or data.get('api_id')
                if not job_id:
                    socketio_instance.emit('error', {'message': 'Missing job_id or api_id in message'})
                    return

                stream_params = data.get('params', {})
                user_id = data.get('user_id', 'anonymous')

                # Start streaming in a separate thread
                thread = threading.Thread(
                    target=self._stream_data,
                    args=(job_id, stream_params, socketio_instance)
                )
                thread.daemon = True
                thread.start()

                self.last_activity[job_id] = datetime.utcnow()

            except Exception as e:
                socketio_instance.emit('error', {
                    'message': f'Error starting data stream: {str(e)}'
                })

        @socketio_instance.on('ping')
        def handle_ping():
            socketio_instance.emit('pong')

    def _process_chat_message(self, job_id: str, message: str, user_id: str) -> Dict[str, Any]:
        """
        Process a chat message and generate appropriate response
        """
        try:
            # Load or get cached data
            df = self._get_job_data(job_id)
            if df is None or df.empty:
                return {
                    'type': 'error',
                    'message': 'No data available for this API',
                    'timestamp': datetime.utcnow().isoformat()
                }

            # Build schema information
            schema = self._build_schema_from_dataframe(df)

            # Get sample data for context
            sample_data = df.head(5).to_dict('records')

            # Debug logging
            print(f"Socket service: Processing message '{message}' for job {job_id}")
            print(f"Socket service: Schema has {len(schema.get('columns', []))} columns, {schema.get('row_count', 0)} rows")
            print(f"Socket service: Sample data has {len(sample_data) if sample_data else 0} records")

            # Use AI service for chat response
            response = asyncio.run(
                self.ai_service.chat_with_data(message, schema, sample_data)
            )

            print(f"Socket service: AI response: {response[:100]}...")

            # Add bot response to history
            if job_id not in self.chat_history:
                self.chat_history[job_id] = []

            self.chat_history[job_id].append({
                'type': 'bot',
                'message': response,
                'timestamp': datetime.utcnow().isoformat(),
                'user_id': user_id
            })

            return {
                'type': 'success',
                'message': response,
                'timestamp': datetime.utcnow().isoformat(),
                'chat_history': self.chat_history[job_id][-10:]  # Last 10 messages
            }

        except Exception as e:
            return {
                'type': 'error',
                'message': f'Error processing chat message: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            }

    def _process_data_query(self, job_id: str, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process structured data queries
        """
        try:
            df = self._get_job_data(job_id)
            if df is None or df.empty:
                return {
                    'type': 'error',
                    'message': 'No data available for this API'
                }

            result_df = df.copy()

            # Apply filters
            filters = query_params.get('filters', {})
            for column, value in filters.items():
                if column in result_df.columns and value is not None:
                    if result_df[column].dtype in ['int64', 'float64']:
                        try:
                            numeric_value = float(value)
                            result_df = result_df[result_df[column] == numeric_value]
                        except ValueError:
                            pass
                    else:
                        result_df = result_df[result_df[column].str.contains(str(value), case=False, na=False)]

            # Apply sorting
            sort_by = query_params.get('sort_by')
            sort_order = query_params.get('sort_order', 'asc')
            if sort_by and sort_by in result_df.columns:
                result_df = result_df.sort_values(sort_by, ascending=(sort_order == 'asc'))

            # Apply pagination
            limit = min(query_params.get('limit', 10), 1000)  # Max 1000 records
            offset = max(query_params.get('offset', 0), 0)

            total_count = len(result_df)
            result_df = result_df.iloc[offset:offset + limit]

            return {
                'type': 'success',
                'data': result_df.to_dict('records'),
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }

        except Exception as e:
            return {
                'type': 'error',
                'message': f'Error processing data query: {str(e)}'
            }

    def _stream_data(self, job_id: str, params: Dict[str, Any], socketio_instance):
        """
        Stream data in chunks to the client
        """
        try:
            df = self._get_job_data(job_id)
            if df is None or df.empty:
                socketio_instance.emit('stream_error', {
                    'message': 'No data available for streaming'
                }, namespace=f'/api/{job_id}')
                return

            chunk_size = min(params.get('chunk_size', 100), 1000)  # Max 1000 per chunk
            delay = max(params.get('delay', 0.1), 0.05)  # Min 50ms delay

            total_rows = len(df)
            chunks_sent = 0

            for i in range(0, total_rows, chunk_size):
                chunk = df.iloc[i:i + chunk_size]
                chunk_data = chunk.to_dict('records')

                socketio_instance.emit('stream_chunk', {
                    'data': chunk_data,
                    'chunk_number': chunks_sent,
                    'total_chunks': (total_rows + chunk_size - 1) // chunk_size,
                    'total_rows': total_rows,
                    'progress': min(100, (i + len(chunk)) / total_rows * 100)
                }, namespace=f'/api/{job_id}')

                chunks_sent += 1
                time.sleep(delay)

            # Send completion signal
            socketio_instance.emit('stream_complete', {
                'total_chunks': chunks_sent,
                'total_rows': total_rows
            }, namespace=f'/api/{job_id}')

        except Exception as e:
            socketio_instance.emit('stream_error', {
                'message': f'Error during data streaming: {str(e)}'
            }, namespace=f'/api/{job_id}')

    def _get_job_data(self, job_id: str) -> Optional[pd.DataFrame]:
        """
        Get cached data for a job, loading from file or API if necessary
        """
        # Check cache first
        if job_id in self.data_cache:
            return self.data_cache[job_id]

        # Try to load from file first (for local development)
        try:
            # Look for uploaded files with this job_id
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads')
            for filename in os.listdir(upload_dir):
                if filename.startswith(job_id):
                    file_path = os.path.join(upload_dir, filename)
                    if filename.endswith('.csv'):
                        df = pd.read_csv(file_path)
                        self.data_cache[job_id] = df
                        return df
                    elif filename.endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(file_path)
                        self.data_cache[job_id] = df
                        return df
        except Exception as e:
            print(f"Error loading local data for job {job_id}: {str(e)}")

        # If no local file found, try to fetch from Cloud Run API
        try:
            # Import requests for API calls
            import requests

            # Check if this is a Cloud Run API by looking up the API URL
            api_url = None
            for jid, job_data in self.jobs.items():  # Access jobs from main app
                if jid == job_id:
                    api_url = job_data.get('api_url')
                    break

            if not api_url:
                print(f"No API URL found for job {job_id}")
                return None

            # Fetch sample data from the Cloud Run API
            data_url = f"{api_url}/data?limit=100"  # Get up to 100 records for chat context
            print(f"[DEBUG] Fetching data from Cloud Run API: {data_url}")

            try:
                # Disable SSL verification for Cloud Run APIs (they may have certificate issues)
                print(f"[DEBUG] Making HTTP request to {data_url} (SSL verification disabled)")
                response = requests.get(data_url, timeout=30, verify=False)
                print(f"[DEBUG] Response status: {response.status_code}")
                print(f"[DEBUG] Response headers: {dict(response.headers)}")

                if response.status_code == 200:
                    print(f"[DEBUG] Response content preview: {response.text[:200]}...")
                    data = response.json()
                    print(f"[DEBUG] Parsed JSON data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")

                    if 'data' in data and data['data']:
                        print(f"[DEBUG] Found data array with {len(data['data'])} records")
                        # Convert to DataFrame
                        df = pd.DataFrame(data['data'])
                        self.data_cache[job_id] = df
                        print(f"[DEBUG] Successfully created DataFrame with {len(df)} rows and {len(df.columns)} columns")
                        print(f"[DEBUG] Column names: {list(df.columns)}")
                        return df
                    else:
                        print(f"[DEBUG] No 'data' key or empty data array in response from Cloud Run API for job {job_id}")
                        print(f"[DEBUG] Full response: {data}")
                else:
                    print(f"[DEBUG] Failed to fetch data from Cloud Run API for job {job_id}: HTTP {response.status_code}")
                    print(f"[DEBUG] Response content: {response.text[:500]}")

            except requests.exceptions.RequestException as e:
                print(f"[DEBUG] Request error fetching from Cloud Run API for job {job_id}: {str(e)}")
            except Exception as e:
                print(f"[DEBUG] General error loading data from Cloud Run API for job {job_id}: {str(e)}")
                import traceback
                print(f"[DEBUG] Full traceback: {traceback.format_exc()}")

            return None
        except Exception as e:
            print(f"Error fetching from Cloud Run API for job {job_id}: {str(e)}")
            return None

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about active socket connections
        """
        now = datetime.utcnow()
        active_count = len(self.active_connections)

        # Clean up old connections (no activity for 5 minutes)
        cutoff = now - timedelta(minutes=5)
        to_remove = []
        for job_id, info in self.active_connections.items():
            if info['last_ping'] < cutoff:
                to_remove.append(job_id)

        for job_id in to_remove:
            del self.active_connections[job_id]

        return {
            'active_connections': len(self.active_connections),
            'total_chat_sessions': len(self.chat_history),
            'cached_datasets': len(self.data_cache),
            'connections_cleaned': len(to_remove)
        }

    def cleanup_old_data(self):
        """
        Clean up old cached data and chat history
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)  # Keep data for 1 hour

        # Clean up old chat history
        to_remove = []
        for job_id, messages in self.chat_history.items():
            if messages and datetime.fromisoformat(messages[-1]['timestamp']) < cutoff:
                to_remove.append(job_id)

        for job_id in to_remove:
            del self.chat_history[job_id]

        # Clean up old data cache (less aggressively)
        cache_cutoff = now - timedelta(hours=6)
        cache_to_remove = []
        for job_id, timestamp in self.last_activity.items():
            if timestamp < cache_cutoff:
                cache_to_remove.append(job_id)

        for job_id in cache_to_remove:
            if job_id in self.data_cache:
                del self.data_cache[job_id]
            if job_id in self.last_activity:
                del self.last_activity[job_id]

    def _build_schema_from_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Build schema information from a pandas DataFrame
        """
        columns = []
        for col_name in df.columns:
            col_info = {
                'name': col_name,
                'inferred_type': self._infer_column_type(df[col_name]),
                'nullable': df[col_name].isnull().any()
            }
            columns.append(col_info)

        return {
            'row_count': len(df),
            'columns': columns
        }

    def _infer_column_type(self, series: pd.Series) -> str:
        """
        Infer the data type of a pandas Series
        """
        dtype = series.dtype

        if dtype == 'int64' or dtype == 'int32':
            return 'integer'
        elif dtype == 'float64' or dtype == 'float32':
            return 'float'
        elif dtype == 'bool':
            return 'boolean'
        elif dtype == 'object':
            # Check if it's actually a string
            if series.dropna().apply(lambda x: isinstance(x, str)).all():
                return 'string'
            else:
                return 'mixed'
        else:
            return 'string'  # Default fallback

# Global socket service instance
socket_service = SocketService()
