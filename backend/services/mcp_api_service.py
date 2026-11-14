"""
MCP API Service - Exposes generated APIs as MCP resources for chat & protocol interaction.
Reads dataset files directly from storage_service (CSV, JSON, XLSX, Parquet) with
in-memory filtering, searching, sorting, pagination, and summary statistics.
"""
import asyncio
import csv
import io
import json
import math
import os
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from core.config import settings
from services.storage_service import storage_service


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


_RESERVED_QUERY_KEYS = {
    "limit", "_limit",
    "offset", "_offset",
    "search", "_search", "q",
    "sort_by", "_sort", "sort",
    "sort_order", "_order", "order",
    "filters",
}


class MCPAPIService:
    """Service for exposing APIs as MCP resources and querying them directly"""

    def __init__(self):
        self.apis_cache: Dict[str, APIResource] = {}
        self.cache_timestamp: Optional[datetime] = None
        self.cache_ttl_seconds = 60  # Cache for 60 seconds
        self.jobs: Dict[str, Any] = {}
        self.running_apis: Dict[str, Any] = {}
        self.api_metadata: Dict[str, Any] = {}

    def set_jobs_reference(self, jobs_dict: Dict[str, Any]):
        """Set reference to jobs data from main application"""
        self.jobs = jobs_dict if jobs_dict is not None else {}

    def set_running_apis_reference(self, running_apis_dict: Dict[str, Any]):
        """Set reference to running APIs data from main application"""
        self.running_apis = running_apis_dict if running_apis_dict is not None else {}

    def set_api_metadata_reference(self, api_metadata_dict: Dict[str, Any]):
        """Set reference to API metadata from main application"""
        self.api_metadata = api_metadata_dict if api_metadata_dict is not None else {}

    def invalidate_cache(self):
        """Force cache refresh on next access"""
        self.cache_timestamp = None

    def _get_base_url(self) -> str:
        """Determine local/self-hosted gateway base URL without hardcoded Cloud Run URLs"""
        configured = getattr(settings, "api_gateway_url", None)
        if configured:
            return configured.rstrip("/")
        return "http://localhost:8000"

    def _build_endpoint_url(self, api_id: str, existing_url: Optional[str] = None) -> str:
        """Return clean self-hosted endpoint metadata URL, replacing dead *.run.app URLs"""
        base_url = self._get_base_url()
        if not existing_url or ".run.app" in existing_url:
            return f"{base_url}/api/{api_id}/data"

        clean = existing_url.split("?")[0].rstrip("/")
        if not clean.endswith("/data"):
            clean = f"{clean}/data"
        return clean

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively normalize numpy/pandas types and replace NaN/Infinity with None"""
        if value is None:
            return None

        if isinstance(value, (datetime, date, pd.Timestamp)):
            try:
                if pd.isna(value):
                    return None
            except Exception:
                pass
            return value.isoformat()

        if hasattr(value, "item") and not isinstance(value, (dict, list, str, bytes)):
            try:
                value = value.item()
            except Exception:
                pass

        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value

        if isinstance(value, (pd.Series, pd.DataFrame)):
            return self._sanitize_value(value.where(~value.isna(), None).to_dict())

        if isinstance(value, dict):
            return {str(key): self._sanitize_value(val) for key, val in value.items()}

        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]

        try:
            if pd.isna(value):  # type: ignore[arg-type]
                return None
        except Exception:
            pass

        return value

    def _should_refresh_cache(self) -> bool:
        """Check if cache should be refreshed"""
        if not self.cache_timestamp:
            return True
        age = (datetime.utcnow() - self.cache_timestamp).total_seconds()
        return age > self.cache_ttl_seconds

    def _parse_file_bytes(self, file_bytes: bytes, file_ext: str) -> List[Dict[str, Any]]:
        """Parse uploaded bytes into a list of row dicts (CSV, JSON, XLSX, XLS, Parquet, TXT)"""
        ext = (file_ext or "").lower()

        if ext in (".csv", ".txt"):
            text = file_bytes.decode("utf-8-sig", errors="replace")
            stripped = text.lstrip()
            if ext == ".txt" and (stripped.startswith("[") or stripped.startswith("{")):
                try:
                    parsed = json.loads(text)
                    return self._normalize_json_records(parsed)
                except Exception:
                    pass
            reader = csv.DictReader(io.StringIO(text))
            return self._sanitize_value([dict(row) for row in reader])

        if ext == ".json":
            parsed = json.loads(file_bytes.decode("utf-8-sig", errors="replace"))
            return self._normalize_json_records(parsed)

        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(file_bytes))
            return self._sanitize_value(df.to_dict("records"))

        if ext == ".parquet":
            df = pd.read_parquet(io.BytesIO(file_bytes))
            return self._sanitize_value(df.to_dict("records"))

        # Best-effort fallback: try JSON then CSV
        try:
            parsed = json.loads(file_bytes.decode("utf-8-sig", errors="replace"))
            return self._normalize_json_records(parsed)
        except Exception:
            text = file_bytes.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            return self._sanitize_value([dict(row) for row in reader])

    def _normalize_json_records(self, parsed: Any) -> List[Dict[str, Any]]:
        """Normalize parsed JSON payload into a list of dictionaries"""
        if isinstance(parsed, list):
            rows = [item if isinstance(item, dict) else {"value": item} for item in parsed]
            return self._sanitize_value(rows)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("data"), list):
                rows = [item if isinstance(item, dict) else {"value": item} for item in parsed["data"]]
                return self._sanitize_value(rows)
            if isinstance(parsed.get("results"), list):
                rows = [item if isinstance(item, dict) else {"value": item} for item in parsed["results"]]
                return self._sanitize_value(rows)
            return self._sanitize_value([parsed])
        return [{"value": self._sanitize_value(parsed)}]

    async def _load_rows_for_api(self, api_id: str) -> Optional[List[Dict[str, Any]]]:
        """Read and parse all rows for a job/API directly from storage_service"""
        job_data = self.jobs.get(api_id) if isinstance(self.jobs, dict) else None
        candidate_paths: List[str] = []

        if isinstance(job_data, dict):
            fp = job_data.get("file_path")
            filename = job_data.get("filename")
            if isinstance(fp, str) and fp.strip():
                candidate_paths.append(fp.strip())
            if isinstance(filename, str) and filename.strip():
                candidate_paths.append(f"uploads/{api_id}_{filename.strip()}")
                candidate_paths.append(f"uploads/{filename.strip()}")

        # Deduplicate while preserving order
        seen_paths = set()
        unique_paths = []
        for p in candidate_paths:
            if p not in seen_paths:
                seen_paths.add(p)
                unique_paths.append(p)

        for path in unique_paths:
            try:
                file_bytes = await asyncio.to_thread(storage_service.get_upload_file, path)
                if file_bytes:
                    ext = os.path.splitext(path)[1].lower()
                    if not ext and isinstance(job_data, dict) and job_data.get("filename"):
                        ext = os.path.splitext(job_data["filename"])[1].lower()
                    return self._parse_file_bytes(file_bytes, ext or ".csv")
            except Exception as e:
                print(f"[MCP API Service] Failed reading {path} for {api_id}: {e}")

        # Fallback: scan uploaded files for prefix {api_id}_
        try:
            uploaded = await asyncio.to_thread(storage_service.list_uploaded_files)
            prefix = f"{api_id}_"
            for info in uploaded:
                name = info.get("name", "")
                if name.startswith(prefix):
                    file_bytes = await asyncio.to_thread(storage_service.get_upload_file, info.get("path", name))
                    if file_bytes:
                        ext = os.path.splitext(name)[1].lower()
                        return self._parse_file_bytes(file_bytes, ext or ".csv")
        except Exception as e:
            print(f"[MCP API Service] Error scanning uploads for {api_id}: {e}")

        # Secondary fallback: generated_apis/<api_id>/data.csv or data.json
        for generated_name in ("data.csv", "data.json"):
            try:
                file_bytes = await asyncio.to_thread(
                    storage_service.get_generated_api_file_bytes, api_id, generated_name
                )
                if file_bytes:
                    ext = os.path.splitext(generated_name)[1].lower()
                    return self._parse_file_bytes(file_bytes, ext)
            except Exception as e:
                print(f"[MCP API Service] Failed reading generated {generated_name} for {api_id}: {e}")

        return None

    async def list_api_resources(self) -> List[APIResource]:
        """List all available APIs as MCP resources"""
        if not self._should_refresh_cache():
            return list(self.apis_cache.values())

        resources: List[APIResource] = []
        new_cache: Dict[str, APIResource] = {}

        # Get APIs from jobs
        for job_id, job_data in (self.jobs or {}).items():
            try:
                endpoint_url = self._build_endpoint_url(job_id, job_data.get("api_url"))
                meta = self.api_metadata.get(job_id, {})
                custom_name = meta.get("custom_name") or job_data.get("filename") or f"API {job_id[:8]}"
                summary = meta.get("summary") or f"API for {job_data.get('filename') or job_id}"

                rows = await self._load_rows_for_api(job_id)
                sample_data = rows[:5] if rows else []

                schema = self._sanitize_value(job_data.get("schema", {})) or {}
                if (not schema or not schema.get("columns")) and rows:
                    schema = self._infer_schema_from_data(rows)
                elif rows is not None and isinstance(schema, dict):
                    schema["row_count"] = len(rows)

                resource = APIResource(
                    id=job_id,
                    name=custom_name,
                    description=summary,
                    endpoint_url=endpoint_url,
                    schema=schema,
                    sample_data=sample_data,
                    created_at=job_data.get("created_at", datetime.utcnow().isoformat()),
                    status=job_data.get("status", "ready"),
                )

                resources.append(resource)
                new_cache[job_id] = resource

            except Exception as e:
                print(f"[MCP API Service] Error processing job {job_id}: {e}")
                continue

        # Get APIs from running_apis that weren't already in jobs
        for api_id, api_info in (self.running_apis or {}).items():
            if api_id in new_cache:
                continue

            try:
                endpoint_url = self._build_endpoint_url(api_id, api_info.get("api_url"))
                meta = self.api_metadata.get(api_id, {})
                custom_name = meta.get("custom_name") or f"API {api_id[:8]}"
                summary = meta.get("summary") or f"Self-hosted API {api_id[:8]}"

                rows = await self._load_rows_for_api(api_id)
                sample_data = rows[:5] if rows else []
                schema = self._sanitize_value(self._infer_schema_from_data(rows or [])) or {}

                resource = APIResource(
                    id=api_id,
                    name=custom_name,
                    description=summary,
                    endpoint_url=endpoint_url,
                    schema=schema,
                    sample_data=sample_data,
                    created_at=api_info.get("started_at", datetime.utcnow().isoformat()),
                    status="running",
                )

                resources.append(resource)
                new_cache[api_id] = resource

            except Exception as e:
                print(f"[MCP API Service] Error processing running API {api_id}: {e}")
                continue

        self.apis_cache = new_cache
        self.cache_timestamp = datetime.utcnow()
        return resources

    async def _fetch_sample_data(self, api_id_or_url: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch sample rows directly from storage without external/loopback HTTP calls"""
        api_id = api_id_or_url
        if "://" in api_id_or_url or "/" in api_id_or_url:
            parts = [p for p in api_id_or_url.split("?")[0].strip("/").split("/") if p]
            if "api" in parts:
                idx = parts.index("api")
                if idx + 1 < len(parts):
                    api_id = parts[idx + 1]
            elif "mock-api" in parts:
                idx = parts.index("mock-api")
                if idx + 1 < len(parts):
                    api_id = parts[idx + 1]

        rows = await self._load_rows_for_api(api_id)
        if rows:
            return rows[:limit]
        return []

    def _infer_schema_from_data(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Infer schema from rows"""
        if not data:
            return {"columns": [], "row_count": 0}

        columns = []
        for key in data[0].keys():
            col_type = "string"
            for row in data:
                value = row.get(key)
                if value is not None and value != "":
                    if isinstance(value, bool):
                        col_type = "boolean"
                    elif isinstance(value, int):
                        col_type = "integer"
                    elif isinstance(value, float):
                        col_type = "float"
                    else:
                        # Detect numeric strings in CSV
                        s = str(value).strip()
                        try:
                            int(s)
                            col_type = "integer"
                        except ValueError:
                            try:
                                f = float(s)
                                if math.isfinite(f):
                                    col_type = "float"
                            except ValueError:
                                if s.lower() in ("true", "false"):
                                    col_type = "boolean"
                    break

            columns.append({
                "name": key,
                "inferred_type": col_type,
                "nullable": any(row.get(key) is None or row.get(key) == "" for row in data),
            })

        return {
            "columns": columns,
            "row_count": len(data),
        }

    async def get_api_resource(self, api_id: str) -> Optional[APIResource]:
        """Get a specific API resource by ID"""
        needs_refresh = self._should_refresh_cache() or (
            api_id not in self.apis_cache
            and (api_id in (self.jobs or {}) or api_id in (self.running_apis or {}))
        )
        if needs_refresh:
            await self.list_api_resources()

        return self.apis_cache.get(api_id)

    def _values_match(self, row_val: Any, filter_val: Any) -> bool:
        """Match column values supporting case-insensitive string and numeric equality"""
        if filter_val is None:
            return row_val is None
        if row_val is None:
            return False

        if str(row_val).strip().lower() == str(filter_val).strip().lower():
            return True

        try:
            if not isinstance(row_val, bool) and not isinstance(filter_val, bool):
                return float(row_val) == float(filter_val)
        except (TypeError, ValueError):
            pass

        return False

    def _sort_key(self, value: Any) -> Tuple[int, int, Any]:
        """Type-safe sort key placing None values last and comparing numbers numerically"""
        if value is None or value == "":
            return (2, 0, "")
        if not isinstance(value, bool):
            try:
                num = float(value)
                if math.isfinite(num):
                    return (0, 0, num)
            except (TypeError, ValueError):
                pass
        return (1, 0, str(value).lower())

    def _apply_query_params(
        self,
        rows: List[Dict[str, Any]],
        query_params: Optional[Dict[str, Any]] = None,
        default_limit: int = 100,
    ) -> Dict[str, Any]:
        """Filter, search, sort, and paginate in-memory dataset rows"""
        params = dict(query_params or {})
        filtered = list(rows)

        # 1. Explicit `filters` dict + any direct column query params
        filters_dict: Dict[str, Any] = {}
        if isinstance(params.get("filters"), dict):
            filters_dict.update(params["filters"])

        for key, val in params.items():
            if key not in _RESERVED_QUERY_KEYS and val is not None and val != "":
                filters_dict[key] = val

        for col, expected in filters_dict.items():
            filtered = [r for r in filtered if col in r and self._values_match(r.get(col), expected)]

        # 2. Full-text substring search across all columns
        search = params.get("search")
        if search is None:
            search = params.get("_search")
        if search is None:
            search = params.get("q")

        if search is not None and str(search).strip() != "":
            needle = str(search).strip().lower()
            filtered = [
                r for r in filtered
                if any(needle in str(v).lower() for v in r.values() if v is not None)
            ]

        # 3. Sorting
        sort_by = params.get("sort_by") or params.get("_sort") or params.get("sort")
        sort_order = str(params.get("sort_order") or params.get("_order") or params.get("order") or "asc").lower()
        reverse = sort_order == "desc"

        if sort_by:
            # Keep None/empty values at the end regardless of direction when ascending,
            # or sort cleanly without TypeError
            non_null = [r for r in filtered if r.get(sort_by) is not None and r.get(sort_by) != ""]
            null_rows = [r for r in filtered if r.get(sort_by) is None or r.get(sort_by) == ""]
            non_null.sort(key=lambda r: self._sort_key(r.get(sort_by)), reverse=reverse)
            filtered = non_null + null_rows

        total_count = len(filtered)

        # 4. Pagination
        raw_limit = params.get("limit", params.get("_limit", default_limit))
        raw_offset = params.get("offset", params.get("_offset", 0))

        try:
            limit = max(0, int(raw_limit)) if raw_limit is not None else default_limit
        except (TypeError, ValueError):
            limit = default_limit

        try:
            offset = max(0, int(raw_offset)) if raw_offset is not None else 0
        except (TypeError, ValueError):
            offset = 0

        paginated = filtered[offset:offset + limit] if limit > 0 else []

        return {
            "data": paginated,
            "total_count": total_count,
            "returned_count": len(paginated),
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(paginated)) < total_count,
        }

    async def query_api(self, api_id: str, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query an API directly via storage_service with filtering, searching, sorting, and pagination"""
        resource = await self.get_api_resource(api_id)

        if not resource:
            return {"error": f"API {api_id} not found", "api_id": api_id}

        try:
            rows = await self._load_rows_for_api(api_id)
            if rows is None:
                return {
                    "error": f"Dataset file not found in storage for API {api_id}",
                    "api_id": api_id,
                    "api_name": resource.name,
                }

            result = self._apply_query_params(rows, query_params)
            return {
                "success": True,
                "api_id": api_id,
                "api_name": resource.name,
                "endpoint_url": resource.endpoint_url,
                **result,
                "schema": resource.schema,
            }
        except Exception as e:
            return {
                "error": f"Error querying API: {str(e)}",
                "api_id": api_id,
            }

    async def summarize_api(self, api_id: str) -> Dict[str, Any]:
        """Compute column-level summary stats for a dataset"""
        resource = await self.get_api_resource(api_id)
        if not resource:
            return {"error": f"Dataset {api_id} not found", "api_id": api_id}

        rows = await self._load_rows_for_api(api_id)
        if rows is None:
            return {
                "error": f"Dataset file not found in storage for {api_id}",
                "api_id": api_id,
                "api_name": resource.name,
                "schema": resource.schema,
            }

        row_count = len(rows)
        col_names: List[str] = []
        seen_cols = set()
        for row in rows:
            for k in row.keys():
                if k not in seen_cols:
                    seen_cols.add(k)
                    col_names.append(k)

        if not col_names and isinstance(resource.schema, dict):
            col_names = [c["name"] for c in resource.schema.get("columns", []) if c.get("name")]

        column_summaries: List[Dict[str, Any]] = []
        for col in col_names:
            non_null = [
                r.get(col) for r in rows
                if r.get(col) is not None and str(r.get(col)).strip() != ""
            ]
            null_count = row_count - len(non_null)
            unique_count = len(set(str(v) for v in non_null))

            numeric_vals: List[float] = []
            is_numeric = len(non_null) > 0
            if is_numeric:
                for v in non_null:
                    if isinstance(v, bool):
                        is_numeric = False
                        break
                    try:
                        num = float(v)
                        if not math.isfinite(num):
                            is_numeric = False
                            break
                        numeric_vals.append(num)
                    except (TypeError, ValueError):
                        is_numeric = False
                        break

            col_summary: Dict[str, Any] = {
                "name": col,
                "non_null_count": len(non_null),
                "null_count": null_count,
                "unique_count": unique_count,
            }

            if is_numeric and numeric_vals:
                total = sum(numeric_vals)
                col_summary.update({
                    "type": "numeric",
                    "min": min(numeric_vals),
                    "max": max(numeric_vals),
                    "avg": round(total / len(numeric_vals), 4),
                    "sum": round(total, 4),
                })
            else:
                counts = Counter(str(v) for v in non_null)
                col_summary.update({
                    "type": "categorical",
                    "top_values": [
                        {"value": val, "count": cnt}
                        for val, cnt in counts.most_common(5)
                    ],
                })

            column_summaries.append(col_summary)

        return {
            "success": True,
            "dataset_id": api_id,
            "name": resource.name,
            "description": resource.description,
            "row_count": row_count,
            "column_count": len(column_summaries),
            "columns": column_summaries,
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
            "successful_apis": list(results.keys()),
        }

    def format_for_chat_context(self, api_resources: List[APIResource]) -> str:
        """Format API resources as context for chat"""
        context = "Available APIs:\n\n"

        for resource in api_resources:
            context += f"API: {resource.name} (ID: {resource.id})\n"
            context += f"Description: {resource.description}\n"
            context += f"Endpoint: {resource.endpoint_url}\n"

            if resource.schema and resource.schema.get("columns"):
                context += f"Columns: {', '.join([col['name'] for col in resource.schema['columns']])}\n"

            if resource.sample_data:
                context += f"Sample records: {len(resource.sample_data)}\n"
                context += f"Example data: {json.dumps(resource.sample_data[0], indent=2)}\n"

            context += "\n"

        return context


# Global instance
mcp_api_service = MCPAPIService()
