import logging
from typing import List, Dict, Any
from io import BytesIO
import json
import re

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from models.request_models import HistoryRequest,OfflineReportRequest
# Import llm from settings
from config.settings import llm, logger
from models.prompts import REPORT_PROMPT, OFFLINE_REPORT_PROMPT

from fastapi import APIRouter

app = APIRouter()

@app.post("/generate_report")
async def generate_report(request: HistoryRequest):
    try:    
        # Extract name, gender, and age from the request
        name = request.name
        gender = request.gender
        age = request.age
        language = request.language  # New field for language support
        
        # Extract chief complaint
        chief_complaint = next(
            (msg["content"] for msg in request.conversation_history 
             if msg["role"] == "user"),
            "Not specified"
        )
        
        # Build conversation history
        conv_history = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" 
            for msg in request.conversation_history
        )

        # Prepare LangChain LLM call
        prompt = PromptTemplate(
            input_variables=["chief_complaint", "history", "conversation_history","language"],
            template=REPORT_PROMPT
        )
        chain = LLMChain(llm=llm, prompt=prompt)
        report_text = await chain.arun(
            chief_complaint=chief_complaint,
            history="From conversation",
            conversation_history=conv_history,
            language=language  # Include language in the prompt
        )

        # PDF Generation with styling
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)

        # Styles
        base_styles = getSampleStyleSheet()
        heading_style = ParagraphStyle(
            'Heading',
            parent=base_styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=12,
            leftIndent=0,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        )
        body_style = ParagraphStyle(
            'Body',
            parent=base_styles['Normal'],
            fontSize=11,
            leading=16,
            leftIndent=20
        )

        story = []

        # Title
        story.append(Paragraph("Medical Consultation Report", heading_style))
        story.append(Spacer(1, 12))

        # Patient Details Section
        story.append(Paragraph("Patient Details", heading_style))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Name: {name}", body_style))
        story.append(Paragraph(f"Gender: {gender}", body_style))
        story.append(Paragraph(f"Age: {age}", body_style))
        story.append(Spacer(1, 12))

        # Split report into sections and format
        for paragraph in report_text.split('\n\n'):
            stripped = paragraph.strip()
            if not stripped:
                continue
            if stripped.endswith(":"):  # Assume it's a heading
                story.append(Spacer(1, 10))
                story.append(Paragraph(stripped, heading_style))
            else:
                story.append(Paragraph(stripped, body_style))
            story.append(Spacer(1, 6))

        doc.build(story)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=medical_report.pdf"}
        )

    except Exception as e:
        logger.error(f"Report error: {str(e)}")
        raise HTTPException(500, "Report generation failed")
    


async def generate_offline_report(request: OfflineReportRequest):
    try:
        prompt = PromptTemplate(
            input_variables=["name", "age", "gender", "department", "language", "responses"],
            template=OFFLINE_REPORT_PROMPT
        )
        chain = LLMChain(llm=llm, prompt=prompt)
        report_content = await chain.arun(
            name=request.name,
            age=request.age,
            gender=request.gender,
            department=request.department,
            language=request.language,  # Include language in the prompt
            responses=request.responses,
        )

        report = {
            "Patient Details": {
                "Name": request.name,
                "Age": request.age,
                "Gender": request.gender,
                "Department": request.department,
                "Language": request.language,  # Include language in the JSON response
            },
            "Report": report_content,
            "Remarks": "This is an auto-generated offline medical  with language consideration.",
        }

        return JSONResponse(
            content=report,
            headers={"Content-Disposition": "attachment; filename=offline_report.json"}
        )
    except Exception as e:
        logger.error(f"Error in /generate_offline_report endpoint: {str(e)}")
        raise HTTPException(500, "Offline report generation failed")
