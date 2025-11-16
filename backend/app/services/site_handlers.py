"""
Site-specific handlers for different websites (Google Maps, Amazon, Flipkart, etc.)
This module contains site-specific extraction and interaction logic.
"""
import asyncio
import urllib.parse
from typing import Dict
from playwright.async_api import Page, BrowserContext


class GoogleMapsHandler:
    """Handler for Google Maps specific operations."""
    
    @staticmethod
    async def search(page: Page, context: BrowserContext, query: str, limit: int = 5, 
                     lat: float = 12.9250, lng: float = 77.6400) -> Dict:
        """
        Search Google Maps for `query` near given lat/lng (defaults to HSR Layout, Bangalore) and extract results.
        This is a robust, battle-tested function that handles Maps' async rendering and common issues.
        
        Returns: {"status":"success","data":[{name, rating, address, url}], "diagnostic": {...}}
        """
        # Ensure context has India locale/timezone and geolocation (helps results & reduces surprises)
        try:
            if context:
                await context.set_default_navigation_timeout(45000)
                await context.grant_permissions(["geolocation"])
                await context.set_geolocation({"latitude": lat, "longitude": lng, "accuracy": 100})
        except Exception as e:
            # Some contexts may not support changing geolocation after creation; ignore if not supported
            pass

        # Build URL containing search term (helps maps initial view)
        encoded = urllib.parse.quote_plus(query)
        maps_url = f"https://www.google.com/maps/search/{encoded}/@{lat},{lng},13z"
        
        try:
            await page.goto(maps_url, wait_until="load", timeout=30000)
        except Exception as e:
            pass

        # Wait for search box to appear (more reliable than networkidle)
        try:
            await page.wait_for_selector("input#searchboxinput, input[aria-label*='Search']", timeout=15000)
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
            input_set = await page.evaluate(set_input_js, query)
            
            # Press Enter to submit search
            await asyncio.sleep(0.25)
            await page.keyboard.press("Enter")
        except Exception as e:
            # As fallback, try page.fill then Enter
            try:
                await page.fill("input#searchboxinput", query, timeout=3000)
                await page.keyboard.press("Enter")
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
            counts = await page.evaluate("""
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
            page_text = await page.evaluate("() => document.body.innerText.slice(0,2000)")
            diagnostic["pageTextPreview"] = page_text[:2000]
            
            # detect captcha keywords
            if any(k in page_text.lower() for k in ["unusual traffic", "automated queries", "captcha", "verify you're not a robot", "/sorry/"]):
                return {"status":"blocked", "message":"Detected CAPTCHA or Google blocking", "diagnostic": diagnostic}

        # Run diagnostic to inspect actual page structure and adapt selectors
        page_diagnostic = await page.evaluate("""
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
        extraction = await page.evaluate(extraction_js, {"limit": limit, "containerSelector": best_selector})

        return {"status": "success", "data": extraction, "diagnostic": diagnostic}


class GoogleSearchHandler:
    """Handler for Google Search-specific operations."""
    
    @staticmethod
    async def extract_search_results(page: Page, limit: int = 10) -> Dict:
        """
        Extract search result URLs from Google search results.
        Only extracts links from actual search result containers, not ads or other links.
        
        Returns: {"status": "success", "data": [{"title": "...", "url": "..."}], "count": N}
        """
        try:
            # Wait for search results to appear
            await page.wait_for_selector("[data-ved], .g, .tF2Cxc", timeout=10000)
        except:
            pass  # Continue anyway
        
        # Extract search results using specialized JavaScript
        results = await page.evaluate(f"""
            () => {{
                const searchResults = [];
                
                // Find all search result containers - Google uses multiple selectors
                const containerSelectors = [
                    '[data-ved]',  // Most reliable - Google uses this for all results
                    '.g',  // Generic result class
                    '.tF2Cxc',  // Result container
                    '.yuRUbf',  // Link container
                    'div[data-ved]'  // Div with data-ved
                ];
                
                let containers = [];
                for (const sel of containerSelectors) {{
                    try {{
                        const found = document.querySelectorAll(sel);
                        if (found.length > 0) {{
                            containers = Array.from(found);
                            break;
                        }}
                    }} catch(e) {{
                        continue;
                    }}
                }}
                
                // Filter to only actual search results (not ads, not navigation, etc.)
                containers = containers.filter(container => {{
                    // Skip if it's an ad
                    if (container.closest('[data-text-ad]') || 
                        container.closest('.ads') ||
                        container.querySelector('[data-text-ad]')) {{
                        return false;
                    }}
                    
                    // Must have a link
                    const link = container.querySelector('a[href*="http"]');
                    if (!link) return false;
                    
                    // Must have a title (h3 or similar)
                    const title = container.querySelector('h3, .LC20lb, .DKV0Md');
                    if (!title) return false;
                    
                    return true;
                }});
                
                for (let i = 0; i < Math.min({limit}, containers.length); i++) {{
                    const container = containers[i];
                    
                    // Get title
                    const titleEl = container.querySelector('h3, .LC20lb, .DKV0Md, [role="heading"]');
                    const title = titleEl ? titleEl.textContent?.trim() || '' : '';
                    
                    // Get URL - from the main link in the result
                    let url = null;
                    const linkEl = container.querySelector('a[href*="http"]');
                    if (linkEl) {{
                        const href = linkEl.getAttribute('href');
                        if (href && href.startsWith('http')) {{
                            url = href;
                        }} else if (href && href.startsWith('/url?q=')) {{
                            // Google sometimes wraps URLs in /url?q=...
                            const match = href.match(/[?&]q=([^&]+)/);
                            if (match) {{
                                url = decodeURIComponent(match[1]);
                            }}
                        }}
                    }}
                    
                    // Only add if we have both title and URL
                    if (title && url && url.startsWith('http')) {{
                        searchResults.push({{
                            title: title,
                            url: url
                        }});
                    }}
                }}
                
                return searchResults;
            }}
        """)
        
        return {
            "status": "success",
            "data": results,
            "count": len(results)
        }


class SwiggyHandler:
    """Handler for Swiggy-specific operations with anti-detection measures."""
    
    @staticmethod
    async def search(page: Page, context: BrowserContext, query: str, location: str = "HSR Layout Bangalore", limit: int = 5, websocket=None, session_id=None, total_steps=7, plan=None) -> Dict:
        """
        Search Swiggy for restaurants matching query at location and extract results.
        Swiggy requires special handling with stealth mode and two-step search activation.
        
        Returns: {"status":"success","data":[{name, rating, cuisine, location, price}], "diagnostic": {...}}
        """
        try:
            print(f"\n=== SWIGGY SEARCH STARTED ===")
            print(f"Query: '{query}'")
            print(f"Location: '{location}'")
            print(f"Limit: {limit}")
            
            # Build Swiggy URL - go to homepage
            base_url = "https://www.swiggy.com"
            
            # Navigate to Swiggy homepage
            try:
                # Find navigate action in plan (step 1)
                navigate_action = None
                if plan:
                    for action in plan:
                        if action.get("action") == "navigate" and "swiggy" in str(action.get("url", "")).lower():
                            navigate_action = action
                            break
                
                if websocket:
                    step_num = 1
                    if plan:
                        # Find the index of navigate action in plan
                        for idx, action in enumerate(plan):
                            if action.get("action") == "navigate" and "swiggy" in str(action.get("url", "")).lower():
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "navigate",
                        "status": "executing",
                        "step": step_num,
                        "total": total_steps,
                        "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url, "description": "Navigate to Swiggy homepage"}
                    })
                
                print(f"\n[1/7] Navigating to Swiggy homepage: {base_url}")
                await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)  # Let page settle
                print(f"✓ Page loaded: {page.url}")
                
                if websocket:
                    step_num = 1
                    if plan:
                        for idx, action in enumerate(plan):
                            if action.get("action") == "navigate" and "swiggy" in str(action.get("url", "")).lower():
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "navigate",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url},
                        "result": {"status": "success", "url": page.url}
                    })
            except Exception as e:
                print(f"✗ Failed to load Swiggy: {e}")
                if websocket:
                    step_num = 1
                    if plan:
                        for idx, action in enumerate(plan):
                            if action.get("action") == "navigate" and "swiggy" in str(action.get("url", "")).lower():
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "navigate",
                        "status": "error",
                        "step": step_num,
                        "total": total_steps,
                        "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url},
                        "result": {"status": "error", "message": str(e)}
                    })
                return {"status": "error", "message": f"Failed to load Swiggy: {str(e)}"}
            
            # STEP 1: Find and fill the LOCATION input (left box)
            # Find type action for location in plan
            type_location_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "type" and location.lower() in str(action.get("text", "")).lower():
                        type_location_action = action
                        break
            
            if websocket:
                step_num = 2
                if plan:
                    for idx, action in enumerate(plan):
                        if action.get("action") == "type" and location.lower() in str(action.get("text", "")).lower():
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "type",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": type_location_action if type_location_action else {"action": "type", "selector": "input[type='text']", "text": location, "description": f"Type location: {location}"}
                })
            
            print(f"\n[2/7] Setting location: '{location}'")
            location_input_selectors = [
                "input[placeholder*='Enter your delivery location']",
                "input[placeholder*='location']",
                "input[placeholder*='area']",
                # Try by position - location input is usually first
            ]
            
            location_input_found = None
            for selector in location_input_selectors:
                try:
                    await page.wait_for_selector(selector, state="visible", timeout=5000)
                    location_input_found = selector
                    break
                except:
                    continue
            
            # If not found by placeholder, get first text input (usually location)
            if not location_input_found:
                try:
                    all_inputs = await page.query_selector_all("input[type='text']")
                    if len(all_inputs) >= 2:
                        # First input is usually location
                        location_input_found = "input[type='text']"
                        # We'll use the first one
                except:
                    pass
            
            if location_input_found:
                try:
                    # Get all text inputs
                    inputs = await page.query_selector_all("input[type='text']")
                    if len(inputs) >= 1:
                        location_input = inputs[0]  # First input is location
                        
                        # Clear and type location
                        print(f"  Typing location into input...")
                        await location_input.fill("")
                        await location_input.type(location, delay=100)
                        await asyncio.sleep(2)
                        print(f"  ✓ Location typed, waiting for suggestions...")
                        
                        # Wait for location suggestions to appear
                        try:
                            # Wait for suggestion dropdown - try multiple selectors
                            suggestion_visible = False
                            wait_selectors = [
                                "div[class*='_2NKIb']",  # Swiggy suggestion container
                                "div[class*='_2BgUI']",  # Swiggy suggestion item
                                "div[class*='_14IZV']",  # Swiggy "Use my current location"
                                "[role='button'][tabindex]",
                                "[class*='suggestion']",
                                "[class*='Suggestion']"
                            ]
                            
                            for wait_sel in wait_selectors:
                                try:
                                    await page.wait_for_selector(wait_sel, state="visible", timeout=2000)
                                    suggestion_visible = True
                                    break
                                except:
                                    continue
                            
                            if suggestion_visible:
                                await asyncio.sleep(1)
                                
                                # Find all suggestion items - try Swiggy-specific selectors first
                                suggestion_selectors = [
                                    "div[class*='_2BgUI'][role='button']",  # Actual location suggestions
                                    "div[class*='_2BgUI']",  # Without role check
                                    "[role='button'][tabindex='2']",  # First location (after "Use my current location" which is tabindex 0)
                                    "[role='button'][tabindex='3']",  # Second location
                                    "[role='button'][tabindex]",
                                    "[role='option']",
                                    "div[class*='suggestion']",
                                    "li[class*='suggestion']"
                                ]
                                
                                first_location_suggestion = None
                                
                                # Check if user wants "near me" or "current location"
                                location_lower = location.lower() if location else ""
                                use_current_location = any(phrase in location_lower for phrase in ["near me", "current location", "my location", "here"])
                                
                                if use_current_location:
                                    # User wants current location - select index 0 ("Use my current location")
                                    for selector in suggestion_selectors:
                                        try:
                                            suggestions = await page.query_selector_all(selector)
                                            if len(suggestions) > 0:
                                                for suggestion in suggestions:
                                                    text = await suggestion.text_content()
                                                    if text and "Use my current location" in text.strip():
                                                        first_location_suggestion = suggestion
                                                        break
                                                if first_location_suggestion:
                                                    break
                                        except:
                                            continue
                                else:
                                    # User specified a location - find first actual location (skip "Use my current location")
                                    for selector in suggestion_selectors:
                                        try:
                                            suggestions = await page.query_selector_all(selector)
                                            if len(suggestions) > 0:
                                                for suggestion in suggestions:
                                                    text = await suggestion.text_content()
                                                    if text and "Use my current location" not in text.strip() and len(text.strip()) > 5:
                                                        # This is the first actual location suggestion
                                                        first_location_suggestion = suggestion
                                                        break
                                                if first_location_suggestion:
                                                    break
                                        except:
                                            continue
                                
                                if first_location_suggestion:
                                    # Click the first location suggestion
                                    suggestion_text = await first_location_suggestion.text_content()
                                    print(f"  ✓ Found location suggestion: '{suggestion_text[:60] if suggestion_text else 'N/A'}'")
                                    
                                    if websocket:
                                        step_num = 2
                                        if plan:
                                            for idx, action in enumerate(plan):
                                                if action.get("action") == "type" and location.lower() in str(action.get("text", "")).lower():
                                                    step_num = idx + 1
                                                    break
                                        
                                        await websocket.send_json({
                                            "type": "action_status",
                                            "action": "type",
                                            "status": "completed",
                                            "step": step_num,
                                            "total": total_steps,
                                            "details": type_location_action if type_location_action else {"action": "type", "text": location},
                                            "result": {"status": "success"}
                                        })
                                        
                                        # Find click action for location suggestion in plan
                                        click_location_action = None
                                        step_num_click = 3
                                        if plan:
                                            for idx, action in enumerate(plan):
                                                if action.get("action") == "click" and ("location" in str(action.get("selector", "")).lower() or "suggestion" in str(action.get("selector", "")).lower()):
                                                    click_location_action = action
                                                    step_num_click = idx + 1
                                                    break
                                        
                                        await websocket.send_json({
                                            "type": "action_status",
                                            "action": "click",
                                            "status": "executing",
                                            "step": step_num_click,
                                            "total": total_steps,
                                            "details": click_location_action if click_location_action else {"action": "click", "selector": "location suggestion", "description": "Click location suggestion"}
                                        })
                                    
                                    print(f"  Clicking location suggestion...")
                                    await first_location_suggestion.click()
                                    await asyncio.sleep(2)
                                    print(f"  ✓ Location set successfully")
                                    
                                    if websocket:
                                        step_num = 3
                                        if plan:
                                            for idx, action in enumerate(plan):
                                                if action.get("action") == "click" and ("location" in str(action.get("selector", "")).lower() or "suggestion" in str(action.get("selector", "")).lower()):
                                                    step_num = idx + 1
                                                    break
                                        
                                        await websocket.send_json({
                                            "type": "action_status",
                                            "action": "click",
                                            "status": "completed",
                                            "step": step_num,
                                            "total": total_steps,
                                            "details": click_location_action if 'click_location_action' in locals() and click_location_action else {"action": "click", "selector": "location suggestion"},
                                            "result": {"status": "success"}
                                        })
                                else:
                                    # Fallback: use keyboard navigation (ArrowDown twice to skip "Use my current location")
                                    await page.keyboard.press("ArrowDown")
                                    await asyncio.sleep(0.3)
                                    await page.keyboard.press("ArrowDown")
                                    await asyncio.sleep(0.3)
                                    await page.keyboard.press("Enter")
                                    await asyncio.sleep(2)
                            else:
                                # If suggestions don't appear, try keyboard navigation
                                await page.keyboard.press("ArrowDown")
                                await asyncio.sleep(0.3)
                                await page.keyboard.press("ArrowDown")
                                await asyncio.sleep(0.3)
                                await page.keyboard.press("Enter")
                                await asyncio.sleep(2)
                        except Exception as e:
                            # If no suggestions appear, use keyboard navigation
                            await page.keyboard.press("ArrowDown")
                            await asyncio.sleep(0.3)
                            await page.keyboard.press("ArrowDown")
                            await asyncio.sleep(0.3)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(2)
                except Exception as e:
                    # If location input fails, continue anyway - maybe location is already set
                    pass
            
            # STEP 2: Find and fill the FOOD SEARCH input (right box)
            # Find click action for search div in plan (if exists)
            click_search_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "click" and ("search" in str(action.get("selector", "")).lower() or "restaurant" in str(action.get("selector", "")).lower()):
                        click_search_action = action
                        break
            
            if websocket and click_search_action:
                step_num = 4
                if plan:
                    for idx, action in enumerate(plan):
                        if action == click_search_action:
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "click",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": click_search_action
                })
            
            print(f"\n[4/7] Opening food search...")
            # The search field is a DIV with type="button", not an input!
            # We need to click it first to open the actual search input
            await asyncio.sleep(2)
            
            search_input = None
            
            # Find the search div (type="button") that contains "Search for restaurant, item or more"
            search_div = await page.query_selector("div[type='button']:has-text('Search for restaurant')")
            
            if not search_div:
                # Try by class (from inspection: sc-dtBdUo eyFBpp)
                search_div = await page.query_selector("div.sc-dtBdUo, div.eyFBpp")
            
            if not search_div:
                # Find any div with the text
                search_div = await page.query_selector("div:has-text('Search for restaurant, item or more')")
            
            if search_div:
                # Click it to open the search input
                print(f"  Found search div, clicking to open search input...")
                await search_div.click()
                await asyncio.sleep(2)  # Wait for search input to appear
                print(f"  ✓ Search input should be visible now")
                
                if websocket and click_search_action:
                    step_num = 4
                    if plan:
                        for idx, action in enumerate(plan):
                            if action == click_search_action:
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "click",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": click_search_action,
                        "result": {"status": "success"}
                    })
                
                # Find type action for food query in plan
                type_food_action = None
                if plan:
                    for action in plan:
                        if action.get("action") == "type" and query.lower() in str(action.get("text", "")).lower() and action != type_location_action:
                            type_food_action = action
                            break
                
                if websocket:
                    step_num = 5
                    if plan and type_food_action:
                        for idx, action in enumerate(plan):
                            if action == type_food_action:
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "type",
                        "status": "executing",
                        "step": step_num,
                        "total": total_steps,
                        "details": type_food_action if type_food_action else {"action": "type", "selector": "search input", "text": query, "description": f"Search for: {query}"}
                    })
            
            # NOW get the actual input that appears after clicking
            all_inputs = await page.query_selector_all("input")
            
            # Find input that's not location - same logic as location input
            for inp in all_inputs:
                try:
                    inp_id = await inp.get_attribute("id")
                    inp_type = await inp.get_attribute("type")
                    placeholder = await inp.get_attribute("placeholder")
                    is_visible = await inp.is_visible()
                    
                    # Skip location input
                    if inp_id == "location" or (placeholder and "location" in placeholder.lower()):
                        continue
                    
                    # Skip hidden inputs
                    if not is_visible:
                        continue
                    
                    # Skip non-text inputs (but allow None/empty type which defaults to text)
                    if inp_type and inp_type not in ['text', 'search']:
                        continue
                    
                    # This is the search input - use it!
                    search_input = inp
                    print(f"  ✓ Found search input (id='{inp_id}', placeholder='{placeholder}')")
                    break
                except:
                    continue
            
            if not search_input:
                print(f"  ✗ Could not find search input")
                return {
                    "status": "error",
                    "message": "Could not find Swiggy food search input. The site structure may have changed.",
                    "suggestion": "Try using Google Maps for restaurant discovery: 'find pizza in HSR on Google Maps'"
                }
            
            # Focus the input first
            await search_input.click()
            await asyncio.sleep(0.3)
            
            # Type ONLY the food/dish query in the search box
            # Check if it's a contenteditable div or regular input
            tag_name = await search_input.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "div":
                # It's a contenteditable div
                await search_input.type(query, delay=100)
            else:
                # Regular input - clear first, then type
                await search_input.fill("")
                await asyncio.sleep(0.2)
                await search_input.type(query, delay=100)
            
            # Wait to ensure text is typed
            await asyncio.sleep(0.5)
            
            # Verify text is still there, retype if needed
            try:
                current_value = await search_input.input_value() if tag_name != "div" else await search_input.evaluate("el => el.textContent || el.innerText")
                if not current_value or query not in current_value:
                    # Text was cleared, retype
                    if tag_name == "div":
                        await search_input.evaluate("el => el.textContent = ''")
                    else:
                        await search_input.fill("")
                    await asyncio.sleep(0.2)
                    await search_input.type(query, delay=100)
                    await asyncio.sleep(0.5)
            except:
                pass
            
            # Press Enter directly on the input (more reliable than clicking button)
            print(f"  Pressing Enter to submit search...")
            await search_input.press("Enter")
            print(f"  ✓ Search submitted")
            
            if websocket:
                step_num = 5
                if plan and type_food_action:
                    for idx, action in enumerate(plan):
                        if action == type_food_action:
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "type",
                    "status": "completed",
                    "step": step_num,
                    "total": total_steps,
                    "details": type_food_action if type_food_action else {"action": "type", "text": query},
                    "result": {"status": "success"}
                })
                
                # Find click action for Restaurants button in plan
                click_restaurants_action = None
                step_num_click = 6
                if plan:
                    for idx, action in enumerate(plan):
                        if action.get("action") == "click" and "restaurant" in str(action.get("selector", "")).lower():
                            click_restaurants_action = action
                            step_num_click = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "click",
                    "status": "executing",
                    "step": step_num_click,
                    "total": total_steps,
                    "details": click_restaurants_action if click_restaurants_action else {"action": "click", "selector": "Restaurants button", "description": "Filter by Restaurants"}
                })
            
            # Wait for results to load - Swiggy uses dynamic loading
            await asyncio.sleep(3)
            
            # STEP 3: Click "Restaurants" filter button (not "Dishes")
            print(f"\n[6/7] Clicking 'Restaurants' filter...")
            # The filter buttons appear after search: "Restaurants" and "Dishes"
            restaurants_button = None
            restaurant_button_selectors = [
                "button:has-text('Restaurants')",
                "div:has-text('Restaurants')",
                "[role='button']:has-text('Restaurants')",
                "button[aria-label*='Restaurants']"
            ]
            
            for selector in restaurant_button_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        is_visible = await btn.is_visible()
                        text = await btn.text_content()
                        if is_visible and text and "Restaurants" in text and "Dishes" not in text:
                            restaurants_button = btn
                            break
                except:
                    continue
            
            # If not found by text, try to find by position (Restaurants is usually first)
            if not restaurants_button:
                try:
                    all_buttons = await page.query_selector_all("button, div[role='button']")
                    for btn in all_buttons:
                        try:
                            text = await btn.text_content()
                            if text and "Restaurants" in text.strip() and "Dishes" not in text.strip():
                                is_visible = await btn.is_visible()
                                if is_visible:
                                    restaurants_button = btn
                                    break
                        except:
                            continue
                except:
                    pass
            
            if restaurants_button:
                print(f"  ✓ Found Restaurants button, clicking...")
                await restaurants_button.click()
                await asyncio.sleep(3)  # Wait for filter to apply and page to update
                print(f"  ✓ Restaurants filter applied")
                
                if websocket:
                    step_num = 6
                    if plan and click_restaurants_action:
                        for idx, action in enumerate(plan):
                            if action == click_restaurants_action:
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "click",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": click_restaurants_action if click_restaurants_action else {"action": "click", "selector": "Restaurants button"},
                        "result": {"status": "success"}
                    })
                    
                    # Find extract action in plan
                    extract_action = None
                    if plan:
                        for action in plan:
                            if action.get("action") == "extract":
                                extract_action = action
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "extract",
                        "status": "executing",
                        "step": total_steps,
                        "total": total_steps,
                        "details": extract_action if extract_action else {"action": "extract", "limit": limit, "description": "Extract restaurant data"}
                    })
            else:
                print(f"  Restaurants button not found, continuing anyway...")
                if websocket:
                    step_num = 6
                    if plan and click_restaurants_action:
                        for idx, action in enumerate(plan):
                            if action == click_restaurants_action:
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "click",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": click_restaurants_action if click_restaurants_action else {"action": "click", "selector": "Restaurants button"},
                        "result": {"status": "success", "note": "Button not found, continuing"}
                    })
                    
                    extract_action = None
                    if plan:
                        for action in plan:
                            if action.get("action") == "extract":
                                extract_action = action
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "extract",
                        "status": "executing",
                        "step": total_steps,
                        "total": total_steps,
                        "details": extract_action if extract_action else {"action": "extract", "limit": limit}
                    })
                
                # Verify we're on restaurants view (not dishes)
                # Check if "Restaurants" button is now selected/active
                try:
                    button_text = await restaurants_button.text_content()
                    # The active button usually has different styling or aria-selected
                    is_selected = await restaurants_button.evaluate("""
                        el => {
                            return el.getAttribute('aria-selected') === 'true' ||
                                   el.classList.contains('selected') ||
                                   el.classList.contains('active') ||
                                   window.getComputedStyle(el).fontWeight === 'bold';
                        }
                    """)
                    if not is_selected:
                        # Try clicking again or wait longer
                        await asyncio.sleep(2)
                except:
                    pass
            
            # Scroll to trigger lazy loading of more results
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(2)
            
            # Poll for restaurant cards
            print(f"\n[7/7] Extracting restaurant data...")
            total_wait = 15
            poll_interval = 2
            elapsed = 0
            found = False
            
            while elapsed < total_wait:
                print(f"  Polling for restaurant cards... ({elapsed}s/{total_wait}s)")
                card_count = await page.evaluate("""
                    () => {
                        // Try multiple strategies to find restaurant cards
                        // NOTE: Swiggy uses "resturant" (typo) in data-testid
                        const selectors = [
                            'a[data-testid="resturant-card-anchor-container"]',  // Actual Swiggy selector (with typo)
                            'a[data-testid*="resturant-card"]',  // Variant with typo
                            'a[href*="/restaurant/"]',  // Restaurant links
                            'a[href*="/city/"]',  // City-based restaurant links
                            'div[data-testid="restaurant-card"]',
                            '[data-testid="restaurant-card"]',
                            'div[class*="restaurant-card"]',
                            'div[class*="RestaurantCard"]',
                            'div[class*="cardContainer"]',
                            'div[class*="CardContainer"]'
                        ];
                        let maxCount = 0;
                        for (const sel of selectors) {
                            const count = document.querySelectorAll(sel).length;
                            if (count > maxCount) maxCount = count;
                        }
                        
                        // Also try finding by structure: links or divs containing restaurant-like text
                        if (maxCount === 0) {
                            const allLinks = Array.from(document.querySelectorAll('a[href*="/restaurant/"], a[href*="/city/"]'));
                            if (allLinks.length > 0) {
                                maxCount = allLinks.length;
                            }
                        }
                        
                        return maxCount;
                    }
                """)
                
                if card_count >= 1:
                    print(f"  ✓ Found {card_count} restaurant cards!")
                    found = True
                    break
                
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            
            if not found:
                # Check if we're blocked or redirected
                current_url = page.url
                page_text = await page.evaluate("() => document.body.innerText.slice(0, 1000)")
                
                return {
                    "status": "error",
                    "message": "No restaurant cards found. Swiggy may be blocking automated access or the search returned no results.",
                    "current_url": current_url,
                    "page_preview": page_text[:500],
                    "suggestion": "Try using Google Maps instead: search 'pizza restaurants in HSR Layout Bangalore' on Google Maps"
                }
            
            # Extract restaurant data
            extraction_js = """
            (params) => {
                const limit = params.limit || 10;
                const results = [];
                
                // Try multiple selectors for restaurant cards (updated based on actual Swiggy structure)
                // NOTE: Swiggy uses "resturant" (typo) in data-testid, not "restaurant"
                const cardSelectors = [
                    'a[data-testid="resturant-card-anchor-container"]',  // Actual Swiggy selector (with typo)
                    'a[data-testid*="resturant-card"]',  // Variant with typo
                    'a[href*="/restaurant/"]',  // Restaurant links
                    'a[href*="/city/"]',  // City-based restaurant links
                    'div[data-testid="restaurant-card"]',
                    '[data-testid="restaurant-card"]',
                    'div[class*="styles__cardContainer"]',
                    'div[class*="RestaurantCard"]',
                    'div[class*="restaurant-card"]',
                    'a[class*="restaurant"]'
                ];
                
                let cards = [];
                for (const sel of cardSelectors) {
                    const found = Array.from(document.querySelectorAll(sel));
                    if (found.length > 0) {
                        console.log(`[Swiggy] Found ${found.length} elements with selector: ${sel}`);
                        // Filter: only keep elements that look like restaurant cards
                        // (contain restaurant name-like text, not just any link)
                        const filtered = found.filter(card => {
                            const text = card.textContent || '';
                            // Restaurant cards usually have names, ratings, delivery info, or price
                            // But be less strict - if it's the right selector, trust it
                            if (sel.includes('data-testid="resturant-card-anchor-container"') || 
                                sel.includes('data-testid*="resturant-card"')) {
                                // Trust the data-testid selector
                                return true;
                            }
                            // For other selectors, filter more strictly
                            return text.length > 20 && (
                                text.match(/\\d+\\.\\d/) ||  // Has rating
                                text.includes('MINS') ||     // Has delivery time
                                text.includes('FOR TWO') ||  // Has price
                                text.includes('Delivers in') ||  // Delivery text
                                text.includes('Cost is')     // Cost text
                            );
                        });
                        if (filtered.length > 0) {
                            console.log(`[Swiggy] Using ${filtered.length} cards with selector: ${sel}`);
                            cards = filtered;
                            break;
                        }
                    }
                }
                
                // If still no cards, try getting all restaurant links without filtering
                if (cards.length === 0) {
                    const allRestaurantLinks = Array.from(document.querySelectorAll('a[href*="/restaurant/"], a[href*="/city/"]'));
                    if (allRestaurantLinks.length > 0) {
                        console.log(`[Swiggy] Found ${allRestaurantLinks.length} restaurant links (no filtering)`);
                        cards = allRestaurantLinks;
                    }
                }
                
                console.log(`[Swiggy] Processing ${Math.min(limit, cards.length)} cards...`);
                
                for (let i = 0; i < Math.min(limit, cards.length); i++) {
                    const card = cards[i];
                    
                    // Extract name - try multiple strategies
                    let name = null;
                    
                    // Strategy 1: Try aria-label (Swiggy sometimes puts name there)
                    try {
                        const ariaLabel = card.getAttribute('aria-label') || '';
                        if (ariaLabel && ariaLabel.includes('Restaurant name')) {
                            const nameMatch = ariaLabel.match(/Restaurant name\\s+(.+?)(?:,|$)/i);
                            if (nameMatch && nameMatch[1].trim().length >= 3) {
                                name = nameMatch[1].trim();
                            }
                        }
                    } catch (e) {}
                    
                    // Strategy 2: Try structured selectors
                    if (!name) {
                        const nameSelectors = [
                            'div[class*="name"]', 
                            'div[class*="Name"]', 
                            'div[class*="title"]',
                            'div[class*="Title"]',
                            'h1', 'h2', 'h3', 'h4'
                        ];
                        
                        for (const sel of nameSelectors) {
                            const elements = card.querySelectorAll(sel);
                            for (const el of elements) {
                                const text = el.textContent.trim();
                                // Name should be 5-80 chars, not contain numbers at start, not common UI text
                                if (text.length >= 5 && text.length <= 80 && 
                                    !/^\d/.test(text) &&
                                    !text.match(/^(Ad|ITEMS|MINS|FOR TWO|₹|Cart|Sign|Help|Offers|NEW|Search|By)$/i) &&
                                    !text.includes('•') &&
                                    !text.match(/^\\d+\\.\\d/) &&  // Not a rating
                                    !text.match(/\\d+\\s*MINS/i) &&  // Not delivery time
                                    !text.match(/₹\\s*\\d+/) &&  // Not price
                                    !text.includes('Pizzas,') &&  // Not cuisine list
                                    !text.includes('Delivers in') &&  // Not delivery text
                                    !text.includes('Cost is')) {  // Not cost text
                                    name = text;
                                    break;
                                }
                            }
                            if (name) break;
                        }
                    }
                    
                    // Strategy 3: Extract from href URL as fallback
                    if (!name && card.href) {
                        try {
                            const urlMatch = card.href.match(/\\/([^/]+)-rest\\d+$/);
                            if (urlMatch) {
                                // Convert URL slug to readable name
                                const slug = urlMatch[1];
                                name = slug.split('-').map(word => 
                                    word.charAt(0).toUpperCase() + word.slice(1)
                                ).join(' ');
                            }
                        } catch (e) {}
                    }
                    
                    // Strategy 4: Parse text content, looking for first substantial line
                    if (!name) {
                        const allText = card.textContent || '';
                        const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                        for (const line of lines) {
                            // Skip common UI elements, cuisine lists, ratings, prices, etc.
                            if (line.length >= 5 && line.length <= 80 &&
                                !/^\d/.test(line) &&
                                !line.match(/^(Ad|ITEMS|MINS|FOR TWO|₹|Cart|Sign|Help|Offers|NEW|Search|Restaurants|Dishes|By)$/i) &&
                                !line.includes('•') &&
                                !line.match(/^\\d+\\.\\d/) &&  // Not a rating
                                !line.match(/\\d+\\s*MINS/i) &&  // Not delivery time
                                !line.match(/₹\\s*\\d+/) &&  // Not price
                                !line.includes('Pizzas,') &&  // Not cuisine list start
                                !line.includes('Delivers in') &&  // Not delivery text
                                !line.includes('Cost is') &&  // Not cost text
                                !line.includes('km away') &&  // Not distance
                                !line.match(/^[A-Z\\s,]+$/)) {  // Not all caps (likely cuisine)
                                name = line;
                                break;
                            }
                        }
                    }
                    
                    // Extract rating - look for decimal numbers with star icon or specific patterns
                    let rating = null;
                    const ratingSelectors = [
                        'div[class*="rating"]', 
                        'span[class*="rating"]', 
                        'div[class*="Rating"]',
                        '[aria-label*="star"]',
                        'svg ~ span',  // Often rating is next to star icon
                        'svg ~ div'
                    ];
                    for (const sel of ratingSelectors) {
                        const el = card.querySelector(sel);
                        if (el) {
                            const text = el.textContent.trim();
                            // Match decimal like "4.5" or "4.3"
                            const match = text.match(/(\d\.\d)/);
                            if (match) {
                                const val = parseFloat(match[1]);
                                if (val >= 1 && val <= 5) {
                                    rating = match[1];
                                    break;
                                }
                            }
                        }
                    }
                    
                    // If no rating found with selectors, scan all text in card
                    if (!rating) {
                        const allText = card.textContent;
                        // First try: rating with word boundary (space before it)
                        let matches = allText.match(/\b(\d\.\d)\b/g);
                        if (!matches || matches.length === 0) {
                            // Second try: rating directly after text (no space) - e.g., "Pizza4.3"
                            matches = allText.match(/([A-Za-z])(\d\.\d)/g);
                            if (matches) {
                                // Extract just the rating part (e.g., "4.3" from "a4.3")
                                matches = matches.map(m => m.match(/(\d\.\d)/)[1]);
                            }
                        }
                        if (matches) {
                            for (const m of matches) {
                                const val = parseFloat(m);
                                if (val >= 1 && val <= 5) {
                                    rating = m;
                                    break;
                                }
                            }
                        }
                    }
                    
                    // Extract cuisine - usually second or third line of text
                    let cuisine = null;
                    const cuisineSelectors = [
                        'div[class*="cuisine"]', 
                        'div[class*="Cuisine"]',
                        'span[class*="cuisine"]',
                        'div[class*="category"]'
                    ];
                    for (const sel of cuisineSelectors) {
                        const el = card.querySelector(sel);
                        if (el && el.textContent.trim()) {
                            cuisine = el.textContent.trim();
                            break;
                        }
                    }
                    
                    // Extract location/area
                    let location = null;
                    const locationSelectors = [
                        'div[class*="location"]', 
                        'div[class*="area"]', 
                        'div[class*="locality"]',
                        'span[class*="location"]'
                    ];
                    for (const sel of locationSelectors) {
                        const el = card.querySelector(sel);
                        if (el && el.textContent.trim()) {
                            location = el.textContent.trim();
                            break;
                        }
                    }
                    
                    // Extract price/cost - look for ₹ symbol
                    let price = null;
                    const priceSelectors = [
                        'div[class*="price"]', 
                        'span[class*="price"]', 
                        'div[class*="cost"]',
                        'span[class*="cost"]'
                    ];
                    for (const sel of priceSelectors) {
                        const el = card.querySelector(sel);
                        if (el && el.textContent.includes('₹')) {
                            price = el.textContent.trim();
                            break;
                        }
                    }
                    
                    // If no price in specific selectors, search card text for ₹ or "FOR TWO"
                    if (!price) {
                        const allText = card.textContent;
                        // Try to find "₹XXX FOR TWO" pattern
                        const forTwoMatch = allText.match(/₹\s*\d+\s*FOR\s*TWO/i);
                        if (forTwoMatch) {
                            price = forTwoMatch[0];
                        } else {
                            // Fallback to any ₹ pattern
                            const priceMatch = allText.match(/₹\s*\d+/);
                            if (priceMatch) {
                                price = priceMatch[0];
                            }
                        }
                    }
                    
                    // Get URL
                    let url = null;
                    const linkEl = card.tagName === 'A' ? card : card.querySelector('a');
                    if (linkEl && linkEl.href) {
                        url = linkEl.href;
                    } else {
                        // Construct URL from restaurant name if available
                        url = 'https://www.swiggy.com';
                    }
                    
                    // Only add if we have at least a name
                    if (name) {
                        results.push({
                            name,
                            rating: rating ? parseFloat(rating) : null,
                            cuisine: cuisine || 'N/A',
                            location: location || 'N/A',
                            price: price || 'N/A',
                            url
                        });
                        console.log(`[Swiggy] Extracted: ${name} (${rating || 'no rating'})`);
                    }
                }
                
                console.log(`[Swiggy] Successfully extracted ${results.length} restaurants`);
                return results;
            }
            """
            
            data = await page.evaluate(extraction_js, {"limit": limit})
            
            print(f"\n=== EXTRACTION COMPLETE ===")
            print(f"Extracted {len(data)} restaurants")
            for i, item in enumerate(data[:3], 1):
                print(f"  {i}. {item.get('name', 'N/A')} - Rating: {item.get('rating', 'N/A')}")
            
            result = {
                "status": "success",
                "data": data,
                "count": len(data)
            }
            
            # Send extract action with results
            if websocket:
                extract_action = None
                if plan:
                    for action in plan:
                        if action.get("action") == "extract":
                            extract_action = action
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "extract",
                    "status": "completed",
                    "step": total_steps,
                    "total": total_steps,
                    "result": result,
                    "details": extract_action if extract_action else {"action": "extract", "limit": limit}
                })
            
            return result
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc()
            }


