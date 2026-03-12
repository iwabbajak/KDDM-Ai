# 🧠 Local LLM Flask Server (Mini ChatGPT)

A lightweight **local ChatGPT-style server** built with:

- 🐍 **Python + Flask**
- 🧠 **llama.cpp via llama-cpp-python**
- 🐳 **Docker containerization**
- 💬 **Streaming browser chat UI**

This project allows you to run a **local Large Language Model (LLM)** such as **Mistral GGUF** completely offline.

Perfect for:

- Private AI assistants
- Offline AI environments
- Personal AI experimentation
- Local development with LLMs
- Privacy-focused deployments

---

# 📌 Architecture

```
Browser UI
     │
     ▼
Flask Web Server
     │
     ▼
llama-cpp-python
     │
     ▼
GGUF Model (Mistral / Llama)
```

---

# ✨ Features

✔ Local LLM server  
✔ ChatGPT-style browser interface  
✔ Streaming responses (SSE)  
✔ Docker support  
✔ Fully offline capable  
✔ Lightweight Flask backend  
✔ Configurable via environment variables  

---

# 📂 Repository Structure
```
local-llm-flask/
│
├── app.py # Flask LLM server
├── Dockerfile # Docker build instructions
├── requirements.txt # Python dependencies
│
├── models/ # GGUF models directory
│
├── static/
│ ├── logo.png
│ └── logo.ico
│
└── README.md
```

---

# ⚙️ Requirements

Minimum requirements depend on the model you run.

| RAM | Recommended Model |
|----|------------------|
8 GB | 3B / 4B models |
16 GB | 7B models |
32 GB | 13B models |

Supported model formats:

- GGUF
- llama.cpp compatible models

Examples:

- Mistral
- LLaMA
- Mixtral

---

# 📥 Download a Model

Create a models directory:

```bash
mkdir models
cd models

Download a GGUF model from:
https://huggingface.co/TheBloke
Example file:
mistral.gguf
```

# 🐳 Build the Docker Image

```bash

From the project root:
docker build -t local-llm-flask .

▶ Run the Server
docker run --rm -it \
-p 8000:8000 \
-e MODEL_PATH=/workspace/models/mistral.gguf \
-e CTX=4096 \
-e THREADS=4 \
-e N_GPU_LAYERS=0 \
-e CHAT_FORMAT=mistral-instruct \
local-llm-flask:latest
```
# 🌐 Access the Web Interface
Once the container is running, open:
http://localhost:8000


# 🖥️ Running Without Docker

Install dependencies:
pip install -r requirements.txt
Run the server:
python app.py
Then open:
http://localhost:8000

# 🚀 Performance Tips

Recommended models based on system RAM:
RAM	Recommended Model
8GB	3B – 7B models
16GB	7B – 13B models
32GB+	13B+ models
Common quantization formats:
Q4_K_M  (balanced speed and quality)
Q5_K_M  (better quality)
Q8_0    (highest quality)

# 🔒 Security Notes

This server is intended for local use.
If exposing publicly:
Add authentication
Use HTTPS
Place behind a reverse proxy (Nginx / Traefik)

# 🧩 Future Improvements
Potential features:
Authentication
Conversation memory
Vector database integration
Document search (RAG)
Mobile optimized UI

# 👤 Author
Created by Jak

⭐ If you find this project useful, consider giving it a star on GitHub.
