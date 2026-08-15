TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a Windows shell command (PowerShell). Use for: running scripts, pip install, file operations, system info, running Python scripts. For multi-line Python, create a .py file first then run it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120)",
                        "default": 120
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read the contents of a file at the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Full path to the file"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Create or overwrite a file with the specified content. Creates parent directories automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Full path to the file"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "quantum",
            "description": "Quantum computing module. CRITICAL RULE: ALWAYS start with mode='bell' (simulator, no token). NEVER use mode='real' unless simulator mode='bell' succeeded first. If user wants real hardware, first prove simulator works, THEN ask for their ibm_token.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["bell", "noise", "real"],
                        "description": "bell = basic Bell state on local simulator (no key needed). noise = simulation with depolarizing noise model. real = ONLY if simulator works вЂ” real IBM Quantum device (requires ibm_token from user)."
                    },
                    "ibm_token": {
                        "type": "string",
                        "description": "IBM Quantum API token. REQUIRED for mode='real'. Ask the user if not provided."
                    },
                    "noise_path": {
                        "type": "string",
                        "description": "Path to a noise model JSON file. Used only with mode='noise'. If empty, uses default depolarizing noise (p=0.01)."
                    },
                    "shots": {
                        "type": "integer",
                        "description": "Number of measurement shots (default: 1024).",
                        "default": 1024
                    }
                },
                "required": ["mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Search for files by glob pattern. Use ** for recursive search. Examples: '**/*.py', '*.json', 'quantum_kit/**'",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files (e.g. '**/*.py', '*.json', 'quantum_kit/**')"
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory (default: current working directory)"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents by regex pattern. Shows filename, line number, and matching line. Use to find function definitions, imports, error sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search (e.g. 'def quantum', 'import qiskit', 'class.*Handler')"
                    },
                    "include": {
                        "type": "string",
                        "description": "File glob filter (e.g. '*.py', '*.{py,json}'). Default: all files."
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory (default: current working directory)"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "automator",
            "description": "Launch Project Automator with an instruction file. Automator generates full project code from a natural language description. Use for: creating new projects, generating boilerplate, scaffolding apps. Write instruction to a file first, then call this tool with the path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction_path": {
                        "type": "string",
                        "description": "Full path to the instruction file (.txt or .md) describing the project to generate."
                    }
                },
                "required": ["instruction_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "quantum_simulator",
            "description": "Run user-provided Python quantum code on a local simulator. Supports Qiskit (AerSimulator) or PennyLane (default.qubit). The code MUST create a variable named 'qc' (QuantumCircuit for Qiskit or a QNode function for PennyLane). Returns beautiful Markdown with state percentages and a visual bar chart. ALWAYS prefer this for custom quantum circuits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quantum_code": {
                        "type": "string",
                        "description": "Python code that creates a quantum circuit. For Qiskit: must end with 'qc = QuantumCircuit(...)'. For PennyLane: must define a function 'qc()' decorated with @qml.qnode."
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["qiskit", "pennylane"],
                        "description": "Quantum framework to use. 'qiskit' (default) or 'pennylane'."
                    },
                    "shots": {
                        "type": "integer",
                        "description": "Number of measurement shots (default: 1024).",
                        "default": 1024
                    }
                },
                "required": ["quantum_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "draw_circuit",
            "description": "Generate an ASCII text diagram of a quantum circuit from user-provided Python code. The code MUST create a variable named 'qc' of type QuantumCircuit (Qiskit). Returns a text-based circuit diagram showing qubits, gates, and measurements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quantum_code": {
                        "type": "string",
                        "description": "Python code that creates a QuantumCircuit variable named 'qc'. Example: from qiskit import QuantumCircuit; qc = QuantumCircuit(2,2); qc.h(0); qc.cx(0,1); qc.measure([0,1],[0,1])"
                    }
                },
                "required": ["quantum_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_result",
            "description": "Parse raw quantum simulation results (counts dict) into a beautifully formatted Markdown report with state percentages and visual bars. Use when you have raw counts data from any source and want a human-readable summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_result": {
                        "type": "string",
                        "description": "JSON string or dict with quantum results. Format: {\"success\": true, \"counts\": {\"00\": 523, \"11\": 501}, \"metadata\": {\"shots\": 1024, \"simulator\": \"AerSimulator\"}}"
                    }
                },
                "required": ["raw_result"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_backends",
            "description": "Connect to IBM Quantum OR Quantum Inspire and list all available backends with specs. For IBM: provide ibm_api_key. For Quantum Inspire: provide qi_api_token (or qi_email + qi_password). Returns backend names, qubit counts, type (real vs simulator/emulator), and status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ibm_api_key": {
                        "type": "string",
                        "description": "IBM Quantum API token. For IBM backends. Get from https://quantum.ibm.com в†’ API Token"
                    },
                    "qi_api_token": {
                        "type": "string",
                        "description": "Quantum Inspire API Token (recommended for QI). Get from quantum-inspire.com dashboard."
                    },
                    "qi_email": {
                        "type": "string",
                        "description": "Quantum Inspire account email. Use with password if no API token."
                    },
                    "qi_password": {
                        "type": "string",
                        "description": "Quantum Inspire account password."
                    }
                },
                "anyOf": [
                    {"required": ["ibm_api_key"]},
                    {"required": ["qi_api_token"]},
                    {"required": ["qi_email", "qi_password"]}
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transpile_circuit",
            "description": "Transpile (adapt) a quantum circuit for a specific backend. For IBM: provide quantum_code (Python) + ibm_api_key. For Quantum Inspire: provide qasm_code (OpenQASM 2.0) + qi_api_token or qi_email+password. Returns gate counts before/after, SWAP gates added, final depth, and ASCII diagram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quantum_code": {
                        "type": "string",
                        "description": "Python code that creates a QuantumCircuit variable named 'qc'. Use for IBM backends."
                    },
                    "qasm_code": {
                        "type": "string",
                        "description": "OpenQASM 2.0 code for the quantum circuit. Use for Quantum Inspire backends."
                    },
                    "backend_name": {
                        "type": "string",
                        "description": "Backend name (e.g. 'ibm_brisbane' for IBM, 'QX single-node simulator' for QI). Default: ibm_brisbane.",
                        "default": "ibm_brisbane"
                    },
                    "ibm_api_key": {
                        "type": "string",
                        "description": "IBM Quantum API token. For IBM backends."
                    },
                    "qi_api_token": {
                        "type": "string",
                        "description": "Quantum Inspire API Token. For QI backends."
                    },
                    "qi_email": {
                        "type": "string",
                        "description": "Quantum Inspire account email. Use with password."
                    },
                    "qi_password": {
                        "type": "string",
                        "description": "Quantum Inspire account password."
                    }
                },
                "anyOf": [
                    {"required": ["quantum_code", "ibm_api_key"]},
                    {"required": ["qasm_code", "qi_api_token"]},
                    {"required": ["qasm_code", "qi_email", "qi_password"]}
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_on_real",
            "description": "Submit a quantum circuit to a real IBM quantum computer for execution. The code MUST create a variable named 'qc' (QuantumCircuit). Connects to IBM Quantum, transpiles the circuit, runs it on the specified backend, waits for results, and returns beautiful Markdown. REQUIRES ibm_api_key. CRITICAL: Always call get_backends first to confirm which backends are operational, then pick one with shortest queue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quantum_code": {
                        "type": "string",
                        "description": "Python code that creates a QuantumCircuit variable named 'qc' with measurements."
                    },
                    "ibm_api_key": {
                        "type": "string",
                        "description": "IBM Quantum API token. REQUIRED."
                    },
                    "backend_name": {
                        "type": "string",
                        "description": "IBM Quantum backend name (e.g. ibm_brisbane). Default: ibm_brisbane.",
                        "default": "ibm_brisbane"
                    },
                    "shots": {
                        "type": "integer",
                        "description": "Number of shots (default: 1024, max depends on backend).",
                        "default": 1024
                    }
                },
                "required": ["quantum_code", "ibm_api_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_on_quantum_inspire",
            "description": "Submit QASM 2.0 code to Quantum Inspire (emulator or real hardware). Supports two auth methods: API Token (recommended) OR Email+Password. Automatically fixes common QASM syntax errors (measure, missing semicolons, etc). Returns beautiful Markdown with results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "qasm_code": {
                        "type": "string",
                        "description": "OpenQASM 2.0 code for the quantum circuit. Must include qreg, creg, gates, and measure instructions."
                    },
                    "qi_api_token": {
                        "type": "string",
                        "description": "Quantum Inspire API Token (recommended). Get from quantum-inspire.com dashboard."
                    },
                    "qi_email": {
                        "type": "string",
                        "description": "Quantum Inspire account email. Use with password if no API token."
                    },
                    "qi_password": {
                        "type": "string",
                        "description": "Quantum Inspire account password. Use with email if no API token."
                    },
                    "shots": {
                        "type": "integer",
                        "description": "Number of measurement shots (default: 1024).",
                        "default": 1024
                    },
                    "backend_name": {
                        "type": "string",
                        "description": "Backend name on Quantum Inspire (default: 'QX single-node simulator').",
                        "default": "QX single-node simulator"
                    }
                },
                "required": ["qasm_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_error_mitigation",
            "description": "Apply error mitigation technique to a QASM quantum circuit: ZNE (Zero Noise Extrapolation), DD (Dynamical Decoupling), or 'none'. ZNE requires qiskit-experiments; DD requires qiskit. Returns estimated noise reduction and modified circuit info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "qasm_code": {
                        "type": "string",
                        "description": "OpenQASM 2.0 code for the quantum circuit."
                    },
                    "mitigation_technique": {
                        "type": "string",
                        "enum": ["ZNE", "DD", "none"],
                        "description": "Error mitigation technique: 'ZNE' (Zero Noise Extrapolation, needs qiskit-experiments), 'DD' (Dynamical Decoupling, needs qiskit), 'none' (no changes)."
                    },
                    "qi_api_token": {
                        "type": "string",
                        "description": "Quantum Inspire API Token (optional, for context)."
                    },
                    "qi_email": {
                        "type": "string",
                        "description": "Quantum Inspire account email (optional)."
                    },
                    "qi_password": {
                        "type": "string",
                        "description": "Quantum Inspire account password (optional)."
                    }
                },
                "required": ["qasm_code", "mitigation_technique"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_backends",
            "description": "Compare multiple Quantum Inspire backends side-by-side. Shows type (emulator/hardware), qubit count, status, and max shots. Returns a Markdown table with a recommendation for the best backend to use.",
            "parameters": {
                "type": "object",
                "properties": {
                    "backend_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of backend names to compare (e.g. ['QX single-node simulator', 'Starmon-5'])."
                    },
                    "qi_api_token": {
                        "type": "string",
                        "description": "Quantum Inspire API Token (recommended)."
                    },
                    "qi_email": {
                        "type": "string",
                        "description": "Quantum Inspire account email. Use with password."
                    },
                    "qi_password": {
                        "type": "string",
                        "description": "Quantum Inspire account password."
                    }
                },
                "required": ["backend_list"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "install_python_package",
            "description": "Install a Python package via pip into the current environment. Use when a ModuleNotFoundError occurs or a required library is missing. After successful installation, the agent should retry the original task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the Python package to install (e.g. 'quantuminspire', 'qiskit', 'qiskit-ibm-runtime')."
                    }
                },
                "required": ["package_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_dataset",
            "description": "Download a dataset from Hugging Face. Use when the user asks to download ML data, get a dataset for training, or load data from Hugging Face. Returns info about the dataset (records, columns, sample data).",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {
                        "type": "string",
                        "description": "Name of the dataset on Hugging Face, e.g. 'imdb', 'sst2', 'mnist', 'ag_news', 'tweet_eval'. Required."
                    },
                    "hf_token": {
                        "type": "string",
                        "description": "Hugging Face API token из боковой панели (поле Hugging Face Token). Можно не передавать — подставится автоматически из настроек пользователя."
                    }
                },
                "required": ["dataset_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_local_ml",
            "description": "Execute Python ML code locally using scikit-learn, pandas, numpy, matplotlib. Use when the user wants to train a model, evaluate metrics, make predictions, analyze data with pandas, or visualize results. The code runs in an isolated process with ML libraries pre-imported. IMPORTANT: if your code outputs a dict with accuracy/loss/confusion_matrix, it will be automatically formatted into a nice markdown report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ml_code": {
                        "type": "string",
                        "description": "Python code for ML. Can use np (numpy), pd (pandas), plt (matplotlib), sklearn, joblib. Examples: 'pd.read_csv(\"data.csv\").describe()', 'from sklearn.ensemble import RandomForestClassifier; model = RandomForestClassifier(); model.fit(X_train, y_train); print(model.score(X_test, y_test))'"
                    }
                },
                "required": ["ml_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_cloud_gpu_ml",
            "description": "Submit ML code to run on a cloud GPU (Kaggle). Use when the user wants to run ML on GPU, train large models, or when local resources are insufficient. Requires Kaggle API credentials (kaggle_username + kaggle_key) from https://www.kaggle.com/settings. Without credentials, returns instructions on how to get them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ml_code": {
                        "type": "string",
                        "description": "Python code for ML that will be executed on cloud GPU. Can use TensorFlow, PyTorch, scikit-learn, etc."
                    },
                    "kaggle_username": {
                        "type": "string",
                        "description": "Kaggle username из боковой панели (поле Kaggle API Key, формат username:key). Можно не передавать — подставится автоматически."
                    },
                    "kaggle_key": {
                        "type": "string",
                        "description": "Kaggle API key из боковой панели (поле Kaggle API Key, формат username:key). Можно не передавать — подставится автоматически."
                    }
                },
                "required": ["ml_code", "kaggle_username", "kaggle_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_ml_metrics",
            "description": "Parse raw ML metrics (accuracy, loss history, confusion matrix) into a beautiful markdown report. Use when the user has raw metrics data and wants a human-readable summary. Input should be a JSON or Python dict with keys like 'accuracy', 'loss', 'loss_history', 'confusion_matrix'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_metrics": {
                        "type": "string",
                        "description": "JSON string or Python dict representation of ML metrics. Example: '{\"accuracy\": 0.95, \"loss\": 0.05, \"loss_history\": [1.2, 0.8, 0.05], \"confusion_matrix\": [[50, 2], [3, 45]]}'"
                    }
                },
                "required": ["raw_metrics"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_ssh_ml",
            "description": "Execute Python ML code on a remote server via SSH. The tool FIRST automatically checks the server (OS, CPU, memory, Python, pip, GPU, installed packages) and returns [СЕРВЕР-ИНФО] — read it before writing code to see what the server actually has. Missing packages are auto-installed on the server via pip (up to 4 retries). If the server is not suitable (no Python, no pip, no GPU for a GPU task) — stop and tell the user which server is needed. Credentials are auto-injected from the sidebar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ml_code": {
                        "type": "string",
                        "description": "Python code for ML that will be executed on the remote server. Can use PyTorch, TensorFlow, JAX, scikit-learn, etc. Write clean Python code — no need for SSH setup commands. Use /tmp/... paths, not Windows-style paths."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 1800 = 30 min, max: 3600). Use 3600 for big dataset downloads.",
                        "default": 1800
                    }
                },
                "required": ["ml_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_modal_ml",
            "description": "Run ML code on cloud GPU via Modal.com. Use when: training large models (CNNs, Transformers), working with datasets >100k records, user requests GPU/cloud compute, or local resources are insufficient. The code runs on Modal's cloud infrastructure with GPU access. IMPORTANT: if your code has @app.function() or @app.local_entrypoint(), it will be used as-is. Otherwise the code is auto-wrapped. After successful run, analyze results and present them to the user. CRITICAL: if the run fails with ModuleNotFoundError or CUDA OOM, the system will self-heal and retry automatically. Modal credentials are auto-injected from the sidebar — do NOT ask the user to provide them in chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ml_code": {
                        "type": "string",
                        "description": "Python code for ML that will run on Modal cloud GPU. Can use PyTorch, TensorFlow, JAX, scikit-learn, etc. If your code defines @app.function or @app.local_entrypoint decorators, those are used. Otherwise a simple wrapper is auto-generated. Examples: 'import modal; app = modal.App(\"train\"); @app.function(gpu=\"A10G\")\\ndef train():\\n    import torch\\n    ...'"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 1800 = 30 min, max: 3600).",
                        "default": 1800
                    }
                },
                "required": ["ml_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bio_check",
            "description": "Check the bioprogramming environment and connect to the biocomputer (Cortical Labs). Returns [БИО-ИНФО] (Python version, which packages are installed: cl-sdk, numpy, pandas, matplotlib, scipy, networkx, python-louvain, tables, websockets, and SNN libraries: Akida, Lava, Brian2, snnTorch, Nengo, Rockpool, BindsNET, Sinabs, JAX, PyTorch) and [БИОКОМП] (channels/neurons count, frames per second, simulator or real chip, read test). Call this FIRST for any bio task to see what the environment actually has. If cl-sdk or a simulator connection is missing — tell the user what to install/start (e.g. the Cortical Labs dish simulator).",
            "parameters": {
                "type": "object",
                "properties": {
                    "bio_project_path": {
                        "type": "string",
                        "description": "Path to the bioproject folder (the one containing .venv) or directly to its python.exe. Auto-injected from the sidebar field «Био-проект» — omit if the field is filled."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bio_ml",
            "description": "Execute Python code in the BIOPROGRAMMING environment (Cortical Labs SDK 'cl') for bio/neuro tasks: connect to the biocomputer (simulator or real DishBrain chip), read neuron activity, send stimuli, build plots, analyze signals. Environment: bio project venv with cl-sdk 1.0.0, numpy, pandas, scipy, matplotlib, networkx, python-louvain, tables, websockets. np, pd, plt are pre-imported. cl API (as in SDK docs): 'with cl.open() as neurons: frames = neurons.read(200)' returns ndarray of shape (frames, 64 neurons); 'neurons.stim(channel_set, stim_design)' sends a stimulus (channel_set=0..63, stim_design=current in nA); 'neurons.get_channel_count()', 'neurons.get_frames_per_second()', 'cl.is_simulator()' (True = simulator). matplotlib uses Agg backend (no windows) — save plots with plt.savefig('name.png'), files appear in the bio project folder; report the full path to the user. If a package is missing (e.g. an SNN library like brian2, snntorch, akida, lava, jax), it will be auto-installed into the bio environment and the code retried (up to 3 times); if that fails, tell the user exactly which package to install. The bio project path is auto-injected from the sidebar field «Био-проект».",
            "parameters": {
                "type": "object",
                "properties": {
                    "bio_code": {
                        "type": "string",
                        "description": "Python code for bioprogramming. Can use np (numpy), pd (pandas), plt (matplotlib) and cl (Cortical Labs SDK). Example: 'import cl\\nwith cl.open() as neurons:\\n    frames = neurons.read(200)\\n    print(frames.shape)\\n    plt.plot(frames[:, 0])\\n    plt.savefig(\"neuron0.png\")'"
                    },
                    "bio_project_path": {
                        "type": "string",
                        "description": "Path to the bioproject folder (the one containing .venv) or directly to its python.exe. Auto-injected from the sidebar field «Био-проект» — omit if the field is filled."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 300 = 5 min, max: 3600). Use a bigger value for long experiments or heavy SNN training.",
                        "default": 300
                    }
                },
                "required": ["bio_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_neuro_check",
            "description": "Check the neuromorphic (SNN) environment: Python version and which spiking neural network libraries are installed (Lava Intel Loihi, Akida BrainChip, PyNN, Brian2, snnTorch, Nengo, Rockpool, BindsNET, Sinabs, JAX, PyTorch, Keras, TensorFlow). Returns [НЕЙРО-ИНФО] block with ПРИСУТСТВУЕТ/НЕТ for each library. Call THIS tool FIRST for any neuromorphic/SNN task (lava, akida, brian2, snntorch, nengo, rockpool, bindsnet, sinabs, jax, spiking). Do NOT use run_bio_check for SNN tasks — run_bio_check is only for the Cortical Labs biocomputer (cl-sdk). The neuro environment is the system Python of the agent — no path is needed normally.",
            "parameters": {
                "type": "object",
                "properties": {
                    "neuro_python_path": {
                        "type": "string",
                        "description": "Path to the neuromorphic environment python.exe or to a folder with .venv inside. Auto-injected from the sidebar field «Нейро-окружение» — omit if the field is filled or if the system Python (default) is used."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_neuro_ml",
            "description": "Execute Python code in the NEUROMORPHIC environment (spiking neural networks) for SNN tasks: build and simulate spiking networks, convert ANN to SNN, process event-based data, train on neuromorphic principles. This is the tool for SNN libraries — do NOT use run_bio_ml for that (run_bio_ml is only for the Cortical Labs biocomputer 'cl'). Environment: system Python with Lava (Intel Loihi: from lava.magma.core.decorator import implements, requires), Akida (BrainChip: import akida; from akida import Model; cnn2snn converter), PyNN (from pyNN import nest — universal SNN API), Brian2 (from brian2 import *; NeuronGroup, Synapses, StateMonitor), snnTorch (import snntorch as snn; from snntorch import spikegen — deep SNN with autograd), Nengo (import nengo; nengo.Network() — NEF brain-scale models), Rockpool (from rockpool import layers), BindsNET (from bindsnet.network import Network), Sinabs (import sinabs; from sinabs.layers import SpikingLinear — DVS event data), JAX (import jax; import jax.numpy as jnp — GPU/TPU acceleration). np, pd, plt are pre-imported. matplotlib uses Agg backend (no windows) — save plots with plt.savefig('name.png') and print the full path. If a package is missing (e.g. 'bindsnet', 'sinabs', 'jax'), it will be auto-installed into the environment and the code retried (up to 3 times); if that fails, tell the user exactly which package to install. The neuro python path is auto-injected from the sidebar field «Нейро-окружение».",
            "parameters": {
                "type": "object",
                "properties": {
                    "neuro_code": {
                        "type": "string",
                        "description": "Python code for neuromorphic computing. Can use np, pd, plt and any SNN library: lava, akida, pyNN, brian2, snntorch, nengo, rockpool, bindsnet, sinabs, jax. Example: 'from brian2 import *\\nG = NeuronGroup(100, \"dv/dt = -v / (10*ms) : 1\", threshold=\"v > 0.5\")\\nM = SpikeMonitor(G)\\nrun(100*ms)\\nprint(M.num_spikes)'"
                    },
                    "neuro_python_path": {
                        "type": "string",
                        "description": "Path to the neuromorphic environment python.exe or to a folder with .venv inside. Auto-injected from the sidebar field «Нейро-окружение» — omit if the field is filled or if the system Python (default) is used."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 300 = 5 min, max: 3600). Use a bigger value for long simulations or SNN training.",
                        "default": 300
                    }
                },
                "required": ["neuro_code"]
            }
        }
    }
]

