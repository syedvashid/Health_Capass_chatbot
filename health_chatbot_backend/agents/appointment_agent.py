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
from services.database_service import location_based_doctor_search, get_doctor_by_id, get_doctor_available_slots, store_appointment_in_database
from models.request_models import ChatRequest,HistoryRequest
# Agentic System Prompts for Appointment Flow
from models.prompts import (
    LOCATION_COLLECTION_PROMPT, ENHANCED_DOCTOR_DISPLAY_PROMPT,DEPARTMENT_PROMPT ,DOCTOR_SELECTION_PROMPT,SLOT_AVAILABILITY_PROMPT,SLOT_SELECTION_PROMPT,
    BOOKING_CONFIRMATION_PROMPT, FINAL_BOOKING_CONFIRMATION_PROMPT
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

def get_updated_appointment_booking_state(conversation_history: List[Dict[str, str]]) -> dict:
    """Get enhanced appointment booking state with slot selection"""
    print("Function: get_updated_appointment_booking_state")
    
    state = {
        "step": "doctor_selection",
        "selected_doctor_id": None,
        "selected_slot": None,
        "ready_for_confirmation": False
    }
    
    # Check for selected doctor
    state["selected_doctor_id"] = get_selected_doctor_from_history(conversation_history)
    
    # Check for selected slot
    state["selected_slot"] = get_selected_slot_from_history(conversation_history)
    
    # Determine current step
    if not state["selected_doctor_id"]:
        state["step"] = "doctor_selection"
    elif not state["selected_slot"]:
        state["step"] = "slot_selection"
    else:
        state["step"] = "confirmation"
        state["ready_for_confirmation"] = True
    
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
            return await handle_slot_selection_with_confirmation(request, doctor)
        
        else:
            # No clear selection - ask for clarification
            doctors_info = "\n".join([
                f"🏥 **Dr. {doc['name']}** - {doc['department']}\n   📍 {doc['location']}\n   🕒 {doc.get('timings', 'Contact for timings')}"
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

async def handle_slot_selection_with_confirmation(request: ChatRequest, doctor: dict):
    """Enhanced slot selection that handles both showing slots and detecting selection"""
    print(f"Function: handle_slot_selection_with_confirmation - Doctor: {doctor['name']}")
    
    try:
        # Get available slots for the doctor
        available_slots = await get_doctor_available_slots(doctor['id'])
        
        if not available_slots:
            return {
                "response": f"Sorry, Dr. {doctor['name']} doesn't have any available slots in the next 7 days. Please try selecting a different doctor or contact the clinic directly."
            }
        
        # Check if user is selecting a slot
        selected_slot = await extract_slot_selection_from_input(request.user_input, available_slots)
        
        if selected_slot:
            # User selected a slot - save to conversation history and show confirmation
            request.conversation_history.append({
                "role": "system",
                "content": f"selected_slot: {json.dumps(selected_slot)}"
            })
            
            # Move to confirmation step
            return await handle_booking_confirmation(request, doctor, selected_slot)
        
        else:
            # Show available slots
            slots_text = ""
            for day_slot in available_slots:
                slots_text += f"\n📅 **{day_slot['day_name']}, {day_slot['formatted_date']}**\n"
                for slot in day_slot['slots']:
                    slots_text += f"   🕒 {slot['time']} - {slot['end_time']}\n"
            
            # Generate response asking for slot selection
            conv_history = "\n".join(
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in request.conversation_history if msg['role'] != "system"
            )
            
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    SLOT_SELECTION_PROMPT.format(
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
        logger.error(f"Slot selection with confirmation error: {str(e)}")
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
#  ===== UPDATED MAIN FLOW FUNCTION =====
async def handle_enhanced_appointment_flow_with_confirmation(request: ChatRequest):
    """Enhanced appointment flow with full confirmation support"""
    print("Function: handle_enhanced_appointment_flow_with_confirmation")
    
    try:
        # Get enhanced appointment booking state
        booking_state = get_updated_appointment_booking_state(request.conversation_history)
        
        if booking_state["step"] == "doctor_selection":
            # Check if we're in the middle of showing doctors
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
                    return await search_and_display_doctors(request)
            else:
                return await collect_location_info(request)
        
        elif booking_state["step"] == "slot_selection":
            # Handle slot selection with confirmation detection
            doctor = await get_doctor_by_id(booking_state["selected_doctor_id"])
            if doctor:
                return await handle_slot_selection_with_confirmation(request, doctor)
            else:
                return {"response": "Sorry, there was an error retrieving doctor information. Please start again."}
        
        elif booking_state["step"] == "confirmation":
            # Handle booking confirmation
            doctor = await get_doctor_by_id(booking_state["selected_doctor_id"])
            selected_slot = booking_state["selected_slot"]
            
            if doctor and selected_slot:
                return await handle_booking_confirmation(request, doctor, selected_slot)
            else:
                return {"response": "Sorry, there was an error with your booking details. Please start again."}
        
        else:
            # Fallback to original appointment flow
            return await handle_smart_appointment_flow(request)
            
    except Exception as e:
        logger.error(f"Enhanced appointment flow with confirmation error: {str(e)}")
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
    




# code after selcting slot and confirming booking
from typing import List, Dict


    
async def extract_slot_selection_from_input(user_input: str, available_slots: list) -> dict:
    """Extract selected date and time from user input"""
    print("Function: extract_slot_selection_from_input")
    
    import re
    from datetime import datetime
    
    user_input_lower = user_input.lower()
    selected_slot = None
    
    # Method 1: Look for specific date mentions
    for day_slot in available_slots:
        date_variations = [
            day_slot['formatted_date'].lower(),
            day_slot['day_name'].lower(),
            day_slot['date'],
        ]
        
        for date_var in date_variations:
            if date_var in user_input_lower:
                # Found date, now look for time
                for slot in day_slot['slots']:
                    time_variations = [
                        slot['time'].lower(),
                        slot['start_24h'],
                        slot['time'].replace(' AM', '').replace(' PM', '').lower(),
                    ]
                    
                    for time_var in time_variations:
                        if time_var in user_input_lower:
                            selected_slot = {
                                'date': day_slot['date'],
                                'formatted_date': day_slot['formatted_date'],
                                'day_name': day_slot['day_name'],
                                'time': slot['time'],
                                'end_time': slot['end_time'],
                                'start_24h': slot['start_24h'],
                                'end_24h': slot['end_24h']
                            }
                            print(f"Found slot selection: {selected_slot}")
                            return selected_slot
    
    # Method 2: Look for time patterns in user input
    time_patterns = [
        r'(\d{1,2}:\d{2}\s*(?:am|pm))',
        r'(\d{1,2}\s*(?:am|pm))',
        r'(\d{1,2}:\d{2})'
    ]
    
    for pattern in time_patterns:
        matches = re.findall(pattern, user_input_lower, re.IGNORECASE)
        if matches:
            selected_time = matches[0]
            # Try to match with available slots
            for day_slot in available_slots:
                for slot in day_slot['slots']:
                    if selected_time.lower() in slot['time'].lower():
                        selected_slot = {
                            'date': day_slot['date'],
                            'formatted_date': day_slot['formatted_date'],
                            'day_name': day_slot['day_name'],
                            'time': slot['time'],
                            'end_time': slot['end_time'],
                            'start_24h': slot['start_24h'],
                            'end_24h': slot['end_24h']
                        }
                        print(f"Found time-based slot selection: {selected_slot}")
                        return selected_slot
    
    # Method 3: Look for position indicators (first slot, second slot, etc.)
    position_indicators = {
        'first': 0, '1st': 0, '1': 0,
        'second': 1, '2nd': 1, '2': 1,
        'third': 2, '3rd': 2, '3': 2,
        'fourth': 3, '4th': 3, '4': 4,
        'fifth': 4, '5th': 4, '5': 5
    }
    
    for indicator, index in position_indicators.items():
        if indicator in user_input_lower:
            # Find the index-th available slot across all days
            slot_count = 0
            for day_slot in available_slots:
                for slot in day_slot['slots']:
                    if slot_count == index:
                        selected_slot = {
                            'date': day_slot['date'],
                            'formatted_date': day_slot['formatted_date'],
                            'day_name': day_slot['day_name'],
                            'time': slot['time'],
                            'end_time': slot['end_time'],
                            'start_24h': slot['start_24h'],
                            'end_24h': slot['end_24h']
                        }
                        print(f"Found position-based slot selection: {selected_slot}")
                        return selected_slot
                    slot_count += 1
    
    print("No slot selection found in user input")
    return None

def get_selected_slot_from_history(conversation_history: List[Dict[str, str]]) -> dict:
    """Extract selected slot from conversation history"""
    print("Function: get_selected_slot_from_history")
    
    for msg in reversed(conversation_history):
        if msg["role"] == "system" and "selected_slot:" in msg.get("content", ""):
            try:
                import json
                slot_data = msg["content"].split("selected_slot:")[1].strip()
                return json.loads(slot_data)
            except:
                continue
    return None

def detect_booking_confirmation_intent(user_input: str) -> bool:
    """Detect if user wants to confirm booking"""
    print("Function: detect_booking_confirmation_intent")
    
    confirmation_keywords = [
        'yes', 'confirm', 'book', 'proceed', 'ok', 'okay', 'sure', 
        'correct', 'right', 'perfect', 'good', 'fine', 'agree',
        'confirm booking', 'book appointment', 'that\'s right',
        'looks good', 'sounds good', 'go ahead'
    ]
    
    user_input_lower = user_input.lower().strip()
    
    for keyword in confirmation_keywords:
        if keyword in user_input_lower:
            print(f"Found confirmation intent: {keyword}")
            return True
        else:
            
            print("Found not confirm ")
    return False


async def handle_booking_confirmation(request: ChatRequest, doctor: dict, selected_slot: dict):
    """Handle booking confirmation display and final confirmation"""
    print("Function: handle_booking_confirmation")
    
    try:
        # Check if user is confirming the booking
        if detect_booking_confirmation_intent(request.user_input):
            # User confirmed - show final booking confirmation
            return await handle_final_booking_confirmation(request, doctor, selected_slot)
        
        else:
            # Show booking details for confirmation
            conv_history = "\n".join(
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in request.conversation_history if msg['role'] != "system"
            )
            
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    BOOKING_CONFIRMATION_PROMPT.format(
                        doctor_name=doctor['name'],
                        doctor_department=doctor['department'],
                        doctor_location=doctor.get('Location', 'Hospital'),
                        selected_date=selected_slot['formatted_date'],
                        selected_day=selected_slot['day_name'],
                        selected_time=selected_slot['time'],
                        selected_end_time=selected_slot['end_time'],
                        user_input=request.user_input,
                        language=request.language,
                        conversation_history=conv_history
                    )
                ),
                HumanMessagePromptTemplate.from_template("{user_input}"),
            ])
            
            chain = LLMChain(llm=llm, prompt=prompt)
            response = await chain.arun(user_input=request.user_input)
            
            return {"response": response.strip()}
            
    except Exception as e:
        logger.error(f"Booking confirmation error: {str(e)}")
        raise HTTPException(500, "Booking confirmation failed")

async def handle_final_booking_confirmation(request: ChatRequest, doctor: dict, selected_slot: dict):
    """Handle final booking confirmation after user confirms - MODIFIED to store in database"""
    print("Function: handle_final_booking_confirmation")
    
    try:
        # Extract patient information from conversation history
        patient_info = extract_patient_info_from_conversation(request)
        print(f"Extracted patient info: {patient_info}")
        # Store appointment in database
        db_result = await store_appointment_in_database(doctor, selected_slot, patient_info)
        
        if db_result['success']:
            # Generate final confirmation message with booking ID
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    FINAL_BOOKING_CONFIRMATION_PROMPT.format(
                        doctor_name=doctor['name'],
                        doctor_department=doctor['department'],
                        doctor_location=doctor.get('Location', 'Hospital'),
                        selected_date=selected_slot['formatted_date'],
                        selected_day=selected_slot['day_name'],
                        selected_time=selected_slot['time'],
                        selected_end_time=selected_slot['end_time'],
                        language=request.language,
                        booking_id=db_result['appointment_id'],  # Add booking ID to prompt
                        patient_name=patient_info.get('name', 'Patient')
                    )
                ),
                HumanMessagePromptTemplate.from_template("{user_input}"),
            ])
            
            chain = LLMChain(llm=llm, prompt=prompt)
            response = await chain.arun(user_input=request.user_input)
            
            # Add booking success information to response
            final_response = f"{response.strip()}\n\n✅ Booking Reference ID: {db_result['appointment_id']}"
            
            return {"response": final_response}
        else:
            # Database storage failed, but still show confirmation
            logger.error(f"Database storage failed: {db_result['error']}")
            
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(
                    FINAL_BOOKING_CONFIRMATION_PROMPT.format(
                        doctor_name=doctor['name'],
                        doctor_department=doctor['department'],
                        doctor_location=doctor.get('Location', 'Hospital'),
                        selected_date=selected_slot['formatted_date'],
                        selected_day=selected_slot['day_name'],
                        selected_time=selected_slot['time'],
                        selected_end_time=selected_slot['end_time'],
                        language=request.language
                    )
                ),
                HumanMessagePromptTemplate.from_template("{user_input}"),
            ])
            
            chain = LLMChain(llm=llm, prompt=prompt)
            response = await chain.arun(user_input=request.user_input)
            
            # Add warning about database issue
            final_response = f"{response.strip()}\n\n⚠️ Note: There was an issue saving your booking details. Please contact support if needed."
            
            return {"response": final_response}
        
    except Exception as e:
        logger.error(f"Final booking confirmation error: {str(e)}")
        raise HTTPException(500, "Final booking confirmation failed")
    

       
def extract_patient_info_from_conversation(request) -> dict:
    """Extract patient information from conversation history or request object"""
    print("Function: extract_patient_info_from_conversation")
    
    patient_info = {
        'name': getattr(request, 'name', None),
        'age': getattr(request, 'age', None),
        'gender': getattr(request, 'gender', None),
        'reason': getattr(request, 'department', None),  # Assuming department is used as reason for visit
    }
    return patient_info
