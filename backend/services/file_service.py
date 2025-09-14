import polars as pl
import json
from typing import Dict, Any, List
from io import BytesIO
import aiofiles
from pathlib import Path
import tempfile

class FileService:
    def __init__(self):
        self.supported_extensions = ['.csv', '.json', '.xlsx', '.parquet']

    async def process_file(self, file, job_id: str) -> Dict[str, Any]:
        """
        Process uploaded file and extract schema information
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as temp_file:
                # Read file content
                content = await file.read()
                temp_file.write(content)
                temp_file_path = temp_file.name

            # Determine file type and process accordingly
            file_extension = Path(file.filename).suffix.lower()

            if file_extension == '.csv':
                schema, sample_data = await self._process_csv(temp_file_path)
            elif file_extension == '.json':
                schema, sample_data = await self._process_json(temp_file_path)
            elif file_extension == '.xlsx':
                schema, sample_data = await self._process_excel(temp_file_path)
            elif file_extension == '.parquet':
                schema, sample_data = await self._process_parquet(temp_file_path)
            else:
                return {"success": False, "error": f"Unsupported file type: {file_extension}"}

            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

            return {
                "success": True,
                "schema": schema,
                "sample_data": sample_data,
                "file_path": temp_file_path
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _process_csv(self, file_path: str) -> tuple:
        """Process CSV file and extract schema"""
        try:
            # Use polars for CSV processing
            df = pl.read_csv(file_path, n_rows=100)  # Read first 100 rows for schema inference

            schema = self._infer_schema(df)
            sample_data = df.head(5).to_dicts()

            return schema, sample_data
        except Exception as e:
            raise Exception(f"Error processing CSV: {str(e)}")

    async def _process_json(self, file_path: str) -> tuple:
        """Process JSON file and extract schema"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            if isinstance(data, list) and len(data) > 0:
                # JSON array of objects
                df = pl.DataFrame(data[:100])  # Take first 100 records
            else:
                # Single JSON object - convert to single row DataFrame
                df = pl.DataFrame([data])

            schema = self._infer_schema(df)
            sample_data = df.head(5).to_dicts()

            return schema, sample_data
        except Exception as e:
            raise Exception(f"Error processing JSON: {str(e)}")

    async def _process_excel(self, file_path: str) -> tuple:
        """Process Excel file and extract schema"""
        try:
            # For now, skip Excel processing and return empty schema
            # Polars Excel support is limited
            return {
                "columns": [],
                "row_count": 0
            }, []
        except Exception as e:
            raise Exception(f"Error processing Excel: {str(e)}")

    async def _process_parquet(self, file_path: str) -> tuple:
        """Process Parquet file and extract schema"""
        try:
            df = pl.read_parquet(file_path)
            if len(df) > 100:
                df = df.head(100)
            schema = self._infer_schema(df)
            sample_data = df.head(5).to_dicts()
            return schema, sample_data
        except Exception as e:
            raise Exception(f"Error processing Parquet: {str(e)}")

    def _infer_schema(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Infer schema from polars DataFrame"""
        schema = {
            "columns": [],
            "row_count": len(df)
        }

        for column in df.columns:
            col_info = {
                "name": column,
                "type": str(df[column].dtype),
                "nullable": df[column].is_null().any(),
                "unique_count": df[column].n_unique()
            }

            # Map polars types to our schema types
            dtype_str = str(df[column].dtype)

            if 'Int' in dtype_str:
                col_info["inferred_type"] = "integer"
            elif 'Float' in dtype_str:
                col_info["inferred_type"] = "float"
            elif 'Bool' in dtype_str:
                col_info["inferred_type"] = "boolean"
            elif 'Date' in dtype_str or 'Time' in dtype_str:
                col_info["inferred_type"] = "date"
            else:
                col_info["inferred_type"] = "string"

            schema["columns"].append(col_info)

        return schema
