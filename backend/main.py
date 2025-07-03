import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferWindowMemory
from tools import create_calendar_event, find_events, update_calendar_event, find_todays_events
import datetime
from tzlocal import get_localzone_name

load_dotenv()

if os.getenv("GOOGLE_API_KEY") is None:
    raise Exception("GOOGLE_API_KEY not found. Please set it in .env file.")

app = FastAPI()

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

# Define the tools
tools = [create_calendar_event, find_events, update_calendar_event, find_todays_events]

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

**Finding Events:**
- When asked about "today's events" or "meetings today", use the `find_todays_events` tool directly.
- For specific event searches (by title/keywords), use the `find_events` tool.
- Always provide event links when available from tool responses.

**Event Creation and Information:**
- When you create an event, always save and remember the event details including the link.
- If asked about "the meeting" or "that event" after creating one, refer to the most recent event discussed.
- Provide event links whenever you have them available from tool responses.

**Workflow for Updating an Event:**
1.  When the user asks to edit, modify, or change an event, your primary goal is to **update** it.
2.  First, you **must** determine the event's title. If the user is vague (e.g., "edit my meeting"), ask for the title or keywords.
3.  Use the `find_events` tool to search. The `query` parameter MUST ONLY be the event's title/keywords, not conversational text.
4.  **If `find_events` returns "No upcoming events found", DO NOT give up.** Inform the user you couldn't find it and ask for a more specific title or different keywords. Do **NOT** suggest creating a new event unless the user asks you to.
5.  If you find multiple events, ask the user to clarify which one to edit.
6.  Once you have the correct `event_id`, use `update_calendar_event` to apply the changes. Do **not** ask the user for the event ID.

**Smart Update Example:**
- User: "Move my 'Project Sync' meeting to 2 PM today."
- Agent Action: First, find the "Project Sync" event. Then, call `update_calendar_event` with **only** the `start_time` set to 2 PM. The tool will handle the rest.

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

@app.get("/")
def read_root():
    return {"message": "Welcome to the Calendar Scheduling Assistant API!"}
