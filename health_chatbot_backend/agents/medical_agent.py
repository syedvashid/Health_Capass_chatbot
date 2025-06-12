import logging
from typing import List, Dict
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from models.database import add_option, add_question
from models.request_models import ChatRequest
from fastapi import HTTPException

# Import llm from settings
from config.settings import llm, logger
# Import utilities
from utils.conversation_utils import count_questions_asked, update_flow_marker
from models.prompts import MEDICAL_PROMPT




# <<< MODIFIED: Function signature and logic to save to DB
async def handle_diagnosis_flow(request: ChatRequest, question_count: int = None):
    print("Function: handle_diagnosis_flow")
    """Handle diagnosis flow, save question/options to DB, and return IDs."""
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
                    department=request.department
                )
            ),
            HumanMessagePromptTemplate.from_template("{user_input}"),
        ])

        chain = LLMChain(llm=llm, prompt=prompt)
        llm_response = await chain.arun(user_input=request.user_input)

        # <<< MODIFIED: Parse response and save to database
        response_lines = llm_response.strip().split('\n')
        question_text = ""
        options = []
        for line in response_lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith(('A.', 'B.', 'C.', 'D.')):
                parts = line.split('(', 1)
                option_text = parts[0].split('.', 1)[1].strip()
                ehr_terminology = parts[1][:-1].strip() if len(parts) > 1 else ""
                options.append({
                    "option_no": line[0],
                    "option_text": option_text,
                    "ehr_terminology": ehr_terminology
                })
            else:
                question_text += line + " "

        question_text = question_text.strip()
        current_question_id = None
        if question_text and len(options) == 4:
            question_data = {
                "chat_history_id": request.chat_history_id,
                "question_no": question_count + 1,
                "question_text": question_text
            }
            current_question_id = await add_question(question_data)
            logger.info(f"Question stored with ID: {current_question_id} for chat {request.chat_history_id}")

            for option in options:
                await add_option({
                    "question_id": current_question_id,
                    "option_no": option["option_no"],
                    "option_text": option["option_text"],
                    "ehr_terminology": option["ehr_terminology"]
                })
            logger.info(f"Stored {len(options)} options for question {current_question_id}")

            return {
                "response": llm_response.strip(),
                "chat_history_id": request.chat_history_id,
                "question_id": str(current_question_id)
            }
        else:
            logger.warning(f"Failed to parse question and options from LLM response: {llm_response}")
            # Fallback to returning raw response if parsing fails
            return {"response": llm_response.strip(), "chat_history_id": request.chat_history_id}

    except Exception as e:
        logger.error(f"Diagnosis flow error: {str(e)}")
        raise HTTPException(500, "Diagnosis processing failed")