class ZomatoHandler:
    """Handler for Zomato-specific operations with anti-detection measures."""
    
    @staticmethod
    async def search(page: Page, context: BrowserContext, query: str, location: str = "HSR Layout", city: str = "bangalore", limit: int = 5, websocket=None, session_id=None, total_steps=8, plan=None) -> Dict:
        """
        Search Zomato for restaurants matching query at location and extract results.
        Zomato requires: navigate to city page → click location dropdown → type location → select suggestion → type food → click dish suggestion → extract.
        
        Returns: {"status":"success","data":[{name, rating, cuisine, location, price, url}]}
        """
        try:
            print(f"\n=== ZOMATO SEARCH STARTED ===")
            print(f"Query: '{query}'")
            print(f"Location: '{location}'")
            print(f"City: '{city}'")
            print(f"Limit: {limit}")
            
            # Build Zomato URL - go to city page
            base_url = f"https://www.zomato.com/{city}"
            
            # STEP 1: Navigate to Zomato city page
            try:
                navigate_action = None
                if plan:
                    for action in plan:
                        if action.get("action") == "navigate" and "zomato" in str(action.get("url", "")).lower():
                            navigate_action = action
                            break
                
                if websocket:
                    step_num = 1
                    if plan:
                        for idx, action in enumerate(plan):
                            if action.get("action") == "navigate" and "zomato" in str(action.get("url", "")).lower():
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "navigate",
                        "status": "executing",
                        "step": step_num,
                        "total": total_steps,
                        "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url, "description": f"Navigate to Zomato {city}"}
                    })
                
                print(f"\n[1/{total_steps}] Navigating to Zomato: {base_url}")
                
                # Try navigation with retries - Zomato sometimes blocks with HTTP2 errors
                navigation_success = False
                last_error = None
                
                # First, try accessing via a simpler URL or with different approach
                # Sometimes going to homepage first helps
                try_urls = [
                    base_url,  # Try city page first
                    "https://www.zomato.com",  # Try homepage as fallback
                ]
                
                for url_to_try in try_urls:
                    for attempt in range(2):  # 2 attempts per URL
                        try:
                            # Add a small random delay to appear more human-like
                            import random
                            await asyncio.sleep(random.uniform(1, 2))
                            
                            # Try with domcontentloaded (fastest, most reliable)
                            await page.goto(url_to_try, wait_until="domcontentloaded", timeout=30000)
                            
                            # Verify page loaded successfully
                            await asyncio.sleep(2)
                            current_url = page.url
                            page_title = await page.title()
                            
                            # Check if we're on Zomato (even if redirected)
                            if "zomato.com" in current_url.lower() or "zomato" in page_title.lower():
                                # If we went to homepage, navigate to city page
                                if url_to_try == "https://www.zomato.com" and city:
                                    try:
                                        await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
                                        await asyncio.sleep(2)
                                    except:
                                        pass  # Continue with homepage if city page fails
                                
                                navigation_success = True
                                break
                        except Exception as e:
                            last_error = e
                            print(f"  Attempt {attempt + 1}/2 for {url_to_try} failed: {str(e)[:100]}")
                            if attempt < 1:
                                await asyncio.sleep(3)  # Wait longer before retry
                    
                    if navigation_success:
                        break
                
                if not navigation_success:
                    error_msg = f"Failed to load Zomato after 3 attempts: {str(last_error)}"
                    if "HTTP2" in str(last_error) or "ERR_HTTP2" in str(last_error):
                        error_msg = "Zomato is blocking automated access (HTTP2 protocol error). This is a known issue with Zomato's anti-bot protection."
                    
                    print(f"✗ {error_msg}")
                    if websocket:
                        step_num = 1
                        if plan:
                            for idx, action in enumerate(plan):
                                if action.get("action") == "navigate" and "zomato" in str(action.get("url", "")).lower():
                                    step_num = idx + 1
                                    break
                        
                        await websocket.send_json({
                            "type": "action_status",
                            "action": "navigate",
                            "status": "error",
                            "step": step_num,
                            "total": total_steps,
                            "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url},
                            "result": {"status": "error", "message": error_msg}
                        })
                    return {
                        "status": "error",
                        "message": error_msg,
                        "suggestion": "Zomato frequently blocks automated access. Try using Swiggy or Google Maps instead: 'find pizza in HSR on Swiggy' or 'find pizza in HSR on Google Maps'"
                    }
                
                await asyncio.sleep(1)  # Let page settle
                print(f"✓ Page loaded: {page.url}")
                
                if websocket:
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "navigate",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url},
                        "result": {"status": "success", "url": page.url}
                    })
            except Exception as e:
                print(f"✗ Failed to load Zomato: {e}")
                if websocket:
                    step_num = 1
                    if plan:
                        for idx, action in enumerate(plan):
                            if action.get("action") == "navigate" and "zomato" in str(action.get("url", "")).lower():
                                step_num = idx + 1
                                break
                    
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "navigate",
                        "status": "error",
                        "step": step_num,
                        "total": total_steps,
                        "details": navigate_action if navigate_action else {"action": "navigate", "url": base_url},
                        "result": {"status": "error", "message": str(e)}
                    })
                return {"status": "error", "message": f"Failed to load Zomato: {str(e)}"}
            
            # STEP 2: Click location dropdown
            if websocket:
                click_location_dropdown_action = None
                step_num = 2
                if plan:
                    for idx, action in enumerate(plan):
                        if action.get("action") == "click" and ("location" in str(action.get("selector", "")).lower() or "dropdown" in str(action.get("selector", "")).lower()):
                            click_location_dropdown_action = action
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "click",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": click_location_dropdown_action if click_location_dropdown_action else {"action": "click", "selector": "location dropdown", "description": "Click location dropdown"}
                })
            
            print(f"\n[2/{total_steps}] Clicking location dropdown...")
            location_dropdown = None
            dropdown_selectors = [
                "div[class*='sc-18n4g8v-0']",  # Zomato location dropdown
                "div[class*='sc-fxmata']",  # Alternative selector
                "div:has-text('Bangalore')",  # Contains city name
                "[aria-label*='location']",
                "[role='button']:has-text('Bangalore')",
                "div[class*='location']",
            ]
            
            for selector in dropdown_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for elem in elements:
                        text = await elem.text_content()
                        if text and (city.lower() in text.lower() or "location" in text.lower()):
                            location_dropdown = elem
                            break
                    if location_dropdown:
                        break
                except:
                    continue
            
            if not location_dropdown:
                # Try finding by input field that shows location - click the input itself to open dropdown
                try:
                    inputs = await page.query_selector_all("input[type='text']")
                    for inp in inputs:
                        placeholder = await inp.get_attribute("placeholder")
                        value = await inp.get_attribute("value")
                        if placeholder and ("location" in placeholder.lower() or "area" in placeholder.lower()):
                            # The input itself might be clickable to open dropdown
                            location_dropdown = inp
                            break
                except:
                    pass
            
            if location_dropdown:
                await location_dropdown.click()
                await asyncio.sleep(1)
                print(f"✓ Location dropdown clicked")
                
                if websocket:
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "click",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": click_location_dropdown_action if click_location_dropdown_action else {"action": "click", "selector": "location dropdown"},
                        "result": {"status": "success"}
                    })
            else:
                print(f"Location dropdown not found, trying to type directly...")
            
            # STEP 3: Type location in the dropdown input
            type_location_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "type" and location.lower() in str(action.get("text", "")).lower():
                        type_location_action = action
                        break
            
            if websocket:
                step_num = 3
                if plan and type_location_action:
                    for idx, action in enumerate(plan):
                        if action == type_location_action:
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "type",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": type_location_action if type_location_action else {"action": "type", "selector": "location input", "text": location, "description": f"Type location: {location}"}
                })
            
            print(f"\n[3/{total_steps}] Typing location: '{location}'")
            location_input = None
            
            # Find the location input that appears after clicking dropdown
            await asyncio.sleep(1)  # Wait for dropdown to open
            
            location_input_selectors = [
                "input[placeholder*='location']",
                "input[placeholder*='area']",
                "input[type='text']",
            ]
            
            for selector in location_input_selectors:
                try:
                    inputs = await page.query_selector_all(selector)
                    for inp in inputs:
                        placeholder = await inp.get_attribute("placeholder")
                        if placeholder and ("location" in placeholder.lower() or "area" in placeholder.lower()):
                            location_input = inp
                            break
                    if location_input:
                        break
                except:
                    continue
            
            # If not found, use first visible text input
            if not location_input:
                try:
                    all_inputs = await page.query_selector_all("input[type='text']")
                    for inp in all_inputs:
                        is_visible = await inp.is_visible()
                        if is_visible:
                            location_input = inp
                            break
                except:
                    pass
            
            if location_input:
                await location_input.fill("")
                await location_input.type(location, delay=100)
                await asyncio.sleep(2)  # Wait for suggestions
                print(f"✓ Location typed, waiting for suggestions...")
                
                if websocket:
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "type",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": type_location_action if type_location_action else {"action": "type", "text": location},
                        "result": {"status": "success"}
                    })
            else:
                print(f"Location input not found")
            
            # STEP 4: Select location suggestion
            click_location_suggestion_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "click" and ("suggestion" in str(action.get("selector", "")).lower() or "location" in str(action.get("selector", "")).lower()):
                        click_location_suggestion_action = action
                        break
            
            if websocket:
                step_num = 4
                if plan and click_location_suggestion_action:
                    for idx, action in enumerate(plan):
                        if action == click_location_suggestion_action:
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "click",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": click_location_suggestion_action if click_location_suggestion_action else {"action": "click", "selector": "location suggestion", "description": "Click location suggestion"}
                })
            
            print(f"\n[4/{total_steps}] Selecting location suggestion...")
            
            # Find suggestions - look for dropdown items
            suggestion_selectors = [
                "div[class*='sc-']",  # Zomato suggestion items
                "[role='option']",
                "div[class*='suggestion']",
                "li[class*='suggestion']",
                "div[class*='dropdown'] div",
            ]
            
            selected_suggestion = None
            location_lower = location.lower()
            
            for selector in suggestion_selectors:
                try:
                    suggestions = await page.query_selector_all(selector)
                    for suggestion in suggestions:
                        text = await suggestion.text_content()
                        if text:
                            text_lower = text.lower()
                            # Check for exact match (case-insensitive)
                            if location_lower in text_lower or text_lower in location_lower:
                                selected_suggestion = suggestion
                                print(f"✓ Found exact location match: '{text[:60]}'")
                                break
                    if selected_suggestion:
                        break
                except:
                    continue
            
            # If no exact match, select first suggestion
            if not selected_suggestion:
                for selector in suggestion_selectors:
                    try:
                        suggestions = await page.query_selector_all(selector)
                        if len(suggestions) > 0:
                            selected_suggestion = suggestions[0]
                            text = await selected_suggestion.text_content()
                            print(f"✓ Selected first suggestion: '{text[:60] if text else 'N/A'}'")
                            break
                    except:
                        continue
            
            if selected_suggestion:
                await selected_suggestion.click()
                await asyncio.sleep(2)  # Wait for location to be set
                print(f"✓ Location selected")
                
                if websocket:
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "click",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": click_location_suggestion_action if click_location_suggestion_action else {"action": "click", "selector": "location suggestion"},
                        "result": {"status": "success"}
                    })
            else:
                print(f"No location suggestion found, continuing...")
            
            # STEP 5: Type food query
            type_food_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "type" and query.lower() in str(action.get("text", "")).lower() and action != type_location_action:
                        type_food_action = action
                        break
            
            if websocket:
                step_num = 5
                if plan and type_food_action:
                    for idx, action in enumerate(plan):
                        if action == type_food_action:
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "type",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": type_food_action if type_food_action else {"action": "type", "selector": "food search", "text": query, "description": f"Search for: {query}"}
                })
            
            print(f"\n[5/{total_steps}] Typing food query: '{query}'")
            
            # Find food search input (usually on the right side of location)
            food_search_input = None
            food_search_selectors = [
                "input[placeholder*='restaurant']",
                "input[placeholder*='cuisine']",
                "input[placeholder*='dish']",
                "input[placeholder*='Search for restaurant']",
            ]
            
            for selector in food_search_selectors:
                try:
                    inp = await page.query_selector(selector)
                    if inp:
                        is_visible = await inp.is_visible()
                        if is_visible:
                            food_search_input = inp
                            break
                except:
                    continue
            
            # If not found, try finding by position (usually second input or has different placeholder)
            if not food_search_input:
                try:
                    all_inputs = await page.query_selector_all("input[type='text']")
                    for inp in all_inputs:
                        placeholder = await inp.get_attribute("placeholder")
                        is_visible = await inp.is_visible()
                        if is_visible and placeholder and ("restaurant" in placeholder.lower() or "cuisine" in placeholder.lower() or "dish" in placeholder.lower() or "search" in placeholder.lower()):
                            food_search_input = inp
                            break
                except:
                    pass
            
            if food_search_input:
                await food_search_input.click()
                await asyncio.sleep(0.3)
                await food_search_input.fill("")
                await food_search_input.type(query, delay=100)
                await asyncio.sleep(2)  # Wait for dish suggestions
                print(f"✓ Food query typed")
                
                if websocket:
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "type",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": type_food_action if type_food_action else {"action": "type", "text": query},
                        "result": {"status": "success"}
                    })
            else:
                print(f"Food search input not found")
            
            # STEP 6: Click first dish suggestion
            click_dish_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "click" and ("dish" in str(action.get("selector", "")).lower() or "suggestion" in str(action.get("selector", "")).lower()):
                        click_dish_action = action
                        break
            
            if websocket:
                step_num = 6
                if plan and click_dish_action:
                    for idx, action in enumerate(plan):
                        if action == click_dish_action:
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "click",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": click_dish_action if click_dish_action else {"action": "click", "selector": "dish suggestion", "description": "Click first dish suggestion"}
                })
            
            print(f"\n[6/{total_steps}] Clicking first dish suggestion...")
            
            # Find dish suggestions dropdown
            dish_suggestion = None
            dish_suggestion_selectors = [
                "div[class*='sc-']",  # Zomato suggestion items
                "[role='option']",
                "div[class*='suggestion']",
                "li[class*='suggestion']",
                "div[class*='dropdown'] div",
                "a[href*='/bangalore/']",  # Restaurant links
            ]
            
            for selector in dish_suggestion_selectors:
                try:
                    suggestions = await page.query_selector_all(selector)
                    if len(suggestions) > 0:
                        # Get first suggestion that's visible and clickable
                        for suggestion in suggestions:
                            is_visible = await suggestion.is_visible()
                            if is_visible:
                                dish_suggestion = suggestion
                                text = await suggestion.text_content()
                                print(f"✓ Found dish suggestion: '{text[:60] if text else 'N/A'}'")
                                break
                        if dish_suggestion:
                            break
                except:
                    continue
            
            if dish_suggestion:
                await dish_suggestion.click()
                await asyncio.sleep(3)  # Wait for results to load
                print(f"✓ Dish suggestion clicked, waiting for results...")
                
                if websocket:
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "click",
                        "status": "completed",
                        "step": step_num,
                        "total": total_steps,
                        "details": click_dish_action if click_dish_action else {"action": "click", "selector": "dish suggestion"},
                        "result": {"status": "success"}
                    })
            else:
                print(f"No dish suggestion found, pressing Enter...")
                if food_search_input:
                    await food_search_input.press("Enter")
                    await asyncio.sleep(3)
            
            # STEP 7: Wait for restaurant results
            if websocket:
                wait_action = None
                step_num = 7
                if plan:
                    for idx, action in enumerate(plan):
                        if action.get("action") == "wait_for":
                            wait_action = action
                            step_num = idx + 1
                            break
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "wait_for",
                    "status": "executing",
                    "step": step_num,
                    "total": total_steps,
                    "details": wait_action if wait_action else {"action": "wait_for", "selector": "restaurant cards", "description": "Wait for restaurant results"}
                })
            
            print(f"\n[7/{total_steps}] Waiting for restaurant results...")
            
            # Wait for restaurant cards to appear
            restaurant_container_selectors = [
                "div[class*='sc-evWYkj']",  # Zomato restaurant card
                "div[class*='sc-fYAFcb']",
                "a[href*='/bangalore/']",
                "div[class*='restaurant']",
                "[data-testid*='restaurant']",
            ]
            
            results_loaded = False
            for selector in restaurant_container_selectors:
                try:
                    await page.wait_for_selector(selector, state="visible", timeout=10000)
                    results_loaded = True
                    print(f"✓ Restaurant results loaded")
                    break
                except:
                    continue
            
            if websocket:
                await websocket.send_json({
                    "type": "action_status",
                    "action": "wait_for",
                    "status": "completed",
                    "step": step_num,
                    "total": total_steps,
                    "details": wait_action if wait_action else {"action": "wait_for"},
                    "result": {"status": "success"}
                })
            
            # Scroll to load more results
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(2)
            
            # STEP 8: Extract restaurant data
            extract_action = None
            if plan:
                for action in plan:
                    if action.get("action") == "extract":
                        extract_action = action
                        break
            
            if websocket:
                await websocket.send_json({
                    "type": "action_status",
                    "action": "extract",
                    "status": "executing",
                    "step": total_steps,
                    "total": total_steps,
                    "details": extract_action if extract_action else {"action": "extract", "limit": limit, "description": "Extract restaurant data"}
                })
            
            print(f"\n[{total_steps}/{total_steps}] Extracting restaurant data...")
            
            # Extract restaurant data using JavaScript
            extraction_js = """
            (async function({limit}) {
                const results = [];
                
                // Find restaurant cards
                const cardSelectors = [
                    'div[class*="sc-evWYkj"]',
                    'div[class*="sc-fYAFcb"]',
                    'a[href*="/bangalore/"]',
                    'div[class*="restaurant"]'
                ];
                
                let cards = [];
                for (const selector of cardSelectors) {
                    cards = Array.from(document.querySelectorAll(selector));
                    if (cards.length > 0) break;
                }
                
                // Limit to requested number
                cards = cards.slice(0, limit);
                
                for (const card of cards) {
                    try {
                        // Extract name
                        let name = '';
                        const nameSelectors = ['h4', 'h3', 'a[href*="/bangalore/"]', '[class*="sc-"]'];
                        for (const sel of nameSelectors) {
                            const elem = card.querySelector(sel);
                            if (elem) {
                                name = elem.textContent?.trim() || '';
                                if (name) break;
                            }
                        }
                        
                        // Extract rating
                        let rating = '';
                        const ratingSelectors = ['[aria-label*="star"]', '[class*="rating"]', '[class*="sc-"]'];
                        for (const sel of ratingSelectors) {
                            const elem = card.querySelector(sel);
                            if (elem) {
                                const text = elem.textContent || elem.getAttribute('aria-label') || '';
                                const match = text.match(/(\\d+\\.?\\d*)/);
                                if (match) {
                                    rating = match[1];
                                    break;
                                }
                            }
                        }
                        
                        // Extract cuisine
                        let cuisine = '';
                        const cuisineText = card.textContent || '';
                        const cuisineMatch = cuisineText.match(/([A-Za-z]+(?:,\\s*[A-Za-z]+)*)/);
                        if (cuisineMatch) {
                            cuisine = cuisineMatch[1].substring(0, 100);
                        }
                        
                        // Extract location
                        let location = '';
                        const locationSelectors = ['[class*="location"]', '[class*="area"]'];
                        for (const sel of locationSelectors) {
                            const elem = card.querySelector(sel);
                            if (elem) {
                                location = elem.textContent?.trim() || '';
                                if (location) break;
                            }
                        }
                        
                        // Extract price
                        let price = '';
                        const priceText = card.textContent || '';
                        const priceMatch = priceText.match(/₹(\\d+)/);
                        if (priceMatch) {
                            price = '₹' + priceMatch[1];
                        }
                        
                        // Extract URL
                        let url = '';
                        const link = card.querySelector('a[href]') || card.closest('a[href]');
                        if (link) {
                            url = link.href || '';
                        }
                        
                        if (name) {
                            results.push({
                                name: name,
                                rating: rating || 'N/A',
                                cuisine: cuisine || 'N/A',
                                location: location || 'N/A',
                                price: price || 'N/A',
                                url: url || ''
                            });
                        }
                    } catch (e) {
                        console.error('Error extracting restaurant:', e);
                    }
                }
                
                return results;
            })
            """
            
            data = await page.evaluate(extraction_js, {"limit": limit})
            
            print(f"\n=== EXTRACTION COMPLETE ===")
            print(f"Extracted {len(data)} restaurants")
            for i, item in enumerate(data[:3], 1):
                print(f"  {i}. {item.get('name', 'N/A')} - Rating: {item.get('rating', 'N/A')}")
            
            result = {
                "status": "success",
                "data": data,
                "count": len(data)
            }
            
            # Send extract action with results
            if websocket:
                await websocket.send_json({
                    "type": "action_status",
                    "action": "extract",
                    "status": "completed",
                    "step": total_steps,
                    "total": total_steps,
                    "result": result,
                    "details": extract_action if extract_action else {"action": "extract", "limit": limit}
                })
            
            return result
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc()
            }

