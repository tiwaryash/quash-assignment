"""Filter and sort extracted results for various use cases."""
import asyncio

def filter_by_price(results: list, max_price: float = None, min_price: float = None) -> list:
    """Filter results by price range."""
    import re
    
    filtered = []
    for item in results:
        price = item.get('price')
        if price is None:
            continue
        
        # Convert price to float, handling various formats
        price_float = None
        
        if isinstance(price, (int, float)):
            price_float = float(price)
        elif isinstance(price, str):
            # Remove all non-digit characters except decimal point
            # Handle Indian format: ₹1,25,999 or 1,25,999 or ₹125999
            price_clean = str(price).strip()
            # Remove currency symbols and commas
            price_clean = re.sub(r'[₹$€£,\s]', '', price_clean)
            # Extract only digits and decimal point
            price_str = re.sub(r'[^\d.]', '', price_clean)
            
            if price_str:
                try:
                    price_float = float(price_str)
                except (ValueError, TypeError):
                    # Try to extract first number found
                    numbers = re.findall(r'\d+\.?\d*', price_clean)
                    if numbers:
                        try:
                            price_float = float(numbers[0])
                        except (ValueError, TypeError):
                            continue
                    else:
                        continue
            else:
                continue
        
        # Apply filters
        if price_float is not None:
            if max_price and price_float > max_price:
                continue
            if min_price and price_float < min_price:
                continue
            
            # Update item with parsed price
            item['price'] = price_float
            filtered.append(item)
    
    return filtered

def filter_by_rating(results: list, min_rating: float = None) -> list:
    """Filter results by minimum rating."""
    if not min_rating:
        return results
    
    filtered = []
    for item in results:
        rating = item.get('rating')
        if rating is None:
            continue
        
        # Handle both string and numeric ratings
        if isinstance(rating, str):
            import re
            rating_match = re.search(r'(\d+\.?\d*)', str(rating))
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    continue
            else:
                continue
        
        if isinstance(rating, (int, float)) and rating >= min_rating:
            filtered.append(item)
    
    return filtered

def sort_results(results: list, sort_by: str = 'rating') -> list:
    """Sort results by rating (descending) or price (ascending)."""
    if sort_by == 'rating':
        return sorted(results, key=lambda x: x.get('rating') or 0, reverse=True)
    elif sort_by == 'price':
        return sorted(results, key=lambda x: x.get('price') or float('inf'))
    return results

def get_top_results(results: list, limit: int = None) -> list:
    """Get top N results sorted by rating. If limit is None, returns all results."""
    # Filter out items with no name
    valid_results = [r for r in results if r.get('name') or r.get('title')]
    sorted_results = sort_results(valid_results, 'rating')
    if limit is None:
        return sorted_results
    return sorted_results[:limit]

def extract_filter_options(results: list) -> dict:
    """Extract available filter options from product results.
    
    NOTE: This function only extracts memory/storage/size from product names.
    Colors should ONLY be extracted from product detail pages, not from names/URLs.
    
    Returns a dict with consolidated filter options (excluding colors - those come from pages).
    """
    import re
    
    filter_options = {
        "memory": set(),
        "storage": set(),
        "size": set(),
        "ram": set(),
        "other": set()
    }
    
    # Memory/storage patterns (in GB or TB)
    memory_pattern = r'(\d+)\s*(GB|TB|gb|tb)'
    
    # RAM patterns
    ram_pattern = r'(\d+)\s*GB\s*RAM'
    
    # Size patterns (for clothes, shoes, etc.)
    size_pattern = r'\b(XS|S|M|L|XL|XXL|\d+\.?\d*\s*(inch|inches|"|cm))\b'
    
    for item in results:
        name = item.get('name', '')
        
        if not name:
            continue
        
        name_lower = name.lower()
        
        # DO NOT extract colors from names/URLs - colors must come from product pages only
        # This prevents false positives like "blue" in "bluetooth" or "red" in "reduced"
        
        # Extract memory/storage
        memory_matches = re.findall(memory_pattern, name, re.IGNORECASE)
        for match in memory_matches:
            value, unit = match
            # Determine if it's RAM or storage based on context
            if 'ram' in name_lower:
                filter_options["ram"].add(f"{value}{unit.upper()}")
            else:
                # Check if it's likely storage (larger numbers) or memory
                if int(value) >= 64 or unit.upper() == 'TB':
                    filter_options["storage"].add(f"{value}{unit.upper()}")
                else:
                    filter_options["memory"].add(f"{value}{unit.upper()}")
        
        # Extract RAM specifically
        ram_matches = re.findall(ram_pattern, name, re.IGNORECASE)
        for match in ram_matches:
            filter_options["ram"].add(f"{match}GB")
        
        # Extract sizes
        size_matches = re.findall(size_pattern, name, re.IGNORECASE)
        for match in size_matches:
            if isinstance(match, tuple):
                filter_options["size"].add(match[0])
            else:
                filter_options["size"].add(match)
    
    # Convert sets to sorted lists and remove empty categories
    result = {}
    for key, values in filter_options.items():
        if values:
            # Sort values intelligently
            sorted_values = sorted(list(values), key=lambda x: (
                # For memory/storage, sort by numeric value
                int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0,
                x
            ))
            result[key] = sorted_values
    
    return result

