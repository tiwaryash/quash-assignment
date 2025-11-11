"""Filter and sort extracted results for various use cases."""

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
            price_str = re.sub(r'[^\d.]', '', str(price).replace(',', ''))
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

def get_top_results(results: list, limit: int = 3) -> list:
    """Get top N results sorted by rating."""
    # Filter out items with no name
    valid_results = [r for r in results if r.get('name') or r.get('title')]
    sorted_results = sort_results(valid_results, 'rating')
    return sorted_results[:limit]

