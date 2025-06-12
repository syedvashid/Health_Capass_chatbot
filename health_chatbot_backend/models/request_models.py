from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    user_input: str
    conversation_history: List[Dict[str, str]] = []
    language: str
    department: str
    name: str
    gender: str
    age: int
    chat_history_id: Optional[str] = None  # To track the chat session
    last_question_id: Optional[str] = None # To link an answer to the last question


class HistoryRequest(BaseModel):
    name: str
    gender: str
    age: int
    language: str
    conversation_history: List[Dict[str, str]]

class OfflineReportRequest(BaseModel):
    name: str
    age: int
    gender: str
    department: str
    language: str
    responses: List[Dict]

class LocationRequest(BaseModel):
    city: str = None
    department: str = None
    doctor_name: str = None
    language: str

class DoctorSelectionRequest(BaseModel):
    user_input: str
    conversation_history: List[Dict[str, str]]
    language: str
    selected_doctor_id: int = None

class SlotBookingRequest(BaseModel):
    user_input: str
    conversation_history: List[Dict[str, str]]
    language: str
    doctor_id: int
    selected_date: str = None
    selected_time: str = None