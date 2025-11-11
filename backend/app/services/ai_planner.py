from openai import OpenAI
from app.core.config import settings
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are a browser automation planner. Convert user instructions into a JSON object with an "actions" array.

IMPORTANT CONTEXT:
- E-commerce searches should work across MULTIPLE sites (Flipkart, Amazon, etc.) for comparison
- If user wants "best" or "compare", search on multiple sites
- For price filters (e.g., "under ₹1,00,000"), you MUST filter results after extraction
- Always navigate to the actual website URL, never "example.com"
- Extract: name, price (as number), rating (as number), and link (full URL)

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
- wait_for: {"action": "wait_for", "selector": "[data-id]", "timeout": 15000}
- extract: {"action": "extract", "limit": 10, "schema": {"name": "._4rR01T", "price": "._30jeq3", "rating": "._3LWZlK", "link": "a._1fQZEK"}}

For product searches:
1. Search on the site (don't include price in search text, filter after)
2. Wait for results to load (use longer timeout: 15000ms)
3. Extract MORE results than needed (limit: 10), then filter by price
4. For multi-site comparison, repeat the flow for each site
5. Extract: name, price (numeric), rating (numeric), link (full URL)

For Flipkart selectors:
- name: "._4rR01T" or "div._4rR01T" or "a[title]"
- price: "._30jeq3" or "div._30jeq3"
- rating: "._3LWZlK" or "div._3LWZlK"
- link: "a._1fQZEK" or "a[href*='/p/']"

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
        # Check if user wants comparison across sites
        wants_comparison = any(word in instruction_lower for word in ['compare', 'best', 'across', 'multiple', 'both'])
        
        if wants_comparison and not site:
            # Multi-site search
            enhanced_instruction = f"{instruction}\n\nContext: User wants to compare products across multiple sites. Search on BOTH Flipkart and Amazon, extract results from each, then provide the best options."
        elif site:
            enhanced_instruction = f"{instruction}\n\nContext: This is an e-commerce product search on {site}. Navigate to {site}, search for products, wait for results to load (15s timeout), extract name, price (as number), rating (as number), and product links. Extract at least 10 results, then filter by price if specified."
        else:
            enhanced_instruction = f"{instruction}\n\nContext: This is an e-commerce product search. Use Flipkart for Indian market. Navigate to the site, search for products, wait for results (15s timeout), extract name, price (as number), rating (as number), and product links. Extract at least 10 results to filter properly."
    
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

