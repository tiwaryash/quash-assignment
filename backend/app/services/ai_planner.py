from openai import OpenAI
from app.core.config import settings
from app.services.intent_classifier import classify_intent
import json

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are an intelligent browser automation planner. Convert user instructions into a JSON object with an "actions" array.

You must handle multiple types of tasks:
1. PRODUCT SEARCH: Find products on e-commerce sites (Flipkart, Amazon, etc.)
2. FORM FILLING: Fill out and submit forms on websites
3. LOCAL DISCOVERY: Find local places (restaurants, services, food) with ratings
4. GENERAL BROWSING: Navigate, extract content, interact with pages

CRITICAL PRINCIPLES:
- Always navigate to REAL website URLs, never "example.com" or placeholders
- Use appropriate selectors for each site (you'll be given context)
- For extraction, determine the schema dynamically based on what the user wants
- For price filters, extract MORE results (20+) then filter after extraction
- For multi-site comparison, create separate action sequences for each site
- For forms, use analyze_form action BEFORE fill_form to detect fields automatically
- For local discovery, prefer Google Maps over Google Search for better results
- When searching on Google Maps, wait for result containers, not individual elements

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
        
        # Site information
        if intent_info["sites"]:
            sites_str = " and ".join([s.capitalize() for s in intent_info["sites"]])
            context_parts.append(f"🛍️ Target sites: {sites_str}")
            
            # If multiple sites, explain comparison flow
            if len(intent_info["sites"]) > 1 or intent_info["comparison"]:
                context_parts.append("⚖️ COMPARISON MODE: Search on EACH site separately")
                context_parts.append("For each site:")
                context_parts.append("  1. Navigate to the site")
                context_parts.append("  2. Search for product")
                context_parts.append("  3. Extract results")
                context_parts.append("  4. Move to next site")
                context_parts.append("Create action sequences for EACH site in the 'actions' array")
        
        # Filter information
        if intent_info["filters"].get("price_max"):
            context_parts.append(f"💰 Price filter: under ₹{intent_info['filters']['price_max']:,.0f}")
            context_parts.append("⚠️ Extract MORE results (20+) first, then filter by price")
        if intent_info["filters"].get("rating_min"):
            context_parts.append(f"⭐ Rating filter: minimum {intent_info['filters']['rating_min']} stars")
        
        context_parts.append(f"📊 Extract fields: {', '.join(intent_info['extraction_fields'])}")
        context_parts.append("")
        context_parts.append("STRATEGY:")
        context_parts.append("1. Navigate to e-commerce site (e.g., https://www.flipkart.com)")
        context_parts.append("2. Type product query into search box")
        context_parts.append("3. Click search button or press Enter")
        context_parts.append("4. Wait for product results to load")
        context_parts.append("5. Scroll down to load more products (optional)")
        context_parts.append("6. Extract 20+ products with name, price, rating, url")
        context_parts.append("7. System will auto-filter by price/rating after extraction")
        context_parts.append("")
        context_parts.append("SITE-SPECIFIC URLS:")
        context_parts.append("- Flipkart: https://www.flipkart.com")
        context_parts.append("- Amazon: https://www.amazon.in")
        context_parts.append("- Myntra: https://www.myntra.com")
        context_parts.append("- Snapdeal: https://www.snapdeal.com")
        
    elif intent_info["intent"] == "form_fill":
        context_parts.append("Task: Fill out and submit a form")
        context_parts.append("Strategy: Navigate → Wait for form → Analyze form (LLM) → Fill fields → Submit → Wait for result → Extract")
        context_parts.append("IMPORTANT: For form filling, you MUST use analyze_form action BEFORE fill_form")
        context_parts.append("Steps: 1) navigate to URL, 2) wait_for form fields (e.g., input[type='email']), 3) analyze_form, 4) fill_form (will use analyzed fields), 5) submit, 6) wait_for result (use flexible selectors or skip if URL changes), 7) extract")
        context_parts.append("The analyze_form action will automatically detect all form fields and generate appropriate values (including temporary emails)")
        context_parts.append("After submit: Don't use hardcoded selectors like .success-message. Instead, wait for URL change or use generic selectors like [role='alert'], .message, or check page content")
        context_parts.append("For extraction after form submission: Extract success/error messages, new page content, or confirmation details")
        
    elif intent_info["intent"] == "local_discovery":
        context_parts.append("Task: Local discovery (finding restaurants, places, services)")
        context_parts.append(f"Extract fields: {', '.join(intent_info['extraction_fields'])}")
        
        # Check if user specified a site
        instruction_lower = instruction.lower()
        
        # Determine the target platform
        target_platform = None
        if "google maps" in instruction_lower or "google_maps" in instruction_lower or "maps.google" in instruction_lower:
            target_platform = "google_maps"
        elif "zomato" in instruction_lower:
            target_platform = "zomato"
        elif "swiggy" in instruction_lower:
            target_platform = "swiggy"
        
        if target_platform == "google_maps" or target_platform is None:
            # Google Maps is the most reliable for local discovery
            context_parts.append("🗺️ PLATFORM: Google Maps (https://www.google.com/maps)")
            context_parts.append("STRATEGY:")
            context_parts.append("1. Navigate to https://www.google.com/maps")
            context_parts.append("2. Type search query into search box - Enter will be pressed automatically")
            context_parts.append("3. Wait 15-20 seconds for results to load - use CONTAINER selectors")
            context_parts.append("4. Extract from result containers")
            context_parts.append("")
            context_parts.append("ACTION SEQUENCE EXAMPLE:")
            context_parts.append('{"action": "navigate", "url": "https://www.google.com/maps"}')
            context_parts.append('{"action": "type", "selector": "input#searchboxinput", "text": "pizza places in Indiranagar"}')
            context_parts.append('{"action": "wait_for", "selector": "div[role=\'article\']", "timeout": 20000}')
            context_parts.append('{"action": "extract", "schema": {...}, "limit": 10}')
            context_parts.append("")
            context_parts.append("GOOGLE MAPS SPECIFIC NOTES:")
            context_parts.append("- DO NOT create a 'click' action for search button - Enter is pressed automatically after typing")
            context_parts.append("- The 'type' action will automatically press Enter and wait for results on Google Maps")
            context_parts.append("- For 'wait_for', use container selectors NOT element selectors")
            context_parts.append("  ✅ Good: [data-result-index], div[role='article'], .section-result")
            context_parts.append("  ❌ Bad: .qBF1Pd, .MW4etd (these are element selectors inside containers)")
            context_parts.append("- Google Maps is a heavy SPA - navigation may timeout but page will still work")
            context_parts.append("- After type action, results will take 5-10 seconds to load, so wait_for timeout should be longer")
            context_parts.append("")
            context_parts.append("EXTRACTION SCHEMA for Google Maps:")
            context_parts.append('{')
            context_parts.append('  "name": ".qBF1Pd, h3, [aria-label*=\\"name\\"]",')
            context_parts.append('  "rating": ".MW4etd, [aria-label*=\\"star\\"], [aria-label*=\\"rating\\"]",')
            context_parts.append('  "location": ".W4Efsd, [class*=\\"address\\"]",')
            context_parts.append('  "url": "a[href*=\\"maps.google.com\\"], a[data-value]"')
            context_parts.append('}')
            
        elif target_platform == "zomato":
            context_parts.append("🍕 PLATFORM: Zomato (https://www.zomato.com)")
            context_parts.append("STRATEGY: Navigate to Zomato → Search for places → Extract restaurant listings")
            context_parts.append("⚠️ WARNING: Zomato may block automated access with HTTP2 errors")
            context_parts.append("If blocked, the system will offer Google Maps as an alternative")
            context_parts.append("Extraction: Look for restaurant cards, extract name, rating, location, cuisine")
            
        elif target_platform == "swiggy":
            context_parts.append("🛵 PLATFORM: Swiggy (https://www.swiggy.com)")
            context_parts.append("STRATEGY: Navigate to Swiggy → Search for places → Extract restaurant listings")
            context_parts.append("⚠️ WARNING: Swiggy may block automated access with HTTP2 errors")
            context_parts.append("If blocked, the system will offer Google Maps as an alternative")
            context_parts.append("Extraction: Look for restaurant cards, extract name, rating, delivery time")
        
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
            temperature=0.3,  # Balanced temperature for consistent yet flexible planning
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