class YouTubeHandler:
    """Handler for YouTube-specific operations."""
    
    @staticmethod
    async def extract_video_urls(page: Page, limit: int = 10) -> Dict:
        """
        Extract video URLs from YouTube search results.
        Only extracts links from video containers, not login or other links.
        
        Returns: {"status": "success", "data": [{"title": "...", "url": "..."}], "count": N}
        """
        try:
            # Wait for video results to appear
            await page.wait_for_selector("#contents ytd-video-renderer, ytd-video-renderer", timeout=10000)
        except:
            pass  # Continue anyway
        
        # Extract videos using specialized JavaScript
        videos = await page.evaluate(f"""
            () => {{
                const videos = [];
                // Find all video renderers
                const videoContainers = document.querySelectorAll('#contents ytd-video-renderer, ytd-video-renderer');
                
                for (let i = 0; i < Math.min({limit}, videoContainers.length); i++) {{
                    const container = videoContainers[i];
                    
                    // Get title
                    const titleEl = container.querySelector('#video-title, a#video-title, #video-title-link');
                    const title = titleEl ? titleEl.textContent?.trim() || titleEl.getAttribute('title') || '' : '';
                    
                    // Get URL - only from video title link, not any link
                    let url = null;
                    const titleLink = container.querySelector('#video-title-link, a#video-title');
                    if (titleLink) {{
                        const href = titleLink.getAttribute('href');
                        if (href) {{
                            // Make absolute URL if relative
                            if (href.startsWith('/')) {{
                                url = 'https://www.youtube.com' + href;
                            }} else if (href.startsWith('http')) {{
                                url = href;
                            }}
                        }}
                    }}
                    
                    // Only add if we have both title and URL
                    if (title && url && url.includes('/watch')) {{
                        videos.push({{
                            title: title,
                            url: url
                        }});
                    }}
                }}
                
                return videos;
            }}
        """)
        
        return {
            "status": "success",
            "data": videos,
            "count": len(videos)
        }


class SiteExtractionHandler:
    """Handler for site-specific extraction logic."""
    
    @staticmethod
    def get_diagnostic_js() -> str:
        """Get JavaScript code for page structure diagnosis."""
        return """
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
        """
    
    @staticmethod
    def get_extraction_js() -> str:
        """Get JavaScript code for site-specific extraction."""
        return r"""
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
            """

