import streamlit as st
import requests
import json

st.title("📅 Calendar Scheduling Assistant")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

def send_message(message):
    """Helper function to send a message and get response from backend"""
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": message})
    
    # Call the backend API
    try:
        payload = {"query": message}
        
        response = requests.post("http://127.0.0.1:8000/chat", json=payload)
        response.raise_for_status()
        
        backend_response = response.json()
        ai_response = backend_response.get("response", "Sorry, I encountered an error.")
        
        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": ai_response})
        
    except requests.exceptions.RequestException as e:
        error_message = f"Could not connect to the backend. Please make sure the backend server is running. Error: {e}"
        st.error(error_message)
        st.session_state.messages.append({"role": "assistant", "content": error_message})
    except json.JSONDecodeError:
        error_message = "Failed to decode the response from the backend."
        st.error(error_message)
        st.session_state.messages.append({"role": "assistant", "content": error_message})

# Add a clear chat button in the main interface
col1, col2 = st.columns([4, 1])
with col2:
    if st.button("🗑️ Clear Chat", help="Clear the conversation history"):
        st.session_state.messages = []
        st.rerun()

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("How can I help you with your calendar?"):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    
    # Use the helper function to send message and get response
    send_message(prompt)
    st.rerun()

# Display helpful examples when chat is empty
if len(st.session_state.messages) == 0:
    st.markdown("---")
    st.markdown("### 💡 Try these examples:")
    
    # Create example buttons that users can click
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📅 Create Events:**")
        if st.button("Schedule team meeting tomorrow at 2 PM"):
            send_message("Schedule a team meeting for tomorrow at 2 PM with my email")
            st.rerun()
        
        if st.button("Create project review meeting"):
            send_message("Create a project review meeting for Friday at 3 PM for 1 hour")
            st.rerun()
    
    with col2:
        st.markdown("**🔍 Find & Update:**")
        if st.button("Find my meetings today"):
            send_message("Find my meetings for today")
            st.rerun()
        
        if st.button("Move my next meeting to 4 PM"):
            send_message("Move my next meeting to 4 PM")
            st.rerun()
    
    st.markdown("---")
    st.markdown("**💬 Examples:**")
    st.markdown("""
    - "Schedule a client call for Monday at 10 AM with karthik@gmail.com"
    - "Find my meeting about the project launch"
    - "Change tomorrow's standup to 11 AM instead"
    - "Add jasmine@gmail.com to the project review meeting"
    """)
