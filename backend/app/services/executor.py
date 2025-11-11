from fastapi import WebSocket
from app.services.ai_planner import create_action_plan
from app.services.browser_agent import browser_agent
from app.services.filter_results import filter_by_price, get_top_results
from app.services.conversation import conversation_manager
import json
import re
import asyncio

async def execute_plan(websocket: WebSocket, instruction: str, session_id: str = "default", is_clarification_response: bool = False):
    """Main execution loop: plan -> execute -> stream updates."""
    
    plan = None  # Initialize to avoid reference errors
    
    try:
        # Store original instruction in session state (for potential retry/clarification)
        # Import here to avoid circular dependency
        from app.api.websocket import manager
        if session_id in manager.session_states:
            # Only update if we don't already have it (preserve original)
            if "original_instruction" not in manager.session_states[session_id] or not manager.session_states[session_id]["original_instruction"]:
                manager.session_states[session_id]["original_instruction"] = instruction
        
        # If this is a clarification response, process it first
        if is_clarification_response:
            clarification_result = conversation_manager.process_clarification_response(instruction, session_id)
            if clarification_result.get("clarification_resolved"):
                instruction = clarification_result["updated_instruction"]
                conversation_manager.clear_clarification(session_id)
                await websocket.send_json({
                    "type": "status",
                    "message": f"Got it! Processing: {instruction}"
                })
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Could not process clarification response. Please try again."
                })
                return
        
        # Check if clarification is needed
        clarification = conversation_manager.needs_clarification(instruction, session_id)
        if clarification:
            conversation_manager.store_clarification(clarification, instruction, session_id)
            # Ensure original instruction is stored
            if session_id in manager.session_states:
                manager.session_states[session_id]["original_instruction"] = instruction
            await websocket.send_json({
                "type": "clarification",
                "question": clarification["question"],
                "options": clarification.get("options"),
                "field": clarification["field"],
                "context": clarification.get("context")
            })
            # Don't execute finally block - return early without cleanup
            return
        
        # Step 1: Create plan
        await websocket.send_json({
            "type": "status",
            "message": "Planning actions..."
        })
        
        try:
            plan = await create_action_plan(instruction)
        except ValueError as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
            return
        except Exception as e:
            error_msg = str(e)
            if "API key" in error_msg or "401" in error_msg:
                await websocket.send_json({
                    "type": "error",
                    "message": "OpenAI API key not configured or invalid. Please set OPENAI_API_KEY in backend/.env file"
                })
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Failed to create action plan: {error_msg}"
                })
            return
        
        if not plan:
            await websocket.send_json({
                "type": "error",
                "message": "Failed to create action plan. Please check your OpenAI API key and try again."
            })
            return
        
        # Send plan to UI
        await websocket.send_json({
            "type": "plan",
            "data": plan
        })
        
        # Step 2: Initialize browser
        await browser_agent.start()
        
        # Step 3: Execute each action
        for idx, action in enumerate(plan):
            action_type = action.get("action")
            
            await websocket.send_json({
                "type": "action_status",
                "action": action_type,
                "status": "executing",
                "step": idx + 1,
                "total": len(plan),
                "details": action
            })
            
            result = None
            
            try:
                if action_type == "navigate":
                    url = action.get("url")
                    result = await browser_agent.navigate(url)
                    
                    # Handle navigation errors with suggestions
                    if result.get("status") == "error":
                        error_msg = result.get("error", "Navigation failed")
                        suggestions = result.get("suggestions", [])
                        alternative = result.get("alternative")
                        partial_success = result.get("partial_success", False)
                        
                        # If it's a partial success (like Google Maps timeout but page might be usable), continue
                        if partial_success:
                            await websocket.send_json({
                                "type": "status",
                                "message": f"Note: {error_msg}. Continuing anyway..."
                            })
                            # Mark as success so execution continues
                            result["status"] = "success"
                            # Continue to next action instead of breaking
                        else:
                            error_data = {
                                "type": "error",
                                "message": error_msg,
                                "action": "navigate",
                                "url": url
                            }
                            
                            if suggestions:
                                error_data["suggestions"] = suggestions
                            
                            await websocket.send_json(error_data)
                            
                            # For retryable errors, suggest retry
                            if result.get("retryable"):
                                await websocket.send_json({
                                    "type": "status",
                                    "message": "You can try the same request again - this might be a temporary network issue."
                                })
                            
                            # If there's an alternative (like Google Maps), offer it
                            if alternative == "google_maps":
                                # Extract location from original instruction
                                from app.api.websocket import manager
                                original_instruction = manager.session_states.get(session_id, {}).get("original_instruction", instruction)
                                
                                # Try to extract location from instruction
                                location = "your area"
                                if "in " in original_instruction.lower():
                                    parts = original_instruction.lower().split("in ")
                                    if len(parts) > 1:
                                        location = parts[-1].strip()
                                
                                await websocket.send_json({
                                    "type": "clarification",
                                    "question": f"Zomato/Swiggy seems to be blocking automated access. Would you like to try Google Maps instead?",
                                    "options": [
                                        {"value": "google_maps", "label": f"Yes, use Google Maps to find pizza places in {location}"},
                                        {"value": "retry", "label": "Retry Zomato (may still be blocked)"},
                                        {"value": "cancel", "label": "Cancel this task"}
                                    ],
                                    "field": "alternative",
                                    "context": "zomato_blocked",
                                    "clarification_type": "zomato_blocked"
                                })
                                # Store original instruction for retry
                                if session_id in manager.session_states:
                                    manager.session_states[session_id]["original_instruction"] = original_instruction
                                break
                        
                        # Don't break - continue to next action if possible, or let user retry
                        break
                    
                    # Handle blocked/CAPTCHA status
                    if result.get("status") == "blocked":
                        await websocket.send_json({
                            "type": "blocked",
                            "message": result.get("message", "Page is blocked"),
                            "block_type": result.get("block_type", "unknown"),
                            "alternatives": result.get("alternatives", []),
                            "action": "navigate",
                            "url": result.get("url")
                        })
                        
                        # For Google CAPTCHA, suggest alternatives
                        if "google" in url.lower() and result.get("block_type") == "captcha":
                            await websocket.send_json({
                                "type": "clarification",
                                "question": "Google is blocking automated access. Would you like to use an alternative?",
                                "options": [
                                    {"value": "zomato", "label": "Use Zomato instead (for restaurants)"},
                                    {"value": "swiggy", "label": "Use Swiggy instead (for food delivery)"},
                                    {"value": "retry", "label": "Retry Google (may still be blocked)"},
                                    {"value": "cancel", "label": "Cancel this task"}
                                ],
                                "field": "alternative",
                                "context": "google_blocked",
                                "clarification_type": "google_blocked"
                            })
                            # Store original instruction in session for retry
                            # Note: This will be handled by the websocket handler
                            break  # Stop execution, wait for user response
                    
                elif action_type == "click":
                    selector = action.get("selector")
                    result = await browser_agent.click(selector)
                    
                elif action_type == "type":
                    selector = action.get("selector")
                    text = action.get("text")
                    result = await browser_agent.type_text(selector, text)
                    
                elif action_type == "analyze_form":
                    # Analyze form on page and determine fields to fill using LLM
                    from app.api.websocket import manager
                    original_instruction = manager.session_states.get(session_id, {}).get("original_instruction", instruction)
                    result = await browser_agent.analyze_form(original_instruction)
                    
                    # Store analyzed fields in session state for fill_form to use
                    if result.get("status") == "success" and result.get("fields"):
                        if session_id not in manager.session_states:
                            manager.session_states[session_id] = {}
                        manager.session_states[session_id]["analyzed_form_fields"] = result["fields"]
                        await websocket.send_json({
                            "type": "status",
                            "message": f"Analyzed form: found {len(result['fields'])} fields to fill"
                        })
                    
                elif action_type == "fill_form":
                    # Dynamic form filling - use analyzed fields if available, otherwise use provided fields
                    from app.api.websocket import manager
                    provided_fields = action.get("fields", {})
                    
                    # Check if we have analyzed fields from analyze_form
                    analyzed_fields = manager.session_states.get(session_id, {}).get("analyzed_form_fields", {})
                    
                    # Use analyzed fields if available, otherwise use provided fields
                    if analyzed_fields and len(analyzed_fields) > 0:
                        form_fields = analyzed_fields
                        await websocket.send_json({
                            "type": "status",
                            "message": f"Using analyzed form fields ({len(form_fields)} fields)"
                        })
                    else:
                        form_fields = provided_fields
                    
                    if not form_fields or len(form_fields) == 0:
                        result = {
                            "status": "error",
                            "error": "No form fields provided. Please run analyze_form first or provide fields in the action."
                        }
                    else:
                        result = await browser_agent.fill_form(form_fields)
                    
                elif action_type == "submit":
                    selector = action.get("selector", "form, button[type='submit'], input[type='submit']")
                    result = await browser_agent.submit_form(selector)
                    
                    # If form submission was successful, check what happened
                    if result.get("status") == "success":
                        result_info = result.get("result_info", {})
                        
                        # If URL changed, that's usually a success indicator
                        if result.get("url_changed"):
                            await websocket.send_json({
                                "type": "status",
                                "message": f"Form submitted successfully. Redirected to: {result.get('url', 'new page')}"
                            })
                        elif result_info.get("hasSuccessMessage"):
                            await websocket.send_json({
                                "type": "status",
                                "message": "Form submitted successfully. Success message detected."
                            })
                        elif result_info.get("hasErrorMessage"):
                            error_msg = result_info.get("messages", [{}])[0].get("text", "Unknown error")
                            await websocket.send_json({
                                "type": "status",
                                "message": f"Form submitted but error detected: {error_msg}"
                            })
                        else:
                            await websocket.send_json({
                                "type": "status",
                                "message": "Form submitted. Checking result..."
                            })
                    
                elif action_type == "wait_for":
                    selector = action.get("selector")
                    timeout = action.get("timeout", 5000)
                    
                    # For form submissions, if waiting for success message, try multiple strategies
                    if selector and (".success" in selector.lower() or "success" in selector.lower()):
                        # After form submission, try to detect result instead of hardcoded selector
                        try:
                            # Wait a bit for page to update
                            await asyncio.sleep(2)
                            
                            # Check if URL changed (common success indicator)
                            current_url = browser_agent.page.url if browser_agent.page else ""
                            if "signup" not in current_url.lower() and "register" not in current_url.lower():
                                # URL changed, likely success
                                result = {
                                    "status": "success",
                                    "selector": "url_change",
                                    "note": "URL changed after form submission, indicating success"
                                }
                            else:
                                # Check for success/error messages
                                result_info = await browser_agent._detect_form_result()
                                if result_info.get("hasSuccessMessage") or result_info.get("hasErrorMessage"):
                                    result = {
                                        "status": "success",
                                        "selector": "message_detected",
                                        "note": f"Form result detected: {'success' if result_info.get('hasSuccessMessage') else 'error'}",
                                        "result_info": result_info
                                    }
                                else:
                                    # Fall back to normal wait
                                    result = await browser_agent.wait_for(selector, timeout)
                        except Exception as e:
                            # Fall back to normal wait
                            result = await browser_agent.wait_for(selector, timeout)
                    else:
                        result = await browser_agent.wait_for(selector, timeout)
                    
                    # For Google Maps, if wait_for has a note about containers found, continue anyway
                    if result.get("status") == "success" and result.get("note"):
                        await websocket.send_json({
                            "type": "status",
                            "message": f"Note: {result.get('note')}. Continuing with extraction..."
                        })
                    
                    # For Google Maps, if wait_for fails but we're on Maps, try to continue anyway
                    # (results might be there but selector might be wrong)
                    if result.get("status") == "error" and browser_agent.current_site == "google_maps":
                        # Check if result containers exist
                        try:
                            containers = await browser_agent.page.query_selector_all("[data-result-index], div[role='article']")
                            if len(containers) > 0:
                                await websocket.send_json({
                                    "type": "status",
                                    "message": f"Wait timeout, but found {len(containers)} result containers. Continuing with extraction..."
                                })
                                # Mark as success so extraction can proceed
                                result["status"] = "success"
                                result["note"] = "Containers found despite wait timeout"
                        except:
                            pass  # If check fails, proceed with error
                    
                    # Handle blocked status during wait
                    if result.get("status") == "blocked":
                        await websocket.send_json({
                            "type": "blocked",
                            "message": result.get("message", "Page is blocked"),
                            "block_type": result.get("block_type", "unknown"),
                            "action": "wait_for",
                            "selector": selector
                        })
                        
                        # For Google CAPTCHA, suggest alternatives
                        if result.get("block_type") == "captcha":
                            await websocket.send_json({
                                "type": "clarification",
                                "question": "Google blocked the request. Would you like to use an alternative?",
                                "options": [
                                    {"value": "zomato", "label": "Use Zomato instead (for restaurants)"},
                                    {"value": "swiggy", "label": "Use Swiggy instead (for food delivery)"},
                                    {"value": "cancel", "label": "Cancel this task"}
                                ],
                                "field": "alternative",
                                "context": "google_blocked",
                                "clarification_type": "google_blocked"
                            })
                            # Store original instruction in session for retry
                            # Note: This will be handled by the websocket handler
                            break  # Stop execution, wait for user response
                    
                elif action_type == "scroll":
                    # Scroll down to load more results
                    if browser_agent.page:
                        await browser_agent.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await browser_agent.page.wait_for_timeout(2000)  # Wait for content to load
                        result = {"status": "success", "message": "Scrolled to load more results"}
                    else:
                        result = {"status": "error", "error": "Browser not initialized"}
                    
                elif action_type == "extract":
                    schema = action.get("schema", {})
                    limit = action.get("limit", None)
                    intent_info = action.get("_intent", {})
                    
                    # For form submissions, if no schema provided, extract form result
                    if intent_info.get("intent") == "form_fill" and (not schema or len(schema) == 0):
                        # Extract form submission result
                        result_info = await browser_agent._detect_form_result()
                        current_url = browser_agent.page.url if browser_agent.page else ""
                        title = ""
                        if browser_agent.page:
                            try:
                                title = await browser_agent.page.title()
                            except:
                                title = ""
                        
                        # Build extraction schema based on what's available
                        if result_info.get("hasSuccessMessage") or result_info.get("hasErrorMessage"):
                            # Extract messages
                            messages = result_info.get("messages", [])
                            if messages:
                                result = {
                                    "status": "success",
                                    "data": [{
                                        "type": messages[0].get("type", "unknown"),
                                        "message": messages[0].get("text", ""),
                                        "url": current_url,
                                        "title": title
                                    }],
                                    "count": 1
                                }
                            else:
                                result = {
                                    "status": "success",
                                    "data": [{
                                        "status": "success" if result_info.get("hasSuccessMessage") else "error",
                                        "url": current_url,
                                        "title": title,
                                        "note": "Form result detected but message text not extracted"
                                    }],
                                    "count": 1
                                }
                        else:
                            # No specific message, but check URL change
                            if "signup" not in current_url.lower() and "register" not in current_url.lower():
                                result = {
                                    "status": "success",
                                    "data": [{
                                        "status": "success",
                                        "url": current_url,
                                        "title": title,
                                        "note": "Form submitted successfully - URL changed"
                                    }],
                                    "count": 1
                                }
                            else:
                                # Try to extract page content
                                result = await browser_agent.extract({
                                    "status": "body",
                                    "message": "[role='alert'], .message, .notification, .alert, h1, h2",
                                    "url": "a[href]"
                                }, limit)
                    else:
                        result = await browser_agent.extract(schema, limit)
                    
                    # Log extraction result for debugging
                    print(f"Extraction result: status={result.get('status')}, count={result.get('count')}, data_length={len(result.get('data', []))}")
                    if result.get("data"):
                        print(f"First item sample: {result.get('data')[0] if result.get('data') else 'None'}")
                    
                    # Post-process extracted data based on intent
                    if result.get("status") == "success" and result.get("data"):
                        extracted_data = result["data"]
                        
                        # Apply filters based on intent
                        if intent_info.get("intent") == "product_search":
                            filters = intent_info.get("filters", {})
                            
                            # Price filtering
                            if filters.get("price_max"):
                                filtered = filter_by_price(extracted_data, max_price=filters["price_max"])
                                if filtered:
                                    top_results = get_top_results(filtered, limit or 3)
                                    result["data"] = top_results
                                    result["count"] = len(top_results)
                                    result["filtered"] = True
                                    result["max_price"] = filters["price_max"]
                                else:
                                    # Show closest matches
                                    sorted_by_price = sorted(
                                        [item for item in extracted_data if item.get('price')], 
                                        key=lambda x: x.get('price') or float('inf')
                                    )
                                    if sorted_by_price:
                                        closest = sorted_by_price[:limit or 3]
                                        result["data"] = closest
                                        result["count"] = len(closest)
                                        result["filtered"] = True
                                        result["max_price"] = filters["price_max"]
                                        result["message"] = f"No products found under ₹{filters['price_max']:,.0f}. Showing closest matches:"
                                    else:
                                        result["data"] = []
                                        result["count"] = 0
                            elif filters.get("price_min"):
                                filtered = filter_by_price(extracted_data, min_price=filters["price_min"])
                                if filtered:
                                    top_results = get_top_results(filtered, limit or 3)
                                    result["data"] = top_results
                                    result["count"] = len(top_results)
                                else:
                                    result["data"] = []
                                    result["count"] = 0
                            else:
                                # Just get top results by rating
                                top_results = get_top_results(extracted_data, limit or 3)
                                result["data"] = top_results
                                result["count"] = len(top_results)
                            
                            # Rating filtering
                            if filters.get("rating_min") and result.get("data"):
                                filtered_by_rating = [
                                    item for item in result["data"] 
                                    if item.get("rating") and item["rating"] >= filters["rating_min"]
                                ]
                                if filtered_by_rating:
                                    result["data"] = filtered_by_rating[:limit or 3]
                                    result["count"] = len(result["data"])
                        
                        elif intent_info.get("intent") == "local_discovery":
                            # For local discovery, sort by rating
                            if result.get("data"):
                                sorted_by_rating = sorted(
                                    [item for item in result["data"] if item.get("rating")],
                                    key=lambda x: x.get("rating") or 0,
                                    reverse=True
                                )
                                result["data"] = sorted_by_rating[:limit or 3]
                                result["count"] = len(result["data"])
                    
                else:
                    result = {
                        "status": "error",
                        "error": f"Unknown action type: {action_type}"
                    }
                
                # Send result with full details
                await websocket.send_json({
                    "type": "action_status",
                    "action": action_type,
                    "status": "completed" if result.get("status") == "success" else "error",
                    "step": idx + 1,
                    "total": len(plan),
                    "result": result,
                    "details": action  # Include original action details
                })
                
                # If error, show helpful message but continue if it's a selector issue
                if result.get("status") == "error":
                    error_msg = result.get("error", "Action failed")
                    suggestions = result.get("suggestions", [])
                    alternatives = result.get("alternatives", [])
                    
                    error_data = {
                        "type": "error",
                        "message": error_msg,
                        "action": action_type,
                        "selector": result.get("selector")
                    }
                    
                    if suggestions:
                        error_data["suggestions"] = suggestions
                        error_msg += f"\n💡 Try these selectors instead: {', '.join(suggestions[:3])}"
                    
                    await websocket.send_json(error_data)
                    
                    # For wait_for errors on Google Maps, continue anyway (extraction might still work)
                    if action_type == "wait_for" and browser_agent.current_site == "google_maps" and "timeout" in error_msg.lower():
                        await websocket.send_json({
                            "type": "status",
                            "message": "Wait timeout on Google Maps, but continuing with extraction anyway..."
                        })
                        # Don't break - continue to extraction
                    
                    # For selector errors, try to continue with next action
                    # For other errors, stop execution
                    elif "selector" not in error_msg.lower() and "timeout" not in error_msg.lower():
                        break
                
                # Handle blocked status
                if result.get("status") == "blocked":
                    await websocket.send_json({
                        "type": "blocked",
                        "message": result.get("message", "Page is blocked"),
                        "block_type": result.get("block_type", "unknown"),
                        "alternatives": result.get("alternatives", []),
                        "action": action_type
                    })
                    break
                    
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Exception during {action_type}: {str(e)}",
                    "action": action_type
                })
                break
    
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"Unexpected error: {str(e)}"
        })
    finally:
        # Only cleanup and send completion if we actually executed a plan
        # (not if we returned early for clarification)
        if plan is not None:
            # Cleanup
            try:
                await browser_agent.close()
            except:
                pass
            
            # Send final summary if we extracted data
            final_extract = None
            for action in plan:
                if action.get("action") == "extract":
                    # We already processed this, but send a summary
                    break
            
            await websocket.send_json({
                "type": "status",
                "message": "Execution completed"
            })

