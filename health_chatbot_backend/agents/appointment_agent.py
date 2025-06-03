import logging
import re
from typing import List, Dict, Any
import json
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate, PromptTemplate
from langchain.chains import LLMChain
from fastapi import HTTPException

# Import llm from settings
from config.settings import llm, logger
# Import utilities
from utils.conversation_utils import update_flow_marker, get_current_flow
# Import database service functions
from services.database_service import location_based_doctor_search, get_doctor_by_id, get_doctor_available_slots
from models.request_models import ChatRequest,HistoryRequest
# Agentic System Prompts for Appointment Flow
from models.prompts import (
    LOCATION_COLLECTION_PROMPT, ENHANCED_DOCTOR_DISPLAY_PROMPT,DEPARTMENT_PROMPT ,DOCTOR_SELECTION_PROMPT,SLOT_AVAILABILITY_PROMPT
)

def extract_user_preferences(user_input: str) -> dict:
    """Extract city, department, or doctor name from user input"""
    print("Function: extract_user_preferences")
    
    user_input_lower = user_input.lower()
    preferences = {"city": None, "department": None, "doctor_name": None}
    
    # Extract city
    cities = ["kanpur", "orai", "jhansi"]
    for city in cities:
        if city in user_input_lower:
            preferences["city"] = city.title()
            break
    
    # Extract department
    dept_mapping = {
        "heart": "Cardiologist", "cardio": "Cardiologist", "cardiologist": "Cardiologist",
        "child": "Pediatrician", "pediatric": "Pediatrician", "pediatrician": "Pediatrician",
        "bone": "Orthopedic", "orthopedic": "Orthopedic", "ortho": "Orthopedic",
        "skin": "Dermatologist", "dermatologist": "Dermatologist",
        "ear": "ENT Specialist", "nose": "ENT Specialist", "throat": "ENT Specialist", "ent": "ENT Specialist",
        "brain": "Neurologist", "neurologist": "Neurologist", "neuro": "Neurologist",
        "mental": "Psychiatrist", "psychiatrist": "Psychiatrist", "psychology": "Psychiatrist",
        "teeth": "Dentist", "dental": "Dentist", "dentist": "Dentist",
        "general": "General Physician", "physician": "General Physician", "family": "General Physician",
        "women": "Gynecologist", "gynecologist": "Gynecologist", "gyno": "Gynecologist"
    }
    
    for keyword, department in dept_mapping.items():
        if keyword in user_input_lower:
            preferences["department"] = department
            break
    
    # Extract doctor name
    import re
    name_patterns = [
        r'dr\.?\s*([a-zA-Z\s]+)',
        r'doctor\s+([a-zA-Z\s]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            preferences["doctor_name"] = match.group(1).strip()
            break
    
    return preferences


def get_appointment_state(conversation_history: List[Dict[str, str]]) -> dict:
    """Extract appointment booking state from conversation history"""
    print("Function: get_appointment_state")
    
    state = {
        "city": None,
        "department": None,
        "doctor_name": None,
        "step": "start"  # start, needs_city, needs_preference, ready_to_search, showing_results
    }
    
    # Parse conversation for collected information
    for msg in conversation_history:
        content = msg.get("content", "").lower()
        
        # Check for city mentions
        cities = ["kanpur", "orai", "jhansi"]
        for city in cities:
            if city in content:
                state["city"] = city.title()
                break
        
        # Check for department mentions
        departments = ["cardiology", "cardiologist", "pediatric", "pediatrician", 
                      "orthopedic", "gynecologist", "dermatologist", "ent", 
                      "neurologist", "psychiatrist", "dentist", "general physician"]
        for dept in departments:
            if dept in content:
                state["department"] = dept
                break
        
        # Check for doctor name mentions (Dr. followed by name)
        if "dr." in content or "doctor" in content:
            import re
            name_match = re.search(r'dr\.?\s+([a-zA-Z\s]+)', content, re.IGNORECASE)
            if name_match:
                state["doctor_name"] = name_match.group(1).strip()
    
    # Determine current step
    if not state["city"]:
        state["step"] = "needs_city"
    elif not state["department"] and not state["doctor_name"]:
        state["step"] = "needs_preference"  
    else:
        state["step"] = "ready_to_search"
    
    return state

def update_appointment_state_in_history(conversation_history: List[Dict[str, str]], new_state: Dict[str, Any]):
    print("Function: update_appointment_state_in_history")
    """Updates the appointment state marker in conversation history."""
    # Remove old state markers
    conversation_history[:] = [
        msg for msg in conversation_history
        if not (msg["role"] == "system" and "appointment_state" in msg.get("content", ""))
    ]
    # Add new state marker
    conversation_history.append({
        "role": "system",
        "content": f"appointment_state:{json.dumps(new_state)}"
    })


async def collect_location_info(request: ChatRequest):
    """Collect city and preference information step by step"""
    print("Function: collect_location_info")
    
    try:
        # Get current state
        state = get_appointment_state(request.conversation_history)
        
        # Extract any new preferences from user input
        user_prefs = extract_user_preferences(request.user_input)
        
        # Update state with new information
        if user_prefs["city"]:
            state["city"] = user_prefs["city"]
        if user_prefs["department"]:
            state["department"] = user_prefs["department"]
        if user_prefs["doctor_name"]:
            state["doctor_name"] = user_prefs["doctor_name"]
        
        # Determine what information is still needed
        city_status = "✅ Collected" if state["city"] else "❌ Missing"
        preference_status = "✅ Collected" if (state["department"] or state["doctor_name"]) else "❌ Missing"
        
        # Generate appropriate response
        conv_history = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in request.conversation_history if msg['role'] != "system"
        )
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                LOCATION_COLLECTION_PROMPT.format(
                    conversation_history=conv_history,
                    user_input=request.user_input,
                    language=request.language,
                    city_status=city_status,
                    preference_status=preference_status
                )
            ),
            HumanMessagePromptTemplate.from_template("{user_input}"),
        ])
        
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(user_input=request.user_input)
        
        return {"response": response.strip()}
        
    except Exception as e:
        logger.error(f"Location collection error: {str(e)}")
        raise HTTPException(500, "Location collection failed")

