import motor.motor_asyncio
from bson.objectid import ObjectId
import time

# MongoDB connection details
MONGO_DETAILS = "mongodb://localhost:27017"  # Replace if different
DATABASE_NAME = "health_chatbot_db"        # Your database name

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DETAILS)
database = client[DATABASE_NAME]

# Define your collections
chat_history_collection = database["chat_history"]
question_collection = database["question"]
options_collection = database["options"]
answer_collection = database["answer"]

async def connect_db():
    try:
        await client.admin.command('ping')
        print("Connected to MongoDB")
    except Exception as e:
        print(f"Could not connect to MongoDB: {e}")

async def close_db():
    client.close()
    print("MongoDB connection closed")

async def add_chat_history(chat_history_data: dict):
    # The ID is created in the main logic to be returned immediately
    new_chat_history = await chat_history_collection.insert_one(chat_history_data)
    return chat_history_data["_id"] # Return the custom ID

async def add_question(question_data: dict):
    new_question = await question_collection.insert_one(question_data)
    return new_question.inserted_id

async def add_option(option_data: dict):
    new_option = await options_collection.insert_one(option_data)
    return new_option.inserted_id

async def add_answer(answer_data: dict):
    new_answer = await answer_collection.insert_one(answer_data)
    return new_answer.inserted_id