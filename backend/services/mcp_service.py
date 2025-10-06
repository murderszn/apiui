import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
import aiofiles
from dataclasses import dataclass
from datetime import datetime
import mimetypes
from services.storage_service import storage_service

@dataclass
class MCPResource:
    uri: str
    mime_type: str
    name: str
    description: str
    size: int
    last_modified: str

class MCPService:
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or os.path.join(os.path.dirname(__file__), '../../uploads'))
        self.base_path.mkdir(exist_ok=True)

    def _is_safe_path(self, requested_path: str) -> bool:
        """Ensure the requested path is within the allowed directory"""
        try:
            resolved_path = (self.base_path / requested_path).resolve()
            return resolved_path.is_relative_to(self.base_path)
        except (ValueError, RuntimeError):
            return False

    def _get_file_info(self, file_path: Path) -> MCPResource:
        """Get file information for MCP resource"""
        stat = file_path.stat()
        mime_type, _ = mimetypes.guess_type(str(file_path))

        return MCPResource(
            uri=f"file://{file_path.name}",
            mime_type=mime_type or "application/octet-stream",
            name=file_path.name,
            description=f"File: {file_path.name} ({file_path.suffix})",
            size=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat()
        )

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    async def list_resources(self) -> List[MCPResource]:
        """List all available files as MCP resources"""
        resources = []

        try:
            # Get uploaded files from storage service
            uploaded_files = storage_service.list_uploaded_files()

            for file_info in uploaded_files:
                # Create MCP resource from file info
                resources.append(MCPResource(
                    uri=f"file://{file_info['name']}",
                    mime_type=self._guess_mime_type(file_info['name']),
                    name=file_info['name'],
                    description=f"File: {file_info['name']} ({file_info['storage']} storage)",
                    size=file_info['size'],
                    last_modified=file_info['last_modified']
                ))
        except Exception as e:
            print(f"Error listing resources: {e}")

        return resources

    async def read_resource(self, uri: str) -> Optional[Dict[str, Any]]:
        """Read a specific file resource"""
        try:
            # Extract filename from URI
            if not uri.startswith("file://"):
                return None

            filename = uri[7:]  # Remove "file://" prefix

            # Look for the file in storage (we need to find the full path)
            uploaded_files = storage_service.list_uploaded_files()
            file_path = None

            for file_info in uploaded_files:
                if file_info['name'] == filename:
                    file_path = file_info['path']
                    break

            if not file_path:
                return {"error": "File not found"}

            # Read file content from storage
            content = storage_service.get_upload_file(file_path)

            if content is None:
                return {"error": "File not found"}

            # Try to determine if it's text content
            try:
                text_content = content.decode('utf-8')
                return {
                    "uri": uri,
                    "mime_type": "text/plain",
                    "content": text_content,
                    "size": len(content)
                }
            except UnicodeDecodeError:
                # Binary file - return as base64 or describe it
                return {
                    "uri": uri,
                    "mime_type": "application/octet-stream",
                    "content": f"Binary file: {filename} ({len(content)} bytes)",
                    "size": len(content),
                    "is_binary": True
                }

        except Exception as e:
            return {"error": f"Error reading file: {str(e)}"}

    async def get_resource_info(self, uri: str) -> Optional[MCPResource]:
        """Get metadata for a specific resource"""
        try:
            if not uri.startswith("file://"):
                return None

            filename = uri[7:]  # Remove "file://" prefix

            if not self._is_safe_path(filename):
                return None

            file_path = self.base_path / filename

            if not file_path.exists() or not file_path.is_file():
                return None

            return self._get_file_info(file_path)

        except Exception as e:
            print(f"Error getting resource info: {e}")
            return None

    async def handle_mcp_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP protocol requests"""
        try:
            method = request_data.get("method", "")
            params = request_data.get("params", {})

            if method == "resources/list":
                resources = await self.list_resources()
                return {
                    "jsonrpc": "2.0",
                    "id": request_data.get("id"),
                    "result": {
                        "resources": [
                            {
                                "uri": r.uri,
                                "mimeType": r.mime_type,
                                "name": r.name,
                                "description": r.description,
                                "size": r.size
                            } for r in resources
                        ]
                    }
                }

            elif method == "resources/read":
                uri = params.get("uri")
                if not uri:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_data.get("id"),
                        "error": {"code": -32602, "message": "Missing uri parameter"}
                    }

                content = await self.read_resource(uri)
                if content and "error" in content:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_data.get("id"),
                        "error": {"code": -32000, "message": content["error"]}
                    }

                if content:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_data.get("id"),
                        "result": {
                            "contents": [{
                                "uri": content["uri"],
                                "mimeType": content["mime_type"],
                                "text": content["content"]
                            }]
                        }
                    }

            return {
                "jsonrpc": "2.0",
                "id": request_data.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_data.get("id", None),
                "error": {"code": -32000, "message": f"Internal error: {str(e)}"}
            }

# Create singleton instance
mcp_service = MCPService()
