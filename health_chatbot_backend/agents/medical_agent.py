import logging
from typing import List, Dict
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from models.request_models import ChatRequest
from fastapi import HTTPException

# Import llm from settings
from config.settings import llm, logger
# Import utilities
from utils.conversation_utils import count_questions_asked, update_flow_marker
from models.prompts import MEDICAL_PROMPT
async def handle_diagnosis_flow(request: ChatRequest, question_count: int = None):
    print("Function: handle_diagnosis_flow")
    """Handle diagnosis flow with question counting and transition logic"""
    try:
        if question_count is None:
            question_count = count_questions_asked(request.conversation_history)
        
        conv_history = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in request.conversation_history if msg['role'] != "system"
        )
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                MEDICAL_PROMPT.format(
                    conversation_history=conv_history,
                    language=request.language,
                    question_count=question_count,
                    department = request.department 
                )
            ),
            HumanMessagePromptTemplate.from_template("{user_input}"),
        ])
        
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(user_input=request.user_input)
        # print(response)
        # If we've asked 5 questions and system suggests appointment, prepare for potential flow switch
        if question_count >= 5 and ("appointment" in response.lower() or "book" in response.lower()):
            # Add a subtle hint that flow switching is possible without forcing it
            response += "\n\nYou can also type 'yes' or 'book appointment' if you'd like to schedule a consultation now."
        
        return {"response": response.strip()}
        
    except Exception as e:
        logger.error(f"Diagnosis flow error: {str(e)}")
        raise HTTPException(500, "Diagnosis processing failed")
