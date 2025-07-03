import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferWindowMemory
from tools import create_calendar_event, get_calendar_events, update_calendar_event, find_available_time_slots, get_event_details
import datetime
from tzlocal import get_localzone_name

# Load environment variables
load_dotenv()

# Check for GOOGLE_API_KEY
if os.getenv("GOOGLE_API_KEY") is None:
    raise Exception("GOOGLE_API_KEY not found. Please set it in .env file.")

# Initialize FastAPI app
app = FastAPI(title="Calendar Assistant API",
             description="A powerful calendar assistant that can create, find, and update Google Calendar events.",
             version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

# Define the tools
tools = [create_calendar_event, get_calendar_events, update_calendar_event, find_available_time_slots, get_event_details]

# Global conversation memory
memory = ConversationBufferWindowMemory(
    memory_key="chat_history",
    return_messages=True,
    k=10 
)

# Create prompt with current time
def create_prompt_with_time():
    local_timezone = get_localzone_name()
    current_time_str = f"{datetime.datetime.now().isoformat()} (Timezone: {local_timezone})"
    
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"""You are a powerful calendar assistant. You can create, find, and update Google Calendar events.
The current date and time is {current_time_str}. Use this for any relative time queries.

**IMPORTANT: Conversation Memory**
- You maintain conversation history and can refer to previous interactions.
- If a user asks about an event you just created or mentioned, use the information from our conversation history.
- When asked for event links, always check if you have the link from a recent tool response.
- Never say you cannot provide information that was shared in our conversation.

**Finding Events with `get_calendar_events`:**
- This is your primary tool for finding any event. It provides a list with summary, time, duration, and ID.
- To find events on a specific day, the LLM must convert terms like "today" or "tomorrow" into a specific 'YYYY-MM-DD' date for the `start_date` and `end_date` parameters.
- **For today's events:** Set `start_date` and `end_date` to today's date.
- **For tomorrow's events:** Set `start_date` and `end_date` to tomorrow's date.
- **For events with a specific title:** Use the `query` parameter.
- If a user is vague (e.g., "my next meeting"), you can call the tool with no parameters to get a list of all upcoming events.

**Getting Specific Event Details:**
- If the user asks for more details about a specific event (like its description or full attendee list), or if you need to confirm details before taking action, use the `get_event_details` tool.
- You **must** provide the exact `event_id` from a previous search. Do not make up an ID.

**Checking Availability:**
- When a user asks if you can "find time," "check my availability," or asks for "free slots," use the `find_available_time_slots` tool.
- The LLM must convert terms like "today" or "tomorrow" into a specific 'YYYY-MM-DD' date.
- By default, assume a 30-minute duration unless the user specifies otherwise.
- Example: "Find some time for a meeting tomorrow afternoon" -> Use `find_available_time_slots` with `start_date` set to tomorrow's date.

**Event Creation and Information:**
- When you create an event, always save and remember the event details including the link.
- If asked about "the meeting" or "that event" after creating one, refer to the most recent event discussed.
- Provide event links whenever you have them available from tool responses.

**Workflow for Updating an Event:**
1.  When the user asks to edit, modify, or change an event, your primary goal is to **update** it.
2.  First, you **must** determine the event's title. If the user is vague (e.g., "edit my meeting"), ask for the title or keywords.
3.  Use the `get_calendar_events` tool to search. The `query` parameter MUST ONLY be the event's title/keywords, not conversational text.
4.  **If `get_calendar_events` returns "No events found", DO NOT give up.** Inform the user you couldn't find it and ask for a more specific title or different keywords. Do **NOT** suggest creating a new event unless the user asks you to.
5.  If you find multiple events, ask the user to clarify which one to edit.
6.  Once you have the correct `event_id` from the tool's output, use `update_calendar_event` to apply the changes. The `event_id` is a short alphanumeric string. You **must** use the exact ID provided in the search results and not invent one.

**Smart Update Example:**
- User: "Move my 'Project Sync' meeting to 2 PM today."
- Agent Action: First, use `get_calendar_events` with `query='Project Sync'` to find the event. Then, call `update_calendar_event` with **only** the `start_time` set to 2 PM. The tool will handle the rest.

**Conversation Context Examples:**
- If you just created a "team meeting" and user asks "what's the link?", provide the link from the creation response.
- If user says "add someone to that meeting", refer to the most recently discussed event.
"""
            ),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )

# Create the prompt and agent
prompt = create_prompt_with_time()
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True,
    handle_parsing_errors=True
)

# Define the request body for the chat endpoint
class ChatRequest(BaseModel):
    query: str

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Receives a user query, processes it through the LangChain agent with conversation history,
    and returns the agent's response.
    """
    response = agent_executor.invoke({"input": request.query})
    return {"response": response["output"]}

@app.post("/clear-history")
async def clear_history():
    """
    Clears the conversation memory.
    """
    memory.clear()
    return {"status": "history cleared"}

@app.get("/")
def read_root():
    return {"message": "Welcome to the Calendar Scheduling Assistant API!"}
