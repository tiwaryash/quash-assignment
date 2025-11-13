from app.core.config import settings
from app.core.llm_provider import get_llm_provider
from app.core.logger import logger
from app.services.intent_classifier import classify_intent, classify_intent_llm
import json

# Initialize LLM provider
try:
    llm_provider = get_llm_provider()
except Exception as e:
    logger.error(f"Failed to initialize LLM provider: {e}")
    llm_provider = None

SYSTEM_PROMPT = """You are an expert browser automation planner for an AI-powered conversational browser control agent. Your role is to convert natural language instructions into structured, executable action plans.

=== YOUR MISSION ===
Transform user instructions into a JSON action plan that:
1. Extracts intent, parameters, targets, filters, and constraints (per assignment NLU requirements)
2. Creates robust action sequences with proper waits and error handling
3. Generates extraction schemas that return structured JSON data
4. Handles multiple task types: product search, form filling, local discovery, general browsing

=== TASK TYPES ===

1. PRODUCT SEARCH
   - Find/buy products on e-commerce platforms (Flipkart, Amazon, Myntra, Snapdeal)
   - Example: "Find MacBook Air 13-inch under ₹1,00,000; give me top 3 with rating and links"
   - Example: "Compare the first three laptops under ₹60,000 on Flipkart"
   - Strategy: Navigate → Type search query → Submit → Wait for results → Extract (20+ items) → Filter by price/rating

2. FORM FILLING
   - Fill out and submit forms on websites
   - Example: "Open this signup page and register with a temporary email"
   - Example: "Fill out the signup form on this URL and submit"
   - Strategy: Navigate → Wait for form → Analyze form (LLM) → Fill fields → Submit → Wait for result → Extract status

3. LOCAL DISCOVERY
   - Find local places, services, restaurants in specific locations
   - Example: "Find top 3 pizza places near Indiranagar with 4★+ ratings"
   - Example: "Show me 24/7 open medical shops in Thane"
   - Strategy: Navigate to Google Maps/Zomato/Swiggy → Search → Wait for results → Extract name, rating, location, url

4. GENERAL BROWSING
   - Navigate, extract content, interact with pages
   - Strategy: Analyze instruction → Determine actions → Execute → Extract

=== AVAILABLE ACTIONS ===

1. navigate
   {"action": "navigate", "url": "https://www.example.com"}
   - ALWAYS use REAL website URLs (never placeholders)
   - Wait for page load (system handles networkidle/domcontentloaded)

2. type
   {"action": "type", "selector": "input[name='q']", "text": "search query"}
   - Types text into input field
   - For Google Maps: Automatically presses Enter after typing
   - Use stable selectors: id > name > placeholder > class

3. click
   {"action": "click", "selector": "button[type='submit']"}
   - Clicks an element
   - System will try fallback selectors if primary fails

4. wait_for
   {"action": "wait_for", "selector": "[data-id]", "timeout": 15000}
   - Waits for element to appear (default timeout: 5000ms)
   - Use container selectors for dynamic content (e.g., div[role='article'])
   - For Google Maps: Use longer timeouts (15000-20000ms) and container selectors

5. scroll
   {"action": "scroll"}
   - Scrolls to bottom to load more content
   - Use after initial results load to get more items

6. analyze_form
   {"action": "analyze_form"}
   - Analyzes form fields on page using LLM
   - MUST be used BEFORE fill_form
   - Automatically detects fields and generates values (including temp emails)

7. fill_form
   {"action": "fill_form", "fields": {"email": {"selector": "input[type='email']", "value": "temp@example.com"}}}
   - Fills form fields with provided values
   - Use after analyze_form (analyzed fields are used automatically)

8. submit
   {"action": "submit", "selector": "button[type='submit']"}
   - Submits a form (selector is optional, system will find submit button)

9. extract
   {"action": "extract", "limit": 10, "schema": {"name": "selector", "price": "selector", "rating": "selector", "url": "selector"}}
   - Extracts structured data from page
   - limit: Number of items to extract (extract MORE than requested for filtering)
   - schema: Object mapping field names to CSS selectors

=== CRITICAL PLANNING PRINCIPLES ===

1. ROBUST WAITS & SELECTORS
   - Always wait_for results before extracting
   - Use container selectors (e.g., [data-id], div[role='article']) not individual elements
   - Prefer stable selectors: data-testid > role > id > name > class
   - System has automatic fallback selectors, but provide good primary selectors

2. EXTRACTION STRATEGY
   - For price filters: Extract 20+ items, system filters after extraction
   - For top N requests: Extract more than N (e.g., extract 20 to get top 3)
   - Use generic selectors that work across sites when possible
   - Schema should match extraction_fields from intent classification

3. MULTI-SITE COMPARISON
   - Create separate action sequences for EACH site
   - Each site: navigate → search → extract
   - All actions in single "actions" array (system handles sequencing)

4. FORM HANDLING
   - ALWAYS use analyze_form BEFORE fill_form
   - After submit: Wait for URL change OR use generic selectors ([role='alert'], .message)
   - Don't use hardcoded success selectors (pages vary)

5. GOOGLE MAPS SPECIFICS
   - URL: https://www.google.com/maps
   - Search input: input#searchboxinput
   - NO click action needed - type action auto-presses Enter
   - Wait for containers: [data-result-index], div[role='article'], .section-result
   - Use longer timeouts (15000-20000ms) - Maps is a heavy SPA
   - Navigation may timeout but page still works

=== SELECTOR GUIDELINES ===

SEARCH INPUTS (priority order):
- input[name='q'], input[type='search'], input[placeholder*='Search']
- [role='searchbox'], textarea[name='q']
- input#searchboxinput (Google Maps)

SUBMIT BUTTONS:
- button[type='submit'], input[type='submit']
- button:has-text('Search'), [aria-label*='Search']

PRODUCT CONTAINERS:
- [data-id] (Flipkart), [data-component-type='s-search-result'] (Amazon)
- .product, .item, [class*='product']

PRICES:
- .a-price-whole (Amazon), ._30jeq3 (Flipkart)
- [class*='price'], [data-price]

RATINGS:
- [aria-label*='star'], .a-icon-alt (Amazon), ._3LWZlK (Flipkart)
- [class*='rating']

LINKS:
- a[href*='/p/'] (Flipkart), a[href*='/dp/'] (Amazon)
- a[href*='/product'], a.product-link

LOCAL DISCOVERY (Google Maps):
- name: .qBF1Pd, h3, [aria-label*='name']
- rating: .MW4etd, [aria-label*='star'], [aria-label*='rating']
- location: .W4Efsd, [class*='address']
- url: a[href*='maps.google.com'], a[href*='/maps/place']

=== EXTRACTION SCHEMA PATTERNS ===

PRODUCT SEARCH:
{
  "name": "selector for product name",
  "price": "selector for price",
  "rating": "selector for rating",
  "url": "selector for product link"
}

LOCAL DISCOVERY:
{
  "name": "selector for place name",
  "rating": "selector for rating",
  "location": "selector for address/location",
  "url": "selector for place link"
}
Add "delivery_available" if delivery mentioned.

FORM RESULT:
{
  "status": "success|error",
  "message": "success/error message text",
  "redirect_url": "new URL after submission"
}

=== ACTION SEQUENCING PATTERNS ===

PRODUCT SEARCH:
1. navigate → e-commerce site URL
2. wait_for → search input (optional, but good practice)
3. type → search query
4. click → submit button OR type action handles Enter
5. wait_for → product containers (e.g., [data-id])
6. scroll → (optional, to load more)
7. extract → with schema and limit (20+ for filtering)

FORM FILLING:
1. navigate → form page URL
2. wait_for → form fields (e.g., input[type='email'])
3. analyze_form → (detects all fields)
4. fill_form → (uses analyzed fields automatically)
5. submit → (optional selector)
6. wait_for → result indicator (URL change OR [role='alert'])
7. extract → status, message, redirect_url

LOCAL DISCOVERY (Google Maps):
1. navigate → https://www.google.com/maps
2. type → search query (auto-presses Enter)
3. wait_for → result containers (div[role='article'], timeout: 20000)
4. extract → name, rating, location, url

=== SITE-SPECIFIC URLS ===
- Flipkart: https://www.flipkart.com
- Amazon: https://www.amazon.in
- Myntra: https://www.myntra.com
- Snapdeal: https://www.snapdeal.com
- Google Maps: https://www.google.com/maps
- Zomato: https://www.zomato.com
- Swiggy: https://www.swiggy.com

=== ERROR HANDLING ===
- System has automatic retries and fallback selectors
- Provide good primary selectors, system handles failures
- Use container selectors for dynamic content
- Longer timeouts for heavy SPAs (Google Maps, etc.)

=== OUTPUT FORMAT ===
Return ONLY valid JSON in this exact structure:
{
  "actions": [
    {"action": "navigate", "url": "https://..."},
    {"action": "type", "selector": "...", "text": "..."},
    {"action": "wait_for", "selector": "...", "timeout": 15000},
    {"action": "extract", "limit": 20, "schema": {...}}
  ]
}

CRITICAL:
- Return ONLY the JSON object, no markdown, no explanations
- All actions must be in the "actions" array
- Use real URLs, not placeholders
- Include proper waits before extraction
- Extract MORE items than requested for filtering"""

