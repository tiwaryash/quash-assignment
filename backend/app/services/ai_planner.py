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
5. **GENERATES OPTIMIZED SEARCH QUERIES** for each site that fetch precise, on-point results

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

4. URL SEARCH
   - Search on a website and get URLs of results
   - Example: "Go to YouTube and search for a video and give me the URL"
   - Example: "Search on Google and give me the first result URL"
   - Strategy: Navigate → Type search → Click submit → Wait for results → Extract URLs (focus on first/top results)

5. GENERAL BROWSING
   - Navigate, extract content, interact with pages
   - Strategy: Analyze instruction → Determine actions → Execute → Extract

=== AVAILABLE ACTIONS ===

1. navigate
   {"action": "navigate", "url": "https://www.example.com"}
   - ALWAYS use REAL website URLs (never placeholders)
   - Wait for page load (system handles networkidle/domcontentloaded)

2. type
   {"action": "type", "selector": "input[name='q']", "text": "optimized search query"}
   - Types text into input field
   - For Google Maps: Automatically presses Enter after typing
   - Use stable selectors: id > name > placeholder > class
   - **IMPORTANT**: Generate an optimized, site-specific search query in the "text" field
   - Query should be concise, precise, and tailored to the target site's search algorithm
   - **DO NOT ADD INFORMATION**: Only use what the user mentioned, remove filler words
   - Examples:
     * User: "Find me the cheapest MacBook Air 13 inch under 1 lakh on Flipkart"
       Query for Flipkart: "MacBook Air 13 inch" (keep size user mentioned, remove filler words)
     * User: "Find MacBook Air"
       Query for Flipkart: "MacBook Air" (DON'T add "M2" or "13 inch" - user didn't mention them)
     * User: "Best pizza places in Indiranagar"
       Query for Google Maps: "pizza restaurants Indiranagar Bangalore" (add city for Maps only)

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

