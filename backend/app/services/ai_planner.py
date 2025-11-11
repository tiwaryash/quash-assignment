from openai import OpenAI
from app.core.config import settings
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are a browser automation planner. Convert user instructions into a JSON object with an "actions" array.

IMPORTANT CONTEXT:
- For shopping sites (Flipkart, Amazon, etc.): navigate to the site first, then search
- For Google searches: use Google.com
- Always navigate to the actual website URL, not "example.com"

SELECTOR GUIDELINES:
- Google: search box is textarea[name='q'] or #APjFqb, submit is input[name='btnK']
- Flipkart: search box is input[name='q'] or ._3704LK, submit is button[type='submit'] or .L0Z3Pu
- Amazon: search box is input[id='twotabsearchtextbox'] or #nav-search-input, submit is input[type='submit'][value='Go']
- Generic shopping sites: try input[name='q'], input[type='search'], or input[placeholder*='Search']
- Modern websites often use textarea for search (Google), but most shopping sites use input

Available actions:
- navigate: {"action": "navigate", "url": "https://www.flipkart.com"}  (use real URLs, not example.com)
- type: {"action": "type", "selector": "input[name='q']", "text": "search query"}
- click: {"action": "click", "selector": "button[type='submit']"}
- wait_for: {"action": "wait_for", "selector": "[data-id]", "timeout": 10000}
- extract: {"action": "extract", "limit": 3, "schema": {"name": ".product-name", "price": ".price", "rating": ".rating", "link": "a"}}

For product searches, extract: name, price, rating, and link/URL fields.

Return ONLY valid JSON object with "actions" key containing the array, no markdown, no explanations."""

async def create_action_plan(instruction: str) -> list[dict]:
    """Convert natural language instruction to a JSON action plan."""
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY in .env file")
    
    # Enhance instruction with context hints
    enhanced_instruction = instruction
    if any(word in instruction.lower() for word in ['flipkart', 'amazon', 'shop', 'buy', 'product', 'laptop', 'phone', '₹', 'rupee']):
        enhanced_instruction = f"{instruction}\n\nNote: This is a shopping/product search. Use Flipkart or Amazon, not Google search."
    
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": enhanced_instruction}
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

