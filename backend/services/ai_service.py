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

    async def generate_api_summary(self, schema: Dict[str, Any], sample_data: Optional[list] = None, api_name: Optional[str] = None) -> str:
        """
        Generate a concise API summary using AI for documentation
        """
        try:
            print(f"AI service: Generating API summary for {api_name or 'unnamed API'}")
            print(f"AI service: Schema has {len(schema.get('columns', []))} columns, {schema.get('row_count', 0)} rows")

            if self.openai_api_key and self.openai_api_key.strip() and self.openai_api_key != "demo-key-placeholder":
                result = await self._generate_summary_with_openai(schema, sample_data, api_name)
                print(f"AI service: Generated summary using OpenAI, length: {len(result)}")
                return result
            else:
                result = await self._generate_summary_mock(schema, sample_data, api_name)
                print(f"AI service: Generated summary using mock, length: {len(result)}")
                return result

        except Exception as e:
            print(f"AI summary generation failed: {str(e)}, falling back to mock")
            return await self._generate_summary_mock(schema, sample_data, api_name)

    async def _generate_summary_with_openai(self, schema: Dict[str, Any], sample_data: Optional[list] = None, api_name: Optional[str] = None) -> str:
        """Generate API summary using OpenAI GPT API"""
        try:
            if not self.openai_api_key or self.openai_api_key == "demo-key-placeholder":
                return await self._generate_summary_mock(schema, sample_data, api_name)

            # Build context about the API
            api_info = self._build_api_summary_context(schema, sample_data, api_name)

            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }

                system_prompt = """You are a technical writer specializing in creating concise, informative API documentation summaries that describe the actual content and structure of the data.

Your task is to write a brief, professional summary of an API based on the provided data schema and samples. The summary should be suitable for API documentation and specifically describe:

1. What type of real-world entities/records the API contains (e.g., "YouTube channels", "football players", "businesses", "products")
2. Key identifying and descriptive fields that users would care about (e.g., "channel names and subscriber counts", "player names, positions, and ratings")
3. The scope and nature of the data (how many records, what makes this data valuable)
4. Any notable data characteristics from the samples (ranges, categories, text content)

Keep the summary to 2-3 sentences maximum. Use clear, professional language. Focus on helping developers understand what specific data they can access and why it would be useful."""

                data = {
                    "model": "gpt-3.5-turbo",  # Use cheaper model for summaries
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": f"Write a brief API summary for: {api_info}"
                        }
                    ],
                    "max_tokens": 200,  # Limit tokens for cost control
                    "temperature": 0.3
                }

                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=20.0
                )

                if response.status_code != 200:
                    print(f"OpenAI summary error: {response.status_code} - {response.text}")
                    return await self._generate_summary_mock(schema, sample_data, api_name)

                result = response.json()
                return result["choices"][0]["message"]["content"].strip()

        except Exception as e:
            print(f"OpenAI summary API error: {str(e)}")
            return await self._generate_summary_mock(schema, sample_data, api_name)

    async def _generate_summary_mock(self, schema: Dict[str, Any], sample_data: Optional[list] = None, api_name: Optional[str] = None) -> str:
        """Generate mock API summary when no AI API is configured"""
        try:
            row_count = schema.get('row_count', 'unknown')
            columns = schema.get('columns', [])
            column_count = len(columns)

            # Extract meaningful column information
            column_names = [col['name'].lower() for col in columns]

            # Try to identify the data domain based on column names
            domain_info = self._identify_data_domain(column_names)

            # Get sample data insights if available
            sample_insights = ""
            if sample_data and len(sample_data) > 0:
                sample_insights = self._analyze_sample_data(sample_data, columns)

            # Determine data types breakdown
            data_types = {}
            for col in columns:
                col_type = col.get('inferred_type', 'unknown')
                data_types[col_type] = data_types.get(col_type, 0) + 1

            # Create a more descriptive summary
            api_title = api_name or "Data API"

            if domain_info:
                summary = f"{api_title} contains {row_count:,} {domain_info['entity']} records with key information including {domain_info['key_fields']}. {sample_insights}This RESTful API supports full CRUD operations with filtering, sorting, and pagination capabilities."
            else:
                # Fallback to generic but more descriptive summary
                key_columns = [col['name'] for col in columns[:5]]  # First 5 columns
                key_fields_str = ", ".join(key_columns)
                if len(columns) > 5:
                    key_fields_str += f", and {len(columns) - 5} more fields"

                summary = f"{api_title} provides access to {row_count:,} data records with {column_count} columns including {key_fields_str}. {sample_insights}This RESTful API supports full CRUD operations with filtering, sorting, and pagination capabilities."

            return summary

        except Exception as e:
            print(f"Mock summary generation error: {str(e)}")
            return f"This API provides access to {schema.get('row_count', 'multiple')} data records with comprehensive CRUD operations and filtering capabilities."

    def _identify_data_domain(self, column_names: list) -> Optional[Dict[str, str]]:
        """Identify the data domain based on column names"""
        # Convert to lowercase for matching
        columns_lower = [name.lower() for name in column_names]

        # YouTube/Video content detection
        youtube_keywords = ['channel', 'subscriber', 'video', 'view', 'title', 'description', 'url', 'thumbnail']
        if any(keyword in ' '.join(columns_lower) for keyword in youtube_keywords):
            key_fields = []
            if any('channel' in col for col in columns_lower):
                key_fields.append('channel names')
            if any('subscriber' in col for col in columns_lower):
                key_fields.append('subscriber counts')
            if any('video' in col for col in columns_lower):
                key_fields.append('video information')
            if not key_fields:
                key_fields = ['channel and video data']
            return {
                'entity': 'YouTube channel',
                'key_fields': ', '.join(key_fields)
            }

        # Sports/Player data detection (FIFA, soccer, etc.)
        sports_keywords = ['player', 'position', 'rating', 'team', 'club', 'nation', 'age', 'height', 'weight', 'pace', 'shooting', 'passing', 'dribbling', 'defending', 'physical']
        if any(keyword in ' '.join(columns_lower) for keyword in sports_keywords):
            key_fields = []
            if any('player' in col for col in columns_lower):
                key_fields.append('player names')
            if any('position' in col for col in columns_lower):
                key_fields.append('playing positions')
            if any('rating' in col for col in columns_lower):
                key_fields.append('performance ratings')
            if any('team' in col or 'club' in col for col in columns_lower):
                key_fields.append('team affiliations')
            if not key_fields:
                key_fields = ['player statistics and attributes']
            return {
                'entity': 'player',
                'key_fields': ', '.join(key_fields)
            }

        # Business/Company data detection
        business_keywords = ['company', 'business', 'revenue', 'employee', 'industry', 'location', 'website', 'contact']
        if any(keyword in ' '.join(columns_lower) for keyword in business_keywords):
            key_fields = []
            if any('company' in col for col in columns_lower):
                key_fields.append('company names')
            if any('revenue' in col or 'employee' in col for col in columns_lower):
                key_fields.append('business metrics')
            if any('industry' in col for col in columns_lower):
                key_fields.append('industry classifications')
            if not key_fields:
                key_fields = ['business information']
            return {
                'entity': 'business',
                'key_fields': ', '.join(key_fields)
            }

        # Product/E-commerce data detection
        product_keywords = ['product', 'price', 'category', 'brand', 'sku', 'inventory', 'description', 'rating', 'review']
        if any(keyword in ' '.join(columns_lower) for keyword in product_keywords):
            key_fields = []
            if any('product' in col for col in columns_lower):
                key_fields.append('product names')
            if any('price' in col for col in columns_lower):
                key_fields.append('pricing information')
            if any('category' in col for col in columns_lower):
                key_fields.append('product categories')
            if not key_fields:
                key_fields = ['product details and specifications']
            return {
                'entity': 'product',
                'key_fields': ', '.join(key_fields)
            }

        # Demographic/Population data detection
        demographic_keywords = ['population', 'age', 'gender', 'income', 'education', 'ethnicity', 'city', 'state', 'country']
        if any(keyword in ' '.join(columns_lower) for keyword in demographic_keywords):
            key_fields = []
            if any('population' in col for col in columns_lower):
                key_fields.append('population figures')
            if any('age' in col or 'income' in col for col in columns_lower):
                key_fields.append('demographic statistics')
            if any('city' in col or 'state' in col or 'country' in col for col in columns_lower):
                key_fields.append('geographic locations')
            if not key_fields:
                key_fields = ['demographic and geographic data']
            return {
                'entity': 'geographic/demographic',
                'key_fields': ', '.join(key_fields)
            }

        return None  # No specific domain identified

    def _analyze_sample_data(self, sample_data: list, columns: list) -> str:
        """Analyze sample data to provide additional insights"""
        try:
            if not sample_data or len(sample_data) == 0:
                return ""

            insights = []

            # Check for date/time patterns
            date_columns = []
            for col in columns:
                col_name = col['name'].lower()
                if any(term in col_name for term in ['date', 'time', 'year', 'month', 'day']):
                    date_columns.append(col['name'])

            if date_columns:
                insights.append(f"includes temporal data across {len(date_columns)} date/time fields")

            # Check for numeric ranges
            numeric_insights = []
            for col in columns:
                if col.get('inferred_type') in ['integer', 'float']:
                    col_name = col['name']
                    # Get sample values for this column
                    sample_values = []
                    for row in sample_data[:10]:  # Check first 10 rows
                        if col_name in row and row[col_name] is not None:
                            try:
                                val = float(row[col_name])
                                sample_values.append(val)
                            except (ValueError, TypeError):
                                continue

                    if sample_values:
                        min_val = min(sample_values)
                        max_val = max(sample_values)
                        if max_val > min_val:
                            numeric_insights.append(f"{col_name}: {min_val:.1f}-{max_val:.1f}")

            if numeric_insights and len(numeric_insights) <= 3:
                insights.append(f"with numeric ranges like {', '.join(numeric_insights[:3])}")

            # Check for text data variety
            text_insights = []
            for col in columns:
                if col.get('inferred_type') == 'string':
                    col_name = col['name']
                    # Get sample values for this column
                    sample_values = []
                    for row in sample_data[:10]:  # Check first 10 rows
                        if col_name in row and row[col_name] is not None:
                            val = str(row[col_name]).strip()
                            if val:
                                sample_values.append(val)

                    # Remove duplicates and check variety
                    unique_values = list(set(sample_values))
                    if len(unique_values) > 1:
                        if len(unique_values) <= 5:
                            # Few unique values - might be categorical
                            text_insights.append(f"{col_name} ({len(unique_values)} categories)")
                        else:
                            # Many unique values - likely descriptive text
                            text_insights.append(f"{col_name} (descriptive text)")

            if text_insights and len(text_insights) <= 3:
                insights.append(f"featuring {', '.join(text_insights[:3])}")

            if insights:
                return " ".join(insights).capitalize() + ". "

            return ""

        except Exception as e:
            print(f"Error analyzing sample data: {str(e)}")
            return ""

    def _build_api_summary_context(self, schema: Dict[str, Any], sample_data: Optional[list] = None, api_name: Optional[str] = None) -> str:
        """Build context string for API summary generation"""
        context_parts = []

        if api_name:
            context_parts.append(f"API Name: {api_name}")

        # Basic stats
        row_count = schema.get('row_count', 'unknown')
        context_parts.append(f"Records: {row_count}")

        # Column analysis with names and types
        columns = schema.get('columns', [])
        context_parts.append(f"Columns: {len(columns)}")

        # Include first 8 column names with their types for better context
        if columns:
            column_details = []
            for col in columns[:8]:  # Show more columns for better AI understanding
                col_name = col.get('name', 'unknown')
                col_type = col.get('inferred_type', 'unknown')
                column_details.append(f"{col_name}({col_type})")

            if len(columns) > 8:
                column_details.append(f"...and {len(columns) - 8} more")
            context_parts.append(f"Column Details: {', '.join(column_details)}")

        # Sample data insights
        if sample_data and len(sample_data) > 0:
            context_parts.append(f"Sample Records: {len(sample_data)} provided")

            # Add some sample data context
            if len(sample_data) > 0 and len(columns) > 0:
                sample_insights = []
                first_sample = sample_data[0]

                # Show a few key values from the first sample record
                for col in columns[:5]:  # First 5 columns
                    col_name = col.get('name')
                    if col_name in first_sample and first_sample[col_name] is not None:
                        value = str(first_sample[col_name])
                        if len(value) > 50:  # Truncate long values
                            value = value[:47] + "..."
                        sample_insights.append(f"{col_name}: {value}")

                if sample_insights:
                    context_parts.append(f"Sample Values: {' | '.join(sample_insights)}")

        return " | ".join(context_parts)

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