async def create_action_plan(instruction: str) -> list[dict]:
    """Convert natural language instruction to a JSON action plan using intent classification."""
    if not llm_provider:
        raise ValueError("LLM provider not configured. Please set API keys in .env file")
    
    logger.info(f"Creating action plan for instruction: {instruction[:100]}...")
    
    # Classify intent and extract context using LLM for better accuracy
    try:
        intent_info = await classify_intent_llm(instruction)
    except Exception as e:
        logger.warning(f"LLM classification failed, using rule-based: {e}")
        intent_info = classify_intent(instruction)
    
    # Build enhanced instruction with context
    context_parts = []
    
    if intent_info["intent"] == "product_search":
        context_parts.append(f"Task: E-commerce product search")
        
        # Site information
        if intent_info["sites"]:
            sites_str = " and ".join([s.capitalize() for s in intent_info["sites"]])
            context_parts.append(f"Target sites: {sites_str}")
            
            # If multiple sites, explain comparison flow
            if len(intent_info["sites"]) > 1 or intent_info["comparison"]:
                context_parts.append("COMPARISON MODE: Search on EACH site separately")
                context_parts.append("For each site:")
                context_parts.append("  1. Navigate to the site")
                context_parts.append("  2. Search for product")
                context_parts.append("  3. Extract results")
                context_parts.append("  4. Move to next site")
                context_parts.append("Create action sequences for EACH site in the 'actions' array")
        
        # Filter information
        if intent_info["filters"].get("price_max"):
            context_parts.append(f"Price filter: under ₹{intent_info['filters']['price_max']:,.0f}")
            context_parts.append("Extract MORE results (20+) first, then filter by price")
        if intent_info["filters"].get("rating_min"):
            context_parts.append(f"Rating filter: minimum {intent_info['filters']['rating_min']} stars")
        
        # Limit information
        requested_limit = intent_info.get("limit")
        if requested_limit:
            context_parts.append(f"User requested: TOP {requested_limit} results")
            context_parts.append(f"IMPORTANT: Extract 20+ items, but system will filter to top {requested_limit} after extraction")
        else:
            context_parts.append("No specific limit requested - extract reasonable number (10-20 items)")
        
        context_parts.append(f"Extract fields: {', '.join(intent_info['extraction_fields'])}")
        context_parts.append("")
        context_parts.append("STRATEGY:")
        context_parts.append("1. Navigate to e-commerce site (e.g., https://www.flipkart.com)")
        context_parts.append("2. Type product query into search box")
        context_parts.append("3. Click search button or press Enter")
        context_parts.append("4. Wait for product results to load")
        context_parts.append("5. Scroll down to load more products (optional)")
        context_parts.append("6. Extract 20+ products with name, price, rating, url")
        context_parts.append("7. System will auto-filter by price/rating and limit to requested count after extraction")
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
        
        # Limit information
        requested_limit = intent_info.get("limit")
        if requested_limit:
            context_parts.append(f"User requested: TOP {requested_limit} results")
            context_parts.append(f"IMPORTANT: Extract more items (10-15), but system will filter to top {requested_limit} after extraction")
        else:
            context_parts.append("No specific limit requested - extract reasonable number (5-10 items)")
        
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
            context_parts.append("PLATFORM: Google Maps (https://www.google.com/maps)")
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
            context_parts.append("  Good: [data-result-index], div[role='article'], .section-result")
            context_parts.append("  Bad: .qBF1Pd, .MW4etd (these are element selectors inside containers)")
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
            context_parts.append("PLATFORM: Zomato (https://www.zomato.com)")
            context_parts.append("STRATEGY: Navigate to Zomato → Search for places → Extract restaurant listings")
            context_parts.append("WARNING: Zomato may block automated access with HTTP2 errors")
            context_parts.append("If blocked, the system will offer Google Maps as an alternative")
            context_parts.append("Extraction: Look for restaurant cards, extract name, rating, location, cuisine")
            
        elif target_platform == "swiggy":
            context_parts.append("PLATFORM: Swiggy (https://www.swiggy.com)")
            context_parts.append("STRATEGY: Navigate to Swiggy → Search for places → Extract restaurant listings")
            context_parts.append("WARNING: Swiggy may block automated access with HTTP2 errors")
            context_parts.append("If blocked, the system will offer Google Maps as an alternative")
            context_parts.append("Extraction: Look for restaurant cards, extract name, rating, delivery time")
        
    else:
        context_parts.append("Task: General browser automation")
        context_parts.append("Strategy: Analyze instruction and determine appropriate actions")
    
    enhanced_instruction = f"{instruction}\n\nContext:\n" + "\n".join(f"- {part}" for part in context_parts)
    
    try:
        result = await llm_provider.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": enhanced_instruction}
            ],
            temperature=0.3,  # Balanced temperature for consistent yet flexible planning
            response_format={"type": "json_object"}
        )
        
        parsed = json.loads(result)
        logger.debug(f"LLM response parsed successfully")
        
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
        
        logger.info(f"Created action plan with {len(actions)} actions")
        return actions
            
    except Exception as e:
        logger.error(f"Error creating plan: {e}")
        return []

