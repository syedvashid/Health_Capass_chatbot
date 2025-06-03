import mysql.connector
from dotenv import load_dotenv
import os
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

def get_db_connection():
    print("Function: get_db_connection")
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),  # Use 127.0.0.1 for TCP/IP
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_DATABASE"),
            port=3306
        )
        logger.info("Database connection successful!")
        return conn
    except mysql.connector.Error as e:
        logger.error(f"Database connection failed: {e}")
        return None

async def location_based_doctor_search(city: str = None, department: str = None, doctor_name: str = None) -> list:
    """Enhanced doctor search with location and multiple criteria"""
    print("Function: location_based_doctor_search")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build dynamic query based on available parameters
        query_parts = []
        params = []
        
        if city:
            query_parts.append("LOWER(Location) = LOWER(%s)")
            params.append(city)
        
        if doctor_name:
            query_parts.append("LOWER(name) LIKE %s")
            params.append(f"%{doctor_name.lower()}%")
        elif department:
            query_parts.append("LOWER(department) LIKE %s")
            params.append(f"%{department.lower()}%")
        
        # Construct final query
        base_query = "SELECT * FROM doctors"
        if query_parts:
            base_query += " WHERE " + " AND ".join(query_parts)
        base_query += " ORDER BY department, name"
        
        print(f"Query: {base_query}")
        print(f"Params: {params}")
        
        cursor.execute(base_query, params)
        doctors_list = cursor.fetchall() or []
        
        cursor.close()
        conn.close()
        
        return doctors_list
        
    except Exception as e:
        logger.error(f"Location-based doctor search error: {str(e)}")
        return []

from typing import Optional  # Add this import if not present