async def search_and_display_doctors(request: ChatRequest):
    """Search doctors based on collected criteria and display results"""
    print("Function: search_and_display_doctors")
    
    try:
        # Get current state
        state = get_appointment_state(request.conversation_history)
        
        # Extract any additional preferences from current input
        user_prefs = extract_user_preferences(request.user_input)
        if user_prefs["city"]:
            state["city"] = user_prefs["city"]
        if user_prefs["department"]:
            state["department"] = user_prefs["department"]
        if user_prefs["doctor_name"]:
            state["doctor_name"] = user_prefs["doctor_name"]
        
        # Perform doctor search
        doctors_list = await location_based_doctor_search(
            city=state["city"],
            department=state["department"],
            doctor_name=state["doctor_name"]
        )
        
        # Format search criteria for display
        search_criteria = []
        if state["doctor_name"]:
            search_criteria.append(f"Doctor: {state['doctor_name']}")
        elif state["department"]:
            search_criteria.append(f"Department: {state['department']}")
        
        search_criteria_text = " & ".join(search_criteria)
        
        # Format doctors info for LLM
        if doctors_list:
            doctors_text = f"FOUND {len(doctors_list)} DOCTORS:\n" + "\n".join([
                f"🏥 Dr. {doc['name']} - {doc['department']}\n   📍 {doc['Location']}\n   🕒 {doc.get('timings', 'Contact for timings')}"
                for doc in doctors_list
            ])
        else:
            doctors_text = "No doctors found matching the criteria."
        
        # Generate response
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                ENHANCED_DOCTOR_DISPLAY_PROMPT.format(
                    search_criteria=search_criteria_text,
                    city=state["city"] or "your location",
                    doctors_info=doctors_text,
                    language=request.language
                )
            ),
            HumanMessagePromptTemplate.from_template("{user_input}"),
        ])
        
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(user_input=request.user_input)
        
        return {"response": response.strip()}
        
    except Exception as e:
        logger.error(f"Doctor search and display error: {str(e)}")
        raise HTTPException(500, "Doctor search failed")
    
from typing import Optional  # Add at the top if not present

