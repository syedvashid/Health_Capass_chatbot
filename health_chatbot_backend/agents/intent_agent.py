import logging
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain

# Import llm from settings
from config.settings import llm, logger
# Import utilities
from utils.conversation_utils import get_conversation_context
from models.prompts import INTENT_DETECTION_PROMPT

async def detect_user_intent(user_input: str, language: str, context: str = "") -> str:
    print("Function: detect_user_intent")
    """Intelligently detect user's intent including flow switching"""
    try:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                INTENT_DETECTION_PROMPT.format(
                    user_input=user_input, 
                    language=language,
                    context=context
                )
            )
        ])
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(input="")
        
        # Extract intent from response
        intent = response.strip().upper()
        valid_intents = ["DIAGNOSIS", "APPOINTMENT", "SWITCH_TO_APPOINTMENT", "SWITCH_TO_DIAGNOSIS", "UNCLEAR"]
        if intent in valid_intents:
            return intent
        else:
            return "UNCLEAR"
            
    except Exception as e:
        logger.error(f"Intent detection error: {str(e)}")
        return "UNCLEAR"

async def generate_clarification(user_input: str, language: str) -> str:
    print("Function: generate_clarification")
    """Generate clarification message when intent is unclear"""
    clarification_prompt = f"""The user said: "{user_input}"

Generate a friendly clarification message in {language} asking whether they want:
1. Medical diagnosis/health questions
2. Appointment booking with doctors

Keep it conversational and helpful."""
    
    try:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(clarification_prompt)
        ])
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(input="")
        return response.strip()
    except Exception as e:
        logger.error(f"Clarification generation error: {str(e)}")
        return "I'd be happy to help! Could you let me know if you need help with medical diagnosis questions or booking an appointment with a doctor?"
