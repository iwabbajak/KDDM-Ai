import os
import json
import logging
import threading
from typing import List, Dict, Generator, Optional
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# IMPORTANT: pin a known good version in requirements.txt, e.g.:
# llama-cpp-python==0.2.90
try:
    from llama_cpp import Llama, __version__ as LLAMA_CPP_PY_VERSION
except Exception as e:
    raise RuntimeError(f"Failed to import llama_cpp: {e}")

# -------------------
# Config via env vars
# -------------------
MODEL_PATH = os.getenv("MODEL_PATH", "/workspace/models/mistral.gguf")
CTX = int(os.getenv("CTX", "4096"))
THREADS = int(os.getenv("THREADS", "4"))
N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", "0"))
CHAT_FORMAT = os.getenv("CHAT_FORMAT", "mistral-instruct")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant. Be concise and accurate.")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
TOP_P = float(os.getenv("TOP_P", "0.9"))

# -------------------
# App init
# -------------------
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = app.logger

# Load model once at startup
log.info(f"[init] Loading model from: {MODEL_PATH}")
try:
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=CTX,
        n_threads=THREADS,
        n_gpu_layers=N_GPU_LAYERS,
        chat_format=CHAT_FORMAT,  # works for instruct/chat GGUFs
        verbose=False
    )
    HAS_CHAT = hasattr(llm, "create_chat_completion")
    log.info(f"[init] llama-cpp-python={LLAMA_CPP_PY_VERSION} | HAS_CHAT={HAS_CHAT} | CHAT_FORMAT={CHAT_FORMAT}")
except Exception as e:
    log.exception("[init] Failed to load model")
    raise


llm_lock = threading.Lock()

def build_messages(user_message: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_message})
    return msgs

def chat_complete(messages: List[Dict[str, str]], max_tokens: int, temperature: float, top_p: float) -> str:

    with llm_lock:

        if HAS_CHAT:
            result = llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p
            )
            return result["choices"][0]["message"]["content"]

        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        prompt = f"<<SYS>>\n{sys_msg}\n<</SYS>>\n\n[INST] {last_user} [/INST]\n"

        result = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p
        )

        return result["choices"][0]["text"]
    
@app.get("/health")
def health():
    return jsonify({"status": "ok", "model": os.path.basename(MODEL_PATH)})

@app.get("/version")
def version():
    return jsonify({
        "llama_cpp_python": LLAMA_CPP_PY_VERSION,
        "chat_format": CHAT_FORMAT,
        "has_chat_api": HAS_CHAT
    })

@app.post("/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    history = data.get("history", [])
    max_tokens = int(data.get("max_tokens", MAX_TOKENS))
    temperature = float(data.get("temperature", TEMPERATURE))
    top_p = float(data.get("top_p", TOP_P))

    msgs = build_messages(message, history)
    log.info(f"[chat] tokens={max_tokens} temp={temperature} top_p={top_p} hist={len(history)}")

    try:
        reply = chat_complete(msgs, max_tokens, temperature, top_p)
        return jsonify({"reply": reply})
    except Exception as e:
        log.exception("[chat] Generation failed")
        return jsonify({"error": str(e)}), 500

@app.post("/chat/stream")
def chat_stream():

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400

    history = data.get("history", [])
    max_tokens = int(data.get("max_tokens", MAX_TOKENS))
    temperature = float(data.get("temperature", TEMPERATURE))
    top_p = float(data.get("top_p", TOP_P))

    msgs = build_messages(message, history)

    log.info(f"[stream] tokens={max_tokens} temp={temperature} top_p={top_p} hist={len(history)}")

    if not HAS_CHAT:
        try:
            text = chat_complete(msgs, max_tokens, temperature, top_p)

            def one_shot():
                yield f"data: {json.dumps({'token': text})}\n\n"
                yield "event: done\ndata: {}\n\n"

            resp = Response(stream_with_context(one_shot()), mimetype="text/event-stream")

        except Exception as e:
            resp = Response(f"data: {json.dumps({'error': str(e)})}\n\n", mimetype="text/event-stream")

        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp


    # ✅ STREAMING CASE
    def generate():

        try:

            with llm_lock:

                for chunk in llm.create_chat_completion(
                    messages=msgs,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stream=True
                ):

                    delta = chunk["choices"][0]["delta"].get("content", "")

                    if delta:
                        yield f"data: {json.dumps({'token': delta})}\n\n"

        except GeneratorExit:
            pass

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "event: done\ndata: {}\n\n"


    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")

    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"

    return resp

# ----- Minimal modern UI (served locally) -----
INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />

<!-- MOBILE RESPONSIVE -->
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>K.D.D.M. AI</title>
<link rel="icon" type="image/x-icon" href="/static/logo.ico">

<style>
:root{
  --bg:#f5f6fa;
  --text:#2d3436;
  --user:#dfe6e9;
  --asst:#0084FF;
  --border:#dcdde1;
  --radius:14px;
}

*{box-sizing:border-box}

body{
  margin:0;
  background:var(--bg);
  font:16px/1.5 system-ui,sans-serif;
  height:100vh;
  display:flex;
  flex-direction:column;
}

/* HEADER */

header{
  display:flex;
  align-items:center;
  gap:10px;
  padding:12px 16px;
  background:#fff;
  border-bottom:1px solid var(--border);
  font-weight:600;
}

.header-logo{
  width:36px;
  height:36px;
  object-fit:contain;
}

/* CHAT AREA */

#log{
  flex:1;
  padding:16px;
  overflow:auto;
}