async def extract_doctor_id_from_selection(user_input: str, doctors_list: list) -> int:
    """Extract doctor ID from user's selection"""
    print("Function: extract_doctor_id_from_selection")
    
    user_input_lower = user_input.lower()
    
    # Method 1: Look for doctor name in user input
    for doctor in doctors_list:
        doctor_name = doctor['name'].lower()
        if doctor_name in user_input_lower or any(name_part in user_input_lower for name_part in doctor_name.split()):
            return doctor['id']
    
    # Method 2: Look for position indicators (first, second, etc.)
    position_mapping = {
        'first': 0, '1st': 0, '1': 0,
        'second': 1, '2nd': 1, '2': 1,
        'third': 2, '3rd': 2, '3': 2,
        'fourth': 3, '4th': 3, '4': 3,
        'fifth': 4, '5th': 4, '5': 4
    }
    
    for indicator, index in position_mapping.items():
        if indicator in user_input_lower and index < len(doctors_list):
            return doctors_list[index]['id']
    
    return None
from typing import Optional  # (already imported above)

def get_selected_doctor_from_history(conversation_history: List[Dict[str, str]]) -> int:
    """Extract selected doctor ID from conversation history"""
    print("Function: get_selected_doctor_from_history")
    
    for msg in reversed(conversation_history):
        if msg["role"] == "system" and "selected_doctor_id" in msg.get("content", ""):
            try:
                return int(msg["content"].split(":")[1].strip())
            except:
                continue
    return None

def get_appointment_booking_state(conversation_history: List[Dict[str, str]]) -> dict:
    """Get current state of appointment booking process"""
    print("Function: get_appointment_booking_state")
    
    state = {
        "step": "doctor_selection",  # doctor_selection, slot_selection, confirmation
        "selected_doctor_id": None,
        "selected_date": None,
        "selected_time": None
    }
    
    # Check for selected doctor
    state["selected_doctor_id"] = get_selected_doctor_from_history(conversation_history)
    
    # Check for selected date/time in recent messages
    for msg in reversed(conversation_history[-5:]):  # Check last 5 messages
        content = msg.get("content", "").lower()
        
        # Look for date selections
        import re
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}',
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                # Extract date info (simplified)
                pass
        
        # Look for time selections
        time_patterns = [
            r'(\d{1,2}:\d{2}\s*(?:am|pm))',
            r'(\d{1,2}\s*(?:am|pm))'
        ]
        
        for pattern in time_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                # Extract time info (simplified)
                pass
    
    # Determine current step
    if not state["selected_doctor_id"]:
        state["step"] = "doctor_selection"
    elif not state["selected_date"] or not state["selected_time"]:
        state["step"] = "slot_selection"
    else:
        state["step"] = "confirmation"
    
    return state

async def handle_doctor_selection(request: ChatRequest, doctors_list: list):
    """Handle doctor selection from the list"""
    print("Function: handle_doctor_selection")
    
    try:
        # Check if user has made a selection
        selected_doctor_id = await extract_doctor_id_from_selection(request.user_input, doctors_list)
        
        if selected_doctor_id:
            # Doctor selected - add to conversation history and move to slot selection
            request.conversation_history.append({
                "role": "system",
                "content": f"selected_doctor_id: {selected_doctor_id}"
            })
            
            # Get doctor details
            doctor = await get_doctor_by_id(selected_doctor_id)
            
            # Move to slot selection
            return await handle_slot_selection(request, doctor)
        
        else:
            # No clear selection - ask for clarification
            doctors_info = "\n".join([
                f"🏥 **Dr. {doc['name']}** - {doc['department']}\n   📍 {doc['Location']}\n   🕒 {doc.get('timings', 'Contact for timings')}"
                for doc in doctors_list
            ])
            
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    DOCTOR_SELECTION_PROMPT.format(
                        user_input=request.user_input,
                        language=request.language,
                        doctors_info=doctors_info
                    )
                ),
                HumanMessagePromptTemplate.from_template("{user_input}"),
            ])
            
            chain = LLMChain(llm=llm, prompt=prompt)
            response = await chain.arun(user_input=request.user_input)
            
            return {"response": response.strip()}
            
    except Exception as e:
        logger.error(f"Doctor selection error: {str(e)}")
        raise HTTPException(500, "Doctor selection failed")