def consolidate_filter_options(filter_options: dict) -> list:
    """Consolidate filter options into a list of user-friendly questions.
    
    Returns a list of filter dictionaries ready to be presented to the user.
    Only includes options that actually exist in the products.
    NOTE: Colors are excluded - removed per user request.
    """
    consolidated = []
    
    # Map internal keys to user-friendly labels
    filter_labels = {
        "memory": "Memory",
        "storage": "Storage",
        "size": "Size",
        "ram": "RAM",
        "other": "Options"
    }
    
    for key, values in filter_options.items():
        # Skip colors - removed per user request
        if key == "colors":
            continue
        
        # Only show if we have actual values (not empty) and multiple options
        # This ensures we only show filters for options that actually exist
        if values and len(values) > 1:
            # Remove duplicates and sort
            unique_values = sorted(list(set(values)))
            consolidated.append({
                "field": key,
                "label": filter_labels.get(key, key.title()),
                "options": unique_values,
                "type": "select"
            })
    
    return consolidated

def filter_by_product_relevance(results: list, query: str) -> list:
    """Filter results to keep only products relevant to the search query.
    
    Removes results that don't contain key brand/product terms from the query.
    Useful for removing off-brand results from e-commerce searches.
    
    Args:
        results: List of product results
        query: Original search query or product name
    
    Returns:
        Filtered list containing only relevant products
    """
    import re
    
    if not query:
        return results
    
    # Extract key brand/product terms (first 2-3 significant words)
    query_lower = query.lower()
    
    # Remove common filler words
    filler_words = ['find', 'show', 'me', 'best', 'cheapest', 'top', 'under', 'above', 'get', 'search', 'for', 'the', 'a', 'an']
    query_words = [w for w in query_lower.split() if w not in filler_words and len(w) > 2]
    
    # Take first 2-3 significant words as key terms (typically brand + product)
    key_terms = query_words[:3] if len(query_words) >= 3 else query_words[:2]
    
    if not key_terms:
        return results
    
    # Filter results
    filtered = []
    for item in results:
        name = item.get('name', '').lower()
        
        # Check if at least the first key term (usually brand) is present
        # For "MacBook Air M2", we require "macbook" to be present
        if key_terms and key_terms[0] in name:
            filtered.append(item)
        # Or if multiple key terms match (e.g., both "mac" and "air")
        elif len(key_terms) > 1:
            matches = sum(1 for term in key_terms if term in name)
            # Require at least 2 matches if we have multiple terms
            if matches >= 2:
                filtered.append(item)
    
    # If filtering removed too many results (>90%), return original
    # This prevents over-filtering on broad searches
    if len(filtered) < len(results) * 0.1 and len(results) > 5:
        return results
    
    return filtered if filtered else results