# ===== NEW DATABASE FUNCTIONS =====
async def get_doctor_by_id(doctor_id: int) -> dict:
    """Get doctor details by ID"""
    print(f"Function: get_doctor_by_id - ID: {doctor_id}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM doctors WHERE id = %s"
        cursor.execute(query, (doctor_id,))
        doctor = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return doctor
        
    except Exception as e:
        logger.error(f"Get doctor by ID error: {str(e)}")
        


def parse_doctor_timings(timings_str: str) -> list:
    """Parse doctor timings string and return working hours"""
    print(f"Function: parse_doctor_timings - Input: {timings_str}")
    
    if not timings_str or timings_str.strip() == "":
        print("No timings provided, using default working hours")
        # Default working hours if no timings specified
        return [("09:00", "12:00"), ("14:00", "17:00")]
    
    working_hours = []
    
    try:
        # Common timing formats to handle:
        # "9:00 AM - 12:00 PM, 2:00 PM - 5:00 PM"
        # "09:00-12:00, 14:00-17:00"
        # "Morning: 9-12, Evening: 2-5"
        
        import re
        
        # Pattern to match time ranges like "9:00 AM - 12:00 PM" or "09:00-12:00"
        time_pattern = r'(\d{1,2}):?(\d{0,2})\s*(AM|PM|am|pm)?\s*[-–]\s*(\d{1,2}):?(\d{0,2})\s*(AM|PM|am|pm)?'
        
        matches = re.findall(time_pattern, timings_str)
        
        for match in matches:
            start_hour, start_min, start_period, end_hour, end_min, end_period = match
            
            # Convert to 24-hour format
            start_hour = int(start_hour)
            start_min = int(start_min) if start_min else 0
            end_hour = int(end_hour)
            end_min = int(end_min) if end_min else 0
            
            # Handle AM/PM conversion
            if start_period and start_period.upper() == 'PM' and start_hour != 12:
                start_hour += 12
            elif start_period and start_period.upper() == 'AM' and start_hour == 12:
                start_hour = 0
                
            if end_period and end_period.upper() == 'PM' and end_hour != 12:
                end_hour += 12
            elif end_period and end_period.upper() == 'AM' and end_hour == 12:
                end_hour = 0
            
            start_time = f"{start_hour:02d}:{start_min:02d}"
            end_time = f"{end_hour:02d}:{end_min:02d}"
            
            working_hours.append((start_time, end_time))
            print(f"Parsed timing slot: {start_time} - {end_time}")
        
        # If no valid patterns found, try simple hour patterns
        if not working_hours:
            # Look for simple patterns like "9-12, 2-5" or "9-12, 14-17"
            simple_pattern = r'(\d{1,2})\s*[-–]\s*(\d{1,2})'
            simple_matches = re.findall(simple_pattern, timings_str)
            
            for match in simple_matches:
                start_hour, end_hour = int(match[0]), int(match[1])
                
                # Assume PM if hours are small (like 2-5 means 2PM-5PM)
                if start_hour < 8:  # Likely afternoon hours
                    start_hour += 12
                    end_hour += 12
                
                start_time = f"{start_hour:02d}:00"
                end_time = f"{end_hour:02d}:00"
                
                working_hours.append((start_time, end_time))
                print(f"Parsed simple timing: {start_time} - {end_time}")
        
        # If still no working hours, use default
        if not working_hours:
            print("Could not parse timings, using default")
            working_hours = [("09:00", "12:00"), ("14:00", "17:00")]
            
    except Exception as e:
        print(f"Error parsing timings: {str(e)}")
        working_hours = [("09:00", "12:00"), ("14:00", "17:00")]
    
    print(f"Final working hours: {working_hours}")
    return working_hours


def generate_available_slots(doctor: dict, busy_slots: list, days_ahead: int = 7) -> list:
    """Generate available time slots using doctor's actual timings from database"""
    print(f"Function: generate_available_slots - Doctor: {doctor['name']}")
    
    from datetime import datetime, timedelta, time
    
    # Parse doctor's actual timings from database
    doctor_timings = doctor.get('timings', '')
    working_hours = parse_doctor_timings(doctor_timings)
    
    print(f"Doctor {doctor['name']} working hours: {working_hours}")
    
    available_slots = []
    
    # Generate slots for next days (excluding Sundays)
    for day in range(1, days_ahead + 1):
        current_date = datetime.now() + timedelta(days=day)
        
        # Skip Sundays (weekday 6) - you can customize this
        if current_date.weekday() == 6:
            continue
            
        date_str = current_date.strftime('%Y-%m-%d')
        day_name = current_date.strftime('%A')
        formatted_date = current_date.strftime('%B %d, %Y')
        
        # Get busy slots for this date
        day_busy_slots = []
        for slot in busy_slots:
            # Handle both datetime and string date formats
            slot_date = slot['Date']
            if hasattr(slot_date, 'strftime'):
                slot_date_str = slot_date.strftime('%Y-%m-%d')
            else:
                slot_date_str = str(slot_date)
                
            if slot_date_str == date_str:
                day_busy_slots.append(slot)
        
        print(f"Date {date_str}: Found {len(day_busy_slots)} busy slots")
        
        # Generate slots based on doctor's actual working hours
        day_slots = []
        for start_time_str, end_time_str in working_hours:
            try:
                start_time = datetime.strptime(start_time_str, '%H:%M').time()
                end_time = datetime.strptime(end_time_str, '%H:%M').time()
                
                # Generate hourly slots within working hours
                current_hour = start_time
                while current_hour < end_time:
                    # Create 1-hour slot
                    next_hour_dt = datetime.combine(datetime.today(), current_hour) + timedelta(hours=1)
                    next_hour = next_hour_dt.time()
                    
                    # Don't exceed the working end time
                    if next_hour > end_time:
                        next_hour = end_time
                    
                    # Check if this slot is busy
                    is_busy = False
                    for busy_slot in day_busy_slots:
                        busy_start = busy_slot['Start_Time']
                        busy_end = busy_slot['End_Time']
                        
                        # Handle different time formats
                        if isinstance(busy_start, str):
                            try:
                                busy_start = datetime.strptime(busy_start, '%H:%M:%S').time()
                            except:
                                busy_start = datetime.strptime(busy_start, '%H:%M').time()
                        elif hasattr(busy_start, 'time'):
                            busy_start = busy_start.time()
                            
                        if isinstance(busy_end, str):
                            try:
                                busy_end = datetime.strptime(busy_end, '%H:%M:%S').time()
                            except:
                                busy_end = datetime.strptime(busy_end, '%H:%M').time()
                        elif hasattr(busy_end, 'time'):
                            busy_end = busy_end.time()
                        
                        # Check for overlap
                        if (current_hour >= busy_start and current_hour < busy_end) or \
                           (next_hour > busy_start and next_hour <= busy_end) or \
                           (current_hour <= busy_start and next_hour >= busy_end):
                            is_busy = True
                            break
                    
                    if not is_busy:
                        day_slots.append({
                            'time': current_hour.strftime('%I:%M %p'),
                            'end_time': next_hour.strftime('%I:%M %p'),
                            'start_24h': current_hour.strftime('%H:%M'),
                            'end_24h': next_hour.strftime('%H:%M')
                        })
                        print(f"Available slot: {current_hour.strftime('%I:%M %p')} - {next_hour.strftime('%I:%M %p')}")
                    else:
                        print(f"Busy slot: {current_hour.strftime('%I:%M %p')} - {next_hour.strftime('%I:%M %p')}")
                    
                    # Move to next hour
                    current_hour = next_hour
                    
                    # Break if we've reached the end time
                    if current_hour >= end_time:
                        break
                        
            except Exception as e:
                print(f"Error processing working hours {start_time_str}-{end_time_str}: {str(e)}")
                continue
        
        if day_slots:
            available_slots.append({
                'date': date_str,
                'formatted_date': formatted_date,
                'day_name': day_name,
                'slots': day_slots
            })
            print(f"Added {len(day_slots)} available slots for {formatted_date}")
    
    print(f"Total available slot days: {len(available_slots)}")
    return available_slots


async def get_doctor_available_slots(doctor_id: int, days_ahead: int = 7) -> list:
    """Get available time slots for a doctor (excluding busy times)"""
    print(f"Function: get_doctor_available_slots - Doctor ID: {doctor_id}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get doctor's general timings
        doctor = await get_doctor_by_id(doctor_id)
        if not doctor:
            return []
        
        # Get busy slots from slot table
        from datetime import datetime, timedelta
        
        end_date = datetime.now() + timedelta(days=days_ahead)
        
        query = """
        SELECT Date, Start_Time, End_Time, Status 
        FROM slot 
        WHERE Doctor_id = %s 
        AND Date >= CURDATE() 
        AND Date <= %s 
        AND Status = 'busy'
        ORDER BY Date, Start_Time
        """
        
        cursor.execute(query, (doctor_id, end_date.strftime('%Y-%m-%d')))
        busy_slots = cursor.fetchall() or []
        
        cursor.close()
        conn.close()
        
        # Generate available slots (this is a simplified version)
        # You can customize this logic based on your business requirements
        available_slots = generate_available_slots(doctor, busy_slots, days_ahead)
        
        return available_slots
        
    except Exception as e:
        logger.error(f"Get available slots error: {str(e)}")
        return []
