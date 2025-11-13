"""Intent classification and context detection for user instructions."""

def classify_intent(instruction: str) -> dict:
    """
    Classify user intent and extract context.
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
                             'in koramangala', 'find places', 'best places']
    for keyword in local_strong_keywords:
        if keyword in instruction_lower:
            intent_scores["local_discovery"] += 8
    
    # Local discovery - medium indicators
    local_medium_keywords = ['place', 'location', 'area', 'delivery available', 'open now']
    for keyword in local_medium_keywords:
        if keyword in instruction_lower:
            intent_scores["local_discovery"] += 3
    
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
    ecommerce_medium_keywords = ['buy', 'purchase', 'shop', 'product', 'price', 'under', 'above', '₹', '$']
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
    filters = {}
    import re
    
    # Price filters
    if 'under' in instruction_lower or 'below' in instruction_lower:
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
        "extraction_fields": extraction_fields,
        "comparison": comparison,
        "needs_clarification": needs_clarification
    }

