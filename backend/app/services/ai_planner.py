from openai import OpenAI
from app.core.config import settings
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are a browser automation planner. Convert user instructions into a JSON object with an "actions" array.

Available actions:
- navigate: {"action": "navigate", "url": "https://example.com"}
- type: {"action": "type", "selector": "input[name='q']", "text": "search query"}
- click: {"action": "click", "selector": "button[type='submit']"}
- wait_for: {"action": "wait_for", "selector": "[data-id]", "timeout": 5000}
- extract: {"action": "extract", "query": "Get top 3 results", "schema": {"name": ".product-name", "price": ".price"}}

Return ONLY valid JSON object with "actions" key containing the array, no markdown, no explanations."""

async def create_action_plan(instruction: str) -> list[dict]:
    """Convert natural language instruction to a JSON action plan."""
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": instruction}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        # Parse the JSON response
        parsed = json.loads(result)
        
        # Handle both {"actions": [...]} and [...] formats
        if isinstance(parsed, dict) and "actions" in parsed:
            return parsed["actions"]
        elif isinstance(parsed, list):
            return parsed
        else:
            return []
            
    except Exception as e:
        print(f"Error creating plan: {e}")
        return []

