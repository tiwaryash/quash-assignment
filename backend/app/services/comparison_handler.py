"""Handler for multi-site comparison workflows."""

from typing import List, Dict, Any
from app.services.browser_agent import BrowserAgent
from app.core.logger import logger
import asyncio

class ComparisonHandler:
    """Handles multi-site product comparison logic."""
    
    def __init__(self, agent: BrowserAgent):
        self.agent = agent
        self.comparison_results = {}
    
    async def compare_products(
        self,
        sites: List[str],
        search_query: str,
        filters: Dict[str, Any],
        limit: int = 3
    ) -> Dict[str, Any]:
        """
        Compare products across multiple e-commerce sites.
        
        Args:
            sites: List of site names (e.g., ['flipkart', 'amazon'])
            search_query: Product to search for
            filters: Price/rating filters
            limit: Number of results per site
            
        Returns:
            Comparison results with data from each site
        """
        logger.info(f"Starting multi-site comparison: {sites}")
        
        results = {
            "status": "success",
            "sites": {},
            "comparison_summary": {},
            "best_deals": []
        }
        
        for site in sites:
            try:
                site_url = self._get_site_url(site)
                logger.info(f"Searching on {site}: {search_query}")
                
                # Navigate to site
                nav_result = await self.agent.navigate(site_url)
                if nav_result.get("status") != "success":
                    results["sites"][site] = {
                        "status": "error",
                        "error": f"Failed to navigate to {site}",
                        "data": []
                    }
                    continue
                
                # Wait a bit for page to settle
                await asyncio.sleep(2)
                
                # Type search query
                search_selector = self._get_search_selector(site)
                type_result = await self.agent.type_text(search_selector, search_query)
                
                if type_result.get("status") != "success":
                    results["sites"][site] = {
                        "status": "error",
                        "error": f"Failed to type search query on {site}",
                        "data": []
                    }
                    continue
                
                # Wait for results
                await asyncio.sleep(3)
                
                # Extract products
                schema = self._get_extraction_schema(site)
                extract_result = await self.agent.extract(schema, limit=limit * 2)
                
                if extract_result.get("status") == "success":
                    # Filter and process results
                    products = extract_result.get("data", [])
                    filtered = self._apply_filters(products, filters)
                    
                    results["sites"][site] = {
                        "status": "success",
                        "data": filtered[:limit],
                        "total_found": len(products),
                        "after_filtering": len(filtered)
                    }
                    
                    logger.info(f"{site}: Found {len(products)} products, {len(filtered)} after filtering")
                else:
                    results["sites"][site] = {
                        "status": "error",
                        "error": extract_result.get("error", "Extraction failed"),
                        "data": []
                    }
            
            except Exception as e:
                logger.error(f"Error comparing on {site}: {e}")
                results["sites"][site] = {
                    "status": "error",
                    "error": str(e),
                    "data": []
                }
        
        # Generate comparison summary
        results["comparison_summary"] = self._generate_summary(results["sites"], filters)
        results["best_deals"] = self._find_best_deals(results["sites"])
        
        return results
    
    def _get_site_url(self, site: str) -> str:
        """Get base URL for a site."""
        urls = {
            "flipkart": "https://www.flipkart.com",
            "amazon": "https://www.amazon.in",
            "myntra": "https://www.myntra.com",
            "snapdeal": "https://www.snapdeal.com"
        }
        return urls.get(site.lower(), "https://www.google.com")
    
    def _get_search_selector(self, site: str) -> str:
        """Get search input selector for a site."""
        selectors = {
            "flipkart": "input[name='q']",
            "amazon": "input#twotabsearchtextbox",
            "myntra": "input[placeholder*='Search']",
            "snapdeal": "input#inputValEnter"
        }
        return selectors.get(site.lower(), "input[type='search']")
    
    def _get_extraction_schema(self, site: str) -> Dict[str, str]:
        """Get extraction schema for a site."""
        return {
            "name": "h2, h3, [class*='title'], [class*='name']",
            "price": "[class*='price']",
            "rating": "[class*='rating'], [aria-label*='star']",
            "url": "a[href*='/p/'], a[href*='/dp/'], a[href*='product']"
        }
    
    def _apply_filters(self, products: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Apply price and rating filters to products."""
        filtered = products
        
        if filters.get("price_max"):
            filtered = [
                p for p in filtered
                if p.get("price") and p["price"] <= filters["price_max"]
            ]
        
        if filters.get("price_min"):
            filtered = [
                p for p in filtered
                if p.get("price") and p["price"] >= filters["price_min"]
            ]
        
        if filters.get("rating_min"):
            filtered = [
                p for p in filtered
                if p.get("rating") and p["rating"] >= filters["rating_min"]
            ]
        
        return filtered
    
    def _generate_summary(self, sites_data: Dict[str, Any], filters: Dict) -> Dict[str, Any]:
        """Generate comparison summary statistics."""
        summary = {
            "total_products_found": 0,
            "sites_successful": 0,
            "sites_failed": 0,
            "price_range": {"min": float('inf'), "max": 0},
            "average_rating": 0
        }
        
        all_ratings = []
        
        for site, data in sites_data.items():
            if data["status"] == "success":
                summary["sites_successful"] += 1
                summary["total_products_found"] += len(data.get("data", []))
                
                for product in data.get("data", []):
                    if product.get("price"):
                        summary["price_range"]["min"] = min(
                            summary["price_range"]["min"],
                            product["price"]
                        )
                        summary["price_range"]["max"] = max(
                            summary["price_range"]["max"],
                            product["price"]
                        )
                    
                    if product.get("rating"):
                        all_ratings.append(product["rating"])
            else:
                summary["sites_failed"] += 1
        
        if all_ratings:
            summary["average_rating"] = sum(all_ratings) / len(all_ratings)
        
        if summary["price_range"]["min"] == float('inf'):
            summary["price_range"]["min"] = 0
        
        return summary
    
    def _find_best_deals(self, sites_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find best deals across all sites."""
        all_products = []
        
        for site, data in sites_data.items():
            if data["status"] == "success":
                for product in data.get("data", []):
                    all_products.append({
                        **product,
                        "site": site
                    })
        
        # Sort by price (lowest first) and rating (highest first)
        all_products.sort(
            key=lambda x: (x.get("price") or float('inf'), -(x.get("rating") or 0))
        )
        
        # Return top 3 best deals
        return all_products[:3]