async def extract_variants_from_product_pages(browser_agent, product_urls: list, max_pages: int = 5) -> dict:
    """Dynamically extract available color/variant options by visiting product detail pages.
    
    This function visits actual product pages to find available variants (colors, sizes, etc.)
    that may not be visible in search results.
    
    Args:
        browser_agent: BrowserAgent instance to use for navigation
        product_urls: List of product URLs to check
        max_pages: Maximum number of product pages to visit (to avoid too many requests)
    
    Returns:
        Dict with extracted variant options (colors, storage, etc.)
    """
    if not browser_agent or not browser_agent.page:
        return {}
    
    variant_options = {
        "storage": set(),
        "memory": set(),
        "ram": set(),
        "size": set()
    }
    
    # Limit number of pages to visit
    urls_to_check = product_urls[:max_pages]
    
    for url in urls_to_check:
        try:
            # Navigate to product page
            nav_result = await browser_agent.navigate(url)
            if nav_result.get("status") != "success":
                continue
            
            # Wait for page to load
            await asyncio.sleep(2)
            
            # Extract variant options from the page
            page_variants = await browser_agent.page.evaluate("""
                () => {
                    const variants = {
                        storage: [],
                        memory: [],
                        ram: [],
                        size: []
                    };
                    
                    // Storage/Memory selectors
                    const storageSelectors = [
                        '[class*="storage"]',
                        '[class*="Storage"]',
                        '[class*="memory"]',
                        '[class*="Memory"]',
                        '[class*="RAM"]',
                        '[class*="ram"]',
                        'button[class*="storage"]',
                        'button[class*="memory"]'
                    ];
                    
                    // Try to find storage/memory options
                    for (const selector of storageSelectors) {
                        try {
                            const elements = document.querySelectorAll(selector);
                            elements.forEach(el => {
                                const text = el.textContent?.trim() || '';
                                // Look for patterns like "256GB", "512GB", "1TB", "8GB RAM", etc.
                                const storageMatch = text.match(/(\d+)\s*(GB|TB|gb|tb)/i);
                                if (storageMatch) {
                                    const value = storageMatch[1];
                                    const unit = storageMatch[2].toUpperCase();
                                    if (text.toLowerCase().includes('ram')) {
                                        variants.ram.push(value + unit);
                                    } else if (parseInt(value) >= 64 || unit === 'TB') {
                                        variants.storage.push(value + unit);
                                    } else {
                                        variants.memory.push(value + unit);
                                    }
                                }
                            });
                        } catch (e) {
                            continue;
                        }
                    }
                    
                    return variants;
                }
            """)
            
            # Add found variants to our set
            if page_variants:
                for key in variant_options:
                    if key in page_variants and isinstance(page_variants[key], list):
                        for item in page_variants[key]:
                            if item:
                                variant_options[key].add(str(item).strip())
            
        except Exception as e:
            # Continue to next URL if this one fails
            continue
    
    # Convert sets to sorted lists
    import re
    result = {}
    for key, values in variant_options.items():
        if values:
            # Sort intelligently
            sorted_values = sorted(list(values), key=lambda x: (
                int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0,
                x
            ))
            result[key] = sorted_values
    
    return result

def apply_variant_filters(results: list, filters: dict) -> list:
    """Filter results by variant options (color, memory, size, etc.)
    
    Args:
        results: List of product results
        filters: Dict of filter criteria, e.g. {"colors": "black", "storage": "256GB"}
                  Note: Use "colors" not "color" to match the filter_options keys
    
    Returns:
        Filtered list of results
    """
    if not filters:
        return results
    
    import re
    
    filtered = []
    for item in results:
        name = item.get('name', '').lower()
        url = str(item.get('url', '') or item.get('link', '')).lower()
        matches = True
        
        for filter_key, filter_value in filters.items():
            if not filter_value:
                continue
            
            filter_value_lower = str(filter_value).lower()
            
            # Skip color filters - removed per user request
            if filter_key in ["color", "colors"]:
                continue
            
            if filter_key in ['memory', 'storage', 'ram']:
                # For memory/storage, be more flexible (e.g., "256GB" matches "256 GB")
                match = re.search(r'(\d+)\s*(gb|tb)', filter_value_lower)
                if match:
                    value, unit = match.groups()
                    # Check for various formats: "256GB", "256 GB", "256gb"
                    pattern = rf'{value}\s*{unit}'
                    if not (re.search(pattern, name, re.IGNORECASE) or 
                            re.search(pattern, url, re.IGNORECASE)):
                        matches = False
                        break
                else:
                    matches = False
                    break
            else:
                # For other filters, check name and URL
                if filter_value_lower not in name and filter_value_lower not in url:
                    matches = False
                    break
        
        if matches:
            filtered.append(item)
    
    return filtered

