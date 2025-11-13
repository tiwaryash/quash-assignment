from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeout
from app.services.site_selectors import get_selectors_for_site, detect_site_from_url
from app.core.config import settings
from app.core.retry import retry_async, RetryConfig
from app.core.logger import logger, log_action
from app.core.llm_provider import get_llm_provider
import asyncio
import json
import random
import string
import urllib.parse
from typing import List, Dict, Optional

class BrowserAgent:
    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None
        self.current_site: str = "generic"  # Track current site for selector strategies
        self._retry_config = RetryConfig(max_retries=3, initial_delay=1.0, exponential_base=2.0)

    async def start(self):
        """Initialize browser instance with error handling."""
        if self.browser is None:
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=settings.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',  # Overcome limited resource problems
                        '--no-sandbox',  # Required for some environments
                    ]
                )
            except Exception as e:
                logger.error(f"Failed to start browser: {e}")
                raise
            # Create context with realistic browser settings
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-IN',  # Indian locale for better local results
                timezone_id='Asia/Kolkata',  # Indian timezone
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            # Remove webdriver property
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
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
            
            # Detect if this is Google Maps - it needs special handling
            is_google_maps = "maps.google" in url.lower() or "google.com/maps" in url.lower()
            
            # Try navigation with retry for network errors
            max_retries = 2
            last_error = None
            for attempt in range(max_retries):
                try:
                    
                    # For Google Maps, use "load" instead of "domcontentloaded" and skip networkidle
                    if is_google_maps:
                        await self.page.goto(url, wait_until="load", timeout=30000)
                        # Google Maps is a heavy SPA that never reaches networkidle
                        # Wait for the search box to appear instead
                        try:
                            # Wait for search input to appear (indicates page is ready)
                            await self.page.wait_for_selector('input[aria-label*="Search"], input[placeholder*="Search"], input#searchboxinput', timeout=15000, state="visible")
                        except Exception as wait_error:
                            # Even if search box doesn't appear, wait a bit for page to settle
                            await asyncio.sleep(3)
                    else:
                        # For other sites, use standard strategy
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        # Wait a bit more for dynamic content, but with shorter timeout for heavy sites
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception as networkidle_error:
                            # For heavy sites, networkidle might never happen, but page is still usable
                            await asyncio.sleep(2)  # Give it a moment anyway
                    
                    break  # Success, exit retry loop
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    
                    # Check if it's a network error that might be retryable
                    if "ERR_HTTP2_PROTOCOL_ERROR" in error_str or "net::" in error_str:
                        if attempt < max_retries - 1:
                            # Wait a bit before retry
                            await asyncio.sleep(2)
                            continue
                    # Check if it's just a timeout (not a critical error for heavy sites)
                    if "Timeout" in error_str and is_google_maps:
                        # Try to check if page loaded anyway
                        try:
                            current_url_check = self.page.url
                            if current_url_check and "maps" in current_url_check.lower():
                                break
                        except:
                            pass
                    
                    # If not retryable or last attempt, raise
                    if attempt == max_retries - 1:
                        raise
            
            current_url = self.page.url
            title = await self.page.title()
            
            # Check for CAPTCHA or blocking pages
            captcha_detected = await self._detect_captcha()
            if captcha_detected:
                return {
                    "status": "blocked",
                    "url": current_url,
                    "title": title,
                    "block_type": "captcha",
                    "message": "Google has detected automated access and is showing a CAPTCHA. This is common when scraping Google search results.",
                    "alternatives": [
                        "Try using Zomato or Swiggy for local discovery instead",
                        "Use a different search engine",
                        "Wait a few minutes and try again"
                    ]
                }
            
            # Detect site type for better selector strategies
            self.current_site = detect_site_from_url(current_url)
            
            return {
                "status": "success",
                "url": current_url,
                "title": title,
                "site": self.current_site
            }
        except Exception as e:
            error_str = str(e)
            # Provide helpful error messages
            if "ERR_HTTP2_PROTOCOL_ERROR" in error_str:
                # Check if it's Zomato or Swiggy - suggest Google Maps as alternative
                url_lower = url.lower()
                suggestions = [
                    "Try again in a few moments",
                    "The site might be temporarily unavailable"
                ]
                
                if "zomato" in url_lower or "swiggy" in url_lower:
                    suggestions.append("Zomato/Swiggy may be blocking automated access")
                    suggestions.append("Try using Google Maps instead for local discovery")
                    suggestions.append("You can search 'pizza places in [location]' on Google Maps")
                
                return {
                    "status": "error",
                    "error": f"Network error connecting to {url}. This might be a temporary network issue or the site might be blocking automated access.",
                    "suggestions": suggestions,
                    "retryable": True,
                    "alternative": "google_maps" if ("zomato" in url_lower or "swiggy" in url_lower) else None
                }
            elif "net::" in error_str:
                return {
                    "status": "error",
                    "error": f"Network error: {error_str}",
                    "suggestions": [
                        "Check your internet connection",
                        "The site might be temporarily unavailable",
                        "Try again in a few moments"
                    ],
                    "retryable": True
                }
            elif "Timeout" in error_str:
                # For timeout errors, check if we're on Google Maps
                if "maps.google" in url.lower():
                    return {
                        "status": "error",
                        "error": f"Timeout loading Google Maps. The page may still be usable, but some features might not be ready.",
                        "suggestions": [
                            "Google Maps is a heavy application and may take time to load",
                            "Try the search anyway - the page might be ready",
                            "Wait a moment and retry"
                        ],
                        "retryable": True,
                        "partial_success": True  # Indicate page might still be usable
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Navigation timeout: {error_str}",
                        "suggestions": [
                            "The page might be taking too long to load",
                            "Try again in a few moments",
                            "Check if the site is accessible"
                        ],
                        "retryable": True
                    }
            else:
                return {
                    "status": "error",
                    "error": f"Navigation failed: {error_str}",
                    "debug_info": f"Exception type: {type(e).__name__}"
                }
    
    async def _detect_captcha(self) -> bool:
        """Detect if the current page is a CAPTCHA or blocking page."""
        if not self.page:
            return False
        
        try:
            current_url = self.page.url
            
            # Check URL for CAPTCHA indicators
            if "/sorry/" in current_url or "/sorry/index" in current_url:
                return True
            
            # Check for common CAPTCHA elements
            captcha_selectors = [
                "#g-recaptcha-response",
                "iframe[src*='recaptcha']",
                ".g-recaptcha",
                "[data-sitekey]",  # reCAPTCHA site key
                "text=unusual traffic",
                "text=automated queries"
            ]
            
            for selector in captcha_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        return True
                except:
                    continue
            
            # Check page content for CAPTCHA indicators
            page_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            captcha_keywords = [
                "unusual traffic",
                "automated queries",
                "captcha",
                "verify you're not a robot",
                "sorry, we have detected"
            ]
            
            if any(keyword in page_text for keyword in captcha_keywords):
                return True
            
            return False
        except:
            return False

    async def search_google_maps(self, query: str, limit: int = 5, lat: float = 12.9250, lng: float = 77.6400) -> Dict:
        """
        Search Google Maps for `query` near given lat/lng (defaults to HSR Layout, Bangalore) and extract results.
        This is a robust, battle-tested function that handles Maps' async rendering and common issues.
        
        Returns: {"status":"success","data":[{name, rating, address, url}], "diagnostic": {...}}
        """
        if not self.page:
            await self.start()


        # Ensure context has India locale/timezone and geolocation (helps results & reduces surprises)
        try:
            if self.context:
                await self.context.set_default_navigation_timeout(45000)
                await self.context.grant_permissions(["geolocation"])
                await self.context.set_geolocation({"latitude": lat, "longitude": lng, "accuracy": 100})
        except Exception as e:
            # Some contexts may not support changing geolocation after creation; ignore if not supported
            pass

        # Build URL containing search term (helps maps initial view)
        encoded = urllib.parse.quote_plus(query)
        maps_url = f"https://www.google.com/maps/search/{encoded}/@{lat},{lng},13z"
        
        try:
            await self.page.goto(maps_url, wait_until="load", timeout=30000)
        except Exception as e:
            pass

        # Wait for search box to appear (more reliable than networkidle)
        try:
            await self.page.wait_for_selector("input#searchboxinput, input[aria-label*='Search']", timeout=15000)
        except Exception as e:
            # continue anyway — sometimes input isn't present but page is usable
            pass

        # Try to set input value robustly via evaluate (dispatch events)
        try:
            set_input_js = """
            (q) => {
                const selectors = ['input#searchboxinput', "input[aria-label*='Search']", 'input[placeholder*="Search"]'];
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) {
                        el.focus();
                        el.value = q;
                        // dispatch input + change events so Maps picks it up
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                        return true;
                    }
                }
                // fallback: try to find a visible input
                const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.offsetParent !== null);
                if (inputs.length) {
                    const el = inputs[0];
                    el.focus();
                    el.value = q;
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                }
                return false;
            }
            """
            input_set = await self.page.evaluate(set_input_js, query)
            
            # Press Enter to submit search
            await asyncio.sleep(0.25)
            await self.page.keyboard.press("Enter")
        except Exception as e:
            # As fallback, try page.fill then Enter
            try:
                await self.page.fill("input#searchboxinput", query, timeout=3000)
                await self.page.keyboard.press("Enter")
            except Exception as e2:
                pass

        # Poll for results for up to 20 seconds
        total_wait = 20
        poll_interval = 1.5
        elapsed = 0.0
        found = False
        diagnostic = {}
        
        while elapsed < total_wait:
            # check common result containers counts
            counts = await self.page.evaluate("""
                () => {
                    return {
                        roleArticle: document.querySelectorAll('div[role="article"]').length,
                        dataResultIndex: document.querySelectorAll('[data-result-index]').length,
                        h3s: document.querySelectorAll('h3').length,
                        paneExists: !!document.querySelector('#pane'),
                        paneChildren: document.querySelector('#pane') ? document.querySelector('#pane').children.length : 0,
                        bodyTextLen: document.body.innerText.length
                    };
                }
            """)
            diagnostic = counts
            
            
            if counts.get("roleArticle", 0) >= 1 or counts.get("dataResultIndex", 0) >= 1 or counts.get("h3s", 0) >= 3 or counts.get("paneChildren", 0) > 0:
                found = True
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # If not found, capture page text to diagnose (maybe blocked)
        if not found:
            page_text = await self.page.evaluate("() => document.body.innerText.slice(0,2000)")
            diagnostic["pageTextPreview"] = page_text[:2000]
            
            # detect captcha keywords
            if any(k in page_text.lower() for k in ["unusual traffic", "automated queries", "captcha", "verify you're not a robot", "/sorry/"]):
                return {"status":"blocked", "message":"Detected CAPTCHA or Google blocking", "diagnostic": diagnostic}

        # Run diagnostic to inspect actual page structure and adapt selectors
        page_diagnostic = await self.page.evaluate("""
            () => {
                const selectors = [
                    'div[role="article"]',
                    '[data-result-index]',
                    'h3',
                    '.Nv2PK',
                    '.qBF1Pd',
                    '.MW4etd',
                    '[aria-label*="star"]',
                    '#pane',
                    '[role="main"]'
                ];
                const counts = {};
                selectors.forEach(s => {
                    try { counts[s] = document.querySelectorAll(s).length; } catch(e){ counts[s]=0; }
                });

                // find first container candidate
                const candidateSelectors = ['div[role="article"]', '[data-result-index]', '.Nv2PK', 'div:has(h3)'];
                let sample = null;
                for (const s of candidateSelectors) {
                    try {
                        const el = document.querySelector(s);
                        if (el) { 
                            sample = {
                                selector: s, 
                                outerHTML: el.outerHTML.slice(0,2000), 
                                textPreview: el.innerText.slice(0,500)
                            }; 
                            break; 
                        }
                    } catch(e){}
                }

                // collect distinct class name frequency from first 200 divs
                const classFreq = {};
                Array.from(document.querySelectorAll('div')).slice(0,200).forEach(d => {
                    const classes = (d.className || '').toString().split(/\\s+/).filter(Boolean);
                    classes.forEach(c => classFreq[c] = (classFreq[c]||0) + 1);
                });

                // gather visible h3 texts
                const h3s = Array.from(document.querySelectorAll('h3')).map(h => h.textContent?.trim()).filter(Boolean).slice(0,10);

                return {
                    counts, 
                    sample, 
                    topH3s: h3s, 
                    topClasses: Object.entries(classFreq).sort((a,b)=>b[1]-a[1]).slice(0,30),
                    bestContainerSelector: counts['.Nv2PK'] > 0 ? '.Nv2PK' : 
                                          counts['div[role="article"]'] > 0 ? 'div[role="article"]' :
                                          counts['[data-result-index]'] > 0 ? '[data-result-index]' : null
                };
            }
        """)
        
        
        # Update diagnostic with page inspection results
        diagnostic.update(page_diagnostic)

        # Extract results from containers using improved extraction logic
        # Use the best container selector found in diagnostic
        best_selector = page_diagnostic.get('bestContainerSelector') or '.Nv2PK'
        
        # Build extraction JS with dynamic selector (using raw string since we pass selector as parameter)
        extraction_js = r"""
        (params) => {
          const limit = params.limit || 10;
          const containerSelector = params.containerSelector || '.Nv2PK';
          const out = [];
          let containers = [];
          
          // Try the primary selector first
          try {
            containers = Array.from(document.querySelectorAll(containerSelector)).filter(n => n && n.textContent && n.textContent.trim().length>10);
            console.log('[MAPS-EXTRACT] Found', containers.length, 'containers with selector:', containerSelector);
          } catch(e) {
            console.log('[MAPS-EXTRACT] Error with primary selector:', e);
          }
          
          // Fallback to other selectors if primary not found
          if (containers.length === 0) {
            const fallbackSelectors = ['.Nv2PK', 'div[role="article"]', '[data-result-index]', 'div:has(h3)'];
            for (const sel of fallbackSelectors) {
              try {
                const found = Array.from(document.querySelectorAll(sel)).filter(c => c && c.textContent && c.textContent.trim().length>10);
                if (found.length > 0) {
                  containers.push(...found);
                  console.log('[MAPS-EXTRACT] Using fallback selector:', sel, 'found', found.length);
                  break;
                }
              } catch(e) { continue; }
            }
          }
          
          for (let i = 0; i < Math.min(limit, containers.length); i++) {
            const c = containers[i];
            // NAME
            const nameEl = c.querySelector('.qBF1Pd') || c.querySelector('[role="heading"]') || c.querySelector('h3');
            const name = nameEl ? nameEl.textContent.trim() : null;

            // URL (maps place link)
            let url = null;
            const a = c.querySelector('a[href*="/maps/place"], a[href*="/maps/dir"], a[href*="maps.google"]');
            if (a && a.href) url = a.href;
            else if (name) url = 'https://www.google.com/maps/search/' + encodeURIComponent(name);

            // RATING and REVIEWS
            let rating = null, reviews = null;
            // preference: aria-label on an element that contains rating+reviews
            const ariaEl = c.querySelector('[aria-label*="stars"], [aria-label*="star"], [aria-label*="Reviews"], [aria-label*="review"]');
            if (ariaEl && ariaEl.getAttribute) {
              const aria = ariaEl.getAttribute('aria-label') || '';
              const rMatch = aria.match(/(\d(?:\.\d)?)/);
              const revMatch = aria.match(/\b(\d[\d,]*)\b(?=\s*Reviews|\))/i);
              if (rMatch) rating = rMatch[1];
              if (revMatch) reviews = revMatch[1].replace(/,/g,'');
            }
            // fallback: numeric .MW4etd inside card
            if (!rating) {
              const rEl = c.querySelector('.MW4etd');
              if (rEl) rating = rEl.textContent.trim().match(/(\d(?:\.\d)?)/)?.[1] || null;
            }
            // Also try to find reviews count inside element .UY7F9 or similar
            if (!reviews) {
              const revEl = c.querySelector('.UY7F9, .QBUL8c ~ .UY7F9') || c.querySelector('[aria-hidden="true"]');
              if (revEl && /\(\d/.test(revEl.textContent)) {
                reviews = (revEl.textContent.match(/\d[\d,]*/) || [null])[0];
                if (reviews) reviews = reviews.replace(/,/g,'');
              }
            }

            // PRICE / CATEGORY / ADDRESS: there are multiple .W4Efsd blocks; get sensible lines
            let category = null, price = null, address = null;
            try {
              const w = Array.from(c.querySelectorAll('.W4Efsd')).map(el => el.innerText && el.innerText.trim()).filter(Boolean);
              // Example structure seen: ["4.7(687) · ₹200–400", "Pizza · HOUSE NO 557, GROUND FLOOR", "Open ⋅ Closes 10 pm"]
              if (w.length >= 1) {
                // try to find price token (₹) and category/address by heuristics
                for (const line of w) {
                  if (line.includes('₹')) {
                    price = line.match(/₹\s*[\d,–\-\s]+/)?.[0] || price;
                  }
                  // category is often short word like "Pizza"
                  const catMatch = line.match(/^[A-Za-z &amp;]+(?=\s*·|$)/);
                  if (catMatch && !category) category = catMatch[0].trim();
                }
                // address: try second line after category if present
                if (w.length >= 2) {
                  // take the portion after the dot separator '·' if exists
                  const possible = w[1].split('·').map(s => s.trim()).filter(Boolean);
                  // prefer anything that looks like an address (contains digits or ALL CAPS words)
                  for (const p of possible) {
                    if (/\d/.test(p) || /[A-Z]{2,}/.test(p) || p.length>10) {
                      address = p;
                      break;
                    }
                  }
                  if (!address) address = possible.join(' · ') || null;
                } else {
                  // fallback: try to parse address from full card text removing name and rating
                  const txt = c.innerText.replace(name || '', '').replace(/[\r\n]+/g,'\n').split('\n').map(s=>s.trim()).filter(Boolean);
                  if (txt.length >= 2) address = txt.slice(1,4).join(' | ');
                }
              }
            } catch(e) {}

            out.push({
              name: name || null,
              rating: rating ? (isNaN(Number(rating)) ? rating : Number(rating)) : null,
              reviews: reviews ? (isNaN(Number(reviews)) ? reviews : Number(reviews)) : null,
              price: price || null,
              category: category || null,
              address: address || null,
              url: url || null
            });
          }
          return out;
        }
        """
        
        # Call extraction with both limit and the dynamically determined selector
        # page.evaluate() only takes one argument after the JS code, so pass both as a dict
        extraction = await self.page.evaluate(extraction_js, {"limit": limit, "containerSelector": best_selector})

        return {"status": "success", "data": extraction, "diagnostic": diagnostic}

    async def click(self, selector: str) -> dict:
        """Click an element by selector with automatic fallback."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # For Google Maps, if clicking a submit button, try pressing Enter on the search input instead
        if self.current_site == "google_maps" and ("submit" in selector.lower() or "button" in selector.lower()):
            # Try to find the search input and press Enter
            try:
                search_input = await self.page.query_selector("input#searchboxinput, input[aria-label*='Search']")
                if search_input:
                    current_url = self.page.url
                    await self.page.keyboard.press("Enter")
                    
                    # Wait for URL to change (indicates search executed)
                    try:
                        await self.page.wait_for_url(lambda url: url != current_url, timeout=10000)
                    except:
                        pass
                    
                    # Wait longer for Google Maps to load results
                    await self.page.wait_for_timeout(5000)  # Increased wait time for Google Maps
                    
                    # Check if results appeared
                    try:
                        await self.page.wait_for_selector(".Nv2PK, [role='article'], [data-result-index]", state="attached", timeout=5000)
                    except:
                        pass
                    
                    return {
                        "status": "success",
                        "selector": "input#searchboxinput (pressed Enter)",
                        "original_selector": selector,
                        "method": "keyboard_enter",
                        "note": "Google Maps search executed, results may take time to load"
                    }
            except Exception as e:
                # Fall through to normal click handling
                pass
        
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
        
        # For Google Maps, prioritize the searchboxinput selector
        if self.current_site == "google_maps":
            if "input#searchboxinput" not in selectors_to_try:
                selectors_to_try.insert(0, "input#searchboxinput")
            # Also add other Maps-specific selectors
            if "input[aria-label*='Search']" not in selectors_to_try:
                selectors_to_try.insert(1, "input[aria-label*='Search']")
        
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
                    
                    # For Google Maps, automatically press Enter after typing
                    if self.current_site == "google_maps":
                        await asyncio.sleep(0.5)  # Small delay to ensure typing is complete
                        await self.page.keyboard.press("Enter")
                        
                        # Wait for URL to change (search executed)
                        current_url = self.page.url
                        try:
                            await self.page.wait_for_url(lambda url: url != current_url, timeout=8000)
                        except:
                            pass
                        
                        # Wait for results to load - Google Maps needs much more time
                        
                        # Poll for results over time instead of just waiting
                        max_wait = 15  # seconds
                        poll_interval = 2  # seconds
                        result_count = 0
                        
                        for i in range(0, max_wait, poll_interval):
                            await asyncio.sleep(poll_interval)
                            result_count = await self.page.evaluate("""
                                () => {
                                    // Try multiple strategies to find results
                                    let count = 0;
                                    count = Math.max(count, document.querySelectorAll('div[role="article"]').length);
                                    count = Math.max(count, document.querySelectorAll('[data-result-index]').length);
                                    const h3s = document.querySelectorAll('h3');
                                    count = Math.max(count, h3s.length);
                                    
                                    // Also try finding any divs with ratings
                                    const withRatings = document.querySelectorAll('[aria-label*="star"]');
                                    count = Math.max(count, withRatings.length);
                                    
                                    return count;
                                }
                            """)
                            
                            
                            if result_count >= 3:  # If we found at least 3 results, stop polling
                                break
                        
                        # Get page structure info for debugging
                        page_info = await self.page.evaluate("""
                            () => {
                                const allDivs = document.querySelectorAll('div');
                                const allH3s = document.querySelectorAll('h3');
                                return {
                                    totalDivs: allDivs.length,
                                    totalH3s: allH3s.length,
                                    sampleH3Text: Array.from(allH3s).slice(0, 5).map(h3 => h3.textContent?.trim()),
                                    hasResults: document.querySelector('#pane') !== null,
                                    hasSidebar: document.querySelector('[role="main"]') !== null
                                };
                            }
                        """)
                        
                        return {
                            "status": "success", 
                            "selector": sel, 
                            "text": text,
                            "original_selector": selector if sel != selector else None,
                            "note": "Search submitted automatically on Google Maps"
                        }
                    
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
        
        # Check for CAPTCHA before waiting
        captcha_detected = await self._detect_captcha()
        if captcha_detected:
            return {
                "status": "blocked",
                "error": "Page is blocked by CAPTCHA. Cannot proceed with automation.",
                "selector": selector,
                "block_type": "captcha",
                "message": "Google has detected automated access. Consider using alternative sites like Zomato or Swiggy for local discovery."
            }
        
        # For Google Maps, use smarter detection - wait for h3 elements as indicators
        if self.current_site == "google_maps":
            
            # First, wait a bit for page to settle after search
            await asyncio.sleep(2)
            
            # Check if results are already present by looking for h3 elements (result names)
            try:
                h3_count = await self.page.evaluate("() => document.querySelectorAll('h3').length")
                if h3_count >= 3:  # If we have at least 3 h3s, likely results are there
                    # Also check if we can find rating elements
                    rating_count = await self.page.evaluate("() => document.querySelectorAll('[aria-label*=\"star\"]').length")
                    return {"status": "success", "selector": "h3 (indicator)", "original_selector": selector, "note": f"Results detected via h3 count ({h3_count} found)"}
            except Exception as e:
                pass
            
            # If it's a name/rating/location selector or container selector, wait for containers
            container_selectors = [
                "h3",  # Names are usually in h3 - use as primary indicator
                "[data-result-index]",
                "div[role='article']",
                "[class*='section-result']",
                ".Nv2PK",
                "[aria-label*='star']"  # Rating elements also indicate results
            ]
            
            container_found = False
            found_selector = None
            
            for container_sel in container_selectors:
                try:
                    # Use a reasonable timeout per selector
                    await self.page.wait_for_selector(container_sel, state="visible", timeout=max(3000, timeout // len(container_selectors)))
                    count = await self.page.evaluate(f"() => document.querySelectorAll('{container_sel}').length")
                    if count > 0:
                        container_found = True
                        found_selector = container_sel
                        # Wait a bit more for individual elements to render
                        await asyncio.sleep(1)
                        break
                except Exception as e:
                    continue
            
            if container_found:
                # If we were waiting for a specific element, try to find it
                if selector not in container_selectors and selector != "h3":
                    try:
                        await self.page.wait_for_selector(selector, state="visible", timeout=3000)
                        return {"status": "success", "selector": selector}
                    except:
                        # Even if specific element not found, containers exist, so continue
                        return {"status": "success", "selector": found_selector or "h3 (fallback)", "original_selector": selector, "note": "Containers found but specific element may not be visible yet"}
                else:
                    return {"status": "success", "selector": found_selector or selector}
        
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            return {"status": "success", "selector": selector}
        except Exception as e:
            # Check if we got redirected to CAPTCHA during wait
            captcha_detected = await self._detect_captcha()
            if captcha_detected:
                return {
                    "status": "blocked",
                    "error": "Page redirected to CAPTCHA during wait",
                    "selector": selector,
                    "block_type": "captcha",
                    "message": "Google blocked the request. Try using Zomato or Swiggy instead for local discovery."
                }
            
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

    async def analyze_form(self, user_instruction: str = "") -> dict:
        """Analyze form on the page and determine what fields to fill using LLM.
        
        Returns: {
            "status": "success",
            "fields": {
                "field_name": {
                    "selector": "css_selector",
                    "value": "generated_value",
                    "type": "email|password|text|etc"
                }
            }
        }
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            # Extract form structure from the page
            form_data = await self.page.evaluate("""
                () => {
                    const forms = Array.from(document.querySelectorAll('form'));
                    if (forms.length === 0) {
                        // If no form tag, look for form-like structures
                        const inputs = Array.from(document.querySelectorAll('input, textarea, select'));
                        if (inputs.length > 0) {
                            return {
                                hasFormTag: false,
                                fields: inputs.map((el, idx) => ({
                                    index: idx,
                                    tag: el.tagName.toLowerCase(),
                                    type: el.type || 'text',
                                    name: el.name || '',
                                    id: el.id || '',
                                    placeholder: el.placeholder || '',
                                    label: (() => {
                                        // Try to find associated label
                                        if (el.id) {
                                            const label = document.querySelector(`label[for="${el.id}"]`);
                                            if (label) return label.textContent?.trim() || '';
                                        }
                                        // Try to find label as parent or sibling
                                        const parent = el.parentElement;
                                        if (parent) {
                                            const label = parent.querySelector('label');
                                            if (label) return label.textContent?.trim() || '';
                                        }
                                        // Try previous sibling
                                        let prev = el.previousElementSibling;
                                        if (prev && prev.tagName.toLowerCase() === 'label') {
                                            return prev.textContent?.trim() || '';
                                        }
                                        return '';
                                    })(),
                                    required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
                                    pattern: el.getAttribute('pattern') || '',
                                    autocomplete: el.getAttribute('autocomplete') || '',
                                    className: el.className || '',
                                    value: el.value || ''
                                }))
                            };
                        }
                    }
                    
                    // Process forms
                    const form = forms[0]; // Use first form
                    const inputs = Array.from(form.querySelectorAll('input, textarea, select'));
                    
                    return {
                        hasFormTag: true,
                        formAction: form.action || '',
                        formMethod: form.method || 'get',
                        fields: inputs.map((el, idx) => ({
                            index: idx,
                            tag: el.tagName.toLowerCase(),
                            type: el.type || 'text',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                            label: (() => {
                                if (el.id) {
                                    const label = document.querySelector(`label[for="${el.id}"]`);
                                    if (label) return label.textContent?.trim() || '';
                                }
                                const parent = el.parentElement;
                                if (parent) {
                                    const label = parent.querySelector('label');
                                    if (label) return label.textContent?.trim() || '';
                                }
                                let prev = el.previousElementSibling;
                                if (prev && prev.tagName.toLowerCase() === 'label') {
                                    return prev.textContent?.trim() || '';
                                }
                                return '';
                            })(),
                            required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
                            pattern: el.getAttribute('pattern') || '',
                            autocomplete: el.getAttribute('autocomplete') || '',
                            className: el.className || '',
                            value: el.value || ''
                        }))
                    };
                }
            """)
            
            if not form_data or not form_data.get("fields") or len(form_data["fields"]) == 0:
                return {
                    "status": "error",
                    "error": "No form fields found on the page"
                }
            
            # Use LLM to determine what values to fill
            try:
                llm_provider = get_llm_provider()
            except Exception as e:
                logger.error(f"Failed to initialize LLM provider for form analysis: {e}")
                return {"status": "error", "error": "LLM provider not configured"}
            
            # Build prompt for LLM
            fields_description = json.dumps(form_data["fields"], indent=2)
            
            prompt = f"""Analyze this form structure and determine what values to fill for each field.

User instruction: {user_instruction}

Form fields found on the page:
{fields_description}

For each field, determine:
1. A CSS selector to target it (prefer id, then name, then other attributes)
2. An appropriate value to fill (generate temporary email if needed, realistic names, etc.)
3. The field type (email, password, text, etc.)

IMPORTANT:
- For email fields, generate a temporary email like: temp_123456@example.com (use random numbers)
- For password fields, generate a secure password like: TempPass1234! (use random numbers)
- For name fields, use realistic names
- For required fields, always provide values
- Skip hidden fields (type='hidden')
- Skip submit buttons (type='submit' or type='button' with submit-like text)

Return JSON in this format:
{{
    "fields": {{
        "field_identifier": {{
            "selector": "css_selector",
            "value": "value_to_fill",
            "type": "email|password|text|etc",
            "required": true|false
        }}
    }}
}}

Use field identifiers like: email, password, name, first_name, last_name, phone, etc.
For selectors, use the most reliable one: id > name > type+placeholder > className"""
            
            response_content = await llm_provider.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a form analysis assistant. Analyze forms and determine appropriate values to fill. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response_content)
            
            # Extract fields from LLM response
            analyzed_fields = result.get("fields", {})
            
            # Generate temporary email if needed
            temp_email = f"temp_{random.randint(100000, 999999)}@example.com"
            temp_password = f"TempPass{random.randint(1000, 9999)}!"
            
            # Post-process: ensure we have selectors and values
            final_fields = {}
            for field_id, field_info in analyzed_fields.items():
                selector = field_info.get("selector")
                value = field_info.get("value")
                field_type = field_info.get("type", "text")
                
                # If it's an email field and value is generic or missing, use temp email
                if field_type == "email":
                    if not value or "example.com" in str(value).lower() or "@" not in str(value):
                        value = temp_email
                
                # If it's a password field and value is generic or missing, use temp password
                if field_type == "password":
                    if not value or len(str(value)) < 6:
                        value = temp_password
                
                if selector and value:
                    final_fields[field_id] = {
                        "selector": selector,
                        "value": value,
                        "type": field_type
                    }
                elif selector:
                    # If we have a selector but no value, try to generate one based on type
                    if field_type == "email":
                        final_fields[field_id] = {
                            "selector": selector,
                            "value": temp_email,
                            "type": field_type
                        }
                    elif field_type == "password":
                        final_fields[field_id] = {
                            "selector": selector,
                            "value": temp_password,
                            "type": field_type
                        }
            
            return {
                "status": "success",
                "fields": final_fields,
                "form_structure": form_data
            }
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            return {
                "status": "error",
                "error": str(e),
                "traceback": error_trace
            }
    
    async def fill_form(self, fields: dict) -> dict:
        """Fill form fields dynamically.
        
        fields format: {"field_name": {"selector": "css_selector", "value": "text"}}
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        results = {}
        for field_name, field_info in fields.items():
            selector = field_info.get("selector")
            value = field_info.get("value")
            
            if not selector or value is None:
                continue
            
            try:
                # Try to find and fill the field
                await self.page.wait_for_selector(selector, state="visible", timeout=5000)
                # Clear the field first
                await self.page.fill(selector, "")
                # Type the value with a small delay to simulate human typing
                await self.page.type(selector, str(value), delay=50)
                results[field_name] = {"status": "success", "selector": selector, "value": value}
            except Exception as e:
                # Try alternative selectors
                field_type = field_info.get("type", "")
                alternative_selectors = []
                
                # Generate alternative selectors based on field type
                if field_type == "email":
                    alternative_selectors = [
                        "input[type='email']",
                        "input[name*='email']",
                        "input[id*='email']",
                        "input[placeholder*='email' i]"
                    ]
                elif field_type == "password":
                    alternative_selectors = [
                        "input[type='password']",
                        "input[name*='password']",
                        "input[id*='password']"
                    ]
                
                # Try alternatives
                filled = False
                for alt_selector in alternative_selectors:
                    try:
                        await self.page.wait_for_selector(alt_selector, state="visible", timeout=2000)
                        await self.page.fill(alt_selector, "")
                        await self.page.type(alt_selector, str(value), delay=50)
                        results[field_name] = {"status": "success", "selector": alt_selector, "value": value, "original_selector": selector}
                        filled = True
                        break
                    except:
                        continue
                
                if not filled:
                    results[field_name] = {"status": "error", "error": str(e), "selector": selector}
        
        return {
            "status": "success" if all(r.get("status") == "success" for r in results.values()) else "partial",
            "fields": results
        }
    
    async def submit_form(self, selector: str = None) -> dict:
        """Submit a form by selector or find submit button."""
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        try:
            # Store current URL before submission
            url_before = self.page.url
            
            if selector:
                await self.page.wait_for_selector(selector, state="visible", timeout=5000)
                await self.page.click(selector)
            else:
                # Try to find submit button
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    "form button",
                    "[type='submit']"
                ]
                for sel in submit_selectors:
                    try:
                        await self.page.wait_for_selector(sel, state="visible", timeout=2000)
                        await self.page.click(sel)
                        break
                    except:
                        continue
                else:
                    return {"status": "error", "error": "No submit button found"}
            
            # Wait for navigation or result
            try:
                # Wait for navigation (if form causes redirect)
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                # If no navigation, wait a bit for any dynamic content
                await self.page.wait_for_timeout(2000)
            
            url_after = self.page.url
            
            # Detect what happened after submission
            result_info = await self._detect_form_result()
            
            return {
                "status": "success",
                "url": url_after,
                "url_changed": url_after != url_before,
                "title": await self.page.title(),
                "result_info": result_info
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _detect_form_result(self) -> dict:
        """Detect what happened after form submission (success, error, etc.)."""
        if not self.page:
            return {}
        
        try:
            result = await self.page.evaluate("""
                () => {
                    const info = {
                        hasSuccessMessage: false,
                        hasErrorMessage: false,
                        successSelectors: [],
                        errorSelectors: [],
                        messages: [],
                        urlChanged: false
                    };
                    
                    // Common success indicators
                    const successPatterns = [
                        /success/i,
                        /thank you/i,
                        /registered/i,
                        /signed up/i,
                        /created/i,
                        /welcome/i,
                        /confirmed/i,
                        /verified/i
                    ];
                    
                    // Common error indicators
                    const errorPatterns = [
                        /error/i,
                        /invalid/i,
                        /required/i,
                        /failed/i,
                        /try again/i,
                        /incorrect/i
                    ];
                    
                    // Check for success/error messages in common locations
                    const selectors = [
                        '.success', '.success-message', '.alert-success', '[class*="success"]',
                        '.error', '.error-message', '.alert-error', '[class*="error"]',
                        '.message', '.notification', '.alert', '.toast',
                        '[role="alert"]', '[role="status"]',
                        'div[class*="message"]', 'p[class*="message"]'
                    ];
                    
                    for (const sel of selectors) {
                        try {
                            const elements = document.querySelectorAll(sel);
                            elements.forEach(el => {
                                const text = el.textContent?.toLowerCase() || '';
                                const isVisible = el.offsetParent !== null && 
                                                 window.getComputedStyle(el).display !== 'none';
                                
                                if (isVisible && text.length > 0) {
                                    const isSuccess = successPatterns.some(pattern => pattern.test(text));
                                    const isError = errorPatterns.some(pattern => pattern.test(text));
                                    
                                    if (isSuccess) {
                                        info.hasSuccessMessage = true;
                                        info.successSelectors.push(sel);
                                        info.messages.push({
                                            type: 'success',
                                            selector: sel,
                                            text: el.textContent?.trim() || ''
                                        });
                                    } else if (isError) {
                                        info.hasErrorMessage = true;
                                        info.errorSelectors.push(sel);
                                        info.messages.push({
                                            type: 'error',
                                            selector: sel,
                                            text: el.textContent?.trim() || ''
                                        });
                                    }
                                }
                            });
                        } catch (e) {
                            continue;
                        }
                    }
                    
                    // Also check page title and body text for indicators
                    const bodyText = document.body.textContent?.toLowerCase() || '';
                    const titleText = document.title.toLowerCase();
                    
                    if (successPatterns.some(p => p.test(bodyText) || p.test(titleText))) {
                        info.hasSuccessMessage = true;
                    }
                    if (errorPatterns.some(p => p.test(bodyText) || p.test(titleText))) {
                        info.hasErrorMessage = true;
                    }
                    
                    return info;
                }
            """)
            
            return result
        except Exception as e:
            return {}

    async def extract(self, schema: dict, limit: int = None) -> dict:
        """Extract data from page using CSS selectors with site-specific fallbacks.
        
        Schema format: {"field_name": "css_selector"}
        Returns structured data with arrays for each field.
        """
        if not self.page:
            return {"status": "error", "error": "Browser not initialized"}
        
        # Get site-specific selectors as fallback
        site_selectors = get_selectors_for_site(self.current_site)
        
        # First, try to diagnose the page structure - especially for Google Maps
        diagnostic = await self.page.evaluate("""
            () => {
                const info = {
                    url: window.location.href,
                    title: document.title,
                    productContainers: [],
                    sampleSelectors: {},
                    mapsStructure: null
                };
                
                // Check for common selectors (Flipkart, Amazon, Google Maps)
                const url = window.location.href;
                const isAmazon = url.includes('amazon');
                const isGoogleMaps = url.includes('maps.google');
                
                // Deep inspection for Google Maps
                if (isGoogleMaps) {
                    info.mapsStructure = {
                        // Try to find result containers with various strategies
                        containers: {
                            dataResultIndex: document.querySelectorAll('[data-result-index]').length,
                            roleArticle: document.querySelectorAll('div[role="article"]').length,
                            sectionResult: document.querySelectorAll('[class*="section-result"]').length,
                            // Look for clickable result items
                            clickableResults: document.querySelectorAll('[jsaction*="click"][role="button"]').length,
                            // Look for result list items
                            resultItems: document.querySelectorAll('div[class*="result"]').length,
                            // Look for items with restaurant names
                            itemsWithH3: document.querySelectorAll('div:has(h3)').length
                        },
                        // Try to find names
                        names: {
                            qBF1Pd: document.querySelectorAll('.qBF1Pd').length,
                            h3Elements: document.querySelectorAll('h3').length,
                            fontHeadline: document.querySelectorAll('[class*="fontHeadline"]').length,
                            // Look for clickable names
                            clickableNames: document.querySelectorAll('a h3, button h3').length
                        },
                        // Try to find ratings
                        ratings: {
                            MW4etd: document.querySelectorAll('.MW4etd').length,
                            ariaLabelStars: document.querySelectorAll('[aria-label*="star"]').length,
                            ratingElements: document.querySelectorAll('[class*="rating"], [class*="Rating"]').length
                        },
                        // Try to find locations
                        locations: {
                            W4Efsd: document.querySelectorAll('.W4Efsd').length,
                            addressElements: document.querySelectorAll('[class*="address"], [class*="Address"]').length,
                            locationText: document.querySelectorAll('[class*="location"], [class*="Location"]').length
                        },
                        // Sample actual structure
                        sampleStructure: null
                    };
                    
                    // Try to find a sample result container
                    let sampleContainer = null;
                    const containerSelectors = [
                        '[data-result-index]',
                        'div[role="article"]',
                        '[class*="section-result"]',
                        'div[jsaction*="click"]',
                        'div:has(h3)'
                    ];
                    
                    for (const sel of containerSelectors) {
                        try {
                            const containers = document.querySelectorAll(sel);
                            if (containers.length > 0) {
                                sampleContainer = containers[0];
                                info.mapsStructure.sampleStructure = {
                                    selector: sel,
                                    count: containers.length,
                                    // Get all classes on the container
                                    classes: Array.from(sampleContainer.classList || []),
                                    // Get inner structure
                                    hasH3: !!sampleContainer.querySelector('h3'),
                                    hasRating: !!sampleContainer.querySelector('[aria-label*="star"]'),
                                    hasLink: !!sampleContainer.querySelector('a[href*="maps.google"]'),
                                    // Get text content preview
                                    textPreview: sampleContainer.textContent?.substring(0, 200) || '',
                                    // Get HTML structure (first 1000 chars)
                                    htmlPreview: sampleContainer.outerHTML?.substring(0, 1000) || ''
                                };
                                break;
                            }
                        } catch (e) {
                            continue;
                        }
                    }
                    
                    // Also try to find results by looking for common patterns
                    // Google Maps often uses specific class patterns
                    const allDivs = Array.from(document.querySelectorAll('div'));
                    const resultCandidates = allDivs.filter(div => {
                        const text = div.textContent || '';
                        const hasRating = /\\d\\.\\d.*star/i.test(text) || div.querySelector('[aria-label*="star"]');
                        const hasName = div.querySelector('h3') || /^[A-Z][a-z]+/.test(text.trim());
                        return hasRating && hasName && text.length > 50 && text.length < 500;
                    });
                    info.mapsStructure.candidateResults = resultCandidates.length;
                    
                    // Get a sample candidate if found
                    if (resultCandidates.length > 0) {
                        const candidate = resultCandidates[0];
                        info.mapsStructure.candidateSample = {
                            classes: Array.from(candidate.classList || []),
                            textPreview: candidate.textContent?.substring(0, 200) || '',
                            htmlPreview: candidate.outerHTML?.substring(0, 1000) || ''
                        };
                    }
                }
                
                const checks = isGoogleMaps ? [
                    { name: 'data-result-index', selector: '[data-result-index]', count: document.querySelectorAll('[data-result-index]').length },
                    { name: 'role=article', selector: 'div[role="article"]', count: document.querySelectorAll('div[role="article"]').length },
                    { name: 'section-result', selector: '[class*="section-result"]', count: document.querySelectorAll('[class*="section-result"]').length },
                    { name: 'qBF1Pd (name)', selector: '.qBF1Pd', count: document.querySelectorAll('.qBF1Pd').length },
                    { name: 'MW4etd (rating)', selector: '.MW4etd', count: document.querySelectorAll('.MW4etd').length },
                    { name: 'W4Efsd (location)', selector: '.W4Efsd', count: document.querySelectorAll('.W4Efsd').length },
                    { name: 'h3 elements', selector: 'h3', count: document.querySelectorAll('h3').length },
                    { name: 'aria-label stars', selector: '[aria-label*="star"]', count: document.querySelectorAll('[aria-label*="star"]').length }
                ] : isAmazon ? [
                    { name: 's-search-result', selector: '[data-component-type="s-search-result"]', count: document.querySelectorAll('[data-component-type="s-search-result"]').length },
                    { name: 's-result-item', selector: '.s-result-item', count: document.querySelectorAll('.s-result-item').length },
                    { name: 'data-asin', selector: '[data-asin]', count: document.querySelectorAll('[data-asin]').length },
                    { name: 'product links', selector: 'a[href*="/dp/"]', count: document.querySelectorAll('a[href*="/dp/"]').length },
                    { name: 'price', selector: '.a-price-whole', count: document.querySelectorAll('.a-price-whole').length },
                    { name: 'rating', selector: '.a-icon-alt', count: document.querySelectorAll('.a-icon-alt').length }
                ] : [
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
                let firstContainer = null;
                if (isGoogleMaps) {
                    firstContainer = document.querySelector('[data-result-index]') || 
                                    document.querySelector('div[role="article"]') ||
                                    document.querySelector('[class*="section-result"]');
                } else if (isAmazon) {
                    firstContainer = document.querySelector('[data-component-type="s-search-result"]') || 
                                    document.querySelector('.s-result-item');
                } else {
                    firstContainer = document.querySelector('div[data-id]') || 
                                    document.querySelector('._1AtVbE');
                }
                if (firstContainer) {
                    info.sampleHTML = firstContainer.outerHTML.substring(0, 500);
                }
                
                return info;
            }
        """)
        
        
        try:
            # Use a smarter extraction strategy - extract from product containers
            result = await self.page.evaluate(r"""
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
                    
                    // For different sites, try to find result containers
                    let productContainers = [];
                    if (site === 'google') {
                        // Google search results - local discovery
                        const containerSelectors = [
                            '[data-ved]',  // Google result items
                            '.g',  // Google result class
                            '.tF2Cxc',  // Google result container
                            '.yuRUbf',  // Google result link container
                            '[data-header-feature]',  // Featured results
                            '.LC20lb',  // Google result title
                            'div[data-ved]'  // Result divs
                        ];
                        for (const sel of containerSelectors) {
                            try {
                                const containers = document.querySelectorAll(sel);
                                if (containers.length > 0) {
                                    productContainers = Array.from(containers).slice(0, 20);
                                    break;
                                }
                            } catch (e) {
                                continue;
                            }
                        }
                    } else if (site === 'flipkart') {
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
                    } else if (site === 'google_maps') {
                        // Google Maps result containers - try multiple strategies
                        const containerSelectors = [
                            '[data-result-index]',  // Most reliable - Maps uses this
                            'div[role="article"]',  // Semantic role
                            '[class*="section-result"]',  // Class-based
                            '[class*="result-container"]',  // Alternative class
                            '.Nv2PK',  // Maps result card class
                            'div[jsaction*="click"]',  // Clickable result divs
                            // Try finding divs with h3 and rating
                            'div:has(h3):has([aria-label*="star"])',
                            // Try finding by structure - divs that contain both name and rating
                            'div:has(h3)'
                        ];
                        
                        for (const sel of containerSelectors) {
                            try {
                                const containers = document.querySelectorAll(sel);
                                if (containers.length > 0) {
                                    // Filter to only include containers that look like results
                                    const filtered = Array.from(containers).filter(container => {
                                        const text = container.textContent || '';
                                        // Should have some text content
                                        if (text.length < 20) return false;
                                        // Should have either a rating indicator or be clickable
                                        const hasRating = container.querySelector('[aria-label*="star"]') || /\\d\\.\\d.*star/i.test(text);
                                        const hasName = container.querySelector('h3') || /^[A-Z]/.test(text.trim());
                                        return hasRating || hasName;
                                    });
                                    
                                    if (filtered.length > 0) {
                                        productContainers = filtered.slice(0, 20); // Limit to 20
                                        console.log(`[DEBUG] Found ${productContainers.length} Google Maps results using selector: ${sel}`);
                                        break;
                                    }
                                }
                            } catch (e) {
                                // Some selectors like :has() might not be supported, skip
                                continue;
                            }
                        }
                        
                        // If still no containers, try a more aggressive search
                        if (productContainers.length === 0) {
                            console.log('[DEBUG] No containers found with standard selectors, trying fallback...');
                            // Look for divs that contain h3 elements (likely result names)
                            try {
                                const allDivs = Array.from(document.querySelectorAll('div'));
                                const candidates = allDivs.filter(div => {
                                    const text = div.textContent || '';
                                    const hasH3 = div.querySelector('h3');
                                    const hasRating = div.querySelector('[aria-label*="star"]') || /\\d\\.\\d.*star/i.test(text);
                                    // Should be a reasonable size (not too small, not too large)
                                    return hasH3 && text.length > 50 && text.length < 1000 && (hasRating || text.includes('Open') || text.includes('Closed'));
                                });
                                
                                if (candidates.length > 0) {
                                    productContainers = candidates.slice(0, 20);
                                    console.log(`[DEBUG] Found ${productContainers.length} Google Maps results using fallback strategy`);
                                }
                            } catch (e) {
                                console.log('[DEBUG] Fallback strategy failed:', e);
                            }
                        }
                    } else if (site === 'amazon') {
                        // Amazon-specific container selectors
                        const containerSelectors = [
                            '[data-component-type="s-search-result"]',  // Most common
                            '.s-result-item',  // Alternative
                            '[data-asin]',  // Products have ASIN
                            '.s-result-list > div',  // Result list items
                            'div[data-index]'  // Indexed items
                        ];
                        for (const sel of containerSelectors) {
                            try {
                                const containers = document.querySelectorAll(sel);
                                if (containers.length > 0) {
                                    productContainers = Array.from(containers).slice(0, 30); // Get more to filter later
                                    break;
                                }
                            } catch (e) {
                                continue;
                            }
                        }
                        
                        // Filter out sponsored items and accessories for Amazon
                        if (productContainers.length > 0) {
                            productContainers = productContainers.filter(container => {
                                const text = (container.textContent || container.innerText || '').toLowerCase();
                                const name = (container.querySelector('h2 a span, h2 a')?.textContent || '').toLowerCase();
                                
                                // Filter out sponsored items
                                if (text.includes('sponsored') || name.includes('sponsored')) {
                                    return false;
                                }
                                
                                // Filter out accessories when searching for laptops/computers
                                // Common accessory keywords
                                const accessoryKeywords = [
                                    'sleeve', 'case', 'cover', 'skin', 'protector', 'keyboard cover',
                                    'screen protector', 'stand', 'bag', 'carrying case', 'sticker',
                                    'decals', 'adapter', 'charger', 'cable', 'hub', 'dock'
                                ];
                                
                                // Check if this looks like an accessory
                                const isAccessory = accessoryKeywords.some(keyword => 
                                    name.includes(keyword) || text.includes(keyword)
                                );
                                
                                // If searching for a product (not an accessory), filter out accessories
                                // This is a heuristic - if the search query contains product names like "macbook", "laptop", etc.
                                // and the item is clearly an accessory, filter it out
                                const searchQuery = window.location.search || '';
                                const isProductSearch = /macbook|laptop|computer|phone|tablet|watch/i.test(searchQuery);
                                
                                if (isProductSearch && isAccessory) {
                                    return false;
                                }
                                
                                return true;
                            }).slice(0, 20); // Limit to 20 after filtering
                        }
                    }
                    
                    // If we found containers, extract from each container
                    if (productContainers.length > 0) {
                        const items = [];
                        const maxItems = limit && limit > 0 ? limit : productContainers.length;
                        
                        for (let i = 0; i < Math.min(maxItems, productContainers.length); i++) {
                            const container = productContainers[i];
                            const item = {};
                            
                            // Extract link/url first (most reliable)
                            // Support both 'link' and 'url' keys, but prefer 'url'
                            const urlKey = schema.url ? 'url' : (schema.link ? 'link' : null);
                            if (urlKey) {
                                let linkEl = null;
                                // Site-specific link selectors
                                if (site === 'amazon') {
                                    linkEl = container.querySelector('a[href*="/dp/"]') || 
                                             container.querySelector('a[href*="/gp/product/"]') ||
                                             container.querySelector('h2 a') ||
                                             container.closest('a[href*="/dp/"]');
                                } else if (site === 'google') {
                                    // Google search results
                                    linkEl = container.querySelector('a[href^="http"]') ||
                                             container.querySelector('h3 a') ||
                                             container.querySelector('.yuRUbf a') ||
                                             container.closest('a[href^="http"]');
                                } else if (site === 'google_maps') {
                                    // Google Maps results - try multiple link strategies
                                    linkEl = container.querySelector('a[href*="maps.google.com"]') ||
                                             container.querySelector('a[href*="/maps/place"]') ||
                                             container.querySelector('a[data-value="url"]') ||
                                             container.closest('a[href*="maps.google.com"]') ||
                                             container.closest('a[href*="/maps/place"]') ||
                                             container.querySelector('a');
                                    
                                    // If no link found, try to find via name element
                                    if (!linkEl) {
                                        const nameEl = container.querySelector('.qBF1Pd, h3, [class*="qBF1Pd"]');
                                        if (nameEl) {
                                            // Try to find parent link or construct URL
                                            linkEl = nameEl.closest('a[href*="maps"]') || 
                                                    nameEl.closest('a') || 
                                                    container.closest('a[href*="maps"]');
                                        }
                                    }
                                } else {
                                    // Flipkart and others
                                    linkEl = container.querySelector('a[href*="/p/"]') || 
                                             container.closest('a[href*="/p/"]');
                                }
                                if (linkEl) {
                                    let href = linkEl.href || linkEl.getAttribute('href') || '';
                                    if (!href.startsWith('http')) {
                                        href = window.location.origin + href;
                                    }
                                    item[urlKey] = href;
                                    // Also set 'url' if schema has it, even if key was 'link'
                                    if (schema.url && urlKey === 'link') {
                                        item['url'] = href;
                                    }
                                } else if (site === 'google_maps' && item.name) {
                                    // For Google Maps, if no link found, construct a search URL
                                    const searchQuery = encodeURIComponent(item.name);
                                    item[urlKey] = `https://www.google.com/maps/search/${searchQuery}`;
                                    if (schema.url && urlKey === 'link') {
                                        item['url'] = item[urlKey];
                                    }
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
                                    let linkEl = null;
                                    if (site === 'amazon') {
                                        linkEl = container.querySelector('h2 a') || 
                                                container.querySelector('a[href*="/dp/"]') ||
                                                container.querySelector('a[href*="/gp/product/"]');
                                    } else if (site === 'google') {
                                        // Google search results - get title from h3
                                        const h3 = container.querySelector('h3, .LC20lb, .DKV0Md');
                                        if (h3) {
                                            name = h3.textContent?.trim() || h3.innerText?.trim();
                                        }
                                        linkEl = container.querySelector('a[href^="http"]') ||
                                                container.querySelector('h3 a');
                                    } else if (site === 'google_maps') {
                                        // Google Maps - get name from h3 or .qBF1Pd
                                        const nameEl = container.querySelector('.qBF1Pd, h3, [class*="qBF1Pd"]');
                                        if (nameEl) {
                                            name = nameEl.textContent?.trim() || nameEl.innerText?.trim();
                                        }
                                        linkEl = container.querySelector('a[href*="maps.google.com"]') ||
                                                container.closest('a[href*="maps.google.com"]');
                                    } else {
                                        linkEl = container.querySelector('a[href*="/p/"]');
                                    }
                                    if (linkEl) {
                                        // Get title attribute first (cleaner)
                                        name = linkEl.getAttribute('title');
                                        if (!name) {
                                            // For Amazon, try span inside h2
                                            if (site === 'amazon') {
                                                const span = linkEl.querySelector('span');
                                                if (span) {
                                                    name = span.textContent?.trim() || span.innerText?.trim();
                                                }
                                            }
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
                                        
                                        // For Amazon, remove "Sponsored" prefix
                                        if (site === 'amazon') {
                                            name = name.replace(/^Sponsored\s*/i, '');
                                            name = name.replace(/Sponsored\s*You are seeing this ad based on.*?Let us know\s*/i, '');
                                        }
                                        
                                        // Remove common prefixes
                                        name = name.replace(/^(Add to Compare|Compare|Add to Cart|Buy Now)\s*/i, '');
                                        
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
                            
                            // Extract price - try multiple strategies (prefer discounted price)
                            if (schema.price) {
                                let price = null;
                                
                                // For Amazon, use .a-offscreen which contains the full price as a single string
                                if (site === 'amazon') {
                                    // Try .a-offscreen first (most reliable - contains full price like "₹93,900.00")
                                    const offscreenPrice = container.querySelector('.a-price .a-offscreen');
                                    if (offscreenPrice) {
                                        price = offscreenPrice.textContent?.trim() || offscreenPrice.innerText?.trim();
                                    }
                                    
                                    // Fallback: construct price from components if offscreen not available
                                    if (!price) {
                                        const priceWhole = container.querySelector('.a-price-whole');
                                        const priceSymbol = container.querySelector('.a-price-symbol');
                                        const priceFraction = container.querySelector('.a-price-fraction');
                                        
                                        if (priceWhole) {
                                            let wholeText = priceWhole.textContent?.trim() || priceWhole.innerText?.trim() || '';
                                            // Remove commas from whole number
                                            wholeText = wholeText.replace(/,/g, '');
                                            
                                            if (priceSymbol && priceFraction) {
                                                const symbol = priceSymbol.textContent?.trim() || '';
                                                const fraction = priceFraction.textContent?.trim() || '';
                                                price = symbol + wholeText + '.' + fraction;
                                            } else if (priceSymbol) {
                                                const symbol = priceSymbol.textContent?.trim() || '';
                                                price = symbol + wholeText;
                                            } else {
                                                price = wholeText;
                                            }
                                        }
                                    }
                                    
                                    // Final fallback: try text pattern matching
                                    if (!price) {
                                        const containerText = container.textContent || container.innerText || '';
                                        // Match price pattern: ₹ followed by digits and commas
                                        const priceMatch = containerText.match(/[₹$]\s*([\d,]+(?:\.\d{2})?)/);
                                        if (priceMatch) {
                                            price = priceMatch[0].trim();
                                        }
                                    }
                                } else {
                                    // For other sites, use existing logic
                                    const priceSelectors = [schema.price];
                                    if (siteSelectors && siteSelectors.product_price) {
                                        priceSelectors.push(...siteSelectors.product_price);
                                    }
                                    const priceValues = trySelectors(priceSelectors, container, false);
                                    
                                    if (priceValues.length > 0) {
                                        price = priceValues[0];
                                    } else {
                                        // Fallback: look for price-like patterns in text
                                        const containerText = container.textContent || container.innerText || '';
                                        const priceMatches = containerText.match(/[₹$]\s*[\d,]+/g);
                                        if (priceMatches && priceMatches.length > 0) {
                                            price = priceMatches[0];
                                        }
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
                                // For Google, add specific selectors
                                if (site === 'google') {
                                    ratingSelectors.push('.fG8Fp', '[aria-label*="star"]', '.Aq14fc', '.z3VRc');
                                } else if (site === 'google_maps') {
                                    // Google Maps rating selectors - try multiple approaches
                                    ratingSelectors.push(
                                        '.MW4etd', 
                                        '[class*="MW4etd"]', 
                                        '[aria-label*="star"]', 
                                        '[data-value="rating"]',
                                        '[aria-label*="rating"]',
                                        '[class*="rating"]',
                                        '[class*="Rating"]'
                                    );
                                    
                                    // Also try to extract from text patterns
                                    const containerText = container.textContent || container.innerText || '';
                                    // Pattern: "4.7" or "4.7 stars" or "4.7★"
                                    const ratingMatch = containerText.match(/(\\d\\.\\d)\\s*(?:star|★|rating)/i);
                                    if (ratingMatch) {
                                        const ratingValue = parseFloat(ratingMatch[1]);
                                        if (ratingValue >= 0 && ratingValue <= 5) {
                                            rating = ratingMatch[1];
                                        }
                                    }
                                }
                                const ratingValues = trySelectors(ratingSelectors, container, false);
                                if (ratingValues[0]) {
                                    rating = ratingValues[0];
                                } else {
                                    // Fallback: look for rating patterns in text
                                    const containerText = container.textContent || container.innerText || '';
                                    // Try to find rating BEFORE the ratings count
                                    // Pattern: "4.7" followed by comma and number (ratings count) or "Ratings"
                                    // We want the first decimal number that's between 0-5 (actual rating)
                                    // NOT the large number after "Ratings" (which is the count)
                                    const ratingPatterns = [
                                        /(\d\.\d)\s*[,\d]+\s*Ratings?/i,  // "4.7 1,846 Ratings" - get 4.7
                                        /(\d\.\d)\s*out of 5/i,  // "4.7 out of 5"
                                        /(\d\.\d)\s*\/\s*5/i,  // "4.7 / 5"
                                        /Rating[:\s]*(\d\.\d)/i,  // "Rating: 4.7"
                                        /^(\d\.\d)\s*[,\d]+/,  // "4.7 1,846" at start
                                        /(\d\.\d)\s*★/  // "4.7 ★" (Google style)
                                    ];
                                    for (const pattern of ratingPatterns) {
                                        const match = containerText.match(pattern);
                                        if (match) {
                                            const ratingValue = parseFloat(match[1]);
                                            // Validate it's a reasonable rating (0-5)
                                            if (ratingValue >= 0 && ratingValue <= 5) {
                                                rating = match[1];
                                                break;
                                            }
                                        }
                                    }
                                    // If still not found, try to find any decimal between 0-5
                                    if (!rating) {
                                        const allDecimals = containerText.match(/\d\.\d/g);
                                        if (allDecimals) {
                                            for (const dec of allDecimals) {
                                                const val = parseFloat(dec);
                                                if (val >= 0 && val <= 5) {
                                                    rating = dec;
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                                item.rating = rating;
                            }
                            
                            // Extract location for local discovery
                            if (schema.location) {
                                let location = null;
                                const locationSelectors = [schema.location];
                                if (site === 'google') {
                                    locationSelectors.push('.VkpGBb', '.fG8Fp', '[data-attrid]');
                                } else if (site === 'google_maps') {
                                    // Google Maps location/address selectors
                                    locationSelectors.push('.W4Efsd', '[class*="W4Efsd"]', '[data-value="address"]', '[aria-label*="Address"]');
                                }
                                const locationValues = trySelectors(locationSelectors, container, false);
                                if (locationValues[0]) {
                                    location = locationValues[0];
                                } else {
                                    // Fallback: look for location patterns
                                    const containerText = container.textContent || container.innerText || '';
                                    // Try to find location indicators
                                    const locationMatch = containerText.match(/(?:near|in|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/);
                                    if (locationMatch) {
                                        location = locationMatch[1];
                                    }
                                    // For Google Maps, try to extract address from text
                                    if (!location && site === 'google_maps') {
                                        // Look for address-like patterns
                                        // Pattern: "Shop No. X, Y, Z" or street addresses
                                        const addressPatterns = [
                                            /(Shop\\s*No\\.?\\s*\\d+[^,]*,\\s*[^,]+(?:,\\s*[A-Z][a-z]+)*)/i,
                                            /(\\d+[^,]*,\\s*[^,]+(?:,\\s*[A-Z][a-z]+)*)/,
                                            /(near\\s+[A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)/i,
                                            /(at\\s+[A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)/i
                                        ];
                                        
                                        for (const pattern of addressPatterns) {
                                            const match = containerText.match(pattern);
                                            if (match && match[1]) {
                                                location = match[1].trim();
                                                break;
                                            }
                                        }
                                        
                                        // If still no location, try to get text after the name
                                        if (!location) {
                                            const lines = containerText.split(/\\n|\\r/).map(l => l.trim()).filter(l => l.length > 5);
                                            // Usually location is in the second or third line
                                            for (let i = 1; i < Math.min(3, lines.length); i++) {
                                                const line = lines[i];
                                                // Skip if it's a rating or common words
                                                if (!/\\d\\.\\d|star|rating|open|closed|order|reserve/i.test(line)) {
                                                    location = line.substring(0, 100);
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                                item.location = location;
                            }
                            
                            // Only add item if it has at least name or url/link
                            if (item.name || item.url || item.link) {
                                items.push(item);
                            }
                        }
                        
                        // Convert to field-based format
                        if (items.length > 0) {
                            for (const key of Object.keys(schema)) {
                                // Map both 'link' and 'url' to the same field if needed
                                if (key === 'url' || key === 'link') {
                                    data[key] = items.map(item => item.url || item.link || null);
                                } else {
                                    data[key] = items.map(item => item[key] || null);
                                }
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
                import re  # Import at the top of the processing block
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
                            # Handle Indian format: ₹1,25,999 or 1,25,999 or ₹125999
                            price_clean = str(value).strip()
                            # Remove currency symbols and commas first
                            price_clean = re.sub(r'[₹$€£,\s]', '', price_clean)
                            # Extract only digits and decimal point
                            price_str = re.sub(r'[^\d.]', '', price_clean)
                            
                            if price_str:
                                try:
                                    item[field] = float(price_str)
                                except (ValueError, TypeError):
                                    # Fallback: try to extract first number
                                    numbers = re.findall(r'\d+\.?\d*', price_clean)
                                    if numbers:
                                        try:
                                            item[field] = float(numbers[0])
                                        except:
                                            item[field] = None
                                    else:
                                        item[field] = None
                            else:
                                item[field] = None
                        elif field == 'rating' and value:
                            # Extract numeric rating (handle "4.5", "4.5 out of 5", "4.5 Ratings", etc.)
                            # Try to extract just the number
                            rating_str = str(value).strip()
                            # Try to parse as float first
                            try:
                                rating_float = float(rating_str)
                                # Validate it's a reasonable rating (0-5)
                                if 0 <= rating_float <= 5:
                                    item[field] = rating_float
                                else:
                                    # If it's a large number, it might be the count, try to find the actual rating
                                    # Look for decimal pattern in the original value
                                    rating_match = re.search(r'(\d\.\d)', str(value))
                                    if rating_match:
                                        rating_float = float(rating_match.group(1))
                                        if 0 <= rating_float <= 5:
                                            item[field] = rating_float
                                        else:
                                            item[field] = None
                                    else:
                                        item[field] = None
                            except:
                                # If parsing fails, try regex to find decimal
                                rating_match = re.search(r'(\d\.\d)', rating_str)
                                if rating_match:
                                    try:
                                        rating_float = float(rating_match.group(1))
                                        if 0 <= rating_float <= 5:
                                            item[field] = rating_float
                                        else:
                                            item[field] = None
                                    except:
                                        item[field] = None
                                else:
                                    item[field] = None
                        elif field == 'link' or field == 'url':
                            # Ensure link is properly formatted
                            if value:
                                item[field] = str(value).strip()
                            else:
                                item[field] = None
                        elif field == 'name':
                            # Clean name
                            if value:
                                name = str(value).strip()
                                # Remove "Add to Compare" and similar prefixes
                                name = re.sub(r'^(Add to Compare|Compare|Add to Cart|Buy Now)\s*', '', name, flags=re.IGNORECASE)
                                item[field] = name.strip()
                            else:
                                item[field] = None
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
            return {
                "status": "error",
                "error": str(e),
                "diagnostic": diagnostic if 'diagnostic' in locals() else None,
                "traceback": error_trace
            }

# Global instance
browser_agent = BrowserAgent()