/* MESSAGE BUBBLES */

.msg{
  max-width:70%;
  padding:12px 14px;
  margin:6px 0;
  border-radius:var(--radius);
  white-space:pre-wrap;
  word-wrap:break-word;
}

.user{
  margin-left:auto;
  background:var(--user);
}

.assistant{
  margin-right:auto;
  background:var(--asst);
  color:#fff;
}

/* INPUT BAR */

.input-bar{
  display:flex;
  gap:8px;
  padding:10px;
  background:#fff;
  border-top:1px solid var(--border);
}

#prompt{
  flex:1;
  padding:12px;
  border:1px solid var(--border);
  border-radius:var(--radius);
  font-size:16px;
}

/* BUTTONS */

button{
  padding:12px 16px;
  border:0;
  border-radius:var(--radius);
  background:#0084FF;
  color:#fff;
  cursor:pointer;
  font-size:15px;
}

button:hover{
  opacity:0.9;
}

.reset{
  background:#d63031;
}

.small{
  font-size:12px;
  color:#636e72;
  margin-left:auto;
}

/* ---------- MOBILE ---------- */

@media (max-width:600px){

  header{
    font-size:15px;
  }

  .msg{
    max-width:85%;
    font-size:15px;
  }

  .input-bar{
    padding:8px;
  }

  #prompt{
    font-size:16px;
  }

  button{
    padding:10px 12px;
    font-size:14px;
  }

}

/* ---------- LARGE SCREENS ---------- */

@media (min-width:1200px){

  #log{
    max-width:900px;
    margin:auto;
    width:100%;
  }

}
</style>
</head>

<body>

<header>
<img src="/static/logo.png" class="header-logo">
K.D.D.M Ai
<span class="small" id="modelInfo"></span>

</header>

<div id="log"></div>

<div class="input-bar">
<input id="prompt" placeholder="Type your message..." />
<button onclick="send()">Send</button>
<button class="reset" onclick="resetChat()">Reset</button>
</div>

<script>

let history=[];

function add(role,text){
  const log=document.getElementById('log');
  const div=document.createElement('div');
  div.className='msg '+role;
  div.textContent=text;
  log.appendChild(div);
  log.scrollTop=log.scrollHeight;
  return div;
}

async function send(){

  const inp=document.getElementById('prompt');
  const text=inp.value.trim();

  if(!text) return;

  add('user',text);
  inp.value='';

  const cur=add('assistant','');

  try{

    const res=await fetch('/chat/stream',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text,history})
    });

    if(!res.ok || !res.body) throw new Error('stream unavailable');

    const reader=res.body.getReader();
    const decoder=new TextDecoder('utf-8');

    let assistant='';

    while(true){

      const {value,done}=await reader.read();

      if(done || !value) break;

      const chunk=decoder.decode(value,{stream:true});
      const events=chunk.split("\\n\\n").filter(Boolean);

      for(const evt of events){

        if(evt.startsWith('data: ')){

          const payload=JSON.parse(evt.slice(6));

          if(payload.token){
            assistant+=payload.token;
            cur.textContent=assistant;
          }

          if(payload.error){
            cur.textContent='[Error] '+payload.error;
          }

        }

      }

    }

    history.push({role:'user',content:text});
    history.push({role:'assistant',content:cur.textContent});

  }catch(e){

    const res=await fetch('/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text,history})
    });

    const js=await res.json();

    cur.textContent=js.reply || js.error || '[error]';

    history.push({role:'user',content:text});
    history.push({role:'assistant',content:cur.textContent});

  }

}

function resetChat(){
  history=[];
  document.getElementById('log').innerHTML='';
}

(async function info(){

  try{

    const r=await fetch('/version');
    const j=await r.json();

    document.getElementById('modelInfo').textContent=`Knowledge Driven & Decision Model AI ` +
      `(llama-cpp-python ${j.llama_cpp_python})`;

  }catch{}

})();

</script>

</body>
</html>
"""

@app.get("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

if __name__ == "__main__":
    # Unbuffered logs inside Docker recommended (-u also works)
    app.run(host="0.0.0.0", port=8000)