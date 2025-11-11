from openai import OpenAI
from app.core.config import settings
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are a browser automation planner. Convert user instructions into a JSON object with an "actions" array.

IMPORTANT SELECTOR GUIDELINES:
- Modern websites often use textarea for search inputs, not input (e.g., Google uses textarea[name='q'])
- Search boxes might be: textarea[name='q'], input[type='search'], #search, or [role='searchbox']
- Submit buttons might be: button[type='submit'], input[type='submit'], button:has-text('Search'), or [aria-label*='Search']
- Always prefer more specific selectors: use IDs (#id), data attributes ([data-testid]), or name attributes
- For Google: search box is textarea[name='q'] or #APjFqb, submit is input[name='btnK'] or button[aria-label*='Search']

Available actions:
- navigate: {"action": "navigate", "url": "https://example.com"}
- type: {"action": "type", "selector": "textarea[name='q']", "text": "search query"}  (use textarea for modern search boxes)
- click: {"action": "click", "selector": "input[name='btnK']"}  (be specific about button selectors)
- wait_for: {"action": "wait_for", "selector": "[data-id]", "timeout": 5000}
- extract: {"action": "extract", "query": "Get top 3 results", "schema": {"name": ".product-name", "price": ".price"}}

Return ONLY valid JSON object with "actions" key containing the array, no markdown, no explanations."""

async def create_action_plan(instruction: str) -> list[dict]:
    """Convert natural language instruction to a JSON action plan."""
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY in .env file")
    
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

