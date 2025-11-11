from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from app.services.site_selectors import get_selectors_for_site, detect_site_from_url
import asyncio

class BrowserAgent:
    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None
        self.current_site: str = "generic"  # Track current site for selector strategies

    async def start(self):
        """Initialize browser instance."""
        if self.browser is None:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()

    async def close(self):
        """Close browser instance."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = None
        self.context = None
        self.page = None

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL and detect the site type."""
        if not self.page:
            await self.start()
        
        try:
            # Add https:// if no protocol specified
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait a bit more for dynamic content
            await self.page.wait_for_load_state("networkidle", timeout=10000)
            current_url = self.page.url
            title = await self.page.title()
            
            # Detect site type for better selector strategies
            self.current_site = detect_site_from_url(current_url)
            
            return {
                "status": "success",
                "url": current_url,
                "title": title,
                "site": self.current_site
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Navigation failed: {str(e)}"
            }

    async def click(self, selector: str) -> dict:
        """Click an element by selector with automatic fallback."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # List of selectors to try
        selectors_to_try = [selector]
        
        # If it's a submit button, try common alternatives
        if "button[type='submit']" in selector or "submit" in selector.lower():
            # Add site-specific search button selectors
            site_selectors = get_selectors_for_site(self.current_site)
            selectors_to_try.extend(site_selectors.get("search_button", [])[:3])
            selectors_to_try.extend([
                "input[name='btnK']",  # Google search button
                "input[type='submit']",
                "input[value='Google Search']",
                "input[value='Search']",
                "button[aria-label*='Search']",
                "button[aria-label*='search']"
            ])
        
        # Remove duplicates while preserving order
        seen = set()
        selectors_to_try = [x for x in selectors_to_try if not (x in seen or seen.add(x))]
        
        if "button" in selector and "submit" not in selector.lower():
            # Try to find button by text if it's a generic button selector
            selectors_to_try.extend([
                "input[type='submit']",
                "[role='button']"
            ])
        
        # Try each selector
        last_error = None
        for sel in selectors_to_try:
            try:
                await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                # Scroll into view if needed - use proper escaping
                try:
                    await self.page.evaluate("""
                        (selector) => {
                            const el = document.querySelector(selector);
                            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    """, sel)
                except:
                    pass  # If scroll fails, continue anyway
                await self.page.wait_for_timeout(500)
                await self.page.click(sel)
                return {
                    "status": "success", 
                    "selector": sel,
                    "original_selector": selector if sel != selector else None
                }
            except Exception as e:
                last_error = str(e)
                continue
        
        # If all failed, get suggestions
        suggestions = await self._suggest_selectors(selector)
        return {
            "status": "error",
            "error": f"Selector not found: {last_error}",
            "selector": selector,
            "suggestions": suggestions,
            "tried_selectors": selectors_to_try[:5]
        }

    async def type_text(self, selector: str, text: str) -> dict:
        """Type text into an input field with automatic fallback to alternatives."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # List of selectors to try in order
        selectors_to_try = [selector]
        
        # Get site-specific selectors if available
        site_selectors = get_selectors_for_site(self.current_site)
        if selector not in site_selectors.get("search_input", []):
            # Add site-specific search input selectors
            selectors_to_try.extend(site_selectors.get("search_input", [])[:3])
        
        # If the original selector is input[name='q'], add textarea alternative (common for Google, etc.)
        if "input[name='q']" in selector:
            selectors_to_try.extend([
                "textarea[name='q']",
                "#APjFqb",  # Google's search box ID
                "textarea",
                "input[type='search']",
                "[role='searchbox']"
            ])
        elif "input" in selector and "textarea" not in selector:
            # If it's an input selector, also try textarea
            textarea_version = selector.replace("input", "textarea")
            selectors_to_try.append(textarea_version)
            selectors_to_try.extend([
                "textarea[name='q']",
                "input[type='search']",
                "[role='searchbox']"
            ])
        
        # Remove duplicates while preserving order
        seen = set()
        selectors_to_try = [x for x in selectors_to_try if not (x in seen or seen.add(x))]
        
        # Try each selector until one works
        last_error = None
        for sel in selectors_to_try:
            try:
                await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                element = await self.page.query_selector(sel)
                if element:
                    # Clear existing value first
                    await self.page.fill(sel, "")
                    # Type the text
                    await self.page.type(sel, text, delay=50)
                    return {
                        "status": "success", 
                        "selector": sel, 
                        "text": text,
                        "original_selector": selector if sel != selector else None
                    }
            except Exception as e:
                last_error = str(e)
                continue
        
        # If all selectors failed, get suggestions
        suggestions = await self._suggest_selectors(selector)
        
        return {
            "status": "error",
            "error": f"Selector not found: {last_error}",
            "selector": selector,
            "suggestions": suggestions,
            "tried_selectors": selectors_to_try[:5]  # Show what we tried
        }

    async def wait_for(self, selector: str, timeout: int = 5000) -> dict:
        """Wait for an element to appear."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            return {"status": "success", "selector": selector}
        except Exception as e:
            suggestions = await self._suggest_selectors(selector)
            return {
                "status": "error",
                "error": f"Element not found within timeout: {str(e)}",
                "selector": selector,
                "suggestions": suggestions
            }
    
    async def _suggest_selectors(self, original_selector: str) -> list:
        """Suggest alternative selectors if the original fails."""
        if not self.page:
            return []
        
        try:
            # Get all input elements on the page
            inputs = await self.page.evaluate("""
                () => {
                    const inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'));
                    return inputs.slice(0, 5).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        className: el.className || ''
                    }));
                }
            """)
            
            suggestions = []
            for inp in inputs:
                if inp['id']:
                    suggestions.append(f"#{inp['id']}")
                if inp['name']:
                    suggestions.append(f"{inp['tag']}[name='{inp['name']}']")
                if inp['placeholder']:
                    suggestions.append(f"{inp['tag']}[placeholder*='{inp['placeholder'][:20]}']")
            
            return list(set(suggestions))[:5]  # Return unique suggestions, max 5
        except:
            return []

    async def extract(self, schema: dict, limit: int = None) -> dict:
        """Extract data from page using CSS selectors with site-specific fallbacks.
        
        Schema format: {"field_name": "css_selector"}
        Returns structured data with arrays for each field.
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # Get site-specific selectors as fallback
        site_selectors = get_selectors_for_site(self.current_site)
        
        # First, try to diagnose the page structure if extraction fails
        diagnostic = await self.page.evaluate("""
            () => {
                const info = {
                    url: window.location.href,
                    title: document.title,
                    productContainers: [],
                    sampleSelectors: {}
                };
                
                // Check for common Flipkart selectors
                const checks = [
                    { name: 'data-id divs', selector: 'div[data-id]', count: document.querySelectorAll('div[data-id]').length },
                    { name: '_1AtVbE class', selector: '._1AtVbE', count: document.querySelectorAll('._1AtVbE').length },
                    { name: '_2kHMtA class', selector: '._2kHMtA', count: document.querySelectorAll('._2kHMtA').length },
                    { name: '_4rR01T (name)', selector: '._4rR01T', count: document.querySelectorAll('._4rR01T').length },
                    { name: '_30jeq3 (price)', selector: '._30jeq3', count: document.querySelectorAll('._30jeq3').length },
                    { name: '_3LWZlK (rating)', selector: '._3LWZlK', count: document.querySelectorAll('._3LWZlK').length },
                    { name: 'product links', selector: 'a[href*="/p/"]', count: document.querySelectorAll('a[href*="/p/"]').length }
                ];
                
                info.selectorChecks = checks;
                
                // Get sample HTML structure
                const firstContainer = document.querySelector('div[data-id]') || document.querySelector('._1AtVbE');
                if (firstContainer) {
                    info.sampleHTML = firstContainer.outerHTML.substring(0, 500);
                }
                
                return info;
            }
        """)
        
        print(f"Page diagnostic: {diagnostic}")
        
        try:
            # Use a smarter extraction strategy - extract from product containers
            result = await self.page.evaluate("""
                ({schema, limit, siteSelectors, site}) => {
                    const data = {};
                    
                    // Helper to try multiple selectors
                    const trySelectors = (selectors, container = null, isLink = false) => {
                        for (const selector of selectors) {
                            try {
                                const searchIn = container || document;
                                const elements = searchIn.querySelectorAll(selector);
                                if (elements.length > 0) {
                                    if (isLink) {
                                        return Array.from(elements).map(el => {
                                            const linkEl = el.tagName === 'A' ? el : el.closest('a');
                                            if (linkEl) {
                                                const href = linkEl.href || linkEl.getAttribute('href') || '';
                                                return href.startsWith('http') ? href : (window.location.origin + href);
                                            }
                                            return '';
                                        }).filter(href => href);
                                    } else {
                                        return Array.from(elements).map(el => {
                                            return el.textContent?.trim() || el.innerText?.trim() || el.title || '';
                                        }).filter(text => text);
                                    }
                                }
                            } catch (e) {
                                continue;
                            }
                        }
                        return [];
                    };
                    
                    // For Flipkart, try to find product containers first
                    let productContainers = [];
                    if (site === 'flipkart') {
                        // Try multiple container selectors - Flipkart uses various structures
                        const containerSelectors = [
                            'div[data-id]',  // Most common
                            '._1AtVbE',  // Product card
                            '._2kHMtA',  // Alternative card
                            '._13oc-S > div',  // Grid container
                            '[class*="_1AtVbE"]',  // Partial class match
                            'div[class*="product"]',  // Generic product div
                            'a[href*="/p/"]'  // Product links as containers
                        ];
                        for (const sel of containerSelectors) {
                            try {
                                const containers = document.querySelectorAll(sel);
                                if (containers.length > 0) {
                                    productContainers = Array.from(containers).slice(0, 20); // Limit to 20
                                    break;
                                }
                            } catch (e) {
                                continue;
                            }
                        }
                    }
                    
                    // If we found containers, extract from each container
                    if (productContainers.length > 0) {
                        const items = [];
                        const maxItems = limit && limit > 0 ? limit : productContainers.length;
                        
                        for (let i = 0; i < Math.min(maxItems, productContainers.length); i++) {
                            const container = productContainers[i];
                            const item = {};
                            
                            // Extract link first (most reliable)
                            if (schema.link || schema.url) {
                                const linkKey = schema.link ? 'link' : 'url';
                                const linkEl = container.querySelector('a[href*="/p/"]') || container.closest('a[href*="/p/"]');
                                if (linkEl) {
                                    let href = linkEl.href || linkEl.getAttribute('href') || '';
                                    if (!href.startsWith('http')) {
                                        href = window.location.origin + href;
                                    }
                                    item[linkKey] = href;
                                }
                            }
                            
                            // Extract name - try multiple strategies
                            if (schema.name) {
                                let name = null;
                                // Try selectors first
                                const nameSelectors = [schema.name];
                                if (siteSelectors && siteSelectors.product_name) {
                                    nameSelectors.push(...siteSelectors.product_name);
                                }
                                const nameValues = trySelectors(nameSelectors, container, false);
                                if (nameValues[0]) {
                                    name = nameValues[0];
                                } else {
                                    // Fallback: get text from link or title
                                    const linkEl = container.querySelector('a[href*="/p/"]');
                                    if (linkEl) {
                                        // Get title attribute first (cleaner)
                                        name = linkEl.getAttribute('title');
                                        if (!name) {
                                            // Try to get just the first line or first meaningful text
                                            const linkText = linkEl.textContent?.trim() || linkEl.innerText?.trim() || '';
                                            // Split by newlines and take first non-empty line, or first 100 chars
                                            const lines = linkText.split(/[\n\r]+/).filter(l => l.trim());
                                            if (lines.length > 0) {
                                                name = lines[0].trim().substring(0, 150);
                                            } else {
                                                name = linkText.substring(0, 150);
                                            }
                                        }
                                    }
                                    // Try to find any heading or text element
                                    if (!name) {
                                        const heading = container.querySelector('h1, h2, h3, h4, [class*="title"], [class*="name"]');
                                        if (heading) {
                                            name = heading.textContent?.trim() || heading.innerText?.trim();
                                        }
                                    }
                                    // Clean up name - remove extra whitespace and limit length
                                    if (name) {
                                        name = name.replace(/\s+/g, ' ').trim();
                                        // Try to extract just the product name (before first number or special marker)
                                        const nameMatch = name.match(/^([^0-9₹$]*?)(?:\s*[-–—]|\s+\d|₹|$)/);
                                        if (nameMatch && nameMatch[1].trim().length > 5) {
                                            name = nameMatch[1].trim();
                                        }
                                        // Limit to reasonable length
                                        if (name.length > 100) {
                                            name = name.substring(0, 100).trim() + '...';
                                        }
                                    }
                                }
                                item.name = name;
                            }
                            
                            // Extract price - try multiple strategies
                            if (schema.price) {
                                let price = null;
                                const priceSelectors = [schema.price];
                                if (siteSelectors && siteSelectors.product_price) {
                                    priceSelectors.push(...siteSelectors.product_price);
                                }
                                const priceValues = trySelectors(priceSelectors, container, false);
                                if (priceValues[0]) {
                                    price = priceValues[0];
                                } else {
                                    // Fallback: look for price-like patterns in text
                                    const containerText = container.textContent || container.innerText || '';
                                    const priceMatch = containerText.match(/[₹$]\s*[\d,]+/);
                                    if (priceMatch) {
                                        price = priceMatch[0];
                                    }
                                }
                                item.price = price;
                            }
                            
                            // Extract rating - try multiple strategies
                            if (schema.rating) {
                                let rating = null;
                                const ratingSelectors = [schema.rating];
                                if (siteSelectors && siteSelectors.product_rating) {
                                    ratingSelectors.push(...siteSelectors.product_rating);
                                }
                                const ratingValues = trySelectors(ratingSelectors, container, false);
                                if (ratingValues[0]) {
                                    rating = ratingValues[0];
                                } else {
                                    // Fallback: look for rating patterns
                                    const containerText = container.textContent || container.innerText || '';
                                    const ratingMatch = containerText.match(/(\d+\.?\d*)\s*(?:out of|stars?|★|⭐)/i);
                                    if (ratingMatch) {
                                        rating = ratingMatch[1];
                                    }
                                }
                                item.rating = rating;
                            }
                            
                            // Only add item if it has at least name or link
                            if (item.name || item.link || item.url) {
                                items.push(item);
                            }
                        }
                        
                        // Convert to field-based format
                        if (items.length > 0) {
                            for (const key of Object.keys(schema)) {
                                data[key] = items.map(item => item[key] || null);
                            }
                        } else {
                            // If no items found, return empty arrays for each schema key
                            for (const key of Object.keys(schema)) {
                                data[key] = [];
                            }
                        }
                    } else {
                        // Fallback: extract globally
                        for (const [key, selector] of Object.entries(schema)) {
                            let selectorsToTry = [selector];
                            
                            if (siteSelectors) {
                                if (key === 'name' && siteSelectors.product_name) {
                                    selectorsToTry = selectorsToTry.concat(siteSelectors.product_name);
                                } else if (key === 'price' && siteSelectors.product_price) {
                                    selectorsToTry = selectorsToTry.concat(siteSelectors.product_price);
                                } else if (key === 'rating' && siteSelectors.product_rating) {
                                    selectorsToTry = selectorsToTry.concat(siteSelectors.product_rating);
                                } else if ((key === 'link' || key === 'url') && siteSelectors.product_link) {
                                    selectorsToTry = selectorsToTry.concat(siteSelectors.product_link);
                                }
                            }
                            
                            const values = trySelectors(selectorsToTry, null, key === 'link' || key === 'url');
                            
                            if (limit && limit > 0) {
                                data[key] = values.slice(0, limit);
                            } else {
                                data[key] = values;
                            }
                        }
                    }
                    
                    return data;
                }
            """, {"schema": schema, "limit": limit or 0, "siteSelectors": site_selectors, "site": self.current_site})
            
            # Transform to list of objects if multiple fields
            if result and len(result) > 0:
                field_names = list(result.keys())
                max_length = max(len(result[field]) for field in field_names) if result else 0
                
                # Create list of objects
                structured = []
                for i in range(max_length):
                    item = {}
                    for field in field_names:
                        value = result[field][i] if i < len(result[field]) else None
                        
                        # Clean and parse values
                        if field == 'price' and value:
                            # Extract numeric price (remove currency symbols, commas)
                            import re
                            # Handle Indian format: ₹1,00,000 or 1,00,000
                            price_str = re.sub(r'[^\d.]', '', str(value).replace(',', ''))
                            try:
                                item[field] = float(price_str) if price_str else None
                            except:
                                item[field] = value
                        elif field == 'rating' and value:
                            # Extract numeric rating (handle "4.5 out of 5" or just "4.5")
                            import re
                            rating_match = re.search(r'([\d.]+)', str(value))
                            try:
                                item[field] = float(rating_match.group(1)) if rating_match else None
                            except:
                                item[field] = value
                        else:
                            item[field] = value
                    structured.append(item)
                
                return {
                    "status": "success",
                    "data": structured,
                    "count": len(structured)
                }
            
            # If no data found, include diagnostic info
            if not result or len(result) == 0 or (isinstance(result, dict) and all(not v or len(v) == 0 for v in result.values() if isinstance(v, list))):
                return {
                    "status": "success",
                    "data": [],
                    "count": 0,
                    "diagnostic": diagnostic,
                    "message": f"No data extracted. Found {diagnostic.get('selectorChecks', [{}])[0].get('count', 0)} product containers."
                }
            
            return {
                "status": "success",
                "data": [],
                "count": 0
            }
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Extraction error: {str(e)}")
            print(f"Traceback: {error_trace}")
            return {
                "status": "error",
                "error": str(e),
                "diagnostic": diagnostic if 'diagnostic' in locals() else None,
                "traceback": error_trace
            }

# Global instance
browser_agent = BrowserAgent()

