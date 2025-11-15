from fastapi import WebSocket
from app.services.ai_planner import create_action_plan
from app.services.browser_agent import browser_agent
from app.services.filter_results import (
    filter_by_price, 
    get_top_results, 
    extract_filter_options, 
    consolidate_filter_options,
    apply_variant_filters,
    filter_by_product_relevance
)
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
        
        # Add user instruction to conversation history
        conversation_manager.add_to_history(session_id, "user", instruction)
        
        # If this is a clarification response, process it first
        if is_clarification_response:
            clarification_result = conversation_manager.process_clarification_response(instruction, session_id)
            if clarification_result.get("clarification_resolved"):
                # Check if this is a filter refinement response
                if clarification_result.get("apply_filters"):
                    filter_selections = clarification_result.get("filter_selections", {})
                    
                    # Apply filters to stored results
                    if session_id in manager.session_states:
                        stored_results = manager.session_states[session_id].get("extracted_results", [])
                        
                        if stored_results:
                            # Apply variant filters
                            filtered_results = apply_variant_filters(stored_results, filter_selections)
                            
                            if filtered_results:
                                await websocket.send_json({
                                    "type": "status",
                                    "message": f"Applied filters. Found {len(filtered_results)} matching products."
                                })
                                
                                # Send filtered results
                                await websocket.send_json({
                                    "type": "action_status",
                                    "action": "filter",
                                    "status": "completed",
                                    "result": {
                                        "status": "success",
                                        "data": filtered_results,
                                        "count": len(filtered_results),
                                        "filters_applied": filter_selections
                                    }
                                })
                            else:
                                await websocket.send_json({
                                    "type": "status",
                                    "message": f"No products match the selected filters. Showing all {len(stored_results)} products."
                                })
                                
                                # Send original results
                                await websocket.send_json({
                                    "type": "action_status",
                                    "action": "filter",
                                    "status": "completed",
                                    "result": {
                                        "status": "success",
                                        "data": stored_results,
                                        "count": len(stored_results),
                                        "filters_applied": filter_selections,
                                        "message": "No exact matches found"
                                    }
                                })
                            
                            # Send completion message to clear loading state
                            await websocket.send_json({
                                "type": "status",
                                "message": "Execution completed"
                            })
                            
                            conversation_manager.clear_clarification(session_id)
                            return
                
                instruction = clarification_result["updated_instruction"]
                conversation_manager.clear_clarification(session_id)
                await websocket.send_json({
                    "type": "status",
                    "message": f"Got it! Processing: {instruction}"
                })
                
                # IMMEDIATE SWIGGY DETECTION: Check right after clarification response
                # This is where "swiggy" gets added to the instruction
                if "swiggy" in instruction.lower():
                    try:
                        await websocket.send_json({
                            "type": "message",
                            "message": "⚡ Using stealth mode for Swiggy...",
                            "level": "info"
                        })
                        
                        # Use current instruction (which has "on swiggy" appended)
                        # Clean up the query - remove common prefixes and "on swiggy"
                        query = instruction
                        query_lower = query.lower()
                        
                        # Remove prefixes
                        prefixes = ["find", "search for", "show me", "get me", "look for"]
                        for prefix in prefixes:
                            if query_lower.startswith(prefix):
                                query = query[len(prefix):].strip()
                                query_lower = query.lower()
                                break
                        
                        # Remove "on swiggy" or "using swiggy" suffix
                        for suffix in ["on swiggy", "using swiggy", "via swiggy", "from swiggy"]:
                            if query_lower.endswith(suffix):
                                query = query[:-len(suffix)].strip()
                                break
                        
                        # If query is empty or too short, try original instruction
                        if not query or len(query.split()) < 2:
                            original_instruction = manager.session_states.get(session_id, {}).get("original_instruction", instruction)
                            query = original_instruction
                            # Remove "on swiggy" from original too
                            query_lower = query.lower()
                            for suffix in ["on swiggy", "using swiggy", "via swiggy", "from swiggy"]:
                                if query_lower.endswith(suffix):
                                    query = query[:-len(suffix)].strip()
                                    break
                        
                        # Extract location from query and clean up query
                        location_match = re.search(r'(?:in|near|at)\s+([A-Za-z\s]+)', query, re.IGNORECASE)
                        location = location_match.group(1).strip() if location_match else "HSR Layout Bangalore"
                        
                        # Remove location from query to get just the food item
                        if location_match:
                            # Remove "in/near/at location" from query
                            query = re.sub(r'\s*(?:in|near|at)\s+[A-Za-z\s]+', '', query, flags=re.IGNORECASE).strip()
                            # Remove common words like "places", "restaurants", "best"
                            query = re.sub(r'\b(best|top|good|great|places?|restaurants?)\b', '', query, flags=re.IGNORECASE).strip()
                            query = query.strip()
                        
                        # If query is empty after cleaning, use a default
                        if not query or len(query.split()) == 0:
                            query = "restaurants"
                        
                        # If location doesn't have city, add Bangalore as default
                        if location and "bangalore" not in location.lower() and "bengaluru" not in location.lower():
                            location = f"{location} Bangalore"
                        
                        # Default limit
                        extraction_limit = 10
                        
                        await websocket.send_json({
                            "type": "message",
                            "message": f"🔍 Searching for '{query}' in {location}...",
                            "level": "info"
                        })
                        
                        # Use specialized Swiggy search function with stealth mode - direct call
                        result = await browser_agent.search_swiggy(query, location=location, limit=extraction_limit)
                        
                        # Format and send result
                        if result.get("status") == "success":
                            for item in result.get("data", []):
                                if "rating" in item and item["rating"]:
                                    try:
                                        item["rating"] = float(item["rating"])
                                    except:
                                        pass
                            
                            result["count"] = len(result.get("data", []))
                            
                            # Send final result
                            await websocket.send_json({
                                "type": "result",
                                "data": result,
                                "count": result["count"]
                            })
                        else:
                            # Swiggy search failed
                            error_message = result.get("message", "Swiggy search failed")
                            suggestion = result.get("suggestion", "Try using Google Maps for restaurant discovery")
                            
                            await websocket.send_json({
                                "type": "error",
                                "message": f"{error_message}. {suggestion}"
                            })
                    except Exception as e:
                        # Handle any errors during Swiggy search
                        error_msg = str(e)
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Error during Swiggy search: {error_msg}"
                        })
                    
                    # Skip everything else - return early
                    return
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Could not process clarification response. Please try again."
                })
                return
        
        # Apply learned preferences to instruction
        instruction = await conversation_manager.apply_learned_preferences(instruction, session_id)
        
        # Check if clarification is needed
        clarification = await conversation_manager.needs_clarification(instruction, session_id)
        if clarification:
            conversation_manager.store_clarification(clarification, instruction, session_id)
            # Ensure original instruction is stored
            if session_id in manager.session_states:
                manager.session_states[session_id]["original_instruction"] = instruction
            
            # Add clarification to history
            conversation_manager.add_to_history(
                session_id, 
                "assistant", 
                clarification["question"],
                {"type": "clarification", "context": clarification.get("context")}
            )
            
            await websocket.send_json({
                "type": "clarification",
                "question": clarification["question"],
                "options": clarification.get("options"),
                "field": clarification["field"],
                "context": clarification.get("context")
            })
            # Don't execute finally block - return early without cleanup
            return
        
        # Step 1: Create plan (LLM generates plan for all instructions including Swiggy)
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
        
        # SPECIAL HANDLING: Detect Swiggy searches in the LLM-generated plan and use optimized path
        # Check if any action in the plan involves Swiggy
        is_swiggy_search = False
        if plan:
            for action in plan:
                action_url = action.get("url", "")
                if action_url and "swiggy" in str(action_url).lower():
                    is_swiggy_search = True
                    break
        
        if is_swiggy_search:
            # LLM has generated the plan, now use optimized Swiggy execution
            # SwiggyHandler will send real-time action_status updates as steps execute
            await websocket.send_json({
                "type": "message",
                "message": "⚡ Using optimized Swiggy search with stealth mode...",
                "level": "info"
            })
            
            # Extract query and location from original instruction
            original_instruction = manager.session_states.get(session_id, {}).get("original_instruction", instruction)
            
            # Clean up the query - remove common prefixes and "on swiggy"
            query = original_instruction
            query_lower = query.lower()
            
            # Remove prefixes
            prefixes = ["find", "search for", "show me", "get me", "look for"]
            for prefix in prefixes:
                if query_lower.startswith(prefix):
                    query = query[len(prefix):].strip()
                    query_lower = query.lower()
                    break
            
            # Remove "on swiggy" or "using swiggy" suffix
            for suffix in ["on swiggy", "using swiggy", "via swiggy", "from swiggy"]:
                if query_lower.endswith(suffix):
                    query = query[:-len(suffix)].strip()
                    break
            
            # If query is empty or too short, use original
            if not query or len(query.split()) < 2:
                query = original_instruction
            
            # Extract location from query and clean up query
            location_match = re.search(r'(?:in|near|at)\s+([A-Za-z\s]+)', query, re.IGNORECASE)
            location = location_match.group(1).strip() if location_match else "HSR Layout Bangalore"
            
            # Remove location from query to get just the food item
            if location_match:
                # Remove "in/near/at location" from query
                query = re.sub(r'\s*(?:in|near|at)\s+[A-Za-z\s]+', '', query, flags=re.IGNORECASE).strip()
                # Remove common words like "places", "restaurants", "best"
                query = re.sub(r'\b(best|top|good|great|places?|restaurants?)\b', '', query, flags=re.IGNORECASE).strip()
                query = query.strip()
            
            # If query is empty after cleaning, use a default
            if not query or len(query.split()) == 0:
                query = "restaurants"
            
            # If location doesn't have city, add Bangalore as default
            if location and "bangalore" not in location.lower() and "bengaluru" not in location.lower():
                location = f"{location} Bangalore"
            
            # Get extraction limit from plan
            extraction_limit = 10
            requested_limit = None
            for action in plan:
                if action.get("action") == "extract":
                    extraction_limit = action.get("limit", 10)
                    intent_info = action.get("_intent", {})
                    requested_limit = intent_info.get("limit", None)
                    break
            
            # Use specialized Swiggy search function with stealth mode
            # SwiggyHandler will send all action_status updates including extract at the right time
            # Pass plan so SwiggyHandler can map its steps to LLM plan steps
            result = await browser_agent.search_swiggy(
                query, 
                location=location, 
                limit=extraction_limit,
                websocket=websocket,
                session_id=session_id,
                plan=plan
            )
            
            # Format and send result
            if result.get("status") == "success":
                for item in result.get("data", []):
                    if "rating" in item and item["rating"]:
                        try:
                            item["rating"] = float(item["rating"])
                        except:
                            pass
                
                result["count"] = len(result.get("data", []))
                
                # Apply requested limit if specified (e.g., "top 3")
                if requested_limit and result.get("data"):
                    sorted_data = sorted(
                        result["data"],
                        key=lambda x: (x.get("rating") or 0),
                        reverse=True
                    )
                    result["data"] = sorted_data[:requested_limit]
                    result["count"] = len(result["data"])
                
                # Send extract action with results
                await websocket.send_json({
                    "type": "action_status",
                    "action": "extract",
                    "status": "completed",
                    "step": len(plan),
                    "total": len(plan),
                    "result": result,
                    "details": {"action": "extract", "limit": requested_limit or extraction_limit}
                })
                
                await websocket.send_json({
                    "type": "status",
                    "message": f"Found {result['count']} restaurants"
                })
            else:
                error_message = result.get("message", "Swiggy search failed")
                suggestion = result.get("suggestion", "Try using Google Maps for restaurant discovery")
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": "extract",
                    "status": "error",
                    "step": len(plan),
                    "total": len(plan),
                    "result": result,
                    "details": {"action": "extract", "error": error_message}
                })
                
                await websocket.send_json({
                    "type": "error",
                    "message": f"{error_message}. {suggestion}"
                })
            
            # Skip normal execution loop
            plan = []
        
        # Check if this is a Google Maps local discovery - use specialized function
        intent_info = plan[0].get("_intent", {}) if plan else {}
        if intent_info.get("intent") == "local_discovery":
            # Check if any action mentions Google Maps
            has_google_maps = any(
                "google" in str(action.get("url", "")).lower() or 
                "maps" in str(action.get("url", "")).lower() or
                browser_agent.current_site == "google_maps"
                for action in plan
            )
            
            if has_google_maps:
                await websocket.send_json({
                    "type": "status",
                    "message": "Using optimized Google Maps search..."
                })
                
                # Send action cards for each step in the plan to show progress
                for idx, action in enumerate(plan):
                    action_type = action.get("action")
                    # Send executing status for each action
                    await websocket.send_json({
                        "type": "action_status",
                        "action": action_type,
                        "status": "executing",
                        "step": idx + 1,
                        "total": len(plan),
                        "details": action
                    })
                    # Small delay to show the executing state
                    await asyncio.sleep(0.3)
                    
                    # Mark as completed (we're using optimized path, so these complete quickly)
                    await websocket.send_json({
                        "type": "action_status",
                        "action": action_type,
                        "status": "completed",
                        "step": idx + 1,
                        "total": len(plan),
                        "details": action,
                        "result": {"status": "success", "note": "Using optimized Google Maps search"}
                    })
                
                # Extract query from original instruction
                original_instruction = manager.session_states.get(session_id, {}).get("original_instruction", instruction)
                
                # Clean up the query - remove common prefixes and "on google maps" but keep the actual search terms
                query = original_instruction
                query_lower = query.lower()
                
                # Remove prefixes but keep the search terms
                prefixes = ["find", "search for", "show me", "get me", "look for"]
                for prefix in prefixes:
                    if query_lower.startswith(prefix):
                        query = query[len(prefix):].strip()
                        query_lower = query.lower()
                        break
                
                # Remove "on google maps" suffix if present
                for suffix in ["on google maps", "on google", "using google maps", "via google maps"]:
                    if query_lower.endswith(suffix):
                        query = query[:-len(suffix)].strip()
                        break
                
                # If query is empty or too short, use original
                if not query or len(query.split()) < 2:
                    query = original_instruction
                
                
                # Extract location from query
                location_match = re.search(r'(?:in|near|at)\s+([A-Za-z\s]+)', query, re.IGNORECASE)
                location = location_match.group(1).strip() if location_match else "HSR"
                
                # Map location names to coordinates
                location_coords = {
                    "hsr": (12.9116, 77.6446),
                    "indiranagar": (12.9784, 77.6408),
                    "koramangala": (12.9352, 77.6245),
                    "whitefield": (12.9698, 77.7499),
                    "bangalore": (12.9716, 77.5946),
                    "bengaluru": (12.9716, 77.5946),
                }
                
                loc_lower = location.lower()
                lat, lng = location_coords.get(loc_lower, (12.9250, 77.6400))
                
                # Get extraction limit and requested limit from intent_info
                extraction_limit = None
                requested_limit = None
                for action in plan:
                    if action.get("action") == "extract":
                        extraction_limit = action.get("limit", 10)
                        intent_info = action.get("_intent", {})
                        requested_limit = intent_info.get("limit", None)
                        break
                
                # Send executing status for extract action
                await websocket.send_json({
                    "type": "action_status",
                    "action": "extract",
                    "status": "executing",
                    "step": len(plan),
                    "total": len(plan),
                    "details": {"action": "extract", "limit": extraction_limit}
                })
                
                # Use specialized Maps search function - extract more than requested for filtering
                result = await browser_agent.search_google_maps(query, limit=extraction_limit or 10, lat=lat, lng=lng)
                
                # Format result
                if result.get("status") == "success":
                    for item in result.get("data", []):
                        if "address" in item and "location" not in item:
                            item["location"] = item.pop("address")
                        elif "address" in item:
                            item["location"] = item["address"]
                        if "rating" in item and item["rating"]:
                            try:
                                item["rating"] = float(item["rating"])
                            except:
                                pass
                        if "reviews" in item and item["reviews"]:
                            try:
                                item["reviews"] = int(item["reviews"])
                            except:
                                pass
                    
                    result["count"] = len(result.get("data", []))
                    
                    # Apply requested limit if specified (e.g., "top 3")
                    if requested_limit and result.get("data"):
                        # Sort by rating and take top N
                        sorted_data = sorted(
                            result["data"],
                            key=lambda x: (x.get("rating") or 0, x.get("reviews") or 0),
                            reverse=True
                        )
                        result["data"] = sorted_data[:requested_limit]
                        result["count"] = len(result["data"])
                    
                    # Send result as if it came from extract action
                    await websocket.send_json({
                        "type": "action_status",
                        "action": "extract",
                        "status": "completed",
                        "step": len(plan),
                        "total": len(plan),
                        "result": result,
                        "details": {"action": "extract", "limit": requested_limit or extraction_limit}
                    })
                    
                    # Skip normal execution loop
                    plan = []  # Empty plan so we skip the loop
        
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
                    
                    # Store submission result in session for extraction step
                    from app.api.websocket import manager
                    if session_id not in manager.session_states:
                        manager.session_states[session_id] = {}
                    manager.session_states[session_id]["last_submission_result"] = result
                    
                    # If form submission was successful, check what happened
                    if result.get("status") == "success":
                        result_info = result.get("result_info", {})
                        
                        # Build detailed status message
                        status_parts = []
                        
                        if result.get("url_changed"):
                            status_parts.append(f"Form submitted successfully. Redirected from {result.get('submitted_url', 'original page')} to {result.get('redirected_url', 'new page')}")
                        else:
                            status_parts.append(f"Form submitted successfully on {result.get('submitted_url', 'current page')}")
                        
                        if result.get("form_data"):
                            status_parts.append(f"Submitted {len(result.get('form_data', {}))} fields")
                        
                        if result_info.get("hasSuccessMessage"):
                            msg = result_info.get("messages", [{}])[0].get("text", "")
                            if msg:
                                status_parts.append(f"Success: {msg}")
                            else:
                                status_parts.append("Success message detected")
                        elif result_info.get("hasErrorMessage"):
                            error_msg = result_info.get("messages", [{}])[0].get("text", "Unknown error")
                            status_parts.append(f"Error: {error_msg}")
                        
                        await websocket.send_json({
                            "type": "status",
                            "message": " | ".join(status_parts) if status_parts else "Form submitted. Checking result..."
                        })
                        
                        # Send detailed submission info
                        await websocket.send_json({
                            "type": "form_submission",
                            "submitted_url": result.get("submitted_url"),
                            "redirected_url": result.get("redirected_url"),
                            "url_changed": result.get("url_changed", False),
                            "form_data": result.get("form_data", {}),
                            "response_data": result.get("response_data", {}),
                            "has_success": result_info.get("hasSuccessMessage", False),
                            "has_error": result_info.get("hasErrorMessage", False),
                            "messages": result_info.get("messages", [])
                        })
                    
                elif action_type == "wait_for":
                    selector = action.get("selector")
                    timeout = action.get("timeout", 5000)
                    
                    # Check if this is a form filling flow
                    is_form_flow = intent_info.get("intent") == "form_fill"
                    
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
                    
                    # For form flows, if wait_for fails with a generic selector, try to continue anyway
                    # (form fields might be there but selector might be too generic)
                    if result.get("status") == "error" and is_form_flow:
                        # Check if any form fields exist on the page
                        try:
                            if browser_agent.page:
                                form_fields_count = await browser_agent.page.evaluate("""
                                    () => {
                                        const inputs = document.querySelectorAll('input, textarea, select');
                                        return inputs.length;
                                    }
                                """)
                                if form_fields_count > 0:
                                    # Form fields exist, continue anyway
                                    await websocket.send_json({
                                        "type": "status",
                                        "message": f"Wait timeout for selector, but found {form_fields_count} form fields. Continuing with form analysis..."
                                    })
                                    result["status"] = "success"
                                    result["note"] = f"Form fields found ({form_fields_count} fields) despite wait timeout"
                                    result["warning"] = True  # Mark as warning, not error
                        except:
                            pass  # If check fails, proceed with error
                    
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
                    extraction_limit = action.get("limit", None)  # Limit for extraction (extract more for filtering)
                    intent_info = action.get("_intent", {})
                    # Get the user's requested limit from intent_info (e.g., "top 3")
                    requested_limit = intent_info.get("limit", None)
                    
                    # For Google Maps, use the specialized search function if this is local discovery
                    if browser_agent.current_site == "google_maps" and intent_info.get("intent") == "local_discovery":
                        await websocket.send_json({
                            "type": "status",
                            "message": "Using optimized Google Maps extraction..."
                        })
                        
                        # Extract location from instruction if possible
                        location_match = re.search(r'(?:in|near|at)\s+([A-Za-z\s]+)', instruction, re.IGNORECASE)
                        location = location_match.group(1).strip() if location_match else "HSR"
                        
                        # Map location names to coordinates (add more as needed)
                        location_coords = {
                            "hsr": (12.9116, 77.6446),
                            "indiranagar": (12.9784, 77.6408),
                            "koramangala": (12.9352, 77.6245),
                            "whitefield": (12.9698, 77.7499),
                            "bangalore": (12.9716, 77.5946),
                            "bengaluru": (12.9716, 77.5946),
                        }
                        
                        loc_lower = location.lower()
                        lat, lng = location_coords.get(loc_lower, (12.9250, 77.6400))  # Default to HSR
                        
                        # Extract query from instruction
                        query = instruction
                        # Try to extract just the main query part
                        for phrase in ["find", "search for", "show me", "get me", "on google maps"]:
                            if phrase in query.lower():
                                query = query.lower().split(phrase, 1)[-1].strip()
                                break
                        
                        # Use the specialized Maps search - extract more than requested for filtering
                        result = await browser_agent.search_google_maps(query, limit=extraction_limit or 10, lat=lat, lng=lng)
                        
                        # Apply requested limit if specified (e.g., "top 3")
                        if requested_limit and result.get("status") == "success" and result.get("data"):
                            # Sort by rating and take top N
                            sorted_data = sorted(
                                result["data"],
                                key=lambda x: (x.get("rating") or 0, x.get("reviews") or 0),
                                reverse=True
                            )
                            result["data"] = sorted_data[:requested_limit]
                            result["count"] = len(result["data"])
                        
                        # If Maps search was successful, format result to match expected structure
                        if result.get("status") == "success":
                            # Convert address field to location for consistency, and ensure all fields are present
                            for item in result.get("data", []):
                                # Map address to location for UI consistency
                                if "address" in item and "location" not in item:
                                    item["location"] = item.pop("address")
                                elif "address" in item:
                                    item["location"] = item["address"]
                                
                                # Ensure rating is a number if present
                                if "rating" in item and item["rating"]:
                                    try:
                                        item["rating"] = float(item["rating"])
                                    except:
                                        pass
                                
                                # Ensure reviews is a number if present
                                if "reviews" in item and item["reviews"]:
                                    try:
                                        item["reviews"] = int(item["reviews"])
                                    except:
                                        pass
                            
                            result["count"] = len(result.get("data", []))
                        
                        # Continue with normal post-processing
                    else:
                        # For form submissions, if no schema provided, extract form result
                        if intent_info.get("intent") == "form_fill" and (not schema or len(schema) == 0):
                            # Get submission result from the submit action (stored in session or get from page)
                            current_url = browser_agent.page.url if browser_agent.page else ""
                            title = ""
                            if browser_agent.page:
                                try:
                                    title = await browser_agent.page.title()
                                except:
                                    title = ""
                            
                            # Try to get submission details from the last submit action result
                            # Check if we have submission info stored
                            from app.api.websocket import manager
                            submission_result = None
                            if session_id in manager.session_states:
                                submission_result = manager.session_states[session_id].get("last_submission_result")
                            
                            # Extract form submission result
                            result_info = await browser_agent._detect_form_result()
                            
                            # Build comprehensive result with all submission details
                            form_result = {
                                "status": "success",
                                "submitted_url": submission_result.get("submitted_url") if submission_result else current_url,
                                "redirected_url": current_url,
                                "url": current_url,
                                "title": title,
                                "url_changed": submission_result.get("url_changed", False) if submission_result else False,
                            }
                            
                            # Add form data that was submitted
                            if submission_result and submission_result.get("form_data"):
                                form_result["form_data"] = submission_result["form_data"]
                            
                            # Add response data if available
                            if submission_result and submission_result.get("response_data"):
                                form_result["response_data"] = submission_result["response_data"]
                            
                            # Add success/error messages
                            if result_info.get("hasSuccessMessage") or result_info.get("hasErrorMessage"):
                                messages = result_info.get("messages", [])
                                if messages:
                                    form_result["message"] = messages[0].get("text", "")
                                    form_result["message_type"] = messages[0].get("type", "unknown")
                                else:
                                    form_result["message_type"] = "success" if result_info.get("hasSuccessMessage") else "error"
                            
                            result = {
                                "status": "success",
                                "data": [form_result],
                                "count": 1
                            }
                        else:
                            # Use extraction_limit for extraction (extract more for filtering)
                            result = await browser_agent.extract(schema, extraction_limit)
                    
                    # Post-process extracted data based on intent
                    if result.get("status") == "success" and result.get("data"):
                        # Make a copy to avoid reference issues
                        extracted_data = list(result["data"]) if isinstance(result["data"], list) else result["data"]
                        
                        # Debug: Log intent info
                        
                        # Apply filters based on intent
                        if intent_info.get("intent") == "url_search":
                            # For URL search, prioritize URLs and ensure they're complete
                            for item in extracted_data:
                                # Ensure URL is absolute (add domain if relative)
                                if item.get("url") and not item["url"].startswith(("http://", "https://")):
                                    # Try to make it absolute
                                    current_url = browser_agent.page.url if browser_agent.page else ""
                                    if current_url:
                                        from urllib.parse import urljoin, urlparse
                                        base_url = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
                                        item["url"] = urljoin(base_url, item["url"])
                                
                                # Ensure we have a title or use URL as fallback
                                if not item.get("title") and item.get("url"):
                                    item["title"] = item["url"]
                            
                            # Limit to first 10 results (user usually wants top results)
                            requested_limit = intent_info.get("limit", 10)
                            if requested_limit:
                                extracted_data = extracted_data[:requested_limit]
                            else:
                                extracted_data = extracted_data[:10]  # Default to 10
                            
                            result["data"] = extracted_data
                            result["count"] = len(extracted_data)
                            
                        elif intent_info.get("intent") == "product_search":
                            # FIRST: Filter by product relevance to remove off-brand results
                            # Extract the main product query from intent or instruction
                            product_query = intent_info.get("product", "")
                            if not product_query:
                                # Try to extract from original instruction
                                from app.api.websocket import manager
                                original_instruction = manager.session_states.get(session_id, {}).get("original_instruction", instruction)
                                product_query = original_instruction
                            
                            # Apply relevance filter
                            extracted_data = filter_by_product_relevance(extracted_data, product_query)
                            
                            if len(extracted_data) < len(result["data"]):
                                # Log that we filtered out irrelevant results
                                filtered_count = len(result["data"]) - len(extracted_data)
                                await websocket.send_json({
                                    "type": "status",
                                    "message": f"Filtered out {filtered_count} irrelevant results"
                                })
                            
                            # Continue with price/rating filters
                            filters = intent_info.get("filters", {})
                            
                            # Price filtering - ensure prices are parsed first
                            if filters.get("price_max"):
                                # Normalize all prices to floats before filtering
                                for item in extracted_data:
                                    if 'price' in item and item['price']:
                                        price = item['price']
                                        if isinstance(price, str):
                                            # Parse string prices - handle Amazon format like "₹93,900.00"
                                            price_clean = re.sub(r'[₹$€£,\s]', '', str(price).strip())
                                            price_str = re.sub(r'[^\d.]', '', price_clean)
                                            if price_str:
                                                try:
                                                    parsed_price = float(price_str)
                                                    # Validate price is reasonable (not obviously wrong)
                                                    # MacBook Air prices should be between ₹50,000 and ₹5,00,000
                                                    # If price is > 10,000,000, it's likely a parsing error
                                                    if parsed_price > 10000000:
                                                        # Try to extract first reasonable number
                                                        numbers = re.findall(r'\d+', price_clean)
                                                        if numbers:
                                                            # Take the first number that's reasonable
                                                            for num_str in numbers:
                                                                num = float(num_str)
                                                                if 50000 <= num <= 5000000:
                                                                    parsed_price = num
                                                                    break
                                                            else:
                                                                # If no reasonable number found, use first one anyway
                                                                parsed_price = float(numbers[0]) if numbers else None
                                                        else:
                                                            parsed_price = None
                                                    item['price'] = parsed_price
                                                except:
                                                    # Try fallback extraction
                                                    numbers = re.findall(r'\d+\.?\d*', price_clean)
                                                    if numbers:
                                                        try:
                                                            # Try to find a reasonable price
                                                            for num_str in numbers:
                                                                num = float(num_str)
                                                                if 50000 <= num <= 5000000:
                                                                    item['price'] = num
                                                                    break
                                                            else:
                                                                item['price'] = float(numbers[0])
                                                        except:
                                                            item['price'] = None
                                                    else:
                                                        item['price'] = None
                                        
                                filtered = filter_by_price(extracted_data, max_price=filters["price_max"])
                                if filtered:
                                    # Use requested_limit (user's "top N") or None for all results
                                    top_results = get_top_results(filtered, requested_limit)
                                    # CRITICAL: Replace the data array completely, don't modify in place
                                    result["data"] = top_results.copy() if hasattr(top_results, 'copy') else list(top_results)
                                    result["count"] = len(result["data"])
                                    result["filtered"] = True
                                    result["max_price"] = filters["price_max"]
                                    # Debug log
                                else:
                                    # Show closest matches (only items with valid prices)
                                    items_with_prices = [
                                        item for item in extracted_data 
                                        if item.get('price') and isinstance(item.get('price'), (int, float))
                                    ]
                                    if items_with_prices:
                                        sorted_by_price = sorted(
                                            items_with_prices, 
                                            key=lambda x: float(x.get('price', 0))
                                        )
                                        if requested_limit is not None:
                                            closest = sorted_by_price[:requested_limit]
                                        else:
                                            closest = sorted_by_price
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
                                    top_results = get_top_results(filtered, requested_limit)
                                    result["data"] = top_results
                                    result["count"] = len(top_results)
                                else:
                                    result["data"] = []
                                    result["count"] = 0
                            else:
                                # Just get top results by rating - use requested_limit (None means all results)
                                top_results = get_top_results(extracted_data, requested_limit)
                                result["data"] = top_results
                                result["count"] = len(top_results)
                            
                            # Rating filtering
                            if filters.get("rating_min") and result.get("data"):
                                filtered_by_rating = [
                                    item for item in result["data"] 
                                    if item.get("rating") and item["rating"] >= filters["rating_min"]
                                ]
                                if filtered_by_rating:
                                    if requested_limit is not None:
                                        result["data"] = filtered_by_rating[:requested_limit]
                                    else:
                                        result["data"] = filtered_by_rating
                                    result["count"] = len(result["data"])
                        
                        elif intent_info.get("intent") == "local_discovery":
                            # For local discovery, sort by rating and apply requested limit
                            if result.get("data"):
                                sorted_by_rating = sorted(
                                    [item for item in result["data"] if item.get("rating")],
                                    key=lambda x: x.get("rating") or 0,
                                    reverse=True
                                )
                                # Use requested_limit (None means all results)
                                if requested_limit is not None:
                                    result["data"] = sorted_by_rating[:requested_limit]
                                else:
                                    result["data"] = sorted_by_rating
                                result["count"] = len(result["data"])
                    
                else:
                    result = {
                        "status": "error",
                        "error": f"Unknown action type: {action_type}"
                    }
                
                # For extract actions, ensure data and count are consistent
                if action_type == "extract" and result.get("status") == "success":
                    if "data" in result and isinstance(result["data"], list):
                        # Ensure count matches actual data length
                        result["count"] = len(result["data"])
                
                # Send result with full details
                # For wait_for with warnings, show as completed with warning
                result_status = "completed"
                if result.get("status") == "error":
                    result_status = "error"
                elif result.get("warning"):
                    result_status = "completed"  # Show as completed but with warning note
                
                await websocket.send_json({
                    "type": "action_status",
                    "action": action_type,
                    "status": result_status,
                    "step": idx + 1,
                    "total": len(plan),
                    "result": result,
                    "details": action,  # Include original action details
                    "warning": result.get("warning", False)  # Include warning flag
                })
                
                # FEATURE: Extract filter options after product extraction
                if action_type == "extract" and result.get("status") == "success" and result.get("data"):
                    intent_info = action.get("_intent", {})
                    
                    # Only for product search, check if we should ask for filter refinement
                    if intent_info.get("intent") == "product_search":
                        # Step 1: Extract basic filter options from product names (memory, storage, size - NO COLORS)
                        filter_options = extract_filter_options(result["data"])
                        
                        # Step 2: Dynamically extract variants (especially COLORS) from product detail pages
                        # Colors should ONLY come from product pages, not from names/URLs
                        await websocket.send_json({
                            "type": "status",
                            "message": "Scanning product pages for available variants..."
                        })
                        
                        # Get product URLs
                        product_urls = [
                            item.get('url') or item.get('link')
                            for item in result["data"]
                            if item.get('url') or item.get('link')
                        ]
                        
                        # Extract variants from product pages (visit up to 5 pages)
                        # NOTE: Colors are excluded - removed per user request
                        if product_urls and browser_agent.page:
                            from app.services.filter_results import extract_variants_from_product_pages
                            
                            # Extract variants from product pages (NO COLORS)
                            page_variants = await extract_variants_from_product_pages(
                                browser_agent, 
                                product_urls, 
                                max_pages=5
                            )
                            
                            # Remove colors from page_variants if present
                            if "colors" in page_variants:
                                del page_variants["colors"]
                            
                            # Merge page variants with name-based filters
                            for key in filter_options:
                                if key in page_variants:
                                    # Combine both sets (remove duplicates)
                                    filter_options[key] = list(set(filter_options[key] + page_variants[key]))
                            
                            # Also add any new keys from page variants (except colors)
                            for key in page_variants:
                                if key != "colors" and key not in filter_options:
                                    filter_options[key] = page_variants[key]
                        
                        # Check if we have multiple variants to offer
                        if filter_options:
                            consolidated_filters = consolidate_filter_options(filter_options)
                            
                            # Debug: Log what filters we found
                            await websocket.send_json({
                                "type": "status",
                                "message": f"Detected filter options: {', '.join([f'{k}: {len(v)}' for k, v in filter_options.items()])}"
                            })
                            
                            # Only ask if there are meaningful filters (at least 1 filter with 2+ options)
                            if consolidated_filters and len(consolidated_filters) > 0:
                                # Store results in session for later filtering
                                from app.api.websocket import manager
                                if session_id not in manager.session_states:
                                    manager.session_states[session_id] = {}
                                
                                manager.session_states[session_id]["extracted_results"] = result["data"]
                                manager.session_states[session_id]["available_filters"] = filter_options
                                manager.session_states[session_id]["original_instruction"] = instruction
                                
                                # Build filter question summary
                                filter_summary = []
                                for f in consolidated_filters[:3]:  # Limit to top 3 most relevant filters
                                    options_str = ', '.join(f['options'][:5])  # Show first 5 options
                                    if len(f['options']) > 5:
                                        options_str += f" (+{len(f['options']) - 5} more)"
                                    filter_summary.append(f"{f['label']}: {options_str}")
                                
                                # Send clarification asking for filter preferences
                                await websocket.send_json({
                                    "type": "filter_options",
                                    "message": f"Found {len(result['data'])} products with multiple options available:",
                                    "filters": consolidated_filters,
                                    "filter_summary": filter_summary,
                                    "question": "Would you like to filter by any specific option? (e.g., '256GB Silver' or 'skip' to see all)",
                                    "context": "product_filter_refinement"
                                })
                                
                                # Store clarification in conversation manager
                                conversation_manager.store_clarification({
                                    "type": "filter_refinement",
                                    "filters": consolidated_filters,
                                    "field": "product_filters",
                                    "context": "product_filter_refinement"
                                }, instruction, session_id)
                                
                                # DON'T return early - let the execution complete first
                                # The user can respond with filter preferences afterward
                            else:
                                await websocket.send_json({
                                    "type": "status",
                                    "message": "No variant options detected (all products are similar)"
                                })
                        else:
                            await websocket.send_json({
                                "type": "status",
                                "message": "No filterable options found in product names"
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

