import time
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, List
import re
from models.database import add_answer, add_chat_history, close_db, connect_db,options_collection
from utils.conversation_utils import count_questions_asked

# Import settings (including llm and logger)
from config.settings import llm, logger

# Import Pydantic models
from models.request_models import (
    ChatRequest, HistoryRequest, OfflineReportRequest,
    LocationRequest, DoctorSelectionRequest, SlotBookingRequest
)

# Import agent functions
from agents.greeting_agent import generate_greeting
from agents.intent_agent import detect_user_intent, generate_clarification
from agents.medical_agent import handle_diagnosis_flow
from agents.appointment_agent import handle_enhanced_appointment_flow_with_confirmation,suggest_department # Renamed for clarity in main.py, was suggest_department_func

# Import service functions
from services.report_service import generate_report, generate_offline_report
from utils.conversation_utils import get_current_flow, update_flow_marker, get_conversation_context
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Health Chatbot API!"}

@app.on_event("startup")
async def startup_db_client():
    await connect_db()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_db()


@app.post("/chat")
async def chat(request: ChatRequest):
    print("Function: chat")
    try:
        # <<< MODIFIED: Handle chat history creation and answer storage
        chat_history_id = request.chat_history_id
        user_input_upper = request.user_input.strip().upper()

        # 1. If no chat_history_id, this is a new chat. Create a record.
        if not chat_history_id:
            # Generate a unique ID like in the old code
            patient_id = f"{request.name}_{request.age}_{int(time.time())}"
            chat_history_id = await add_chat_history({
                "_id": patient_id,
                "reason_for_visit": request.department,
                "language": request.language,
                "patient_name": request.name,
                "age": request.age,
                "gender": request.gender
            })
            request.chat_history_id = chat_history_id
            logger.info(f"New chat history created with ID: {chat_history_id}")
        
        # 2. Check if the user is providing an answer to a previous question
        if request.last_question_id and user_input_upper in ['A', 'B', 'C', 'D']:
            option = await options_collection.find_one({
                "question_id": ObjectId(request.last_question_id),
                "option_no": user_input_upper
            })
            if option:
                await add_answer({
                    "question_id": ObjectId(request.last_question_id),
                    "answer_id": option["_id"]
                })
                logger.info(f"Answer '{user_input_upper}' stored for question {request.last_question_id}")
            else:
                logger.warning(f"Could not find option '{user_input_upper}' for question {request.last_question_id}")


        # 3. Handle initial greeting
        if not request.conversation_history:
            greeting_response = await generate_greeting(request.language)
            # Return chat_history_id with the first response
            return {"response": greeting_response, "chat_history_id": chat_history_id}

        # 4. Agentic logic (intent detection and flow handling)
        current_flow = get_current_flow(request.conversation_history)
        question_count = count_questions_asked(request.conversation_history)
        conv_context = get_conversation_context(request.conversation_history)
        intent = await detect_user_intent(request.user_input, request.language, conv_context)
        print(f"Detected intent: {intent}")

        # --- The rest of your agentic flow logic remains the same ---
        # Note: The agent calls will now return a dict with more data
        
        if intent == "SWITCH_TO_APPOINTMENT":
            update_flow_marker(request.conversation_history, "appointment")
            return await handle_enhanced_appointment_flow_with_confirmation(request) # Modify this agent if it needs to return IDs

        if current_flow == "diagnosis" or intent == "DIAGNOSIS":
            if question_count >= 5 and intent == "APPOINTMENT":
                update_flow_marker(request.conversation_history, "appointment")
                return await handle_enhanced_appointment_flow_with_confirmation(request)
            else:
                # This call now returns the full payload
                return await handle_diagnosis_flow(request, question_count)

        elif current_flow == "appointment" or intent == "APPOINTMENT":
             return await handle_enhanced_appointment_flow_with_confirmation(request)
        
        else:  # UNCLEAR intent
            clarification_response = await generate_clarification(request.user_input, request.language)
            return {"response": clarification_response, "chat_history_id": chat_history_id}

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(500, "Chat processing failed")

@app.post("/suggest_department")
async def suggest_department_endpoint(request: HistoryRequest):
    logger.info(f"Received /suggest_department request for language: {request.language}")
    suggested_dept = await suggest_department(request.conversation_history, request.language)
    return {"suggested_department": suggested_dept}

@app.post("/generate_report")
async def generate_consultation_report(request: HistoryRequest):
    logger.info("Received /generate_report request")
    # For report generation, you might need to infer department or pass it from client if available
    # For now, let's pass a placeholder or try to infer from history if possible within generate_report func.
    # The current `generate_report` function expects 'department' as an arg, so passing 'N/A' or inferring from history if available.
    # In a real app, you might have a dedicated step to confirm this.
    inferred_department = "N/A" # Placeholder, update if you have logic to infer from history
    for msg in reversed(request.conversation_history):
        if "department" in msg.get("content", "").lower():
            match = re.search(r"department:\s*([a-zA-Z\s]+)", msg["content"], re.IGNORECASE)
            if match:
                inferred_department = match.group(1).strip()
                break

    return await generate_report(
        name=request.name,
        gender=request.gender,
        age=request.age,
        language=request.language,
        conversation_history=request.conversation_history,
        department=inferred_department
    )

@app.post("/generate_offline_report")
async def generate_offline_report_endpoint(request: OfflineReportRequest):
    logger.info("Received /generate_offline_report request")
    return await generate_offline_report(
        name=request.name,
        age=request.age,
        gender=request.gender,
        department=request.department,
        language=request.language,
        responses=request.responses
    )