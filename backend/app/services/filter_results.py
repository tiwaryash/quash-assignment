"""Filter and sort extracted results for various use cases."""

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

def get_top_results(results: list, limit: int = 3) -> list:
    """Get top N results sorted by rating."""
    # Filter out items with no name
    valid_results = [r for r in results if r.get('name') or r.get('title')]
    sorted_results = sort_results(valid_results, 'rating')
    return sorted_results[:limit]

