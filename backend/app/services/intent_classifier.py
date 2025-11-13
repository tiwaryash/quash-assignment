"""Intent classification and context detection for user instructions."""
import re
import json
from app.core.llm_provider import get_llm_provider
from app.core.logger import logger

# Cache for LLM provider to avoid repeated initialization
_llm_provider = None

def _get_llm_provider():
    """Get or initialize LLM provider."""
    global _llm_provider
    if _llm_provider is None:
        try:
            _llm_provider = get_llm_provider()
        except Exception as e:
            logger.warning(f"Failed to initialize LLM provider for intent classification: {e}")
            _llm_provider = None
    return _llm_provider

async def classify_intent_llm(instruction: str) -> dict:
    """
    Classify user intent using LLM for accurate understanding.
    Falls back to rule-based if LLM is unavailable.
    """
    llm_provider = _get_llm_provider()
    
    if llm_provider is None:
        # Fallback to rule-based classification
        logger.info("LLM provider not available, using rule-based intent classification")
        return _classify_intent_rule_based(instruction)
    
    try:
        prompt = f"""You are an expert intent classifier for a browser automation system. Analyze the user instruction and classify it accurately.

USER INSTRUCTION: "{instruction}"

=== INTENT CATEGORIES ===

1. PRODUCT_SEARCH
   - User wants to find, search, or buy products on e-commerce platforms
   - Examples: "Find MacBook Air under ₹1,00,000", "Compare laptops on Flipkart", "Search for iPhone on Amazon"
   - Keywords: laptop, phone, macbook, iphone, electronics, clothes, shoes, watch, gadget, appliance, buy, purchase, product, price, under, above
   - Sites: flipkart, amazon, myntra, snapdeal
   - Domain: "ecommerce"
   - Extraction fields: ["name", "price", "rating", "url"]

2. LOCAL_DISCOVERY
   - User wants to find local places, services, or businesses in a specific location
   - Examples: "Find top pizza places near Indiranagar", "Show me 24/7 open medical shops in Thane", "Best restaurants in HSR with 4★+ ratings"
   - Keywords: restaurant, cafe, pizza place, medical shop, pharmacy, chemist, hospital, clinic, gym, hotel, nearby, near me, in [location], at [location]
   - Time indicators: 24/7, 24x7, open now, open 24 hours, all night, round the clock
   - Services: medical, pharmacy, hospital, clinic, doctor, dentist, salon, spa, fitness, repair, service center, grocery, supermarket, store, shop (with location), outlet, showroom, atm, bank
   - Sites: zomato, swiggy, google_maps, google maps
   - Domain: "local"
   - Extraction fields: ["name", "rating", "location", "url"] (add "delivery_available" if delivery mentioned)

3. FORM_FILL
   - User wants to fill out and submit a form on a website
   - Examples: "Fill out the signup form on this URL", "Register with a temporary email", "Open this signup page and submit"
   - Keywords: form, signup, register, sign up, sign in, login, submit, fill out, create account
   - Domain: "forms"
   - Extraction fields: ["status", "message", "redirect_url"]

4. GENERAL
   - General browsing, navigation, extraction, or unclear intent
   - Examples: "Navigate to example.com", "Extract data from this page", vague or ambiguous queries
   - Domain: "general"
   - Extraction fields: ["title", "content", "url"]

=== CRITICAL CLASSIFICATION RULES ===

LOCAL_DISCOVERY vs PRODUCT_SEARCH:
- "shop" + location (e.g., "in Thane", "near me") = LOCAL_DISCOVERY (physical shop)
- "shop" + e-commerce context (buy, purchase, online, order) = PRODUCT_SEARCH
- "shop" alone = Check context - if ambiguous, prefer LOCAL_DISCOVERY if location mentioned
- Medical/pharmacy/hospital/clinic + location = LOCAL_DISCOVERY (always)
- Product names (laptop, phone) + price filters = PRODUCT_SEARCH
- Service keywords (medical, pharmacy, repair) + location = LOCAL_DISCOVERY

LOCATION DETECTION:
- Patterns: "in [location]", "near [location]", "at [location]", "nearby", "near me"
- Any location mention with service/place keywords = LOCAL_DISCOVERY

SITE DETECTION:
- E-commerce: flipkart, amazon, myntra, snapdeal
- Local discovery: zomato, swiggy, google_maps (or "google maps")
- Extract ALL mentioned sites into the sites array

FILTER EXTRACTION:
- Price filters: "under ₹X", "below ₹X", "less than ₹X", "upto ₹X", "max ₹X" → price_max
- Price filters: "above ₹X", "over ₹X", "minimum ₹X" → price_min
- Rating filters: "4★+", "4 star", "rating above 4" → rating_min
- Extract numeric values, remove currency symbols and commas

LIMIT EXTRACTION:
- Extract "top N", "first N", "N results", "give me N" → limit: N
- Examples: "top 3" → limit: 3, "first 5" → limit: 5, "give me 3" → limit: 3
- If no limit mentioned, use null/undefined (system will use default)
- Always extract the numeric value after "top", "first", or number before "results"

COMPARISON DETECTION:
- Keywords: "compare", "comparison", "versus", "vs", "across", "multiple sites", "both"
- Set comparison: true if any comparison keyword found
- If comparison and sites.length < 2: needs_clarification = true

CLARIFICATION NEEDED:
- needs_clarification = true if:
  * (intent == "product_search" OR intent == "local_discovery") AND sites.length == 0
  * comparison == true AND sites.length < 2
- Otherwise: needs_clarification = false

=== EXTRACTION FIELDS BY INTENT ===

PRODUCT_SEARCH: ["name", "price", "rating", "url"]
- Always include these 4 fields
- Add "link" if user mentions "link" or "url"

LOCAL_DISCOVERY: ["name", "rating", "location", "url"]
- Always include these 4 fields
- Add "delivery_available" if "delivery" mentioned in instruction

FORM_FILL: ["status", "message", "redirect_url"]
- Always include these 3 fields

GENERAL: ["title", "content", "url"]
- Default fields for general browsing

=== EXAMPLES ===

Example 1: "Find MacBook Air 13-inch under ₹1,00,000; give me top 3 with rating and links"
→ intent: "product_search", domain: "ecommerce", sites: [], filters: {{"price_max": 100000}}, needs_clarification: true

Example 2: "Compare the first three laptops under ₹60,000 on Flipkart"
→ intent: "product_search", domain: "ecommerce", sites: ["flipkart"], filters: {{"price_max": 60000}}, comparison: false, needs_clarification: false

Example 3: "Find top 3 pizza places near Indiranagar with 4★+ ratings"
→ intent: "local_discovery", domain: "local", sites: [], filters: {{"rating_min": 4}}, needs_clarification: true

Example 4: "Show me 24/7 open medical shops in Thane"
→ intent: "local_discovery", domain: "local", sites: [], filters: {{}}, needs_clarification: true

Example 5: "Fill out the signup form on this URL and submit"
→ intent: "form_fill", domain: "forms", sites: [], needs_clarification: false

Example 6: "Compare laptops on Flipkart and Amazon"
→ intent: "product_search", domain: "ecommerce", sites: ["flipkart", "amazon"], comparison: true, needs_clarification: false

=== OUTPUT FORMAT ===

Return ONLY valid JSON in this exact structure:
{{
    "intent": "product_search|local_discovery|form_fill|general",
    "domain": "ecommerce|local|forms|general",
    "sites": ["site1", "site2"] or [],
    "filters": {{"price_max": number, "price_min": number, "rating_min": number}} or {{}},
    "limit": number or null,
    "extraction_fields": ["field1", "field2", ...],
    "comparison": true or false,
    "needs_clarification": true or false
}}

IMPORTANT: 
- Return ONLY the JSON object, no markdown, no explanations
- Ensure all arrays are proper JSON arrays
- Ensure all objects are proper JSON objects
- Use null/empty for missing values, not undefined
- Be precise with intent classification - when in doubt between local_discovery and product_search, prefer local_discovery if location is mentioned"""

        response = await llm_provider.chat_completion(
            messages=[
                {
                    "role": "system", 
                    "content": """You are an expert Natural Language Understanding (NLU) system for a browser automation agent. 
Your task is to accurately classify user intent and extract all relevant parameters, targets, filters, and constraints.

Key responsibilities:
1. Classify intent into: product_search, local_discovery, form_fill, or general
2. Extract sites/platforms mentioned (e-commerce or local discovery platforms)
3. Extract filters (price ranges, rating thresholds)
4. Determine extraction fields needed based on intent
5. Detect comparison requests
6. Identify when clarification is needed

You must be precise and handle edge cases correctly. Always return valid, well-structured JSON with no markdown formatting."""
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for consistent, deterministic classification
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response)
        
        # Validate and normalize the response
        intent = result.get("intent", "general")
        if intent not in ["product_search", "local_discovery", "form_fill", "general"]:
            intent = "general"
        
        domain = result.get("domain", {
            "product_search": "ecommerce",
            "local_discovery": "local",
            "form_fill": "forms",
            "general": "general"
        }.get(intent, "general"))
        
        # Ensure sites is a list
        sites = result.get("sites", [])
        if not isinstance(sites, list):
            sites = []
        
        # Ensure filters is a dict
        filters = result.get("filters", {})
        if not isinstance(filters, dict):
            filters = {}
        
        # Ensure extraction_fields is a list and enhance based on instruction
        extraction_fields = result.get("extraction_fields", [])
        if not isinstance(extraction_fields, list) or len(extraction_fields) == 0:
            # Set defaults based on intent
            if intent == "product_search":
                extraction_fields = ["name", "price", "rating", "url"]
            elif intent == "local_discovery":
                extraction_fields = ["name", "rating", "location", "url"]
            elif intent == "form_fill":
                extraction_fields = ["status", "message", "redirect_url"]
            else:
                extraction_fields = ["title", "content", "url"]
        
        # Enhance extraction fields based on what user mentions
        instruction_lower = instruction.lower()
        if intent == "product_search":
            if "link" in instruction_lower or "url" in instruction_lower:
                if "url" not in extraction_fields and "link" not in extraction_fields:
                    extraction_fields.append("url")
            if "rating" in instruction_lower:
                if "rating" not in extraction_fields:
                    extraction_fields.append("rating")
        elif intent == "local_discovery":
            if "delivery" in instruction_lower:
                if "delivery_available" not in extraction_fields:
                    extraction_fields.append("delivery_available")
        
        # Validate and clean filters
        if isinstance(filters, dict):
            # Ensure numeric values are properly typed
            for key in ["price_max", "price_min", "rating_min"]:
                if key in filters:
                    try:
                        filters[key] = float(filters[key])
                    except (ValueError, TypeError):
                        del filters[key]
        else:
            filters = {}
        
        # Extract and validate limit
        limit = result.get("limit", None)
        if limit is not None:
            try:
                limit = int(float(limit))  # Handle both int and float strings
                if limit <= 0:
                    limit = None
            except (ValueError, TypeError):
                limit = None
        
        # If limit not extracted by LLM, try to extract from instruction
        if limit is None:
            import re
            # Patterns: "top 3", "first 3", "3 results", "give me 3", "top three"
            limit_patterns = [
                r'top\s+(\d+)',
                r'first\s+(\d+)',
                r'(\d+)\s+results?',
                r'give\s+me\s+(\d+)',
                r'get\s+me\s+(\d+)',
                r'show\s+me\s+(\d+)',
                r'(\d+)\s+items?',
                r'(\d+)\s+products?',
                r'(\d+)\s+places?'
            ]
            instruction_lower = instruction.lower()
            for pattern in limit_patterns:
                match = re.search(pattern, instruction_lower)
                if match:
                    try:
                        limit = int(match.group(1))
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Determine if clarification is needed (override LLM decision if needed)
        needs_clarification = result.get("needs_clarification", False)
        # Re-validate clarification logic
        if not sites:
            if domain == "ecommerce" or domain == "local":
                needs_clarification = True
        
        comparison = result.get("comparison", False)
        if isinstance(comparison, str):
            comparison = comparison.lower() in ["true", "1", "yes"]
        if comparison and len(sites) < 2:
            needs_clarification = True
        
        return {
            "intent": intent,
            "domain": domain,
            "sites": sites,
            "filters": filters,
            "limit": limit,
            "extraction_fields": extraction_fields,
            "comparison": comparison,
            "needs_clarification": needs_clarification
        }
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}. Falling back to rule-based classification.")
        return _classify_intent_rule_based(instruction)
    except Exception as e:
        logger.warning(f"LLM intent classification failed: {e}. Falling back to rule-based classification.")
        return _classify_intent_rule_based(instruction)

def _classify_intent_rule_based(instruction: str) -> dict:
    """
    Rule-based intent classification (fallback when LLM is unavailable).
    """
    instruction_lower = instruction.lower()
    
    # Detect intent type with priority scoring
    intent_scores = {
        "form_fill": 0,
        "local_discovery": 0,
        "product_search": 0,
        "general": 0
    }
    
    # Form fill - highest priority keywords (if present, usually means form)
    form_keywords = ['form', 'signup', 'register', 'sign up', 'sign in', 'login', 'submit', 'fill out']
    for keyword in form_keywords:
        if keyword in instruction_lower:
            intent_scores["form_fill"] += 10
    
    # Local discovery - strong indicators (restaurants, places, nearby)
    local_strong_keywords = ['restaurant', 'pizza place', 'coffee shop', 'cafe', 'hotel', 'gym', 
                             'nearby', 'near me', 'in indiranagar', 'in hsr', 'in bangalore',
                             'in koramangala', 'find places', 'best places', 'medical shop', 
                             'pharmacy', 'chemist', 'hospital', 'clinic', 'doctor', 'dentist',
                             'grocery shop', 'supermarket', 'store', 'atm', 'bank']
    for keyword in local_strong_keywords:
        if keyword in instruction_lower:
            intent_scores["local_discovery"] += 8
    
    # Local discovery - medium indicators
    local_medium_keywords = ['place', 'location', 'area', 'delivery available', 'open now', 
                            'open', '24/7', '24x7', '24 hours', 'all night', 'round the clock']
    for keyword in local_medium_keywords:
        if keyword in instruction_lower:
            intent_scores["local_discovery"] += 3
    
    # Check for location pattern: "in [location]" or "near [location]" - flexible pattern matching
    location_patterns = [
        r'\bin\s+([a-z]+)',  # "in thane", "in mumbai", etc.
        r'\bnear\s+([a-z]+)',  # "near thane", "near station", etc.
        r'\bat\s+([a-z]+)',  # "at thane", "at mall", etc.
    ]
    for pattern in location_patterns:
        if re.search(pattern, instruction_lower):
            intent_scores["local_discovery"] += 6
            break
    
    # Service-related keywords that indicate local discovery (not e-commerce)
    service_keywords = ['medical', 'pharmacy', 'chemist', 'hospital', 'clinic', 'doctor', 
                       'dentist', 'salon', 'spa', 'gym', 'fitness', 'repair', 'service center',
                       'grocery', 'supermarket', 'store', 'shop', 'outlet', 'showroom']
    # If service keyword is present AND location is mentioned, it's definitely local discovery
    has_service_keyword = any(keyword in instruction_lower for keyword in service_keywords)
    has_location = any(re.search(pattern, instruction_lower) for pattern in location_patterns)
    if has_service_keyword and has_location:
        intent_scores["local_discovery"] += 10  # Very strong indicator
    elif has_service_keyword and not any(site in instruction_lower for site in ['flipkart', 'amazon', 'myntra', 'snapdeal']):
        # Service keyword without e-commerce site = likely local discovery
        intent_scores["local_discovery"] += 5
    
    # Food-related words strongly suggest local discovery unless e-commerce site mentioned
    food_keywords = ['pizza', 'burger', 'food', 'restaurant', 'dine', 'eat', 'meal']
    if any(keyword in instruction_lower for keyword in food_keywords):
        # Check if e-commerce site is mentioned
        if not any(site in instruction_lower for site in ['flipkart', 'amazon', 'myntra', 'snapdeal']):
            intent_scores["local_discovery"] += 6
    
    # E-commerce / Product search - strong indicators
    ecommerce_strong_keywords = ['laptop', 'phone', 'macbook', 'iphone', 'electronics', 
                                'clothes', 'shoe', 'watch', 'gadget', 'appliance',
                                'flipkart', 'amazon', 'myntra', 'snapdeal']
    for keyword in ecommerce_strong_keywords:
        if keyword in instruction_lower:
            intent_scores["product_search"] += 8
    
    # E-commerce - medium indicators
    # Note: "shop" is context-dependent - if it's with location/service keywords, it's local discovery
    ecommerce_medium_keywords = ['buy', 'purchase', 'product', 'price', 'under', 'above', '₹', '$']
    # Only add "shop" to e-commerce if it's clearly about online shopping (with buy/purchase/product)
    has_ecommerce_context = any(word in instruction_lower for word in ['buy', 'purchase', 'online', 'order', 'cart'])
    if has_ecommerce_context and 'shop' in instruction_lower:
        intent_scores["product_search"] += 3
    elif 'shop' in instruction_lower and not has_ecommerce_context:
        # "shop" without e-commerce context might be local discovery (physical shop)
        # Don't add to product_search, let local discovery keywords handle it
        pass
    
    for keyword in ecommerce_medium_keywords:
        if keyword in instruction_lower:
            intent_scores["product_search"] += 3
    
    # Determine final intent based on scores
    max_score = max(intent_scores.values())
    if max_score == 0:
        intent = "general"
    else:
        intent = max(intent_scores, key=intent_scores.get)
    
    domain = {
        "product_search": "ecommerce",
        "form_fill": "forms",
        "local_discovery": "local",
        "general": "general"
    }[intent]
    
    # Detect sites
    sites = []
    needs_clarification = False
    
    # E-commerce sites
    if 'flipkart' in instruction_lower:
        sites.append('flipkart')
    if 'amazon' in instruction_lower:
        sites.append('amazon')
    if 'myntra' in instruction_lower:
        sites.append('myntra')
    if 'snapdeal' in instruction_lower:
        sites.append('snapdeal')
    
    # Local discovery sites/services
    if 'zomato' in instruction_lower:
        sites.append('zomato')
    if 'swiggy' in instruction_lower:
        sites.append('swiggy')
    if 'google maps' in instruction_lower or 'maps.google' in instruction_lower:
        sites.append('google_maps')
    
    # If no site specified, mark as needing clarification
    if not sites:
        if domain == "ecommerce":
            # For e-commerce without site, ask user which site to use
            needs_clarification = True
        elif domain == "local":
            # For local discovery without site, ask user which platform
            needs_clarification = True
    
    # Extract filters
    # Price filters - check for "under", "below", "less than", "upto", "max"
    filters = {}
    if any(keyword in instruction_lower for keyword in ['under', 'below', 'less than', 'upto', 'upto', 'max', 'maximum']):
        price_match = re.search(r'[₹$]?\s*([\d,]+)', instruction)
        if price_match:
            try:
                filters['price_max'] = float(price_match.group(1).replace(',', ''))
            except:
                pass
    
    if 'above' in instruction_lower or 'over' in instruction_lower:
        price_match = re.search(r'[₹$]?\s*([\d,]+)', instruction)
        if price_match:
            try:
                filters['price_min'] = float(price_match.group(1).replace(',', ''))
            except:
                pass
    
    # Rating filters
    rating_match = re.search(r'(\d+)\s*[★⭐]', instruction_lower)
    if rating_match:
        try:
            filters['rating_min'] = float(rating_match.group(1))
        except:
            pass
    
    # Extract limit (top N, first N, etc.)
    limit = None
    limit_patterns = [
        r'top\s+(\d+)',
        r'first\s+(\d+)',
        r'(\d+)\s+results?',
        r'give\s+me\s+(\d+)',
        r'get\s+me\s+(\d+)',
        r'show\s+me\s+(\d+)',
        r'(\d+)\s+items?',
        r'(\d+)\s+products?',
        r'(\d+)\s+places?'
    ]
    for pattern in limit_patterns:
        match = re.search(pattern, instruction_lower)
        if match:
            try:
                limit = int(match.group(1))
                break
            except (ValueError, TypeError):
                continue
    
    # Determine extraction fields based on intent
    extraction_fields = []
    if intent == "product_search":
        extraction_fields = ["name", "price", "rating", "url"]
        # Add fields based on what user mentions
        if 'rating' in instruction_lower:
            extraction_fields.append("rating")
        if 'link' in instruction_lower or 'url' in instruction_lower:
            extraction_fields.append("url")
    elif intent == "local_discovery":
        extraction_fields = ["name", "rating", "location", "url"]
        if 'delivery' in instruction_lower:
            extraction_fields.append("delivery_available")
    elif intent == "form_fill":
        extraction_fields = ["status", "message", "redirect_url"]
    else:
        # General extraction - let LLM decide
        extraction_fields = ["title", "content", "url"]
    
    # Check for comparison
    comparison = any(word in instruction_lower for word in ['compare', 'comparison', 'versus', 'vs', 'across', 'multiple sites', 'both'])
    
    # If user wants comparison but only specified one site or none, need clarification
    if comparison and len(sites) < 2:
        needs_clarification = True
    
    return {
        "intent": intent,
        "domain": domain,
        "sites": sites,
        "filters": filters,
        "limit": limit,
        "extraction_fields": extraction_fields,
        "comparison": comparison,
        "needs_clarification": needs_clarification
    }

# Main function - use async LLM classification
def classify_intent(instruction: str) -> dict:
    """
    Classify user intent and extract context.
    This is a synchronous wrapper that uses rule-based classification.
    For async LLM-based classification, use classify_intent_llm().
    
    Returns: {
        "intent": "product_search" | "form_fill" | "local_discovery" | "general",
        "domain": "ecommerce" | "forms" | "local" | "general",
        "sites": ["flipkart", "amazon", ...],
        "filters": {"price_max": 100000, "rating_min": 4.0, ...},
        "extraction_fields": ["name", "price", "rating", "url"],
        "comparison": True/False,
        "needs_clarification": True/False
    }
    """
    # Use rule-based for synchronous calls (backward compatibility)
    return _classify_intent_rule_based(instruction)
