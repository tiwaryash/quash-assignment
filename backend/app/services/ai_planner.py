from openai import OpenAI
from app.core.config import settings
from app.services.intent_classifier import classify_intent
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are an intelligent browser automation planner. Convert user instructions into a JSON object with an "actions" array.

You must handle multiple types of tasks:
1. PRODUCT SEARCH: Find products on e-commerce sites (Flipkart, Amazon, etc.)
2. FORM FILLING: Fill out and submit forms on websites
3. LOCAL DISCOVERY: Find local places (restaurants, services) with ratings
4. GENERAL BROWSING: Navigate, extract content, interact with pages

IMPORTANT PRINCIPLES:
- Always navigate to REAL website URLs, never "example.com"
- Use appropriate selectors for each site (you'll be given context)
- For extraction, determine the schema dynamically based on what the user wants
- For price filters, extract MORE results then filter after extraction
- For multi-site comparison, repeat the flow for each site
- For forms, identify all required fields and fill them appropriately

SELECTOR GUIDELINES (use as hints, but be flexible):
- Search inputs: input[name='q'], input[type='search'], input[placeholder*='Search'], [role='searchbox'], textarea[name='q']
- Submit buttons: button[type='submit'], input[type='submit'], button:has-text('Search'), [aria-label*='Search']
- Product containers: [data-id], .product, .item, [class*='product'], [data-component-type='s-search-result']
- Prices: .price, [class*='price'], [data-price], .a-price-whole
- Ratings: .rating, [class*='rating'], [aria-label*='star'], .a-icon-alt
- Links: a[href*='/p/'], a[href*='/dp/'], a[href*='/product'], a.product-link

Available actions:
- navigate: {"action": "navigate", "url": "https://www.example.com"}  (ALWAYS use real URLs)
- type: {"action": "type", "selector": "input[name='q']", "text": "search query"}
- click: {"action": "click", "selector": "button[type='submit']"}
- wait_for: {"action": "wait_for", "selector": "[data-id]", "timeout": 15000}
- scroll: {"action": "scroll"}  (scroll to load more content)
- analyze_form: {"action": "analyze_form"}  (analyze form fields on page and determine values using LLM)
- fill_form: {"action": "fill_form", "fields": {"email": {"selector": "input[type='email']", "value": "test@example.com"}}}  (use after analyze_form)
- submit: {"action": "submit", "selector": "button[type='submit']"}  (optional selector)
- extract: {"action": "extract", "limit": 10, "schema": {"field_name": "css_selector"}}

EXTRACTION SCHEMA GUIDELINES:
- For product searches: {"name": "selector", "price": "selector", "rating": "selector", "url": "selector"}
- For local discovery: {"name": "selector", "rating": "selector", "location": "selector", "url": "selector"}
- For general content: {"title": "selector", "content": "selector", "url": "selector"}
- Use generic selectors that work across sites: [class*='title'], [class*='price'], [class*='rating']
- The system will automatically try fallback selectors, so focus on the most common patterns

PLANNING STRATEGY:
1. Analyze the user's intent and determine the task type
2. Identify the target website(s)
3. Plan navigation, interaction, and extraction steps
4. For searches: navigate → type query → click search → wait for results → scroll if needed → extract
5. For forms: navigate → identify fields → fill fields → submit → extract result
6. For local discovery: navigate → search → wait → extract name, rating, location, url
7. Always extract MORE results than requested (e.g., extract 20 to get top 3 after filtering)

Return ONLY valid JSON object with "actions" key containing the array, no markdown, no explanations."""

async def create_action_plan(instruction: str) -> list[dict]:
    """Convert natural language instruction to a JSON action plan using intent classification."""
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY in .env file")
    
    # Classify intent and extract context
    intent_info = classify_intent(instruction)
    
    # Build enhanced instruction with context
    context_parts = []
    
    if intent_info["intent"] == "product_search":
        context_parts.append(f"Task: E-commerce product search")
        if intent_info["sites"]:
            sites_str = " and ".join([s.capitalize() for s in intent_info["sites"]])
            context_parts.append(f"Target sites: {sites_str}")
        if intent_info["comparison"]:
            context_parts.append("User wants to COMPARE products across multiple sites - search on all relevant sites")
        if intent_info["filters"].get("price_max"):
            context_parts.append(f"Price filter: under ₹{intent_info['filters']['price_max']:,.0f}")
        context_parts.append(f"Extract fields: {', '.join(intent_info['extraction_fields'])}")
        context_parts.append("Strategy: Navigate → Search → Wait for results → Scroll → Extract 20+ results → Filter by price → Return top results")
        
    elif intent_info["intent"] == "form_fill":
        context_parts.append("Task: Fill out and submit a form")
        context_parts.append("Strategy: Navigate → Wait for form → Analyze form (LLM) → Fill fields → Submit → Wait for result → Extract")
        context_parts.append("IMPORTANT: For form filling, you MUST use analyze_form action BEFORE fill_form")
        context_parts.append("Steps: 1) navigate to URL, 2) wait_for form fields (e.g., input[type='email']), 3) analyze_form, 4) fill_form (will use analyzed fields), 5) submit, 6) wait_for result (use flexible selectors or skip if URL changes), 7) extract")
        context_parts.append("The analyze_form action will automatically detect all form fields and generate appropriate values (including temporary emails)")
        context_parts.append("After submit: Don't use hardcoded selectors like .success-message. Instead, wait for URL change or use generic selectors like [role='alert'], .message, or check page content")
        context_parts.append("For extraction after form submission: Extract success/error messages, new page content, or confirmation details")
        
    elif intent_info["intent"] == "local_discovery":
        context_parts.append("Task: Local discovery (restaurants, places)")
        context_parts.append(f"Extract fields: {', '.join(intent_info['extraction_fields'])}")
        
        # Check if user specified a site
        instruction_lower = instruction.lower()
        if "zomato" in instruction_lower:
            context_parts.append("Strategy: Navigate to Zomato → Search for places → Extract restaurant listings with ratings")
            context_parts.append("Site: Zomato (zomato.com)")
            context_parts.append("Note: Zomato may block automated access. If blocked, suggest Google Maps as alternative")
        elif "swiggy" in instruction_lower:
            context_parts.append("Strategy: Navigate to Swiggy → Search for places → Extract restaurant listings with ratings")
            context_parts.append("Site: Swiggy (swiggy.com)")
            context_parts.append("Note: Swiggy may block automated access. If blocked, suggest Google Maps as alternative")
        elif "google maps" in instruction_lower or "maps.google" in instruction_lower:
            context_parts.append("Strategy: Use Google Maps → Search for places → Extract from search results")
            context_parts.append("Site: Google Maps (maps.google.com)")
            context_parts.append("For Google Maps: Navigate to maps.google.com, search for query, wait for results, extract from search results")
            context_parts.append("IMPORTANT: For wait_for action, use result container selectors like [data-result-index] or div[role='article'], NOT individual element selectors like .qBF1Pd")
            context_parts.append("Wait for selectors: [data-result-index], div[role='article'], [class*='section-result']")
            context_parts.append("Extraction schema: {\"name\": \".qBF1Pd, h3\", \"rating\": \".MW4etd, [aria-label*='star']\", \"location\": \".W4Efsd\", \"url\": \"a[href*='maps.google.com']\"}")
        else:
            # Default to Google search, but mention it may be blocked
            context_parts.append("Strategy: Use Google search → Search for places → Extract from search results")
            context_parts.append("Note: Google may block automated access. If blocked, suggest Google Maps as alternative")
            context_parts.append("For Google results: Extract from .g or [data-ved] containers, get title from h3/.LC20lb, rating from .fG8Fp or similar")
            context_parts.append("Schema example: {\"name\": \"h3, .LC20lb\", \"rating\": \".fG8Fp, [aria-label*='star']\", \"location\": \".VkpGBb, .fG8Fp\", \"url\": \"a[href^='http']\"}")
        
    else:
        context_parts.append("Task: General browser automation")
        context_parts.append("Strategy: Analyze instruction and determine appropriate actions")
    
    enhanced_instruction = f"{instruction}\n\nContext:\n" + "\n".join(f"- {part}" for part in context_parts)
    
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": enhanced_instruction}
            ],
            temperature=0.2,  # Lower temperature for more consistent planning
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        parsed = json.loads(result)
        
        # Handle both {"actions": [...]} and [...] formats
        if isinstance(parsed, dict) and "actions" in parsed:
            actions = parsed["actions"]
        elif isinstance(parsed, list):
            actions = parsed
        else:
            actions = []
        
        # Store intent info in each action for later use
        for action in actions:
            action["_intent"] = intent_info
        
        return actions
            
    except Exception as e:
        print(f"Error creating plan: {e}")
        return []

