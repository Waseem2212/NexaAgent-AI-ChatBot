from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from dotenv import load_dotenv
import sqlite3
import uuid
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

load_dotenv()

# -------------------
# FastAPI App Setup
# -------------------
app = FastAPI(title="LangGraph Chatbot API", version="1.0.0")

# Pydantic models for request/response bodies (simple data validation)
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None

class ThreadResponse(BaseModel):
    thread_id: str

class MessageResponse(BaseModel):
    role: str
    content: str

class MessagesResponse(BaseModel):
    messages: List[MessageResponse]

class ThreadInfo(BaseModel):
    thread_id: str
    name: str

class ThreadsResponse(BaseModel):
    threads: List[ThreadInfo]

class DeleteResponse(BaseModel):
    success: bool

# -------------------
# 1. LLM (Language Model)
# -------------------
llm = ChatGroq(model="moonshotai/kimi-k2-instruct-0905")

# -------------------
# 2. Tools (Search and Calculator)
# -------------------
search_tool = DuckDuckGoSearchRun(region="us-en")

@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """Perform a basic arithmetic operation on two numbers."""
    try:
        if operation == "add": result = first_num + second_num
        elif operation == "sub": result = first_num - second_num
        elif operation == "mul": result = first_num * second_num
        elif operation == "div":
            if second_num == 0: return {"error": "Division by zero"}
            result = first_num / second_num
        else: return {"error": f"Unsupported operation '{operation}'"}
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

tools = [search_tool, calculator]
llm_with_tools = llm.bind_tools(tools)

# -------------------
# 3. State (Conversation State)
# -------------------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# -------------------
# 4. Nodes (Graph Processing Logic)
# -------------------
def chat_node(state: ChatState):
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)

# -------------------
# 5. Checkpointer (Memory Storage)
# -------------------
conn = sqlite3.connect(database="chatbot.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)

# -------------------
# 6. Graph (Conversation Flow)
# -------------------
graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge('tools', 'chat_node')
chatbot = graph.compile(checkpointer=checkpointer)

# -------------------
# 7. Helper Functions
# -------------------
def retrieve_all_threads():
    """Get all thread IDs from database"""
    all_threads = set()
    try:
        for checkpoint in checkpointer.list(None):
            t_id = checkpoint.config["configurable"]["thread_id"]
            if t_id:
                all_threads.add(t_id)
    except sqlite3.OperationalError:
        return []
    return list(all_threads)

def delete_thread(thread_id):
    """Delete a thread and all its data from database"""
    try:
        t_id_str = str(thread_id)
        cursor = conn.cursor()
        
        tables = ["checkpoints", "checkpoint_writes", "checkpoint_blobs"]
        
        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table} WHERE thread_id = ?", (t_id_str,))
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    continue
                else:
                    raise e
                    
        conn.commit()
        print(f"Successfully deleted thread: {t_id_str}")
        return True
    except Exception as e:
        print(f"Error deleting thread: {e}")
        return False

def load_conversation(thread_id):
    """Load conversation history for a specific thread"""
    try:
        state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
        return state.values.get("messages", [])
    except Exception:
        return []

def get_thread_name(messages):
    """Generate a name for the thread based on first message"""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            words = msg.content.split()
            return " ".join(words[:5]) + ("..." if len(words) > 5 else "")
    return "New Chat"

# -------------------
# 8. FastAPI Endpoints
# -------------------

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Send a message and get streaming response from chatbot
    Body: {"message": "your message", "thread_id": "optional_thread_id"}
    Returns: Server-sent events stream
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    async def generate_response():
        """Generator function for streaming response"""
        try:
            full_response = ""
            for message_chunk, metadata in chatbot.stream(
                {"messages": [HumanMessage(content=request.message)]},
                config=config,
                stream_mode="messages",
            ):
                if isinstance(message_chunk, AIMessage) and message_chunk.content:
                    chunk_data = {
                        "type": "chunk",
                        "content": message_chunk.content,
                        "thread_id": thread_id
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    full_response += message_chunk.content
            
            complete_data = {
                "type": "complete",
                "content": full_response,
                "thread_id": thread_id
            }
            yield f"data: {json.dumps(complete_data)}\n\n"
            
        except Exception as e:
            error_data = {
                "type": "error",
                "content": str(e),
                "thread_id": thread_id
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@app.post("/threads", response_model=ThreadResponse)
async def create_thread():
    """
    Create a new chat thread
    Returns: {"thread_id": "new_uuid"}
    """
    thread_id = str(uuid.uuid4())
    return {"thread_id": thread_id}

@app.get("/threads", response_model=ThreadsResponse)
async def get_threads():
    """
    Get all chat threads with their names
    Returns: {"threads": [{"thread_id": "", "name": ""}]}
    """
    all_thread_ids = retrieve_all_threads()
    threads_info = []
    
    for thread_id in all_thread_ids:
        messages = load_conversation(thread_id)
        thread_name = get_thread_name(messages)
        threads_info.append({
            "thread_id": thread_id,
            "name": thread_name
        })
    
    threads_info.sort(key=lambda x: x["thread_id"], reverse=True)
    
    return {"threads": threads_info}

@app.get("/threads/{thread_id}/messages", response_model=MessagesResponse)
async def get_thread_messages(thread_id: str):
    """
    Get conversation history for a specific thread
    Returns: {"messages": [{"role": "user/assistant", "content": ""}]}
    """
    messages = load_conversation(thread_id)
    
    formatted_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            formatted_messages.append({
                "role": "user",
                "content": msg.content
            })
        elif isinstance(msg, AIMessage) and msg.content:
            formatted_messages.append({
                "role": "assistant", 
                "content": msg.content
            })
    
    return {"messages": formatted_messages}

@app.delete("/threads/{thread_id}", response_model=DeleteResponse)
async def delete_thread_endpoint(thread_id: str):
    """
    Delete a specific thread and all its data
    Returns: {"success": true/false}
    """
    success = delete_thread(thread_id)
    return {"success": success}

# -------------------
# 9. Run Server
# -------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
