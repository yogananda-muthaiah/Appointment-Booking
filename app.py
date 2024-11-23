import sqlite3
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import os

app = FastAPI()
cf_port = os.getenv("PORT", 3000)

class Appointment(BaseModel):
    slot_id: int
    customer_name: str
    customer_email: str
    customer_phone: str

class DateRequest(BaseModel):
    date: str

def get_db_connection():
    conn = sqlite3.connect('appointments.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS timeslots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            is_booked INTEGER DEFAULT 0,
            customer_name TEXT,
            customer_email TEXT,
            customer_phone TEXT
        )
    ''')
    conn.close()

def generate_timeslots(date, start_hour=9, end_hour=17, slot_duration=60):
    conn = get_db_connection()
    start = datetime.strptime(date, '%Y-%m-%d').replace(hour=start_hour, minute=0)
    end = datetime.strptime(date, '%Y-%m-%d').replace(hour=end_hour, minute=0)
    
    current = start
    while current < end:
        slot_end = current + timedelta(minutes=slot_duration)
        
        # Check if slot already exists
        existing = conn.execute(
            'SELECT * FROM timeslots WHERE date = ? AND start_time = ?', 
            (date, current.strftime('%H:%M'))
        ).fetchone()
        
        if not existing:
            conn.execute(
                'INSERT INTO timeslots (date, start_time, end_time, is_booked) VALUES (?, ?, ?, 0)',
                (date, current.strftime('%H:%M'), slot_end.strftime('%H:%M'))
            )
        
        current = slot_end
    
    conn.commit()
    conn.close()

@app.post('/generate-timeslots')
async def create_timeslots(request: DateRequest):
    date = request.date
    
    if not date:
        raise HTTPException(status_code=400, detail="Date is required")
    
    try:
        generate_timeslots(date)
        return JSONResponse(content={'message': 'Timeslots generated successfully'}, status_code=201)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/available-timeslots')
async def get_available_timeslots(date: str):
    if not date:
        raise HTTPException(status_code=400, detail="Date is required")
    
    conn = get_db_connection()
    available_slots = conn.execute(
        'SELECT * FROM timeslots WHERE date = ? AND is_booked = 0', 
        (date,)
    ).fetchall()
    conn.close()
    
    return [dict(slot) for slot in available_slots]

@app.post('/book-appointment')
async def book_appointment(request: Appointment):
    data = request.dict()
    
    conn = get_db_connection()
    try:
        # Check if slot is available
        slot = conn.execute(
            'SELECT * FROM timeslots WHERE id = ? AND is_booked = 0', 
            (data['slot_id'],)
        ).fetchone()
        
        if not slot:
            raise HTTPException(status_code=400, detail="Slot is already booked or does not exist")
        
        # Book the slot
        conn.execute(
            '''UPDATE timeslots 
            SET is_booked = 1, 
                customer_name = ?, 
                customer_email = ?, 
                customer_phone = ? 
            WHERE id = ?''', 
            (data['customer_name'], data['customer_email'], 
             data['customer_phone'], data['slot_id'])
        )
        
        conn.commit()
        return JSONResponse(content={'message': 'Appointment booked successfully'}, status_code=201)
    
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post('/cancel-appointment')
async def cancel_appointment(slot_id: int):
    if not slot_id:
        raise HTTPException(status_code=400, detail="Slot ID is required")
    
    conn = get_db_connection()
    try:
        # Check if slot is booked
        slot = conn.execute(
            'SELECT * FROM timeslots WHERE id = ? AND is_booked = 1', 
            (slot_id,)
        ).fetchone()
        
        if not slot:
            raise HTTPException(status_code=400, detail="No booked appointment found for this slot")
        
        # Cancel the booking
        conn.execute(
            '''UPDATE timeslots 
            SET is_booked = 0, 
                customer_name = NULL, 
                customer_email = NULL, 
                customer_phone = NULL 
            WHERE id = ?''', 
            (slot_id,)
        )
        
        conn.commit()
        return JSONResponse(content={'message': 'Appointment cancelled successfully'}, status_code=200)
    
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get('/booked-appointments')
async def get_booked_appointments(date: str = None):
    conn = get_db_connection()
    try:
        if date:
            # If date is provided, get booked slots for that specific date
            booked_slots = conn.execute(
                'SELECT * FROM timeslots WHERE is_booked = 1 AND date = ?', 
                (date,)
            ).fetchall()
        else:
            # If no date, get all booked slots
            booked_slots = conn.execute(
                'SELECT * FROM timeslots WHERE is_booked = 1'
            ).fetchall()
        
        return [dict(slot) for slot in booked_slots]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

if __name__ == '__main__':
    import uvicorn
    init_db()
    uvicorn.run(app, host='0.0.0.0', port=int(cf_port))
