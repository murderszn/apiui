import json
import httpx
from typing import Dict, Any, Optional
from core.config import settings

class AIService:
    def __init__(self):
        self.openai_api_key = settings.openai_api_key

    async def generate_api_code(self, schema: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        """
        Generate FastAPI code using AI based on data schema
        """
        try:
            if self.openai_api_key and self.openai_api_key.strip() and self.openai_api_key != "demo-key-placeholder":
                result = await self._generate_with_openai(schema, job_id)
                if result["success"]:
                    return result
                else:
                    print(f"OpenAI failed: {result['error']}, falling back to mock")
            # Always fall back to mock generation
            return await self._generate_mock_code(schema, job_id)

        except Exception as e:
            print(f"AI generation failed: {str(e)}, falling back to mock")
            return await self._generate_mock_code(schema, job_id)

    async def chat_with_data(self, message: str, schema: Dict[str, Any], sample_data: Optional[list] = None) -> str:
        """
        Chat with data using AI to answer natural language questions
        """
        try:
            print(f"AI service: Received message '{message}'")
            print(f"AI service: Schema has {len(schema.get('columns', []))} columns, {schema.get('row_count', 0)} rows")
            print(f"AI service: Sample data has {len(sample_data) if sample_data else 0} records")
            print(f"AI service: OpenAI key configured: {bool(self.openai_api_key and self.openai_api_key.strip() and self.openai_api_key != 'demo-key-placeholder')}")

            if self.openai_api_key and self.openai_api_key.strip() and self.openai_api_key != "demo-key-placeholder":
                result = await self._chat_with_openai(message, schema, sample_data)
                print(f"AI service: Using OpenAI, response length: {len(result)}")
                return result
            else:
                result = await self._chat_with_mock(message, schema, sample_data)
                print(f"AI service: Using mock, response length: {len(result)}")
                return result

        except Exception as e:
            print(f"AI chat failed: {str(e)}, falling back to mock")
            return await self._chat_with_mock(message, schema, sample_data)

    async def _chat_with_openai(self, message: str, schema: Dict[str, Any], sample_data: Optional[list] = None) -> str:
        """Chat using OpenAI GPT API"""
        try:
            if not self.openai_api_key or self.openai_api_key == "demo-key-placeholder":
                return await self._chat_with_mock(message, schema, sample_data)

            # Build context about the data
            data_info = self._build_data_context(schema, sample_data)

            # Build sample data info for the prompt
            sample_data_info = ""
            if sample_data and len(sample_data) > 0:
                sample_data_info = f"\nHere are {len(sample_data)} sample records from the dataset:\n" + "\n".join([f"- {json.dumps(record, default=str)}" for record in sample_data[:5]])  # Limit to 5 samples

            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }

                system_prompt = f"""You are a helpful data analyst assistant. You have access to a dataset with the following information:

{data_info}

{sample_data_info if sample_data else "No sample data is currently available."}

Your role is to help users understand and analyze this data through natural language conversations. Be helpful, accurate, and provide insights when appropriate. If the user asks for specific data operations (like filtering, sorting, or calculations), explain what you can do and provide the results when possible.

Keep your responses conversational but informative. If you need to show data, format it clearly and use the actual sample data provided when relevant."""

                data = {
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": message
                        }
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7
                }

                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=30.0
                )

                if response.status_code != 200:
                    print(f"OpenAI chat error: {response.status_code} - {response.text}")
                    return await self._chat_with_mock(message, schema, sample_data)

                result = response.json()
                return result["choices"][0]["message"]["content"].strip()

        except Exception as e:
            print(f"OpenAI chat API error: {str(e)}")
            return await self._chat_with_mock(message, schema, sample_data)

    async def _chat_with_mock(self, message: str, schema: Dict[str, Any], sample_data: Optional[list] = None) -> str:
        """Mock chat responses when no AI API is configured"""
        message_lower = message.lower()

        # Simple keyword-based responses
        if 'count' in message_lower or 'how many' in message_lower:
            row_count = schema.get('row_count', 'unknown')
            return f"The dataset contains {row_count} records."

        elif 'columns' in message_lower or 'fields' in message_lower:
            columns = [col['name'] for col in schema.get('columns', [])]
            return f"The dataset has {len(columns)} columns: {', '.join(columns)}."

        elif 'sample' in message_lower or 'show me' in message_lower or 'examples' in message_lower:
            if sample_data and len(sample_data) > 0:
                sample = sample_data[:3]  # First 3 records
                return f"Here are the first {len(sample)} records:\n" + json.dumps(sample, indent=2, default=str)
            else:
                return "I don't have access to sample data at the moment."

        elif 'describe' in message_lower or 'summary' in message_lower:
            columns = schema.get('columns', [])
            summary = f"The dataset has {schema.get('row_count', 'unknown')} rows and {len(columns)} columns."
            if columns:
                numeric_cols = [col['name'] for col in columns if col.get('inferred_type') in ['integer', 'float']]
                text_cols = [col['name'] for col in columns if col.get('inferred_type') == 'string']
                if numeric_cols:
                    summary += f"\nNumeric columns: {', '.join(numeric_cols)}"
                if text_cols:
                    summary += f"\nText columns: {', '.join(text_cols)}"
            return summary

        else:
            return "I can help you with questions about your data! Try asking about the number of records, column names, sample data, or a summary of the dataset."

    def _build_data_context(self, schema: Dict[str, Any], sample_data: Optional[list] = None) -> str:
        """Build context string about the data for the AI"""
        context_parts = []

        # Basic info
        row_count = schema.get('row_count', 'unknown')
        context_parts.append(f"- Total records: {row_count}")

        # Columns info
        columns = schema.get('columns', [])
        if columns:
            context_parts.append(f"- Number of columns: {len(columns)}")
            context_parts.append("- Columns:")

            for col in columns[:10]:  # Limit to first 10 columns
                col_type = col.get('inferred_type', 'unknown')
                nullable = 'nullable' if col.get('nullable', False) else 'required'
                context_parts.append(f"  - {col['name']}: {col_type} ({nullable})")

            if len(columns) > 10:
                context_parts.append(f"  ... and {len(columns) - 10} more columns")

        # Sample data if available
        if sample_data and len(sample_data) > 0:
            context_parts.append(f"- Sample records available: {len(sample_data)} shown")

        return "\n".join(context_parts)

    async def _generate_with_openai(self, schema: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        """Generate code using OpenAI GPT API"""
        try:
            # Check if API key is valid (not placeholder/demo)
            if not self.openai_api_key or self.openai_api_key == "demo-key-placeholder":
                print("OpenAI API key not configured, falling back to mock generation")
                return await self._generate_mock_code(schema, job_id)

            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }

                data = {
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert Python developer specializing in creating secure, efficient FastAPI applications."
                        },
                        {
                            "role": "user",
                            "content": self._build_ai_prompt(schema)
                        }
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.1
                }

                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=60.0
                )

                if response.status_code != 200:
                    print(f"OpenAI API error: {response.status_code} - {response.text}")
                    print("Falling back to mock generation")
                    return await self._generate_mock_code(schema, job_id)

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                parsed_result = self._parse_ai_response(content)

                return parsed_result

        except Exception as e:
            print(f"OpenAI API error: {str(e)}")
            print("Falling back to mock generation")
            return await self._generate_mock_code(schema, job_id)

    async def _generate_mock_code(self, schema: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        """Generate mock code for testing when no AI API is configured"""
        try:
            # Generate a simple FastAPI application
            main_py = self._generate_mock_main_py(schema)
            requirements_txt = self._generate_mock_requirements()
            dockerfile = self._generate_mock_dockerfile()

            return {
                "success": True,
                "main_py": main_py,
                "requirements_txt": requirements_txt,
                "dockerfile": dockerfile
            }

        except Exception as e:
            return {"success": False, "error": f"Mock generation failed: {str(e)}"}

    def _build_ai_prompt(self, schema: Dict[str, Any]) -> str:
        """Build the AI prompt for code generation"""
        columns_info = []
        for col in schema.get("columns", []):
            columns_info.append(f"- {col['name']}: {col['inferred_type']} ({'nullable' if col['nullable'] else 'required'})")

        prompt = f"""
You are an expert Python developer specializing in creating secure, efficient FastAPI applications.

CONTEXT:
The user has uploaded a data file with the following schema:
- Total rows: {schema.get('row_count', 'unknown')}
- Columns:
{chr(10).join(columns_info)}

TASK:
Generate a complete, container-ready FastAPI application to serve this data. The application must:

1. Read data from a CSV file mounted at /app/data.csv and support writing back changes
2. Support full CRUD operations (Create, Read, Update, Delete)
3. Support pagination (limit, offset parameters)
4. Support basic filtering on all columns using query parameters
5. Support sorting by any column (sort_by and sort_order parameters)
6. Include proper error handling and validation
7. Use Pydantic models for request/response validation
8. Include comprehensive API documentation
9. Persist data changes back to the CSV file

OUTPUT FORMAT:
You MUST return a single, minified JSON object with exactly three keys: main_py, requirements_txt, and dockerfile.
Do not include any other text, explanations, or formatting. The JSON should be valid and parseable.

Example format:
{{"main_py": "from fastapi import FastAPI...", "requirements_txt": "fastapi\\nuvicorn", "dockerfile": "FROM python:3.9\\n..."}}
"""

        return prompt

    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the AI response and extract the generated code"""
        try:
            # Clean the response text (remove markdown formatting if present)
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]

            # Parse JSON
            result = json.loads(cleaned_text.strip())

            # Validate required keys
            required_keys = ["main_py", "requirements_txt", "dockerfile"]
            for key in required_keys:
                if key not in result:
                    raise ValueError(f"Missing required key: {key}")

            return {
                "success": True,
                "main_py": result["main_py"],
                "requirements_txt": result["requirements_txt"],
                "dockerfile": result["dockerfile"]
            }

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response from AI: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Error parsing AI response: {str(e)}"}

    def _generate_mock_main_py(self, schema: Dict[str, Any]) -> str:
        """Generate a mock main.py for testing"""
        columns = [col["name"] for col in schema.get("columns", [])]
        column_types = {}
        for col in schema.get("columns", []):
            if col["inferred_type"] == "integer":
                column_types[col["name"]] = "int"
            elif col["inferred_type"] == "float":
                column_types[col["name"]] = "float"
            elif col["inferred_type"] == "boolean":
                column_types[col["name"]] = "bool"
            else:
                column_types[col["name"]] = "str"

        # Generate Pydantic models
        model_fields = []
        for col in columns:
            col_type = column_types[col]
            model_fields.append(f"    {col}: Optional[{col_type}] = None")

        filter_model = f"""
class DataFilter(BaseModel):
{chr(10).join(model_fields)}
"""

        # Generate DataItem model for create/update operations
        create_model_fields = []
        update_model_fields = []
        for col in columns:
            col_type = column_types[col]
            create_model_fields.append(f"    {col}: Optional[{col_type}] = None")
            update_model_fields.append(f"    {col}: Optional[{col_type}] = None")

        data_item_model = f"""
class DataItem(BaseModel):
{chr(10).join(create_model_fields)}

class DataItemUpdate(BaseModel):
{chr(10).join(update_model_fields)}
"""

        # Generate main FastAPI app
        main_py = f'''from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd
import os
from enum import Enum

app = FastAPI(
    title="Generated API",
    description="API generated from user data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

{filter_model}

{data_item_model}

# Load data on startup
@app.on_event("startup")
async def load_data():
    global df
    data_path = os.getenv("DATA_PATH", "/app/data.csv")
    try:
        df = pd.read_csv(data_path)
        print(f"Loaded {{len(df)}} rows from {{data_path}}")
    except Exception as e:
        print(f"Error loading data: {{e}}")
        df = pd.DataFrame()

@app.get("/")
async def root():
    return {{"message": "API is running", "endpoints": ["/data", "/data/{{id}}", "POST /data", "PUT /data/{{id}}", "PATCH /data/{{id}}", "DELETE /data/{{id}}"]}}

@app.get("/data")
async def get_data(
    limit: int = Query(10, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = None,
    sort_order: SortOrder = SortOrder.ASC,
    **filters
):
    """Get paginated data with optional filtering and sorting"""
    try:
        # Start with all data
        result_df = df.copy()

        # Apply filters
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
        if sort_by and sort_by in result_df.columns:
            result_df = result_df.sort_values(sort_by, ascending=(sort_order == SortOrder.ASC))

        # Apply pagination
        total_count = len(result_df)
        result_df = result_df.iloc[offset:offset + limit]

        return {{
            "data": result_df.to_dict('records'),
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/{{item_id}}")
async def get_data_item(item_id: int):
    """Get a specific data item by index"""
    try:
        if item_id < 0 or item_id >= len(df):
            raise HTTPException(status_code=404, detail="Item not found")

        item = df.iloc[item_id].to_dict()
        return item

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schema")
async def get_schema():
    """Get the data schema information"""
    schema_info = []
    for col in df.columns:
        col_info = {{
            "name": col,
            "type": str(df[col].dtype),
            "nullable": df[col].isnull().any(),
            "unique_count": df[col].nunique()
        }}
        schema_info.append(col_info)

    return {{
        "columns": schema_info,
        "total_rows": len(df)
    }}

def save_data():
    """Save the dataframe back to CSV file"""
    global df
    try:
        data_path = os.getenv("DATA_PATH", "/app/data.csv")
        df.to_csv(data_path, index=False)
        print(f"Saved {{len(df)}} rows to {{data_path}}")
    except Exception as e:
        print(f"Error saving data: {{e}}")
        raise HTTPException(status_code=500, detail=f"Failed to save data: {{str(e)}}")

@app.post("/data")
async def create_data_item(item: DataItem):
    """Create a new data item"""
    global df
    try:
        # Convert Pydantic model to dict, filter out None values
        item_dict = {{k: v for k, v in item.dict().items() if v is not None}}

        # Create new row
        new_row = pd.DataFrame([item_dict])

        # Ensure all columns exist (add missing columns with None)
        for col in df.columns:
            if col not in new_row.columns:
                new_row[col] = None

        # Reorder columns to match existing dataframe
        new_row = new_row[df.columns]

        # Append to dataframe
        df = pd.concat([df, new_row], ignore_index=True)

        # Save to file
        save_data()

        return {{
            "message": "Item created successfully",
            "id": len(df) - 1,
            "item": item_dict
        }}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/data/{{item_id}}")
async def update_data_item(item_id: int, item: DataItem):
    """Update an existing data item completely"""
    global df
    try:
        if item_id < 0 or item_id >= len(df):
            raise HTTPException(status_code=404, detail="Item not found")

        # Convert Pydantic model to dict, filter out None values
        item_dict = {{k: v for k, v in item.dict().items() if v is not None}}

        # Update the row
        for key, value in item_dict.items():
            if key in df.columns:
                df.at[item_id, key] = value

        # Save to file
        save_data()

        return {{
            "message": "Item updated successfully",
            "id": item_id,
            "item": df.iloc[item_id].to_dict()
        }}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/data/{{item_id}}")
async def patch_data_item(item_id: int, item: DataItemUpdate):
    """Partially update an existing data item"""
    global df
    try:
        if item_id < 0 or item_id >= len(df):
            raise HTTPException(status_code=404, detail="Item not found")

        # Convert Pydantic model to dict, filter out None values
        item_dict = {{k: v for k, v in item.dict().items() if v is not None}}

        # Update only provided fields
        for key, value in item_dict.items():
            if key in df.columns:
                df.at[item_id, key] = value

        # Save to file
        save_data()

        return {{
            "message": "Item updated successfully",
            "id": item_id,
            "item": df.iloc[item_id].to_dict()
        }}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/data/{{item_id}}")
async def delete_data_item(item_id: int):
    """Delete a data item"""
    global df
    try:
        if item_id < 0 or item_id >= len(df):
            raise HTTPException(status_code=404, detail="Item not found")

        # Store the item before deletion for response
        deleted_item = df.iloc[item_id].to_dict()

        # Delete the row
        df = df.drop(item_id).reset_index(drop=True)

        # Save to file
        save_data()

        return {{
            "message": "Item deleted successfully",
            "id": item_id,
            "deleted_item": deleted_item
        }}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
'''

        return main_py

    def _generate_mock_requirements(self) -> str:
        """Generate requirements.txt for the mock API"""
        return """fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pandas==2.1.4
python-multipart==0.0.6"""

    def _generate_mock_dockerfile(self) -> str:
        """Generate Dockerfile for the mock API"""
        return """FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY main.py .
COPY data.csv .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]"""
