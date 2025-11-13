from fastapi import WebSocket, WebSocketDisconnect
from app.services.executor import execute_plan
from app.services.conversation import conversation_manager
import json
import uuid


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.session_states: dict[str, dict] = {}  # Track session state

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.session_states[session_id] = {
            "waiting_for_clarification": False,
            "pending_alternative": None
        }

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.session_states:
            del self.session_states[session_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

manager = ConnectionManager()

async def websocket_endpoint(websocket: WebSocket):
    # Generate a session ID for this connection
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                instruction = message.get("instruction", data)
                is_clarification = message.get("is_clarification", False)
                clarification_type = message.get("clarification_type")
                
                # Check if this is a response to a clarification
                if is_clarification or clarification_type:
                    # Handle alternative selection for Google blocking or Zomato blocking
                    if clarification_type == "google_blocked" or clarification_type == "zomato_blocked" or clarification_type == "alternative":
                        alternative = message.get("value") or instruction.lower()
                        session_state = manager.session_states.get(session_id, {})
                        
                        if alternative in ["zomato", "swiggy", "google_maps"]:
                            # Remember preference for future tasks
                            conversation_manager.remember_preference(session_id, "preferred_site", alternative)
                            
                            # Update instruction to use alternative site
                            original_instruction = session_state.get("original_instruction", "find pizza places")
                            if "pizza" in original_instruction.lower() or "restaurant" in original_instruction.lower():
                                updated_instruction = f"Find top pizza places on {alternative} with ratings"
                            else:
                                updated_instruction = f"{original_instruction} on {alternative}"
                            
                            await websocket.send_json({
                                "type": "status",
                                "message": f"Switching to {alternative.capitalize()}... (I'll remember this preference)"
                            })
                            
                            # Execute with updated instruction
                            await execute_plan(websocket, updated_instruction, session_id, False)
                            session_state["waiting_for_clarification"] = False
                            session_state["pending_alternative"] = None
                            continue
                        elif alternative == "google_maps":
                            # Switch to Google Maps
                            original_instruction = session_state.get("original_instruction", "find pizza places")
                            # Update instruction to use Google Maps
                            updated_instruction = f"{original_instruction} on google maps"
                            
                            await websocket.send_json({
                                "type": "status",
                                "message": "Switching to Google Maps..."
                            })
                            
                            # Execute with updated instruction
                            await execute_plan(websocket, updated_instruction, session_id, False)
                            session_state["waiting_for_clarification"] = False
                            continue
                        elif alternative == "cancel":
                            await websocket.send_json({
                                "type": "status",
                                "message": "Task cancelled."
                            })
                            session_state["waiting_for_clarification"] = False
                            continue
                        elif alternative == "retry":
                            # Retry with original instruction
                            original_instruction = session_state.get("original_instruction", instruction)
                            await execute_plan(websocket, original_instruction, session_id, False)
                            session_state["waiting_for_clarification"] = False
                            continue
                    
                    # Regular clarification response - need to get original instruction
                    # The instruction here is just the response (e.g., "zomato"), not the full instruction
                    session_state = manager.session_states.get(session_id, {})
                    original_instruction = session_state.get("original_instruction", instruction)
                    
                    # Check if this is a site selection (for local discovery or product search)
                    response_lower = instruction.lower().strip()
                    if response_lower in ["zomato", "swiggy", "google", "google_maps", "flipkart", "amazon", "both"] or clarification_type in ["site_selection", "local_discovery", "product_search"]:
                        # Remember the site preference
                        if response_lower in ["zomato", "swiggy", "google_maps"]:
                            conversation_manager.remember_preference(session_id, "preferred_site", response_lower)
                        elif response_lower in ["flipkart", "amazon"]:
                            conversation_manager.remember_preference(session_id, "preferred_site", response_lower)
                        
                        # This is a site selection response
                        if original_instruction and original_instruction != instruction:
                            # We have the original instruction, use it
                            if response_lower == "google_maps":
                                updated_instruction = f"{original_instruction} on google maps"
                            else:
                                updated_instruction = f"{original_instruction} on {response_lower}"
                        else:
                            # Fallback: construct from response
                            updated_instruction = f"Find best pizza places in HSR on {response_lower}"
                        
                        site_display = "Google Maps" if response_lower == "google_maps" else response_lower.capitalize()
                        await websocket.send_json({
                            "type": "status",
                            "message": f"Using {site_display}... (I'll remember this preference for next time)"
                        })
                        # Don't overwrite original_instruction - keep it for reference
                        # The updated instruction will be passed to execute_plan
                        await execute_plan(websocket, updated_instruction, session_id, False)
                    else:
                        # Regular clarification response
                        await execute_plan(websocket, instruction, session_id, True)
                else:
                    # Store original instruction for potential retry
                    manager.session_states[session_id]["original_instruction"] = instruction
                    # Execute the plan
                    await execute_plan(websocket, instruction, session_id, False)
                    
            except json.JSONDecodeError:
                # If not JSON, treat as plain text instruction
                manager.session_states[session_id]["original_instruction"] = data
                await execute_plan(websocket, data, session_id, False)
                
    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"Server error: {str(e)}"
        })
        manager.disconnect(session_id)
