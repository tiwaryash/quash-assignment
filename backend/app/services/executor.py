from fastapi import WebSocket
from app.services.ai_planner import create_action_plan
from app.services.browser_agent import browser_agent
import json

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
                    
                else:
                    result = {
                        "status": "error",
                        "error": f"Unknown action type: {action_type}"
                    }
                
                # Send result
                await websocket.send_json({
                    "type": "action_status",
                    "action": action_type,
                    "status": "completed" if result.get("status") == "success" else "error",
                    "step": idx + 1,
                    "total": len(plan),
                    "result": result
                })
                
                # If error, stop execution
                if result.get("status") == "error":
                    await websocket.send_json({
                        "type": "error",
                        "message": result.get("error", "Action failed"),
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
        # Cleanup
        try:
            await browser_agent.close()
        except:
            pass
        
        await websocket.send_json({
            "type": "status",
            "message": "Execution completed"
        })

