from openai import OpenAI
from app.core.config import settings
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are a browser automation planner. Convert user instructions into a JSON object with an "actions" array.

IMPORTANT CONTEXT:
- E-commerce searches can be on Flipkart, Amazon, Myntra, Snapdeal, or other shopping sites
- If user mentions a specific site (e.g., "on Flipkart"), use that site
- If no site mentioned, default to Flipkart for Indian market, Amazon for international
- For price filters (e.g., "under ₹1,00,000"), include price in search query or filter after results
- Always navigate to the actual website URL, never "example.com"

SITE-SPECIFIC SELECTORS:
- Flipkart: 
  * Search: input[name='q'] or ._3704LK or input[placeholder*='Search']
  * Submit: button[type='submit'] or .L0Z3Pu or button._2KpZ6l
  * Products: ._1AtVbE or [data-id] or ._2kHMtA
  * Price: ._30jeq3 or ._1_WHN1
  * Rating: ._3LWZlK or [class*='rating']
  * Link: a[href*='/p/'] or a._1fQZEK
  
- Amazon:
  * Search: input[id='twotabsearchtextbox'] or #nav-search-input or input[name='field-keywords']
  * Submit: input[type='submit'][value='Go'] or #nav-search-submit-button
  * Products: [data-component-type='s-search-result'] or .s-result-item
  * Price: .a-price-whole or .a-price .a-offscreen
  * Rating: .a-icon-alt or [aria-label*='stars']
  * Link: a.a-link-normal[href*='/dp/']
  
- Generic shopping sites:
  * Search: input[name='q'], input[type='search'], input[placeholder*='Search'], [role='searchbox']
  * Submit: button[type='submit'], input[type='submit'], button:has-text('Search')
  * Products: [data-id], .product, .item, [class*='product']
  * Price: .price, [class*='price'], [data-price]
  * Rating: .rating, [class*='rating'], [aria-label*='star']
  * Link: a[href*='/p/'], a[href*='/product'], a.product-link

Available actions:
- navigate: {"action": "navigate", "url": "https://www.flipkart.com"}  (use real URLs)
- type: {"action": "type", "selector": "input[name='q']", "text": "MacBook Air 13 inch"}
- click: {"action": "click", "selector": "button[type='submit']"}
- wait_for: {"action": "wait_for", "selector": "[data-id]", "timeout": 10000}
- extract: {"action": "extract", "limit": 3, "schema": {"name": "._4rR01T", "price": "._30jeq3", "rating": "._3LWZlK", "link": "a._1fQZEK"}}

For product searches with price filters:
1. Include price range in search text if possible (e.g., "MacBook Air under 100000")
2. Or search first, then filter results
3. Extract: name, price (as number), rating, and link (full URL)

Return ONLY valid JSON object with "actions" key containing the array, no markdown, no explanations."""

async def create_action_plan(instruction: str) -> list[dict]:
    """Convert natural language instruction to a JSON action plan."""
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY in .env file")
    
    # Enhance instruction with context hints
    enhanced_instruction = instruction
    instruction_lower = instruction.lower()
    
    # Detect e-commerce context
    ecommerce_keywords = ['flipkart', 'amazon', 'myntra', 'snapdeal', 'shop', 'buy', 'product', 'laptop', 'phone', '₹', 'rupee', 'price', 'under', 'above', 'compare', 'rating', 'delivery']
    is_ecommerce = any(word in instruction_lower for word in ecommerce_keywords)
    
    # Detect specific site
    site = None
    if 'flipkart' in instruction_lower:
        site = 'Flipkart'
    elif 'amazon' in instruction_lower:
        site = 'Amazon'
    elif 'myntra' in instruction_lower:
        site = 'Myntra'
    elif 'snapdeal' in instruction_lower:
        site = 'Snapdeal'
    
    if is_ecommerce:
        if site:
            enhanced_instruction = f"{instruction}\n\nContext: This is an e-commerce product search on {site}. Navigate to {site}, search for products, and extract name, price, rating, and product links."
        else:
            enhanced_instruction = f"{instruction}\n\nContext: This is an e-commerce product search. Use Flipkart (for Indian market) or Amazon. Navigate to the site, search for products, and extract name, price, rating, and product links."
    
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

