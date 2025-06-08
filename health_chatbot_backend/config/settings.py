import logging
import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Ollama
llm = ChatOllama(
    model="llama3",
    temperature=0.7,
    max_tokens=500,
    timeout=30
) 

# You can add other global settings here if needed