# Mika Backend

The shared "brain" for your assistant: one server, called by both the phone/web
avatar and (later) a Telegram bot, so memory and personality stay consistent
across both.

## Setup

```bash
cd mika-backend
pip install -r requirements.txt
export OPENAI_API_KEY=sk-your-key-here
uvicorn main:app --reload --port 8000
```

Server now runs at `http://localhost:8000` (and `ws://localhost:8000/ws/{user_id}`).

## Try it

```bash
curl -X POST http://localhost:8000/chat/test-user \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi, I'\''m Alex. Can you remind me to call mom at 6pm?"}'
```

You should get back a reply, and `memory.db` (created automatically) will now
have a saved fact ("User's name is Alex") and a logged reminder action.
Send another message later in the same `test-user` thread and Mika will
remember Alex's name without being told again.

## Deploying on Render (no laptop needed)

1. Push this folder to a GitHub repo (GitHub's web "Upload files" works fine from a phone browser — no git required).
2. On [render.com](https://render.com): **New → Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT` (also set via the included `Procfile`)
5. In the service's **Environment** tab, add `OPENAI_API_KEY` with your key.
6. Deploy. You'll get a public URL like `https://mika-backend.onrender.com`.

Free tier spins down after ~15 min idle and takes ~30s to wake on the next
request — normal, not a bug.

Once deployed, use that URL everywhere you'd have used `localhost:8000`:
`https://mika-backend.onrender.com/chat/test-user` and
`wss://mika-backend.onrender.com/ws/your-user-id`.

## Connecting the avatar prototype

In `anime-ai-assistant.html`, replace the `handleSend()` function's local
`handleUserMessage()` call with a WebSocket call to this server:

```js
const ws = new WebSocket(
  "wss://mika-backend.onrender.com/ws/your-user-id"
);
ws.onmessage = (e) => {
  const { reply, action } = JSON.parse(e.data);
  say(reply);
  if (action) showToast(action);
};

function handleSend(msg) {
  if (!msg.trim()) return;
  setStatus('thinking');
  ws.send(JSON.stringify({ message: msg.trim() }));
}
```

(For a real phone build, point this at your deployed server's `wss://` URL
instead of localhost.)

## What's stubbed vs. real

| Piece | Status |
|---|---|
| GPT conversation + memory | Real — actually calls OpenAI |
| Short-term memory (recent messages) | Real — SQLite |
| Long-term memory (facts) | Real — SQLite, model decides what to save |
| `set_alarm` / `set_reminder` | Logged to DB only — wire to Android intents or a scheduler to actually fire |
| Telegram | Not yet built — next step, see below |
| Voice in/out | Not yet built — add streaming STT/TTS (Deepgram, ElevenLabs) around the same `generate_reply()` function |

## Next step: Telegram

A Telegram bot is a thin client on top of this same server — it just calls
`POST /chat/{telegram_user_id}` for every incoming message and sends back
`reply`. Say the word and I'll build `telegram_bot.py` next, using the same
`generate_reply` logic so a user's memory carries over between the phone app
and Telegram.
