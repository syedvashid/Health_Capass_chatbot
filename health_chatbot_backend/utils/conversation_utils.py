import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_current_flow(conversation_history: List[Dict[str, str]]) -> str:
    print("Function: get_current_flow")
    """Extract current flow from conversation history"""
    # Get the most recent flow marker
    for msg in reversed(conversation_history):
        if msg["role"] == "system" and "selected_flow" in msg.get("content", ""):
            return msg["content"].split(":")[1].strip()
    return None

def count_questions_asked(conversation_history: List[Dict[str, str]]) -> int:
    print("Function: count_questions_asked")
    """Count how many medical questions have been asked"""
    question_count = 0
    for msg in conversation_history:
        if msg["role"] == "assistant":
            content = msg.get("content", "").lower()
            # Check if message contains multiple choice options (A., B., C., D.)
            if "a." in content and "b." in content and "c." in content and "d." in content:
                question_count += 1
    return question_count

def get_conversation_context(conversation_history: List[Dict[str, str]]) -> str:
    print("Function: get_conversation_context")
    """Get conversation context for better intent detection"""
    current_flow = get_current_flow(conversation_history)
    question_count = count_questions_asked(conversation_history)
    
    context = f"Current flow: {current_flow or 'none'}, Questions asked: {question_count}"
    
    # Add recent conversation context
    recent_messages = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
    recent_context = " | ".join([
        f"{msg['role']}: {msg['content'][:50]}..." 
        for msg in recent_messages if msg['role'] != 'system'
    ])
    
    return f"{context} | Recent: {recent_context}"

def update_flow_marker(conversation_history: List[Dict[str, str]], new_flow: str):
    print("Function: update_flow_marker")
    """Update flow marker in conversation history"""
    # Remove old flow markers
    conversation_history[:] = [
        msg for msg in conversation_history 
        if not (msg["role"] == "system" and "selected_flow" in msg.get("content", ""))
    ]
    # Add new flow marker
    conversation_history.append({
        "role": "system", 
        "content": f"selected_flow: {new_flow}"
    })