1. OPTIMIZED SEARCH QUERIES (FORMAT ONLY - DON'T ADD INFORMATION)
   - **CRITICAL**: Only optimize the FORMAT of the query, DO NOT add information that wasn't in the user's query
   - Extract ONLY what the user mentioned - don't add model numbers, years, or variants unless explicitly stated
   - Remove unnecessary words like "find", "search for", "best", "cheapest", "under X price"
   - Keep ONLY what user mentioned: brand, product name, size (if mentioned), location (if mentioned)
   - Examples:
     * User: "Find MacBook Air" → Query: "MacBook Air" 
     * User: "MacBook Air 13 inch" → Query: "MacBook Air 13 inch" (keep the size user mentioned)
     * User: "iPhone 15" → Query: "iPhone 15" 
     * User: "pizza places Indiranagar" → Query: "pizza restaurants Indiranagar Bangalore" (add city for Maps)
   - For Google Maps: You CAN add city name if only neighborhood is mentioned (helps with search)
   - For e-commerce: Keep it simple - just the product name user mentioned
   - Each site should get its own optimized query in the "text" field of type action

2. ROBUST WAITS & SELECTORS
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

URL SEARCH:
{
  "title": "selector for result title/name",
  "url": "selector for result link (a[href])"
}
Focus on extracting URLs - use site-specific selectors:
- YouTube: title: "#video-title", url: "a[href*='/watch']"
- Google: title: "h3", url: "a[href*='http']"
- Reddit: title: "h3", url: "a[href*='/r/']"

FORM RESULT:
{
  "status": "success|error",
  "message": "success/error message text",
  "redirect_url": "new URL after submission"
}

=== ACTION SEQUENCING PATTERNS ===

PRODUCT SEARCH:
1. navigate → e-commerce site URL
2. type → **OPTIMIZED search query for this specific site** (no wait_for needed after type)
3. click → submit button (type action may auto-press Enter, but click ensures submission)
4. wait_for → product containers (e.g., [data-id]) - WAIT AFTER CLICK, not after type
5. scroll → (optional, to load more results)
6. extract → with schema and limit (20+ for filtering)

IMPORTANT FOR PRODUCT SEARCH:
- DO NOT add wait_for after type action - type doesn't need waiting
- DO add wait_for AFTER click/submit - this is when results load
- Keep it simple: navigate → type → click → wait_for → scroll → extract

**Query Optimization Examples (FORMAT ONLY - NO ADDITIONS):**
- User: "Find MacBook Air under 1 lakh"
  * Flipkart query: "MacBook Air" (DON'T add "M2" or "13" - user didn't mention them)
  * Amazon query: "MacBook Air" (same - keep it simple)
- User: "MacBook Air 13 inch"
  * Flipkart query: "MacBook Air 13 inch" (keep size user mentioned)
- User: "Gaming laptops with RTX 4060"
  * Flipkart query: "gaming laptop RTX 4060" (keep what user mentioned)
  * Amazon query: "gaming laptop RTX 4060" (same - don't add "NVIDIA" unless user said it)

FORM FILLING:
1. navigate → form page URL
2. analyze_form → (detects all fields, automatically waits for form to load)
3. fill_form → (uses analyzed fields automatically)
4. submit → (optional selector, automatically detects result)

IMPORTANT FOR FORM FILLING:
- DO NOT add wait_for before analyze_form - analyze_form will wait for form fields automatically
- DO NOT add wait_for after submit - submit action already detects success/error messages and URL changes
- DO NOT add extract after submit - submit action already returns all submission details (URL, form data, response, messages)
- Keep it simple: navigate → analyze_form → fill_form → submit (4 actions only)

LOCAL DISCOVERY (Google Maps):
1. navigate → https://www.google.com/maps
2. type → **OPTIMIZED location search query** (auto-presses Enter)
3. wait_for → result containers (div[role='article'], timeout: 20000)
4. extract → name, rating, location, url

URL SEARCH (YouTube, Google, etc.):
1. navigate → website URL (e.g., https://www.youtube.com)
2. type → search query (auto-presses Enter for YouTube, like Google Maps)
3. wait_for → result containers (e.g., #contents ytd-video-renderer for YouTube, [data-ved] for Google)
4. extract → title, url (focus on URLs, extract first 5-10 results)

IMPORTANT FOR URL SEARCH:
- Focus on extracting URLs from search results
- Extract first 5-10 results (user usually wants top results)
- Use site-specific selectors for result containers and links
- For YouTube: NO click needed - type action auto-presses Enter (like Google Maps)
  * Result containers: #contents ytd-video-renderer
  * Links: a[href*='/watch'], #video-title-link
  * Title: #video-title, a#video-title
- For Google: click needed after type
  * Result containers: [data-ved], .g
  * Links: a[href*='http']

**Location Query Optimization:**
- User: "Pizza places near me" or "Find pizza in Indiranagar"
  * Query: "pizza restaurants Indiranagar Bangalore"
- User: "24/7 medical shops in Koramangala"
  * Query: "24 hour pharmacy Koramangala Bangalore"
- Include: business type + neighborhood + city for best results

=== SITE-SPECIFIC URLS ===
- Flipkart: https://www.flipkart.com
- Amazon: https://www.amazon.in
- Myntra: https://www.myntra.com
- Snapdeal: https://www.snapdeal.com
- Google Maps: https://www.google.com/maps
- Zomato: https://www.zomato.com
- Swiggy: https://www.swiggy.com
- YouTube: https://www.youtube.com
- Google: https://www.google.com
- Reddit: https://www.reddit.com
- Twitter/X: https://twitter.com or https://x.com

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
- Extract MORE items than requested for filtering
- **GENERATE OPTIMIZED SEARCH QUERIES** - Format optimization ONLY, don't add information!
  * Extract ONLY what user mentioned (brand, product name, size if mentioned, location if mentioned)
  * Remove filler words ("find", "show me", "best", "cheapest", "under X price")
  * DO NOT add model numbers, years, variants, or specs unless user explicitly mentioned them
  * Tailor query format to each site's search algorithm (but keep content same)
  * Example: User says "Find me cheapest MacBook Air under 1 lakh on Flipkart"
            → Your type action should have text: "MacBook Air"
            NOT "MacBook Air M2 13 inch" (user didn't mention M2 or 13 inch)
            NOT "cheapest MacBook Air under 1 lakh" (remove filler words)

=== QUERY GENERATION GUIDELINES ===

For PRODUCT SEARCH:
- Include: ONLY what user mentioned (Brand + Product Line + Size/Variant if user said it)
- Exclude: Price constraints, quality descriptors, action verbs
- DO NOT ADD: Model numbers, years, storage, RAM, colors unless user explicitly mentioned them
- Examples:
  * "Find best iPhone 15 under 80k" → "iPhone 15" (DON'T add "128GB" - user didn't say it)
  * "Show me laptops with 16GB RAM" → "laptop 16GB RAM" (keep RAM - user mentioned it)
  * "Gaming mouse under 3000" → "gaming mouse" (keep gaming - user mentioned it)
  * "MacBook Air" → "MacBook Air" (DON'T add "M2" or "13 inch")

For LOCAL DISCOVERY:
- Include: Business Type + Neighborhood + City
- Exclude: Qualifiers like "best", "top rated", distance
- Examples:
  * "Best pizza places near Indiranagar" → "pizza restaurants Indiranagar Bangalore"
  * "Find gyms in Koramangala" → "fitness gym Koramangala Bangalore"
  * "Coffee shops HSR Layout" → "coffee cafe HSR Layout Bangalore"

For COMPARISON (multiple sites):
- Generate a slightly different optimized query for EACH site
- Flipkart: simpler, direct keywords
- Amazon: include model numbers, years
- Google Maps: include area + city"""

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
        context_parts.append("2. Type product query into search box (no wait_for needed after type)")
        context_parts.append("3. Click search button (wait_for should come AFTER click, not after type)")
        context_parts.append("4. Wait for product results to load (wait_for [data-id] or similar container)")
        context_parts.append("5. Scroll down to load more products (optional)")
        context_parts.append("6. Extract 20+ products with name, price, rating, url")
        context_parts.append("7. System will auto-filter by price/rating and limit to requested count after extraction")
        context_parts.append("")
        context_parts.append("IMPORTANT: Do NOT add wait_for after type action. Add wait_for AFTER click/submit when results are loading.")
        context_parts.append("")
        context_parts.append("SITE-SPECIFIC URLS:")
        context_parts.append("- Flipkart: https://www.flipkart.com")
        context_parts.append("- Amazon: https://www.amazon.in")
        context_parts.append("- Myntra: https://www.myntra.com")
        context_parts.append("- Snapdeal: https://www.snapdeal.com")
        
    elif intent_info["intent"] == "form_fill":
        context_parts.append("Task: Fill out and submit a form")
        context_parts.append("Strategy: Navigate → Analyze form (LLM) → Fill fields → Submit")
        context_parts.append("IMPORTANT: For form filling, keep the plan SIMPLE - only 4 actions needed:")
        context_parts.append("1) navigate to URL")
        context_parts.append("2) analyze_form (automatically waits for form fields, no need for wait_for)")
        context_parts.append("3) fill_form (uses analyzed fields automatically)")
        context_parts.append("4) submit (automatically detects result, no need for wait_for or extract)")
        context_parts.append("")
        context_parts.append("DO NOT ADD:")
        context_parts.append("- wait_for before analyze_form (analyze_form handles waiting)")
        context_parts.append("- wait_for after submit (submit action already detects success/error)")
        context_parts.append("- extract after submit (submit action already returns all details)")
        context_parts.append("")
        context_parts.append("The analyze_form action will automatically detect all form fields and generate appropriate values (including temporary emails)")
        context_parts.append("The submit action automatically returns: submitted_url, redirected_url, form_data, response_data, and success/error messages")
        
    elif intent_info["intent"] == "url_search":
        context_parts.append("Task: Search on a website and get URLs of results")
        context_parts.append("Strategy: Navigate → Type search → Click submit → Wait for results → Extract URLs")
        context_parts.append("")
        context_parts.append("IMPORTANT: Focus on extracting URLs from search results")
        context_parts.append("Extract first 5-10 results (user usually wants top results)")
        context_parts.append("")
        context_parts.append("SITE-SPECIFIC GUIDANCE:")
        
        # Detect which site user wants
        instruction_lower = instruction.lower()
        if "youtube" in instruction_lower:
            context_parts.append("SITE: YouTube (https://www.youtube.com)")
            context_parts.append("Search input: input[name='search_query'] or #search")
            context_parts.append("IMPORTANT: YouTube auto-submits on Enter - NO click action needed after type")
            context_parts.append("The type action will automatically press Enter (like Google Maps)")
            context_parts.append("Result containers: #contents ytd-video-renderer")
            context_parts.append("Extraction schema: {{'title': '#video-title, a#video-title', 'url': 'a[href*=\\'/watch\\'], #video-title-link'}}")
            context_parts.append("Extract 5-10 video URLs")
            context_parts.append("")
            context_parts.append("ACTION SEQUENCE FOR YOUTUBE:")
            context_parts.append("1. navigate → https://www.youtube.com")
            context_parts.append("2. type → search query (Enter will be pressed automatically)")
            context_parts.append("3. wait_for → #contents ytd-video-renderer (wait for video results)")
            context_parts.append("4. extract → title, url (limit: 5-10)")
            context_parts.append("")
            context_parts.append("DO NOT add click action for YouTube - type action handles Enter automatically")
        elif "google" in instruction_lower and "maps" not in instruction_lower:
            context_parts.append("SITE: Google Search (https://www.google.com)")
            context_parts.append("Search input: input[name='q'], textarea[name='q']")
            context_parts.append("Search button: input[type='submit'], button[type='submit']")
            context_parts.append("Result containers: [data-ved], .g")
            context_parts.append("Extraction schema: {{'title': 'h3', 'url': 'a[href*=\\'http\\']'}}")
            context_parts.append("Extract 5-10 search result URLs")
        else:
            context_parts.append("SITE: Generic (extract from instruction)")
            context_parts.append("Use common search patterns:")
            context_parts.append("- Search input: input[name='q'], input[type='search'], input[placeholder*='Search']")
            context_parts.append("- Search button: button[type='submit'], button:has-text('Search')")
            context_parts.append("- Result containers: Look for result cards/items")
            context_parts.append("- Extraction schema: {{'title': 'h3, h2, .title', 'url': 'a[href]'}}")
        
        context_parts.append("")
        context_parts.append("ACTION SEQUENCE:")
        context_parts.append("1. navigate → website URL")
        context_parts.append("2. type → search query")
        context_parts.append("3. click → search button")
        context_parts.append("4. wait_for → result containers")
        context_parts.append("5. extract → title, url (limit: 5-10)")
        
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
            context_parts.append("STRATEGY: Swiggy requires a TWO-STEP search process:")
            context_parts.append("1. First, set the delivery location (left input box)")
            context_parts.append("2. Then, search for food/restaurants (right input box)")
            context_parts.append("3. Click 'Restaurants' filter button (not 'Dishes')")
            context_parts.append("4. Extract restaurant data")
            context_parts.append("")
            context_parts.append("SWIGGY-SPECIFIC ACTION SEQUENCE:")
            context_parts.append('{"action": "navigate", "url": "https://www.swiggy.com"}')
            context_parts.append('{"action": "type", "selector": "input[placeholder*=\\"location\\"], input[placeholder*=\\"Enter your delivery location\\"]", "text": "LOCATION_NAME"}')
            context_parts.append('{"action": "click", "selector": "div[class*=\\"_2BgUI\\"][role=\\"button\\"], div[tabindex=\\"0\\"]", "description": "Click first location suggestion (skip \\"Use my current location\\")"}')
            context_parts.append('{"action": "click", "selector": "div[type=\\"button\\"]:has-text(\\"Search for restaurant\\"), div:has-text(\\"Search for restaurant, item or more\\")", "description": "Open food search input"}')
            context_parts.append('{"action": "type", "selector": "input[placeholder*=\\"Search for restaurants\\"], input[placeholder*=\\"Search\\"]", "text": "FOOD_QUERY"}')
            context_parts.append('{"action": "click", "selector": "button:has-text(\\"Restaurants\\"), div:has-text(\\"Restaurants\\")", "description": "Filter by Restaurants (not Dishes)"}')
            context_parts.append('{"action": "wait_for", "selector": "a[data-testid=\\"resturant-card-anchor-container\\"], div[class*=\\"styles__cardContainer\\"]", "timeout": 15000}')
            context_parts.append('{"action": "extract", "schema": {...}, "limit": 10}')
            context_parts.append("")
            context_parts.append("IMPORTANT SWIGGY NOTES:")
            context_parts.append("- Location must be set FIRST before food search")
            context_parts.append("- Location input is usually the FIRST input on the page")
            context_parts.append("- After typing location, wait for suggestions dropdown, then click the FIRST actual location (skip 'Use my current location')")
            context_parts.append("- Food search input may need to be opened by clicking a search div/button first")
            context_parts.append("- Food search input is usually the SECOND input, or has placeholder containing 'Search for restaurants'")
            context_parts.append("- After typing food query, press Enter or wait for results")
            context_parts.append("- MUST click 'Restaurants' filter button to show only restaurants (not dishes)")
            context_parts.append("- Swiggy uses dynamic loading - wait_for should use container selectors")
            context_parts.append("- Note: Swiggy has a typo in data-testid: 'resturant' (not 'restaurant')")
            context_parts.append("")
            context_parts.append("EXTRACTION SCHEMA for Swiggy:")
            context_parts.append('{')
            context_parts.append('  "name": "a[data-testid=\\"resturant-card-anchor-container\\"] h3, ._1HEuF, [class*=\\"restaurantName\\"]",')
            context_parts.append('  "rating": "[class*=\\"rating\\"], ._9uwBC, [aria-label*=\\"star\\"]",')
            context_parts.append('  "cuisine": "[class*=\\"cuisine\\"], ._1heLw, [class*=\\"foodType\\"]",')
            context_parts.append('  "location": "[class*=\\"location\\"], ._1HEuF + div, [class*=\\"areaName\\"]",')
            context_parts.append('  "price": "[class*=\\"price\\"], ._1HEuF ~ div, [class*=\\"costForTwo\\"]",')
            context_parts.append('  "url": "a[data-testid=\\"resturant-card-anchor-container\\"], a[href*=\\"swiggy.com/restaurants\\"]"')
            context_parts.append('}')
            context_parts.append("")
            context_parts.append("QUERY OPTIMIZATION for Swiggy:")
            context_parts.append("- Location query: Extract location from user instruction (e.g., 'HSR Layout Bangalore', 'Indiranagar Bangalore')")
            context_parts.append("- Food query: Extract food item/type from user instruction (e.g., 'pizza', 'biryani', 'restaurants')")
            context_parts.append("- Remove filler words: 'best', 'top', 'places', 'restaurants' (unless user specifically wants restaurants)")
            context_parts.append("- If user says 'pizza places in HSR', location='HSR Layout Bangalore', food='pizza'")
            
        
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

