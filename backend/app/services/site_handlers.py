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

