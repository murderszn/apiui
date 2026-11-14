"""
Spec-compliant MCP (Model Context Protocol) JSON-RPC 2.0 Server for ApiUi.

Supports:
- Streamable HTTP transport: POST /mcp, GET /mcp, DELETE /mcp
- HTTP+SSE transport: GET /mcp/sse, POST /mcp/messages
- Client configuration endpoint: GET /mcp/client-config
"""
import asyncio
import inspect
import json
import queue
import threading
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Response, jsonify, request, stream_with_context

from core.config import settings
from services.mcp_api_service import mcp_api_service
from services.mcp_service import mcp_service

SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL_VERSION = "2025-03-26"

SERVER_INFO = {
    "name": "apiui-mcp",
    "version": "2.0.0",
}

SERVER_CAPABILITIES = {
    "resources": {"listChanged": False},
    "tools": {"listChanged": False},
    "prompts": {"listChanged": False},
}

TOOLS_DEFINITION: List[Dict[str, Any]] = [
    {
        "name": "list_datasets",
        "description": "List all hosted datasets and APIs with ID, name, description, row count, and columns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_dataset_schema",
        "description": "Return detailed schema (columns, types, nullability, row count) and sample rows for a dataset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "The ID of the hosted dataset / API.",
                }
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "query_dataset",
        "description": "Query a dataset with optional column filters, substring search, sorting, and pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "The ID of the hosted dataset / API.",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional dictionary of column -> expected value filters.",
                    "additionalProperties": True,
                },
                "search": {
                    "type": "string",
                    "description": "Optional case-insensitive substring search across all columns.",
                },
                "sort_by": {
                    "type": "string",
                    "description": "Optional column name to sort results by.",
                },
                "sort_order": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "default": "asc",
                    "description": "Sort direction ('asc' or 'desc').",
                },
                "limit": {
                    "type": "integer",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum number of rows to return (default 25).",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Number of rows to skip for pagination (default 0).",
                },
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "summarize_dataset",
        "description": "Compute column-level summary statistics (row count, numeric min/max/avg, null counts, and top values for categorical columns) for a dataset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "The ID of the hosted dataset / API.",
                }
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    },
]

PROMPTS_DEFINITION: List[Dict[str, Any]] = [
    {
        "name": "analyze_dataset",
        "description": "Analyze a hosted ApiUi dataset using its schema and sample rows.",
        "arguments": [
            {
                "name": "dataset_id",
                "description": "The ID of the dataset to analyze.",
                "required": True,
            }
        ],
    }
]


