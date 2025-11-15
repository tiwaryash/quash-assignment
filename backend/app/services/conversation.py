"""Conversation layer for handling clarifications and multi-turn conversations."""

from typing import Optional, Dict, Any
from app.services.intent_classifier import classify_intent, classify_intent_llm

class ConversationManager:
    """Manages conversation state and clarification questions."""
    
    def __init__(self):
        self.pending_clarifications: Dict[str, Dict] = {}
        self.conversation_context: Dict[str, Any] = {}
        self.conversation_history: Dict[str, list] = {}  # Track conversation turns per session
        self.user_preferences: Dict[str, Dict] = {}  # Remember user preferences across tasks
    
    async def needs_clarification(self, instruction: str, session_id: str = "default") -> Optional[Dict]:
        """
        Check if the instruction needs clarification.
        Returns a clarification question dict if needed, None otherwise.
        Uses LLM-based intent classification for better accuracy.
        """
        # Use LLM-based classification for better accuracy
        try:
            intent_info = await classify_intent_llm(instruction)
        except Exception as e:
            # Fallback to rule-based if LLM fails
            from app.core.logger import logger
            logger.warning(f"LLM classification failed, using rule-based: {e}")
            intent_info = classify_intent(instruction)
        
        # Use the needs_clarification flag from intent classifier
        if intent_info.get("needs_clarification"):
            
            # For local discovery without site specification
            if intent_info["intent"] == "local_discovery" and not intent_info["sites"]:
                # Extract location if mentioned
                location = "your area"
                instruction_lower = instruction.lower()
                if " in " in instruction_lower:
                    parts = instruction_lower.split(" in ")
                    if len(parts) > 1:
                        location = parts[-1].strip().split()[0]  # Get first word after "in"
                
                return {
                    "type": "clarification",
                    "question": f"Which platform would you like to use to find places in {location}?",
                    "options": [
                        {"value": "google_maps", "label": "Google Maps (most reliable, comprehensive results)"},
                        {"value": "zomato", "label": "Zomato (restaurants, ratings, reviews)"},
                        {"value": "swiggy", "label": "Swiggy (food delivery, restaurant listings)"}
                    ],
                    "field": "site",
                    "context": "local_discovery"
                }
            
            # For product search without site
            elif intent_info["intent"] == "product_search" and not intent_info["sites"]:
                # Check if comparison was requested
                if intent_info.get("comparison"):
                    return {
                        "type": "clarification",
                        "question": "Which e-commerce sites would you like to compare?",
                        "options": [
                            {"value": "flipkart,amazon", "label": "Both Flipkart and Amazon"},
                            {"value": "flipkart", "label": "Flipkart only"},
                            {"value": "amazon", "label": "Amazon only"}
                        ],
                        "field": "sites",
                        "context": "product_search_comparison"
                    }
                else:
                    return {
                        "type": "clarification",
                        "question": "Which e-commerce platform would you like to search on?",
                        "options": [
                            {"value": "flipkart", "label": "Flipkart (Indian marketplace)"},
                            {"value": "amazon", "label": "Amazon (global marketplace)"},
                            {"value": "both", "label": "Search both and compare"}
                        ],
                        "field": "site",
                        "context": "product_search"
                    }
            
            # For comparison with only one site specified
            elif intent_info.get("comparison") and len(intent_info["sites"]) < 2:
                current_site = intent_info["sites"][0] if intent_info["sites"] else "flipkart"
                other_options = []
                if current_site != "flipkart":
                    other_options.append({"value": "flipkart", "label": "Flipkart"})
                if current_site != "amazon":
                    other_options.append({"value": "amazon", "label": "Amazon"})
                
                return {
                    "type": "clarification",
                    "question": f"You want to compare products. You mentioned {current_site}. Which other site would you like to compare with?",
                    "options": other_options + [{"value": "skip", "label": "Just search on " + current_site}],
                    "field": "additional_site",
                    "context": "product_search_comparison"
                }
        
        # For ambiguous queries, ask for more details
        if intent_info["intent"] == "general":
            # Check if it's too vague
            if len(instruction.split()) < 3:
                return {
                    "type": "clarification",
                    "question": "Could you provide more details about what you'd like me to do?",
                    "options": [
                        {"value": "search", "label": "Search for products or information"},
                        {"value": "local", "label": "Find local places (restaurants, services)"},
                        {"value": "form", "label": "Fill out a form or sign up"},
                        {"value": "navigate", "label": "Navigate to a website and extract data"}
                    ],
                    "field": "task_type",
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
        context = clarification.get("context", "")
        field = clarification.get("field", "")
        
        # Update instruction based on clarification response
        response_lower = response.lower().strip()
        
        # Handle local discovery site selection
        if context == "local_discovery" or (field == "site" and "local" in context):
            if response_lower == "google_maps":
                updated_instruction = f"{original_instruction} on google maps"
            elif response_lower in ["zomato", "swiggy"]:
                updated_instruction = f"{original_instruction} on {response_lower}"
            elif "google" in response_lower or "maps" in response_lower:
                updated_instruction = f"{original_instruction} on google maps"
            else:
                # Fallback - try to extract from options
                for opt in clarification.get("options", []):
                    if opt["value"] in response_lower:
                        site = opt["value"]
                        if site == "google":
                            site = "google_maps"
                        updated_instruction = f"{original_instruction} on {site}"
                        break
                else:
                    updated_instruction = original_instruction
            
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        # Handle product search site selection
        elif context == "product_search" or (field == "site" and "product" in context):
            if "both" in response_lower or ("flipkart" in response_lower and "amazon" in response_lower):
                updated_instruction = f"Compare {original_instruction} on both Flipkart and Amazon"
            elif "flipkart" in response_lower:
                updated_instruction = f"{original_instruction} on Flipkart"
            elif "amazon" in response_lower:
                updated_instruction = f"{original_instruction} on Amazon"
            else:
                updated_instruction = original_instruction
            
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        # Handle comparison clarifications
        elif context == "product_search_comparison" or field == "sites":
            # Handle comma-separated sites (e.g., "flipkart,amazon")
            if "," in response_lower:
                sites = [s.strip() for s in response_lower.split(",")]
                updated_instruction = f"Compare {original_instruction} on {' and '.join(sites)}"
            elif "both" in response_lower:
                updated_instruction = f"Compare {original_instruction} on Flipkart and Amazon"
            elif "flipkart" in response_lower and "amazon" in response_lower:
                updated_instruction = f"Compare {original_instruction} on Flipkart and Amazon"
            elif "skip" in response_lower:
                # User wants to skip comparison
                updated_instruction = original_instruction
            else:
                # Single site selected
                updated_instruction = f"{original_instruction} on {response_lower}"
            
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        # Handle additional site for comparison
        elif field == "additional_site":
            current_sites = clarification.get("current_sites", [])
            if "skip" in response_lower:
                # Don't add comparison
                updated_instruction = original_instruction
            else:
                additional_site = response_lower
                if current_sites:
                    updated_instruction = f"Compare {original_instruction} on {' and '.join(current_sites + [additional_site])}"
                else:
                    updated_instruction = f"{original_instruction} on {additional_site}"
            
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        # Handle general task type selection
        elif field == "task_type":
            if "search" in response_lower:
                updated_instruction = f"Search for {original_instruction}"
            elif "local" in response_lower:
                updated_instruction = f"Find local places for {original_instruction}"
            elif "form" in response_lower:
                updated_instruction = f"Fill out form: {original_instruction}"
            elif "navigate" in response_lower:
                updated_instruction = f"Navigate to {original_instruction} and extract data"
            else:
                updated_instruction = response  # User's free-form response
            
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        elif field == "details":
            # User provided more details, combine with original
            updated_instruction = f"{original_instruction}. {response}"
            return {
                "updated_instruction": updated_instruction,
                "clarification_resolved": True
            }
        
        # Handle filter refinement responses
        elif field == "product_filters" or context == "product_filter_refinement":
            # User is selecting filter options
            # Response could be JSON with filter selections, e.g. {"storage": "256GB", "color": "Black"}
            import json
            try:
                # Try to parse as JSON
                filter_selections = json.loads(response)
                return {
                    "filter_selections": filter_selections,
                    "clarification_resolved": True,
                    "apply_filters": True
                }
            except:
                # If not JSON, try to parse as natural language
                # e.g., "256GB black" or "black 256GB"
                response_lower = response.lower()
                filter_selections = {}
                
                # Check against available filters in clarification
                available_filters = clarification.get("filters", [])
                for filter_def in available_filters:
                    field_name = filter_def.get("field")
                    options = filter_def.get("options", [])
                    
                    # Check if any option is mentioned in response
                    # Try exact match first, then partial match
                    for option in options:
                        option_lower = option.lower()
                        # Exact match
                        if option_lower == response_lower or option_lower in response_lower:
                            filter_selections[field_name] = option
                            break
                        # Partial match (e.g., "silver" matches "space gray silver")
                        elif option_lower in response_lower or response_lower in option_lower:
                            filter_selections[field_name] = option
                            break
                    
                    # Also check for multi-word colors (e.g., "space gray" in "256GB space gray")
                    if field_name == "colors" and not filter_selections.get(field_name):
                        for option in options:
                            option_words = option.lower().split()
                            if len(option_words) > 1:
                                # Check if all words of the color are in response
                                if all(word in response_lower for word in option_words):
                                    filter_selections[field_name] = option
                                    break
                
                return {
                    "filter_selections": filter_selections,
                    "clarification_resolved": True,
                    "apply_filters": True
                }
        
        # Default: just use response if meaningful, else append to original
        if len(response.split()) > 2:
            updated_instruction = f"{original_instruction}. {response}"
        else:
            # Short response, likely a site name or keyword
            updated_instruction = f"{original_instruction} {response}"
        
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
    
    def add_to_history(self, session_id: str, role: str, content: str, metadata: Dict = None):
        """Add a turn to conversation history."""
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
        
        self.conversation_history[session_id].append({
            "role": role,  # "user" or "assistant"
            "content": content,
            "metadata": metadata or {},
            "timestamp": __import__('time').time()
        })
        
        # Keep only last 10 turns to avoid memory bloat
        if len(self.conversation_history[session_id]) > 10:
            self.conversation_history[session_id] = self.conversation_history[session_id][-10:]
    
    def get_history(self, session_id: str, limit: int = 5) -> list:
        """Get recent conversation history."""
        if session_id not in self.conversation_history:
            return []
        return self.conversation_history[session_id][-limit:]
    
    def remember_preference(self, session_id: str, preference_type: str, value: Any):
        """Remember a user preference (e.g., preferred site, preferred filters)."""
        if session_id not in self.user_preferences:
            self.user_preferences[session_id] = {}
        
        self.user_preferences[session_id][preference_type] = value
    
    def get_preference(self, session_id: str, preference_type: str) -> Optional[Any]:
        """Get a remembered user preference."""
        if session_id not in self.user_preferences:
            return None
        return self.user_preferences[session_id].get(preference_type)
    
    async def apply_learned_preferences(self, instruction: str, session_id: str) -> str:
        """Apply learned preferences to make instruction more specific."""
        if session_id not in self.user_preferences:
            return instruction
        
        prefs = self.user_preferences[session_id]
        instruction_lower = instruction.lower()
        
        # Apply preferred site if not specified in instruction
        preferred_site = prefs.get("preferred_site")
        if preferred_site:
            # Check if instruction is about e-commerce or local discovery
            try:
                intent = await classify_intent_llm(instruction)
            except Exception:
                intent = classify_intent(instruction)
            
            # Only apply if no site mentioned
            has_site = any(site in instruction_lower for site in [
                "flipkart", "amazon", "zomato", "swiggy", "google maps"
            ])
            
            if not has_site:
                if intent["intent"] == "product_search" and preferred_site in ["flipkart", "amazon"]:
                    instruction = f"{instruction} on {preferred_site}"
                elif intent["intent"] == "local_discovery" and preferred_site in ["zomato", "swiggy", "google_maps"]:
                    instruction = f"{instruction} on {preferred_site}"
        
        return instruction
    
    def clear_session(self, session_id: str):
        """Clear all data for a session."""
        if session_id in self.pending_clarifications:
            del self.pending_clarifications[session_id]
        if session_id in self.conversation_context:
            del self.conversation_context[session_id]
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
        # Don't clear preferences - they persist across sessions

# Global instance
conversation_manager = ConversationManager()

