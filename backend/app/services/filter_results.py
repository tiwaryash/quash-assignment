"""Filter and sort extracted product results."""

def filter_by_price(results: list, max_price: float = None, min_price: float = None) -> list:
    """Filter results by price range."""
    filtered = []
    for item in results:
        price = item.get('price')
        if price is None:
            continue
        
        # Handle both string and numeric prices
        if isinstance(price, str):
            import re
            price_str = re.sub(r'[^\d.]', '', str(price))
            try:
                price = float(price_str)
            except:
                continue
        
        if isinstance(price, (int, float)):
            if max_price and price > max_price:
                continue
            if min_price and price < min_price:
                continue
            item['price'] = price
            filtered.append(item)
    
    return filtered

def sort_results(results: list, sort_by: str = 'rating') -> list:
    """Sort results by rating (descending) or price (ascending)."""
    if sort_by == 'rating':
        return sorted(results, key=lambda x: x.get('rating') or 0, reverse=True)
    elif sort_by == 'price':
        return sorted(results, key=lambda x: x.get('price') or float('inf'))
    return results

def get_top_results(results: list, limit: int = 3) -> list:
    """Get top N results sorted by rating."""
    # Filter out items with no name or price
    valid_results = [r for r in results if r.get('name') and r.get('price')]
    sorted_results = sort_results(valid_results, 'rating')
    return sorted_results[:limit]

