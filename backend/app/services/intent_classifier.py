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
        "comparison": True/False
    }
    """
    instruction_lower = instruction.lower()
    
    # Detect intent type
    intent = "general"
    domain = "general"
    
    # E-commerce / Product search
    ecommerce_keywords = ['flipkart', 'amazon', 'myntra', 'snapdeal', 'shop', 'buy', 'product', 
                          'laptop', 'phone', 'macbook', 'iphone', '₹', 'rupee', 'price', 
                          'under', 'above', 'compare', 'rating', 'delivery', 'purchase']
    if any(word in instruction_lower for word in ecommerce_keywords):
        intent = "product_search"
        domain = "ecommerce"
    
    # Form fill
    form_keywords = ['form', 'signup', 'register', 'login', 'submit', 'fill', 'field', 
                     'email', 'password', 'sign up', 'sign in']
    if any(word in instruction_lower for word in form_keywords):
        intent = "form_fill"
        domain = "forms"
    
    # Local discovery
    local_keywords = ['near', 'pizza', 'restaurant', 'place', 'location', 'delivery', 
                      'availability', 'indiranagar', 'nearby', 'local', 'find places']
    if any(word in instruction_lower for word in local_keywords):
        intent = "local_discovery"
        domain = "local"
    
    # Detect sites
    sites = []
    if 'flipkart' in instruction_lower:
        sites.append('flipkart')
    if 'amazon' in instruction_lower:
        sites.append('amazon')
    if 'myntra' in instruction_lower:
        sites.append('myntra')
    if 'snapdeal' in instruction_lower:
        sites.append('snapdeal')
    
    # If no site specified and e-commerce, default based on context
    if not sites and domain == "ecommerce":
        # Default to Flipkart for Indian market (₹), Amazon for international ($)
        if '₹' in instruction or 'rupee' in instruction_lower:
            sites.append('flipkart')
        elif '$' in instruction or 'dollar' in instruction_lower:
            sites.append('amazon')
        else:
            sites.append('flipkart')  # Default for Indian context
    
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
    comparison = any(word in instruction_lower for word in ['compare', 'best', 'across', 'multiple', 'both'])
    
    return {
        "intent": intent,
        "domain": domain,
        "sites": sites,
        "filters": filters,
        "extraction_fields": extraction_fields,
        "comparison": comparison
    }