async def handle_slot_selection(request: ChatRequest, doctor: dict):
    """Handle time slot selection for the chosen doctor"""
    print(f"Function: handle_slot_selection - Doctor: {doctor['name']}")
    
    try:
        # Get available slots for the doctor
        available_slots = await get_doctor_available_slots(doctor['id'])
        
        if not available_slots:
            return {
                "response": f"Sorry, Dr. {doctor['name']} doesn't have any available slots in the next 7 days. Please try selecting a different doctor or contact the clinic directly."
            }
        
        # Format slots for LLM
        slots_text = ""
        for day_slot in available_slots:
            slots_text += f"\n📅 **{day_slot['day_name']}, {day_slot['formatted_date']}**\n"
            for slot in day_slot['slots']:
                slots_text += f"   🕒 {slot['time']} - {slot['end_time']}\n"
        
        # Generate response
        conv_history = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in request.conversation_history if msg['role'] != "system"
        )
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                SLOT_AVAILABILITY_PROMPT.format(
                    doctor_name=doctor['name'],
                    doctor_department=doctor['department'],
                    user_input=request.user_input,
                    language=request.language,
                    available_slots=slots_text,
                    conversation_history=conv_history
                )
            ),
            HumanMessagePromptTemplate.from_template("{user_input}"),
        ])
        
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(user_input=request.user_input)
        
        return {"response": response.strip()}
        
    except Exception as e:
        logger.error(f"Slot selection error: {str(e)}")
        raise HTTPException(500, "Slot selection failed")



async def handle_smart_appointment_flow(request: ChatRequest):
    """Enhanced appointment flow with location-based search"""
    print("Function: handle_smart_appointment_flow - Enhanced Version")
    
    try:
        # Get current appointment state
        state = get_appointment_state(request.conversation_history)
        
        print(f"Current appointment state: {state}")
        
        # Handle different steps of appointment booking
        if state["step"] == "needs_city":
            return await collect_location_info(request)
        
        elif state["step"] == "needs_preference":
            return await collect_location_info(request)
        
        elif state["step"] == "ready_to_search":
            return await search_and_display_doctors(request)
        
        else:  # start step
            # Initial appointment flow - ask for city first
            return await collect_location_info(request)
            
    except Exception as e:
        logger.error(f"Enhanced appointment flow error: {str(e)}")
        raise HTTPException(500, "Enhanced appointment processing failed")

import re
# This function is the primary entry point for appointment flow as per the original main.py structure

async def handle_enhanced_appointment_flow(request: ChatRequest):
    """Enhanced appointment flow with doctor selection and slot booking"""
    print("Function: handle_enhanced_appointment_flow")
    
    try:
        # Get appointment booking state
        booking_state = get_appointment_booking_state(request.conversation_history)
        
        if booking_state["step"] == "doctor_selection":
            # Check if we're in the middle of showing doctors
            # Look for recent doctor search results in conversation
            doctors_list = []
            
            # Try to get doctors from a recent search or from current search
            current_state = get_appointment_state(request.conversation_history)
            
            if current_state["step"] == "ready_to_search":
                # Perform doctor search
                doctors_list = await location_based_doctor_search(
                    city=current_state["city"],
                    department=current_state["department"],
                    doctor_name=current_state["doctor_name"]
                )
                
                if doctors_list:
                    return await handle_doctor_selection(request, doctors_list)
                else:
                    # No doctors found - fallback to original flow
                    return await search_and_display_doctors(request)
            else:
                # Still collecting location info
                return await collect_location_info(request)
        
        elif booking_state["step"] == "slot_selection":
            # Handle slot selection
            doctor = await get_doctor_by_id(booking_state["selected_doctor_id"])
            if doctor:
                return await handle_slot_selection(request, doctor)
            else:
                return {"response": "Sorry, there was an error retrieving doctor information. Please start again."}
        
        else:
            # Fallback to original appointment flow
            return await handle_smart_appointment_flow(request)
            
    except Exception as e:
        logger.error(f"Enhanced appointment flow error: {str(e)}")
        raise HTTPException(500, "Enhanced appointment processing failed")


async def suggest_department(request: HistoryRequest):
    try:
        conv_history = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" 
            for msg in request.conversation_history
        )
        
        prompt = PromptTemplate(
            input_variables=["conversation_history"],
            template=DEPARTMENT_PROMPT
        )
        chain = LLMChain(llm=llm, prompt=prompt)
        department = await chain.arun(conversation_history=conv_history)
        return {"department": department.strip()}
    
    except Exception as e:
        logger.error(f"Department error: {str(e)}")
        return {"department": "General Medicine"}