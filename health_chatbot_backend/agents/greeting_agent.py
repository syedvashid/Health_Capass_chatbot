import logging
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain.chains import LLMChain

# Import llm from settings
from config.settings import llm, logger
from models.prompts import GREETING_AGENT_PROMPT
# Agentic System Prompts

async def generate_greeting(language: str) -> str:
    print("Function: generate_greeting")
    """Generate dynamic, personalized greeting"""
    try:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(GREETING_AGENT_PROMPT.format(language=language))
        ])
        chain = LLMChain(llm=llm, prompt=prompt)
        response = await chain.arun(input="")
        return response.strip()
    except Exception as e:
        logger.error(f"Greeting generation error: {str(e)}")
        return "Hello! How can I help you today? I can assist with medical diagnosis questions or appointment booking."
