from fastapi import WebSocket
from app.services.ai_planner import create_action_plan
from app.services.browser_agent import browser_agent
from app.services.filter_results import filter_by_price, get_top_results
import json
import re

async def execute_plan(websocket: WebSocket, instruction: str):
    """Main execution loop: plan -> execute -> stream updates."""
    
    try:
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
                    
                elif action_type == "click":
                    selector = action.get("selector")
                    result = await browser_agent.click(selector)
                    
                elif action_type == "type":
                    selector = action.get("selector")
                    text = action.get("text")
                    result = await browser_agent.type_text(selector, text)
                    
                elif action_type == "wait_for":
                    selector = action.get("selector")
                    timeout = action.get("timeout", 5000)
                    result = await browser_agent.wait_for(selector, timeout)
                    
                elif action_type == "extract":
                    schema = action.get("schema", {})
                    limit = action.get("limit", None)
                    result = await browser_agent.extract(schema, limit)
                    
                    # Log extraction result for debugging
                    print(f"Extraction result: status={result.get('status')}, count={result.get('count')}, data_length={len(result.get('data', []))}")
                    if result.get("data"):
                        print(f"First item sample: {result.get('data')[0] if result.get('data') else 'None'}")
                    
                    # Post-process extracted data: filter by price if needed
                    if result.get("status") == "success" and result.get("data"):
                        extracted_data = result["data"]
                        
                        # Check if instruction has price filter
                        # Extract price from original instruction if available
                        max_price = None
                        instruction_lower = instruction.lower()
                        if "under" in instruction_lower or "below" in instruction_lower:
                            # Look for price pattern after "under" or "below"
                            # Match: "under ₹1,00,000" or "under 100000" or "below ₹50,000"
                            price_patterns = [
                                r'(?:under|below)\s*[₹$]?\s*([\d,]+)',  # After "under" or "below"
                                r'[₹$]\s*([\d,]+)',  # Direct currency symbol
                            ]
                            for pattern in price_patterns:
                                price_match = re.search(pattern, instruction, re.IGNORECASE)
                                if price_match:
                                    price_str = price_match.group(1).replace(',', '')
                                    try:
                                        max_price = float(price_str)
                                        # Validate it's a reasonable price (not just "13" from "13-inch")
                                        if max_price > 100:  # Minimum reasonable price
                                            break
                                        else:
                                            max_price = None
                                    except:
                                        pass
                        
                        if max_price:
                            filtered = filter_by_price(extracted_data, max_price=max_price)
                            if filtered:
                                # Get top results by rating
                                top_results = get_top_results(filtered, limit or 3)
                                result["data"] = top_results
                                result["count"] = len(top_results)
                                result["filtered"] = True
                                result["max_price"] = max_price
                            else:
                                result["data"] = []
                                result["count"] = 0
                                result["message"] = f"No products found under ₹{max_price:,.0f}"
                        else:
                            # Just get top results by rating
                            top_results = get_top_results(extracted_data, limit or 3)
                            result["data"] = top_results
                            result["count"] = len(top_results)
                    
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
                    
                    # For selector errors, try to continue with next action
                    # For other errors, stop execution
                    if "selector" not in error_msg.lower() and "timeout" not in error_msg.lower():
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

