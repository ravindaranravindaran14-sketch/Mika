"""
main.py — Mika backend API.

One server, two ways in:
  - WebSocket /ws/{user_id}   -> for the avatar app (low-latency, streaming-ready)
  - HTTP POST /chat/{user_id} -> for anything simpler (e.g. a Telegram bot later)

Both paths call the SAME generate_reply() function, so the same memory and
the same personality show up everywhere the user talks to Mika.

Run:
  pip install -r requirements.txt
  export OPENAI_API_KEY=sk-...
  uvicorn main:app --reload --port 8000
"""

import os
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from memory import MemoryStore

app = FastAPI(title="Mika Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before shipping anywhere real
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
memory = MemoryStore("memory.db")

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "You are Mika, a warm, upbeat AI companion who talks to the user through "
    "a phone app and remembers past conversations. Keep replies short and "
    "spoken-friendly (1-3 sentences) since they'll be read aloud by "
    "text-to-speech. Use the 'known facts' below to personalize your "
    "replies, and when the user tells you something worth remembering "
    "long-term (their name, preferences, routines), call remember_fact."
)

# ---- function-calling schema: what Mika is allowed to "do" ----
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Schedule a reminder for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to remind them about"},
                    "when": {"type": "string", "description": "When, in natural language or ISO 8601"},
                },
                "required": ["text", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Set an alarm at a specific time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "description": "e.g. '7:00 AM'"},
                },
                "required": ["time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Save a durable fact about the user for future conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "A short, standalone fact, e.g. 'User's name is Alex'"},
                },
                "required": ["fact"],
            },
        },
    },
]


def execute_action(name: str, args: dict, user_id: str) -> str:
    """
    Runs the action and returns a short result string fed back to the model.
    Right now these just log to memory — wire them to real device/Telegram
    actions (Android intents, Telegram scheduled messages, etc.) later.
    """
    if name == "set_reminder":
        memory.add_action(user_id, "reminder", args)
        return f"Reminder saved: '{args['text']}' at {args['when']}."
    if name == "set_alarm":
        memory.add_action(user_id, "alarm", args)
        return f"Alarm saved for {args['time']}."
    if name == "remember_fact":
        memory.add_fact(user_id, args["fact"])
        return f"Noted: {args['fact']}"
    return f"Unknown action: {name}"


def generate_reply(user_id: str, user_message: str):
    history = memory.get_recent_messages(user_id, limit=20)
    facts = memory.get_facts(user_id)

    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nKnown facts about this user:\n{facts}"}
    ]
    messages += history
    messages.append({"role": "user", "content": user_message})

    resp = client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
    )
    msg = resp.choices[0].message

    action_result = None
    if msg.tool_calls:
        messages.append(msg)
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = execute_action(call.function.name, args, user_id)
            action_result = action_result or result
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )
        # let the model phrase a natural reply that reflects the action taken
        resp2 = client.chat.completions.create(model=MODEL, messages=messages)
        reply_text = resp2.choices[0].message.content
    else:
        reply_text = msg.content

    memory.add_message(user_id, "user", user_message)
    memory.add_message(user_id, "assistant", reply_text)

    return reply_text, action_result


@app.get("/")
def health():
    return {"status": "ok", "service": "mika-backend"}


@app.post("/chat/{user_id}")
async def chat_http(user_id: str, payload: dict):
    user_message = payload.get("message", "")
    reply, action = generate_reply(user_id, user_message)
    return {"reply": reply, "action": action}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            user_message = payload.get("message", "")
            reply, action = generate_reply(user_id, user_message)
            await websocket.send_text(json.dumps({"reply": reply, "action": action}))
    except WebSocketDisconnect:
        pass
