import streamlit as st
import requests
import json
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid

st.set_page_config(page_title="ChatBot Assistant", layout="wide")

# =========================== API Configuration ===========================
API_BASE = "http://localhost:8000"

# =========================== Utilities ===========================
def generate_thread_id():
    return str(uuid.uuid4())

def reset_chat():
    """Create new chat thread via API"""
    try:
        response = requests.post(f"{API_BASE}/threads")
        if response.status_code == 200:
            data = response.json()
            st.session_state["thread_id"] = data["thread_id"]
            st.session_state["message_history"] = []
            st.rerun()
    except Exception as e:
        st.error(f"Error creating new chat: {e}")

def load_threads_from_api():
    """Load all threads from API"""
    try:
        response = requests.get(f"{API_BASE}/threads")
        if response.status_code == 200:
            data = response.json()
            return data["threads"]
    except Exception as e:
        st.error(f"Error loading threads: {e}")
    return []

def load_conversation_from_api(thread_id):
    """Load conversation history from API"""
    try:
        response = requests.get(f"{API_BASE}/threads/{thread_id}/messages")
        if response.status_code == 200:
            data = response.json()
            return data["messages"]
    except Exception as e:
        st.error(f"Error loading conversation: {e}")
    return []

def delete_thread_from_api(thread_id):
    """Delete thread via API"""
    try:
        response = requests.delete(f"{API_BASE}/threads/{thread_id}")
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting thread: {e}")
    return False

def send_message_to_api(message, thread_id):
    """Send message to API and get streaming response"""
    try:
        response = requests.post(
            f"{API_BASE}/chat",
            json={"message": message, "thread_id": thread_id},
            stream=True
        )
        return response
    except Exception as e:
        st.error(f"Error sending message: {e}")
        return None

def get_thread_name(messages):
    """Generate a name for the thread based on first message"""
    for msg in messages:
        if msg.get("role") == "user":
            words = msg["content"].split()
            return " ".join(words[:5]) + ("..." if len(words) > 5 else "")
    return "New Chat"

# ======================= Session Initialization ===================
if "message_history" not in st.session_state:
    st.session_state["message_history"] = []

if "thread_id" not in st.session_state:
    # Try to create new thread on startup
    reset_chat()

# Load threads from API
st.session_state["chat_threads"] = load_threads_from_api()

# ============================ Sidebar ============================
st.sidebar.title("AI Agent Chatbot 🤖")

if st.sidebar.button("➕ New Chat", key="new_chat_btn"):
    reset_chat()

st.sidebar.header("My Conversations 🗂️")

for thread in sorted(st.session_state["chat_threads"], key=lambda x: x["thread_id"], reverse=True):
    thread_id = thread["thread_id"]
    thread_name = thread["name"]

    cols = st.sidebar.columns([4, 1])
    
    # Select Thread Button
    if cols[0].button(f"💬 {thread_name}", key=f"thread_{thread_id}"):
        st.session_state["thread_id"] = thread_id
        messages = load_conversation_from_api(thread_id)
        st.session_state["message_history"] = messages
        st.rerun()

    # Delete Thread Button
    if cols[1].button("❌", key=f"delete_{thread_id}"):
        if delete_thread_from_api(thread_id):
            # Remove from session threads
            st.session_state["chat_threads"] = [
                t for t in st.session_state["chat_threads"] 
                if t["thread_id"] != thread_id
            ]
            
            # If deleted thread was current, create new chat
            if st.session_state["thread_id"] == thread_id:
                reset_chat()
            else:
                st.sidebar.success("Deleted!")
                st.rerun()

# ============================ Main UI ============================
st.title("NexaAgent 🧠⚡ – Agentic AI Chatbot")

chat_container = st.container()

with chat_container:
    for message in st.session_state["message_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

user_input = st.chat_input("Type here… ✍️")

if user_input:
    # Add user message to chat
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Get response from API
    with st.chat_message("assistant"):
        full_response = ""
        placeholder = st.empty()
        
        # Send message to API
        response = send_message_to_api(user_input, st.session_state["thread_id"])
        
        if response:
            # Process streaming response
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            
                            if data.get("type") == "chunk":
                                full_response += data.get("content", "")
                                placeholder.markdown(full_response)
                            elif data.get("type") == "complete":
                                full_response = data.get("content", "")
                                placeholder.markdown(full_response)
                                break
                            elif data.get("type") == "error":
                                full_response = f"Error: {data.get('content', 'Unknown error')}"
                                placeholder.markdown(full_response)
                                break
                        except json.JSONDecodeError:
                            continue
        
        # Add assistant response to history
        if full_response:
            st.session_state["message_history"].append({"role": "assistant", "content": full_response})
        
        # Reload threads to update names
        st.session_state["chat_threads"] = load_threads_from_api()
        st.rerun()

