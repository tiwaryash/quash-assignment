"""Conversation layer for handling clarifications and multi-turn conversations."""

from typing import Optional, Dict, Any
from app.services.intent_classifier import classify_intent

class ConversationManager:
    """Manages conversation state and clarification questions."""
    
    def __init__(self):
        self.pending_clarifications: Dict[str, Dict] = {}
        self.conversation_context: Dict[str, Any] = {}
    
    def needs_clarification(self, instruction: str, session_id: str = "default") -> Optional[Dict]:
        """
        Check if the instruction needs clarification.
        Returns a clarification question dict if needed, None otherwise.
        """
        intent_info = classify_intent(instruction)
        
        # For local discovery without site specification, ask which site
        if intent_info["intent"] == "local_discovery":
            if not any(site in instruction.lower() for site in ["zomato", "swiggy", "google", "maps"]):
                return {
                    "type": "clarification",
                    "question": "Which platform would you like to use for local discovery?",
                    "options": [
                        {"value": "zomato", "label": "Zomato (restaurants, ratings, delivery)"},
                        {"value": "swiggy", "label": "Swiggy (food delivery, restaurants)"},
                        {"value": "google", "label": "Google Search (may be blocked)"}
                    ],
                    "field": "site",
                    "context": "local_discovery"
                }
        
        # For product search without site, ask if they want comparison
        if intent_info["intent"] == "product_search":
            if not intent_info["sites"] or len(intent_info["sites"]) == 0:
                # Already handled by intent_classifier default, but we can still ask
                pass
            elif intent_info["comparison"] and len(intent_info["sites"]) < 2:
                return {
                    "type": "clarification",
                    "question": "You mentioned comparing products. Which sites would you like to compare?",
                    "options": [
                        {"value": "flipkart", "label": "Flipkart"},
                        {"value": "amazon", "label": "Amazon"},
                        {"value": "both", "label": "Both Flipkart and Amazon"}
                    ],
                    "field": "sites",
                    "context": "product_search"
                }
        
        # For ambiguous queries, ask for more details
        if intent_info["intent"] == "general":
            # Check if it's too vague
            if len(instruction.split()) < 3:
                return {
                    "type": "clarification",
                    "question": "Could you provide more details about what you'd like me to do?",
                    "options": None,
                    "field": "details",
                    "context": "general"
                }
        
        return None
    
    def process_clarification_response(self, response: str, session_id: str = "default") -> Dict:
        """
        Process a user's response to a clarification question.
        Returns updated instruction with clarification context.
        """
        if session_id not in self.pending_clarifications:
            # If no pending clarification, might be a direct response (e.g., from blocked state)
            # Return as-is for websocket handler to process
            return {
                "updated_instruction": response,
                "clarification_resolved": True
            }
        
        clarification = self.pending_clarifications[session_id]
        original_instruction = clarification.get("original_instruction", "")
        
        # Update instruction based on clarification response
        response_lower = response.lower().strip()
        
        if clarification["field"] == "site" or clarification.get("context") == "local_discovery":
            if response_lower in ["zomato", "swiggy", "google"]:
                # Add site to instruction
                updated_instruction = f"{original_instruction} on {response_lower}"
                return {
                    "updated_instruction": updated_instruction,
                    "clarification_resolved": True
                }
            elif any(opt["value"] in response_lower for opt in clarification.get("options", [])):
                # Extract site from response
                for opt in clarification.get("options", []):
                    if opt["value"] in response_lower:
                        updated_instruction = f"{original_instruction} on {opt['value']}"
                        return {
                            "updated_instruction": updated_instruction,
                            "clarification_resolved": True
                        }
        
        elif clarification["field"] == "sites":
            if "both" in response_lower or "flipkart" in response_lower and "amazon" in response_lower:
                updated_instruction = f"{original_instruction} (compare on Flipkart and Amazon)"
            elif "flipkart" in response_lower:
                updated_instruction = f"{original_instruction} (on Flipkart)"
            elif "amazon" in response_lower:
                updated_instruction = f"{original_instruction} (on Amazon)"
            else:
                updated_instruction = original_instruction
            
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        elif clarification["field"] == "details":
            # User provided more details, combine with original
            updated_instruction = f"{original_instruction}. {response}"
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        # Default: just append response
        updated_instruction = f"{original_instruction}. {response}"
        return {
            "updated_instruction": updated_instruction,
            "clarification_resolved": True
        }
    
    def store_clarification(self, clarification: Dict, original_instruction: str, session_id: str = "default"):
        """Store a pending clarification."""
        self.pending_clarifications[session_id] = {
            **clarification,
            "original_instruction": original_instruction
        }
    
    def clear_clarification(self, session_id: str = "default"):
        """Clear a pending clarification."""
        if session_id in self.pending_clarifications:
            del self.pending_clarifications[session_id]

# Global instance
conversation_manager = ConversationManager()

