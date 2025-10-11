"""
MCP API Service - Exposes generated APIs as MCP resources for chat interaction
This service allows AI models to discover and query all available APIs
"""
import os
import json
import math
import asyncio
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

@dataclass
class APIResource:
    """Represents an API as an MCP resource"""
    id: str
    name: str
    description: str
    endpoint_url: str
    schema: Dict[str, Any]
    sample_data: List[Dict[str, Any]]
    created_at: str
    status: str

class MCPAPIService:
    """Service for exposing APIs as MCP resources"""
    
    def __init__(self):
        self.apis_cache: Dict[str, APIResource] = {}
        self.cache_timestamp: Optional[datetime] = None
        self.cache_ttl_seconds = 60  # Cache for 60 seconds
        
    def set_jobs_reference(self, jobs_dict: Dict[str, Any]):
        """Set reference to jobs data from main application"""
        self.jobs = jobs_dict
        
    def set_running_apis_reference(self, running_apis_dict: Dict[str, Any]):
        """Set reference to running APIs data from main application"""
        self.running_apis = running_apis_dict
        
    def set_api_metadata_reference(self, api_metadata_dict: Dict[str, Any]):
        """Set reference to API metadata from main application"""
        self.api_metadata = api_metadata_dict

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively replace NaN/Infinity values with None for JSON serialization"""
        try:
            if value is None:
                return None

            # Handle pandas/numpy scalar NaN
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    return None

            # pandas uses numpy scalar types; use pd.isna to catch them
            if isinstance(value, (pd.Series, pd.DataFrame)):
                return value.where(~value.isna(), None).to_dict()

            if pd.isna(value):  # type: ignore[arg-type]
                return None
        except Exception:
            # If pd.isna fails (e.g., for dict/list), ignore and continue recursion
            pass

        if isinstance(value, dict):
            return {key: self._sanitize_value(val) for key, val in value.items()}

        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]

        return value

    def _should_refresh_cache(self) -> bool:
        """Check if cache should be refreshed"""
        if not self.cache_timestamp:
            return True
        age = (datetime.utcnow() - self.cache_timestamp).total_seconds()
        return age > self.cache_ttl_seconds
    
    async def list_api_resources(self) -> List[APIResource]:
        """List all available APIs as MCP resources"""
        if not self._should_refresh_cache():
            return list(self.apis_cache.values())

        print(f"[DEBUG] MCP API Service: jobs={len(self.jobs) if self.jobs else 0}, running_apis={len(self.running_apis) if self.running_apis else 0}")

        resources = []
        
        # Get APIs from jobs
        for job_id, job_data in self.jobs.items():
            try:
                api_url = job_data.get('api_url')
                if not api_url:
                    # Construct default URL
                    api_url = f"https://apiui-backend-44565368406.us-central1.run.app/api/{job_id}/data"
                
                # Get custom name from metadata
                custom_name = self.api_metadata.get(job_id, {}).get('custom_name', job_data.get('filename', f'API {job_id[:8]}'))
                summary = self.api_metadata.get(job_id, {}).get('summary', f"API for {job_data.get('filename', 'data')}")
                
                # Get schema
                schema = self._sanitize_value(job_data.get('schema', {})) or {}
                
                # Try to fetch sample data
                sample_data = await self._fetch_sample_data(api_url)
                
                resource = APIResource(
                    id=job_id,
                    name=custom_name,
                    description=summary,
                    endpoint_url=api_url,
                    schema=schema,
                    sample_data=sample_data,
                    created_at=job_data.get('created_at', datetime.utcnow().isoformat()),
                    status=job_data.get('status', 'ready')
                )
                
                resources.append(resource)
                self.apis_cache[job_id] = resource
                
            except Exception as e:
                print(f"Error processing job {job_id}: {e}")
                continue
        
        # Get APIs from running_apis
        for api_id, api_info in self.running_apis.items():
            if api_id in self.apis_cache:
                continue  # Already processed
            
            try:
                api_url = api_info.get('api_url')
                if not api_url:
                    continue
                
                custom_name = self.api_metadata.get(api_id, {}).get('custom_name', f'API {api_id[:8]}')
                summary = self.api_metadata.get(api_id, {}).get('summary', f"Cloud Run API")
                
                # Try to fetch schema and sample data
                sample_data = await self._fetch_sample_data(api_url)
                schema = self._sanitize_value(self._infer_schema_from_data(sample_data)) or {}
                
                resource = APIResource(
                    id=api_id,
                    name=custom_name,
                    description=summary,
                    endpoint_url=api_url,
                    schema=schema,
                    sample_data=sample_data,
                    created_at=api_info.get('started_at', datetime.utcnow().isoformat()),
                    status='running'
                )
                
                resources.append(resource)
                self.apis_cache[api_id] = resource
                
            except Exception as e:
                print(f"Error processing running API {api_id}: {e}")
                continue
        
        self.cache_timestamp = datetime.utcnow()
        return resources
    
    async def _fetch_sample_data(self, api_url: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch sample data from an API"""
        try:
            # Ensure URL ends with proper format
            if not api_url.endswith('/data'):
                if '?' in api_url:
                    api_url = api_url.split('?')[0]
                if not api_url.endswith('/data'):
                    api_url = f"{api_url}/data" if api_url.endswith('/') else f"{api_url}/data"
            
            # Add limit parameter
            separator = '&' if '?' in api_url else '?'
            fetch_url = f"{api_url}{separator}limit={limit}"
            
            print(f"[MCP API Service] Fetching sample data from: {fetch_url}")
            
            # Make request with timeout
            response = requests.get(fetch_url, timeout=10, verify=False)
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle different response formats
                if isinstance(data, dict):
                    if 'data' in data:
                        sample = data['data'][:limit] if isinstance(data['data'], list) else []
                        print(f"[MCP API Service] Fetched {len(sample)} records")
                        return self._sanitize_value(sample)
                    elif 'results' in data:
                        sample = data['results'][:limit] if isinstance(data['results'], list) else []
                        print(f"[MCP API Service] Fetched {len(sample)} records")
                        return self._sanitize_value(sample)
                elif isinstance(data, list):
                    sample = data[:limit]
                    print(f"[MCP API Service] Fetched {len(sample)} records")
                    return self._sanitize_value(sample)
            
            print(f"[MCP API Service] Failed to fetch data: HTTP {response.status_code}")
            return []
            
        except Exception as e:
            print(f"[MCP API Service] Error fetching sample data from {api_url}: {e}")
            return []
    
    def _infer_schema_from_data(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Infer schema from sample data"""
        if not data:
            return {"columns": [], "row_count": 0}
        
        columns = []
        for key in data[0].keys():
            # Infer type from first non-null value
            col_type = "string"
            for row in data:
                value = row.get(key)
                if value is not None:
                    if isinstance(value, bool):
                        col_type = "boolean"
                    elif isinstance(value, int):
                        col_type = "integer"
                    elif isinstance(value, float):
                        col_type = "float"
                    break
            
            columns.append({
                "name": key,
                "inferred_type": col_type,
                "nullable": any(row.get(key) is None for row in data)
            })
        
        return {
            "columns": columns,
            "row_count": len(data)
        }
    
    async def get_api_resource(self, api_id: str) -> Optional[APIResource]:
        """Get a specific API resource by ID"""
        # Refresh cache if needed
        if self._should_refresh_cache():
            await self.list_api_resources()
        
        return self.apis_cache.get(api_id)
    
    async def query_api(self, api_id: str, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query an API and return results"""
        resource = await self.get_api_resource(api_id)
        
        if not resource:
            return {"error": f"API {api_id} not found"}
        
        try:
            # Build query URL
            url = resource.endpoint_url
            
            if query_params:
                # Add query parameters
                params = []
                for key, value in query_params.items():
                    params.append(f"{key}={value}")
                
                separator = '&' if '?' in url else '?'
                url = f"{url}{separator}{'&'.join(params)}"
            
            print(f"[MCP API Service] Querying {url}")
            
            # Make request
            response = requests.get(url, timeout=30, verify=False)
            
            if response.status_code == 200:
                data = response.json()
                
                # Normalize response format
                if isinstance(data, dict) and 'data' in data:
                    return {
                        "success": True,
                        "api_id": api_id,
                        "api_name": resource.name,
                        "data": data['data'],
                        "total_count": data.get('total_count', len(data.get('data', []))),
                        "schema": resource.schema
                    }
                elif isinstance(data, list):
                    return {
                        "success": True,
                        "api_id": api_id,
                        "api_name": resource.name,
                        "data": data,
                        "total_count": len(data),
                        "schema": resource.schema
                    }
                else:
                    return {
                        "success": True,
                        "api_id": api_id,
                        "api_name": resource.name,
                        "data": data,
                        "schema": resource.schema
                    }
            else:
                return {
                    "error": f"API returned HTTP {response.status_code}",
                    "api_id": api_id
                }
                
        except Exception as e:
            return {
                "error": f"Error querying API: {str(e)}",
                "api_id": api_id
            }
    
    async def query_multiple_apis(self, api_ids: List[str], query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query multiple APIs and combine results"""
        results = {}
        errors = []
        
        for api_id in api_ids:
            try:
                result = await self.query_api(api_id, query_params)
                if "error" in result:
                    errors.append(f"{api_id}: {result['error']}")
                else:
                    results[api_id] = result
            except Exception as e:
                errors.append(f"{api_id}: {str(e)}")
        
        return {
            "success": len(results) > 0,
            "results": results,
            "errors": errors if errors else None,
            "queried_apis": api_ids,
            "successful_apis": list(results.keys())
        }
    
    def format_for_chat_context(self, api_resources: List[APIResource]) -> str:
        """Format API resources as context for chat"""
        context = "Available APIs:\n\n"
        
        for resource in api_resources:
            context += f"API: {resource.name} (ID: {resource.id})\n"
            context += f"Description: {resource.description}\n"
            context += f"Endpoint: {resource.endpoint_url}\n"
            
            if resource.schema and resource.schema.get('columns'):
                context += f"Columns: {', '.join([col['name'] for col in resource.schema['columns']])}\n"
            
            if resource.sample_data:
                context += f"Sample records: {len(resource.sample_data)}\n"
                context += f"Example data: {json.dumps(resource.sample_data[0], indent=2)}\n"
            
            context += "\n"
        
        return context

# Global instance
mcp_api_service = MCPAPIService()