def _jsonrpc_result(req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _tool_text_result(payload: Any, is_error: bool = False) -> Dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _resolve_server_base_url() -> str:
    """Determine the external/self-hosted base URL for client config generation."""
    configured = getattr(settings, "api_gateway_url", None)
    if configured:
        return configured.rstrip("/")

    forwarded_host = request.headers.get("X-Forwarded-Host")
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    if forwarded_host:
        scheme = (forwarded_proto or request.scheme or "http").split(",")[0].strip()
        host = forwarded_host.split(",")[0].strip()
        return f"{scheme}://{host}".rstrip("/")

    if request.host_url:
        return request.host_url.rstrip("/")

    return "http://localhost:8000"


def register_mcp_routes(app, load_persistent_data: Optional[Callable] = None):
    """Register spec-compliant MCP JSON-RPC 2.0 transports and config routes on Flask app."""

    sessions_lock = threading.Lock()
    sse_sessions: Dict[str, queue.Queue] = {}
    streamable_sessions: Dict[str, Dict[str, Any]] = {}

    async def ensure_data_loaded():
        if load_persistent_data is None:
            return
        if inspect.iscoroutinefunction(load_persistent_data):
            await load_persistent_data()
        else:
            res = load_persistent_data()
            if inspect.isawaitable(res):
                await res

    async def handle_single_rpc(
        payload: Any,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Dispatch a single JSON-RPC 2.0 request or notification."""
        if not isinstance(payload, dict):
            return _jsonrpc_error(None, -32600, "Invalid Request: expected JSON object"), session_id

        if payload.get("jsonrpc") != "2.0":
            return _jsonrpc_error(payload.get("id"), -32600, "Invalid Request: jsonrpc must be '2.0'"), session_id

        method = payload.get("method")
        if not isinstance(method, str) or not method:
            return _jsonrpc_error(payload.get("id"), -32600, "Invalid Request: missing method"), session_id

        has_id = "id" in payload and payload.get("id") is not None
        req_id = payload.get("id")
        params = payload.get("params")
        if params is None:
            params = {}
        elif not isinstance(params, dict):
            return _jsonrpc_error(req_id, -32602, "Invalid params: expected object"), session_id

        try:
            # 1. Lifecycle: initialize
            if method == "initialize":
                requested_version = params.get("protocolVersion")
                negotiated = (
                    requested_version
                    if requested_version in SUPPORTED_PROTOCOL_VERSIONS
                    else DEFAULT_PROTOCOL_VERSION
                )
                new_session_id = session_id or uuid.uuid4().hex
                with sessions_lock:
                    streamable_sessions[new_session_id] = {
                        "created_at": datetime.utcnow().isoformat(),
                        "protocol_version": negotiated,
                        "client_info": params.get("clientInfo", {}),
                        "queue": queue.Queue(),
                    }
                result = {
                    "protocolVersion": negotiated,
                    "serverInfo": SERVER_INFO,
                    "capabilities": SERVER_CAPABILITIES,
                }
                return _jsonrpc_result(req_id, result), new_session_id

            # 2. Notifications
            if method.startswith("notifications/"):
                if has_id:
                    return _jsonrpc_result(req_id, {}), session_id
                return None, session_id

            # 3. Ping
            if method == "ping":
                return _jsonrpc_result(req_id, {}), session_id

            # 4. Resources: resources/list
            if method == "resources/list":
                await ensure_data_loaded()
                file_resources = await mcp_service.list_resources()
                api_resources = await mcp_api_service.list_api_resources()

                combined: List[Dict[str, Any]] = []
                for r in file_resources:
                    combined.append({
                        "uri": r.uri,
                        "name": r.name,
                        "description": r.description,
                        "mimeType": r.mime_type,
                    })

                for api in api_resources:
                    combined.append({
                        "uri": f"apiui://dataset/{api.id}",
                        "name": api.name,
                        "description": f"{api.description} (endpoint: {api.endpoint_url})",
                        "mimeType": "application/json",
                    })

                return _jsonrpc_result(req_id, {"resources": combined}), session_id

            # 5. Resources: resources/read
            if method == "resources/read":
                uri = params.get("uri")
                if not uri or not isinstance(uri, str):
                    return _jsonrpc_error(req_id, -32602, "Missing or invalid 'uri' parameter"), session_id

                if uri.startswith("file://"):
                    content = await mcp_service.read_resource(uri)
                    if not content or "error" in content:
                        msg = (content or {}).get("error", f"Resource not found: {uri}")
                        return _jsonrpc_error(req_id, -32002, msg), session_id
                    return _jsonrpc_result(
                        req_id,
                        {
                            "contents": [{
                                "uri": content["uri"],
                                "mimeType": content["mime_type"],
                                "text": content["content"],
                            }]
                        },
                    ), session_id

                if uri.startswith("apiui://dataset/"):
                    dataset_id = uri[len("apiui://dataset/"):].strip()
                    if not dataset_id:
                        return _jsonrpc_error(req_id, -32602, "Missing dataset ID in URI"), session_id

                    await ensure_data_loaded()
                    resource = await mcp_api_service.get_api_resource(dataset_id)
                    if not resource:
                        return _jsonrpc_error(req_id, -32002, f"Dataset not found: {dataset_id}"), session_id

                    payload_obj = {
                        "id": resource.id,
                        "name": resource.name,
                        "description": resource.description,
                        "endpoint_url": resource.endpoint_url,
                        "status": resource.status,
                        "created_at": resource.created_at,
                        "schema": resource.schema,
                        "sample_data": resource.sample_data,
                    }
                    return _jsonrpc_result(
                        req_id,
                        {
                            "contents": [{
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(payload_obj, indent=2, default=str),
                            }]
                        },
                    ), session_id

                return _jsonrpc_error(req_id, -32602, f"Unsupported resource URI scheme: {uri}"), session_id

            # 6. Tools: tools/list
            if method == "tools/list":
                return _jsonrpc_result(req_id, {"tools": TOOLS_DEFINITION}), session_id

            # 7. Tools: tools/call
            if method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments") or {}
                if not tool_name or not isinstance(tool_name, str):
                    return _jsonrpc_error(req_id, -32602, "Missing or invalid tool 'name'"), session_id
                if not isinstance(arguments, dict):
                    return _jsonrpc_error(req_id, -32602, "Invalid tool 'arguments': expected object"), session_id

                valid_names = {t["name"] for t in TOOLS_DEFINITION}
                if tool_name not in valid_names:
                    return _jsonrpc_error(req_id, -32602, f"Unknown tool: {tool_name}"), session_id

                await ensure_data_loaded()

                if tool_name == "list_datasets":
                    resources = await mcp_api_service.list_api_resources()
                    datasets = []
                    for r in resources:
                        schema = r.schema or {}
                        cols = [
                            {"name": c.get("name"), "type": c.get("inferred_type") or c.get("type", "string")}
                            for c in (schema.get("columns") or [])
                            if c.get("name")
                        ]
                        datasets.append({
                            "id": r.id,
                            "name": r.name,
                            "description": r.description,
                            "status": r.status,
                            "endpoint_url": r.endpoint_url,
                            "row_count": schema.get("row_count", len(r.sample_data or [])),
                            "columns": cols,
                        })
                    return _jsonrpc_result(
                        req_id,
                        _tool_text_result({"datasets": datasets, "total": len(datasets)}),
                    ), session_id

                dataset_id = arguments.get("dataset_id")
                if not dataset_id or not isinstance(dataset_id, str):
                    return _jsonrpc_error(req_id, -32602, "Missing required argument: 'dataset_id'"), session_id

                if tool_name == "get_dataset_schema":
                    resource = await mcp_api_service.get_api_resource(dataset_id)
                    if not resource:
                        return _jsonrpc_result(
                            req_id,
                            _tool_text_result({"error": f"Dataset '{dataset_id}' not found"}, is_error=True),
                        ), session_id
                    return _jsonrpc_result(
                        req_id,
                        _tool_text_result({
                            "id": resource.id,
                            "name": resource.name,
                            "description": resource.description,
                            "endpoint_url": resource.endpoint_url,
                            "status": resource.status,
                            "schema": resource.schema,
                            "sample_data": resource.sample_data,
                        }),
                    ), session_id

                if tool_name == "query_dataset":
                    query_params: Dict[str, Any] = {
                        "limit": arguments.get("limit", 25),
                        "offset": arguments.get("offset", 0),
                    }
                    if arguments.get("filters") is not None:
                        query_params["filters"] = arguments["filters"]
                    if arguments.get("search") is not None:
                        query_params["search"] = arguments["search"]
                    if arguments.get("sort_by") is not None:
                        query_params["sort_by"] = arguments["sort_by"]
                    if arguments.get("sort_order") is not None:
                        query_params["sort_order"] = arguments["sort_order"]

                    result = await mcp_api_service.query_api(dataset_id, query_params)
                    is_err = "error" in result
                    return _jsonrpc_result(
                        req_id,
                        _tool_text_result(result, is_error=is_err),
                    ), session_id

                if tool_name == "summarize_dataset":
                    summary = await mcp_api_service.summarize_api(dataset_id)
                    is_err = "error" in summary
                    return _jsonrpc_result(
                        req_id,
                        _tool_text_result(summary, is_error=is_err),
                    ), session_id

            # 8. Prompts: prompts/list
            if method == "prompts/list":
                return _jsonrpc_result(req_id, {"prompts": PROMPTS_DEFINITION}), session_id

            # 9. Prompts: prompts/get
            if method == "prompts/get":
                prompt_name = params.get("name")
                arguments = params.get("arguments") or {}
                if prompt_name != "analyze_dataset":
                    return _jsonrpc_error(req_id, -32602, f"Unknown prompt: {prompt_name}"), session_id

                dataset_id = arguments.get("dataset_id") if isinstance(arguments, dict) else None
                if not dataset_id or not isinstance(dataset_id, str):
                    return _jsonrpc_error(req_id, -32602, "Missing required prompt argument: 'dataset_id'"), session_id

                await ensure_data_loaded()
                resource = await mcp_api_service.get_api_resource(dataset_id)
                if not resource:
                    return _jsonrpc_error(req_id, -32002, f"Dataset not found: {dataset_id}"), session_id

                prompt_text = (
                    f"Please analyze the following ApiUi dataset and summarize key patterns, "
                    f"data quality observations, and interesting insights.\n\n"
                    f"Dataset Name: {resource.name}\n"
                    f"Dataset ID: {resource.id}\n"
                    f"Description: {resource.description}\n"
                    f"Endpoint URL: {resource.endpoint_url}\n\n"
                    f"Schema:\n{json.dumps(resource.schema, indent=2, default=str)}\n\n"
                    f"Sample Rows:\n{json.dumps(resource.sample_data, indent=2, default=str)}\n"
                )
                return _jsonrpc_result(
                    req_id,
                    {
                        "description": f"Analyze dataset {resource.name} ({resource.id})",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": prompt_text,
                                },
                            }
                        ],
                    },
                ), session_id

            return _jsonrpc_error(req_id, -32601, f"Method not found: {method}"), session_id

        except Exception as e:
            return _jsonrpc_error(req_id, -32603, f"Internal error: {str(e)}"), session_id

    async def process_rpc_body(
        body: Any,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[Any], Optional[str]]:
        """Process either a single JSON-RPC object or a JSON-RPC batch array."""
        if isinstance(body, list):
            if not body:
                return _jsonrpc_error(None, -32600, "Invalid Request: empty batch"), session_id
            responses: List[Dict[str, Any]] = []
            current_session = session_id
            for item in body:
                resp, current_session = await handle_single_rpc(item, current_session)
                if resp is not None:
                    responses.append(resp)
            return (responses if responses else None), current_session

        return await handle_single_rpc(body, session_id)

    # ------------------------------------------------------------------
    # Streamable HTTP Transport: POST /mcp, GET /mcp, DELETE /mcp
    # ------------------------------------------------------------------
    @app.route("/mcp", methods=["GET", "POST", "DELETE"])
    def mcp_streamable_endpoint():
        if request.method == "DELETE":
            sid = request.headers.get("Mcp-Session-Id")
            if sid:
                with sessions_lock:
                    streamable_sessions.pop(sid, None)
            return Response("", status=204)

        if request.method == "GET":
            accept = request.headers.get("Accept", "")
            wants_sse = (
                "text/event-stream" in accept
                and "application/json" not in accept
            ) or request.args.get("stream") == "1"

            if wants_sse:
                sid = request.headers.get("Mcp-Session-Id") or uuid.uuid4().hex
                with sessions_lock:
                    session_entry = streamable_sessions.get(sid)
                    if not session_entry:
                        session_entry = {
                            "created_at": datetime.utcnow().isoformat(),
                            "protocol_version": DEFAULT_PROTOCOL_VERSION,
                            "queue": queue.Queue(),
                        }
                        streamable_sessions[sid] = session_entry
                    q: queue.Queue = session_entry["queue"]

                def event_stream():
                    yield f": connected {sid}\n\n"
                    try:
                        while True:
                            try:
                                msg = q.get(timeout=15)
                                if msg is None:
                                    break
                                yield f"event: message\ndata: {msg}\n\n"
                            except queue.Empty:
                                yield ": keepalive\n\n"
                    except GeneratorExit:
                        pass

                resp = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
                resp.headers["Cache-Control"] = "no-cache"
                resp.headers["Connection"] = "keep-alive"
                resp.headers["X-Accel-Buffering"] = "no"
                resp.headers["Mcp-Session-Id"] = sid
                resp.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"
                return resp

            base_url = _resolve_server_base_url()
            return jsonify({
                "name": SERVER_INFO["name"],
                "version": SERVER_INFO["version"],
                "protocol": "mcp",
                "protocolVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "capabilities": SERVER_CAPABILITIES,
                "transports": {
                    "streamable_http": f"{base_url}/mcp",
                    "sse": f"{base_url}/mcp/sse",
                    "messages": f"{base_url}/mcp/messages",
                },
                "client_config": f"{base_url}/mcp/client-config",
            })

        # POST /mcp
        raw_body = request.get_data(as_text=True)
        try:
            body = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError as e:
            err = _jsonrpc_error(None, -32700, f"Parse error: {str(e)}")
            return Response(json.dumps(err), status=400, mimetype="application/json")

        if body is None:
            err = _jsonrpc_error(None, -32600, "Invalid Request: empty body")
            return Response(json.dumps(err), status=400, mimetype="application/json")

        incoming_sid = request.headers.get("Mcp-Session-Id")
        rpc_response, active_sid = asyncio.run(process_rpc_body(body, incoming_sid))

        headers: Dict[str, str] = {
            "Access-Control-Expose-Headers": "Mcp-Session-Id",
        }
        if active_sid:
            headers["Mcp-Session-Id"] = active_sid

        # Notifications return 202 Accepted with empty body per Streamable HTTP spec
        if rpc_response is None:
            return Response("", status=202, headers=headers)

        accept = request.headers.get("Accept", "")
        prefers_sse_only = "text/event-stream" in accept and "application/json" not in accept
        serialized = json.dumps(rpc_response, default=str)

        if prefers_sse_only:
            sse_payload = f"event: message\ndata: {serialized}\n\n"
            return Response(sse_payload, status=200, mimetype="text/event-stream", headers=headers)

        return Response(serialized, status=200, mimetype="application/json", headers=headers)

    # ------------------------------------------------------------------
    # HTTP+SSE Transport: GET /mcp/sse and POST /mcp/messages
    # ------------------------------------------------------------------
    @app.route("/mcp/sse", methods=["GET"])
    def mcp_sse_endpoint():
        session_id = uuid.uuid4().hex
        msg_queue: queue.Queue = queue.Queue()
        with sessions_lock:
            sse_sessions[session_id] = msg_queue

        def sse_stream():
            try:
                yield f"event: endpoint\ndata: /mcp/messages?sessionId={session_id}\n\n"
                while True:
                    try:
                        data = msg_queue.get(timeout=15)
                        if data is None:
                            break
                        yield f"event: message\ndata: {data}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            except GeneratorExit:
                pass
            finally:
                with sessions_lock:
                    sse_sessions.pop(session_id, None)

        resp = Response(stream_with_context(sse_stream()), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Connection"] = "keep-alive"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.route("/mcp/messages", methods=["POST"])
    def mcp_messages_endpoint():
        session_id = request.args.get("sessionId") or request.args.get("session_id")
        raw_body = request.get_data(as_text=True)

        try:
            body = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError as e:
            err = _jsonrpc_error(None, -32700, f"Parse error: {str(e)}")
            return Response(json.dumps(err), status=400, mimetype="application/json")

        if body is None:
            err = _jsonrpc_error(None, -32600, "Invalid Request: empty body")
            return Response(json.dumps(err), status=400, mimetype="application/json")

        target_queue: Optional[queue.Queue] = None
        if session_id:
            with sessions_lock:
                target_queue = sse_sessions.get(session_id)
            if target_queue is None:
                return jsonify({"error": f"Unknown SSE sessionId: {session_id}"}), 404

        rpc_response, _ = asyncio.run(process_rpc_body(body, session_id))

        if target_queue is not None:
            if rpc_response is not None:
                target_queue.put(json.dumps(rpc_response, default=str))
            return Response("Accepted", status=202, mimetype="text/plain")

        # Direct fallback when called without an SSE sessionId
        if rpc_response is None:
            return Response("", status=202)
        return Response(json.dumps(rpc_response, default=str), status=200, mimetype="application/json")

    # ------------------------------------------------------------------
    # Client Config Endpoint: GET /mcp/client-config
    # ------------------------------------------------------------------
    @app.route("/mcp/client-config", methods=["GET"])
    def mcp_client_config_endpoint():
        base_url = _resolve_server_base_url()
        streamable_url = f"{base_url}/mcp"
        sse_url = f"{base_url}/mcp/sse"

        return jsonify({
            "server": SERVER_INFO,
            "base_url": base_url,
            "endpoints": {
                "streamable_http": streamable_url,
                "sse": sse_url,
                "messages": f"{base_url}/mcp/messages",
            },
            "mcpServers": {
                "apiui": {
                    "url": streamable_url,
                    "transport": "streamable-http",
                }
            },
            "clients": {
                "claude_desktop": {
                    "config_path": "~/Library/Application Support/Claude/claude_desktop_config.json",
                    "config": {
                        "mcpServers": {
                            "apiui": {
                                "command": "npx",
                                "args": ["-y", "mcp-remote", streamable_url],
                            }
                        }
                    },
                },
                "cursor": {
                    "config_path": "~/.cursor/mcp.json",
                    "config": {
                        "mcpServers": {
                            "apiui": {
                                "url": streamable_url,
                            }
                        }
                    },
                    "sse_fallback_config": {
                        "mcpServers": {
                            "apiui": {
                                "url": sse_url,
                            }
                        }
                    },
                },
                "antigravity": {
                    "config_path": "~/.gemini/antigravity/mcp_config.json",
                    "config": {
                        "mcpServers": {
                            "apiui": {
                                "serverUrl": streamable_url,
                            }
                        }
                    },
                },
            },
        })
