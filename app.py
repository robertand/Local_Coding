#!/usr/bin/env python3
"""
Python Debug Assistant Pro - NVIDIA A6000 ULTRA OPTIMIZED
Asistent general de codare cu feedback interactiv
"""

import os
import sys
import json
import subprocess
import threading
import queue
import time
import re
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import customtkinter as ctk
from typing import Optional, Dict, List, Any, Callable
import venv
import shutil
import gc
import socket
import tempfile
import http.client
import signal

# Configurare temă modernă
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ============================================================================
# Environment Manager
# ============================================================================

class EnvironmentManager:
    def __init__(self, base_path: str = "./debug_envs"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.current_env = None
        self.installed_packages = set()
        self.active_process = None
        self.active_temp_file = None
        
    def create_environment(self, name: str = None) -> str:
        if name is None:
            name = f"env_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        env_path = self.base_path / name
        venv.create(env_path, with_pip=True)
        self.current_env = env_path
        return str(env_path)
    
    def ensure_environment(self):
        if not self.current_env:
            env_name = f"auto_env_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.create_environment(env_name)
            return True
        return False
    
    def install_package(self, package_name: str) -> tuple[bool, str]:
        if not self.current_env:
            return False, "Niciun mediu activ"
        
        pip_path = self.current_env / "bin" / "pip"
        if sys.platform == "win32":
            pip_path = self.current_env / "Scripts" / "pip.exe"
        
        cmd = [str(pip_path), "install", package_name, "--quiet"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                self.installed_packages.add(package_name)
                return True, result.stdout
            return False, result.stderr
        except Exception as e:
            return False, str(e)
    
    def auto_install_dependencies(self, code: str):
        imports = re.findall(r'^import (\w+)|^from (\w+) import', code, re.MULTILINE)
        deps = []
        std_lib = {'os', 'sys', 're', 'json', 'time', 'datetime', 'math', 'random', 
                   'collections', 'itertools', 'pathlib', 'typing', 'functools',
                   'socket', 'threading', 'http', 'urllib', 'argparse', 'logging',
                   'hashlib', 'base64', 'csv', 'sqlite3', 'xml', 'unittest',
                   'socketserver', 'io'}
        
        for imp in imports:
            for item in imp:
                if item and item not in std_lib and item not in deps:
                    if item == 'cv2':
                        deps.append('opencv-python')
                    elif item == 'PIL':
                        deps.append('Pillow')
                    elif item == 'flask':
                        deps.append('flask')
                    elif item == 'requests':
                        deps.append('requests')
                    else:
                        deps.append(item)
        
        if deps:
            for dep in deps:
                if dep not in self.installed_packages:
                    self.install_package(dep)
    
    def stop_active_process(self):
        """Oprește procesul activ (serverul)"""
        if self.active_process:
            try:
                if sys.platform == "win32":
                    self.active_process.terminate()
                else:
                    self.active_process.terminate()
                    time.sleep(1)
                    if self.active_process.poll() is None:
                        self.active_process.kill()
                
                self.active_process.wait(timeout=3)
                self.active_process = None
                
                if self.active_temp_file and os.path.exists(self.active_temp_file):
                    os.unlink(self.active_temp_file)
                    self.active_temp_file = None
                
                return True, "Proces oprit cu succes"
            except Exception as e:
                return False, str(e)
        return False, "Niciun proces activ"
    
    def run_code(self, code: str, timeout: int = 30) -> dict:
        if not self.current_env:
            return {"success": False, "output": "", "error": "Niciun mediu activ"}
        
        python_path = self.current_env / "bin" / "python"
        if sys.platform == "win32":
            python_path = self.current_env / "Scripts" / "python.exe"
        
        # Detectează dacă e cod de server
        is_server = any(x in code for x in ['flask', 'http.server', 'serve_forever', 'app.run', 'socket'])
        
        if is_server:
            return self.run_server_code(python_path, code)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                [str(python_path), temp_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "", "error": f"Timeout după {timeout} secunde"}
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def run_server_code(self, python_path, code):
        # Extrage portul din cod
        port_match = re.search(r'port\s*[=:]\s*(\d+)', code)
        port = int(port_match.group(1)) if port_match else 8000
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        output_lines = []
        process = None
        
        try:
            process = subprocess.Popen(
                [str(python_path), temp_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            time.sleep(2)
            
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                return {"success": False, "output": stdout, "error": stderr or "Procesul s-a oprit imediat"}
            
            max_attempts = 10
            for i in range(max_attempts):
                time.sleep(0.5)
                
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=1)
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                    return {"success": False, "output": stdout, "error": stderr or "Procesul s-a oprit"}
                
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex(('127.0.0.1', port))
                    sock.close()
                    
                    if result == 0:
                        output_lines.append(f"✅ Server pornit pe portul {port}")
                        
                        try:
                            conn = http.client.HTTPConnection(f"127.0.0.1:{port}", timeout=3)
                            conn.request("GET", "/")
                            response = conn.getresponse()
                            data = response.read().decode('utf-8', errors='ignore')[:200]
                            output_lines.append(f"📥 Răspuns: {data}...")
                            conn.close()
                        except:
                            pass
                        
                        self.active_process = process
                        self.active_temp_file = temp_file
                        
                        return {
                            "success": True, 
                            "output": "\n".join(output_lines), 
                            "error": ""
                        }
                except:
                    pass
            
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except:
                    process.kill()
            
            if os.path.exists(temp_file):
                os.unlink(temp_file)
            
            return {
                "success": False, 
                "output": "\n".join(output_lines), 
                "error": f"❌ Serverul nu a pornit pe portul {port}"
            }
            
        except Exception as e:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
            return {"success": False, "output": "", "error": str(e)}

# ============================================================================
# Model Manager
# ============================================================================

class ModelManager:
    def __init__(self, callback=None):
        self.callback = callback
        self.models_dir = Path("./llm_models")
        self.models_dir.mkdir(exist_ok=True)
        self.custom_models_file = self.models_dir / "custom_models.json"
        self.custom_models = self.load_custom_models()
    
    PREDEFINED_MODELS = {
        "CodeLlama 7B": {
            "id": "codellama-7b",
            "filename": "codellama-7b.Q4_K_M.gguf",
            "size": "3.8 GB",
            "description": "Optim pentru programare"
        },
        "Mistral 7B Instruct": {
            "id": "mistral-7b",
            "filename": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
            "size": "4.1 GB",
            "description": "General purpose"
        },
        "Phi-3 Mini": {
            "id": "phi-3",
            "filename": "Phi-3-mini-4k-instruct-q4.gguf",
            "size": "2.2 GB",
            "description": "Mic și rapid"
        },
        "DeepSeek Coder 6.7B": {
            "id": "deepseek-6.7b",
            "filename": "deepseek-coder-6.7b-instruct.Q4_K_M.gguf",
            "size": "4.1 GB",
            "description": "Specializat pe cod"
        }
    }
    
    def load_custom_models(self):
        if self.custom_models_file.exists():
            try:
                with open(self.custom_models_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_custom_models(self):
        with open(self.custom_models_file, 'w') as f:
            json.dump(self.custom_models, f, indent=2)
    
    def add_custom_model(self, name: str, file_path: str, description: str = ""):
        file_path = Path(file_path)
        if not file_path.exists():
            return False, "Fișierul nu există"
        
        if file_path.suffix.lower() not in ['.gguf']:
            return False, "Format neacceptat. Folosește .gguf"
        
        dest_path = self.models_dir / file_path.name
        if not dest_path.exists():
            shutil.copy2(file_path, dest_path)
        
        model_id = f"custom_{int(time.time())}"
        
        self.custom_models[model_id] = {
            "name": name,
            "file_path": str(dest_path),
            "description": description,
            "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "size": self.get_file_size(dest_path),
            "type": "custom"
        }
        self.save_custom_models()
        return True, model_id
    
    def get_file_size(self, file_path):
        size = file_path.stat().st_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def get_all_models(self):
        models = {}
        for name, info in self.PREDEFINED_MODELS.items():
            models[name] = {**info, "type": "predefined"}
        
        for model_id, info in self.custom_models.items():
            if info.get("type") == "custom":
                display_name = f"📁 {info['name']}"
                models[display_name] = {
                    "id": model_id,
                    "file_path": info["file_path"],
                    "description": info.get("description", ""),
                    "size": info.get("size", "N/A"),
                    "type": "custom_file"
                }
        return models
    
    def delete_custom_model(self, model_display_name: str):
        models = self.get_all_models()
        if model_display_name not in models:
            return False, "Model negăsit"
        
        model_info = models[model_display_name]
        if model_info["type"] != "custom_file":
            return False, "Nu poți șterge modelele predefinite"
        
        model_id = model_info["id"]
        
        if "file_path" in self.custom_models[model_id]:
            try:
                file_path = Path(self.custom_models[model_id]["file_path"])
                if file_path.exists():
                    file_path.unlink()
            except:
                pass
        
        del self.custom_models[model_id]
        self.save_custom_models()
        return True, "Model șters cu succes"

# ============================================================================
# LLM Engine
# ============================================================================

class LocalLLMEngine:
    def __init__(self, model_manager: ModelManager, callback=None):
        self.model_manager = model_manager
        self.callback = callback
        self.model = None
        self.model_path = None
        self.model_name = None
        self.llama_cpp_available = False
        self.initialized = False
        self.is_generating = False
        self.stop_generation_flag = False
        self.use_gpu = False
        self.gpu_info = self.check_cuda()
        self._root = None
        
        # Setări generare
        self.temperature = 0.7
        self.top_p = 0.95
        self.max_tokens = 2000
        
    def check_cuda(self):
        info = {
            'available': False,
            'gpu_name': None,
            'vram': 0
        }
        
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    parts = lines[0].split(', ')
                    info['gpu_name'] = parts[0]
                    if len(parts) > 1:
                        vram_str = parts[1].replace(' MiB', '').replace(' GiB', '')
                        if 'GiB' in parts[1]:
                            info['vram'] = int(float(vram_str) * 1024)
                        else:
                            info['vram'] = int(vram_str)
                    info['available'] = True
        except:
            pass
        
        return info
    
    def log(self, msg, level="info"):
        if self.callback:
            self.callback({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": level,
                "message": msg
            })
    
    def check_dependencies(self):
        try:
            import llama_cpp
            self.llama_cpp_available = True
            return True
        except ImportError:
            return False
    
    def install_dependencies(self):
        if self.gpu_info['available']:
            self.log("🚀 Instalez versiune CUDA...", "info")
            try:
                try:
                    import llama_cpp
                    if hasattr(llama_cpp, 'llama_backend_init'):
                        self.log("✅ Versiune CUDA deja instalată", "success")
                        return True
                except:
                    pass
                
                env = os.environ.copy()
                env['CMAKE_ARGS'] = '-DLLAMA_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80'
                env['FORCE_CMAKE'] = '1'
                
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "llama-cpp-python", "--force-reinstall", "--upgrade", "--no-cache-dir"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    self.log("✅ Versiune CUDA instalată!", "success")
                    return True
                else:
                    self.log(f"❌ Eroare: {result.stderr[:200]}", "error")
                    return False
            except Exception as e:
                self.log(f"❌ Eroare: {e}", "error")
                return False
        else:
            self.log("ℹ️ Instalez versiunea CPU...", "info")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "llama-cpp-python"],
                    check=True,
                    capture_output=True
                )
                self.log("✅ Dependințe instalate", "success")
                return True
            except Exception as e:
                self.log(f"❌ Eroare: {e}", "error")
                return False
    
    def load_model(self, model_display_name: str) -> bool:
        if not self.llama_cpp_available:
            if not self.install_dependencies():
                return False
            try:
                import llama_cpp
                self.llama_cpp_available = True
            except:
                return False
        
        models = self.model_manager.get_all_models()
        if model_display_name not in models:
            self.log(f"❌ Model negăsit", "error")
            return False
        
        model_info = models[model_display_name]
        
        try:
            if model_info["type"] == "predefined":
                filename = model_info["filename"]
                self.model_path = str(self.model_manager.models_dir / filename)
                
                if not Path(self.model_path).exists():
                    self.log(f"📥 Modelul nu există local. Descarcă manual fișierul .gguf", "warning")
                    return False
                    
            elif model_info["type"] == "custom_file":
                self.model_path = model_info["file_path"]
            
            self.model_name = model_display_name
            
            from llama_cpp import Llama
            
            config = {
                'model_path': self.model_path,
                'n_ctx': 2048,
                'n_batch': 1024,
                'n_gpu_layers': -1,
                'use_mmap': True,
                'use_mlock': True,
                'f16_kv': True,
                'verbose': False,
            }
            
            self.log(f"🚀 Încarc modelul...", "info")
            self.model = Llama(**config)
            
            self.initialized = True
            self.use_gpu = self.gpu_info['available']
            
            if self.use_gpu:
                test_start = time.time()
                self.model("Test", max_tokens=20, echo=False)
                test_time = time.time() - test_start
                speed = 20 / test_time
                self.log(f"   ⚡ Viteză: {speed:.1f} tokeni/sec", "success")
            
            self.log(f"✅ Model încărcat!", "success")
            return True
            
        except Exception as e:
            self.log(f"❌ Eroare: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "error")
            return False
    
    def unload_model(self):
        if self.model:
            try:
                del self.model
                self.model = None
                self.initialized = False
                self.model_name = None
                self.model_path = None
                gc.collect()
                self.log("✅ Model descărcat", "success")
                return True
            except Exception as e:
                self.log(f"❌ Eroare: {e}", "error")
                return False
        return False
    
    def generate_stream(self, prompt: str, max_tokens: int = None) -> str:
        if not self.initialized or not self.model:
            return "Eroare: Modelul nu este încărcat"
        
        if max_tokens is None:
            max_tokens = self.max_tokens
        
        self.is_generating = True
        self.stop_generation_flag = False
        
        try:
            full_response = ""
            self.log(f"\n🎮 GENERARE:", "stream_start")
            self.log("="*50, "stream_start")
            
            start_time = time.time()
            token_count = 0
            batch = []
            
            for chunk in self.model(prompt, 
                                   max_tokens=max_tokens,
                                   temperature=self.temperature,
                                   top_p=self.top_p,
                                   stop=["```\n", "\n\n\n"],
                                   stream=True,
                                   echo=False):
                
                if self.stop_generation_flag:
                    break
                
                token = chunk['choices'][0]['text']
                full_response += token
                token_count += 1
                batch.append(token)
                
                if len(batch) >= 5:
                    if self.callback:
                        self.callback({
                            "level": "stream_chunk",
                            "message": ''.join(batch)
                        })
                    batch = []
            
            if batch and self.callback:
                self.callback({
                    "level": "stream_chunk",
                    "message": ''.join(batch)
                })
            
            elapsed = time.time() - start_time
            speed = token_count / elapsed if elapsed > 0 else 0
            
            self.log("="*50, "stream_end")
            self.log(f"✅ Generat {token_count} tokeni în {elapsed:.1f}s ({speed:.1f} tok/sec)", "success")
            
            return full_response
            
        except Exception as e:
            self.log(f"❌ Eroare: {e}", "error")
            return f"Eroare: {str(e)}"
        finally:
            self.is_generating = False
    
    def stop_generation(self):
        self.stop_generation_flag = True

# ============================================================================
# Debugging Agent - Cu feedback loop
# ============================================================================

class DebuggingAgent:
    def __init__(self, llm_engine: LocalLLMEngine, model_manager: ModelManager, callback=None, root=None):
        self.llm = llm_engine
        self.model_manager = model_manager
        self.callback = callback
        self.is_running = False
        self.current_task = None
        self.env_manager = EnvironmentManager()
        self.conversation_history = []
        
        if root:
            self.llm._root = root
    
    def log(self, message: str, level: str = "info"):
        if self.callback:
            self.callback({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": level,
                "message": message
            })
    
    def stop_server(self):
        success, message = self.env_manager.stop_active_process()
        if success:
            self.log(f"🛑 {message}", "warning")
        return success
    
    def identify_dependencies(self, code: str) -> list:
        imports = re.findall(r'^import (\w+)|^from (\w+) import', code, re.MULTILINE)
        deps = []
        std_lib = {
            'os', 'sys', 're', 'json', 'time', 'datetime', 'math', 'random', 
            'collections', 'itertools', 'pathlib', 'typing', 'functools',
            'socket', 'threading', 'http', 'urllib', 'argparse', 'logging',
            'hashlib', 'base64', 'csv', 'sqlite3', 'xml', 'unittest',
            'socketserver', 'io'
        }
        
        for imp in imports:
            for item in imp:
                if item and item not in std_lib and item not in deps:
                    if item == 'cv2':
                        deps.append('opencv-python')
                    elif item == 'PIL':
                        deps.append('Pillow')
                    elif item == 'flask':
                        deps.append('flask')
                    elif item == 'requests':
                        deps.append('requests')
                    else:
                        deps.append(item)
        
        return list(set(deps))
    
    def extract_code(self, text: str) -> str:
        """Extrage codul din răspuns"""
        lines = text.split('\n')
        lines = [line for line in lines if line.strip() != '```']
        
        start_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('```'):
                if (stripped.startswith('import ') or 
                    stripped.startswith('from ') or 
                    stripped.startswith('def ') or 
                    stripped.startswith('class ') or
                    stripped.startswith('@') or
                    stripped.startswith('if __name__')):
                    start_idx = i
                    break
        
        if start_idx == -1:
            for i, line in enumerate(lines):
                if line.strip():
                    start_idx = i
                    break
        
        if start_idx == -1:
            return text
        
        code_lines = lines[start_idx:]
        
        if code_lines:
            code_lines[0] = code_lines[0].lstrip()
        
        while code_lines and not code_lines[-1].strip():
            code_lines.pop()
        
        return '\n'.join(code_lines)
    
    def generate_code(self, user_request: str, context: str = None) -> str:
        """Generează cod pe baza cerințelor utilizatorului"""
        
        if context:
            prompt = f"""
            Context anterior:
            {context}
            
            Cerința curentă:
            {user_request}
            
            Generează cod Python care îndeplinește această cerință.
            Include toate importurile necesare.
            Returnează DOAR codul, fără explicații.
            """
        else:
            prompt = f"""
            Cerință: {user_request}
            
            Generează cod Python complet care îndeplinește această cerință.
            Include toate importurile necesare.
            Returnează DOAR codul, fără explicații.
            """
        
        self.log("\n🎨 GENERARE COD", "info")
        self.log("📝 " + user_request[:100] + ("..." if len(user_request) > 100 else ""), "info")
        
        code = self.llm.generate_stream(prompt, max_tokens=2000)
        return self.extract_code(code)
    
    def refine_code(self, current_code: str, feedback: str) -> str:
        """Rafinează codul pe baza feedback-ului utilizatorului"""
        
        prompt = f"""
        Codul curent:
        ```python
        {current_code}
        ```
        
        Feedback pentru modificare:
        {feedback}
        
        Rescrie codul complet implementând acest feedback.
        Păstrează structura generală dar modifică conform cerințelor.
        Returnează DOAR codul nou, fără explicații.
        """
        
        self.log("\n🔄 REFINEMENT", "info")
        self.log("📝 " + feedback[:100] + ("..." if len(feedback) > 100 else ""), "info")
        
        new_code = self.llm.generate_stream(prompt, max_tokens=2000)
        return self.extract_code(new_code)
    
    def run_code_in_env(self, code: str) -> dict:
        if not self.env_manager.current_env:
            env_name = f"env_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.env_manager.create_environment(env_name)
            self.log(f"📦 Mediu virtual: {env_name}", "info")
        
        code = self.extract_code(code)
        
        first_lines = '\n'.join(code.split('\n')[:3])
        self.log(f"📄 Cod (primele 3 linii):\n{first_lines}", "info")
        
        deps = self.identify_dependencies(code)
        if deps:
            self.log("📦 Instalez: " + ", ".join(deps), "info")
            for dep in deps:
                if dep not in self.env_manager.installed_packages:
                    self.env_manager.install_package(dep)
        
        return self.env_manager.run_code(code)
    
    def stop(self):
        self.is_running = False
        self.llm.stop_generation()

# ============================================================================
# Main Application
# ============================================================================

class CodingAssistantApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("🐍 Python Coding Assistant Pro")
        self.geometry("1400x900")
        self.minsize(1200, 700)
        
        self.model_manager = ModelManager(self.log_message)
        self.llm_engine = LocalLLMEngine(self.model_manager, self.log_message)
        self.debug_agent = DebuggingAgent(self.llm_engine, self.model_manager, self.log_message, self)
        self.env_manager = EnvironmentManager()
        self.message_queue = queue.Queue()
        
        self.current_code = ""
        self.conversation_history = []
        
        self.setup_ui()
        self.after(100, self.process_queue)
        self.after(1000, self.initial_check)
    
    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self.header = ctk.CTkFrame(self, height=80, corner_radius=0)
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        title_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        title_frame.pack(side="left", padx=20, pady=10)
        
        ctk.CTkLabel(
            title_frame,
            text="🐍 Python Coding Assistant Pro",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            title_frame,
            text="Asistent general de codare cu feedback interactiv",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(anchor="w")
        
        status_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        status_frame.pack(side="right", padx=20, pady=10)
        
        self.gpu_status = ctk.CTkLabel(status_frame, text="🔍 Detectare GPU...")
        self.gpu_status.pack(anchor="e")
        
        self.model_status = ctk.CTkLabel(
            status_frame,
            text="⏸️ Model neîncărcat",
            text_color="orange"
        )
        self.model_status.pack(anchor="e", pady=(5,0))
        
        # Panoul stânga
        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        self.left_panel.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(3, weight=1)
        
        self.create_model_card()
        self.create_settings_card()
        self.create_control_card()
        self.create_logs_card()
        
        # Panoul dreapta
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=1, column=1, sticky="nsew", padx=(0,10), pady=(0,10))
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_rowconfigure(2, weight=1)
        
        self.create_chat_card()
        self.create_editor_card()
        self.create_console_card()
    
    def create_model_card(self):
        card = ctk.CTkFrame(self.left_panel)
        card.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15,5))
        
        ctk.CTkLabel(header, text="🤖 Model", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="➕ Add", width=60, height=28, command=self.show_add_model_dialog).pack(side="right")
        
        self.model_var = ctk.StringVar()
        self.model_menu = ctk.CTkComboBox(
            card, 
            variable=self.model_var, 
            values=self.get_model_list(),
            command=self.on_model_selected,
            width=300
        )
        self.model_menu.pack(fill="x", padx=15, pady=5)
        
        self.model_info = ctk.CTkTextbox(card, height=40, wrap="word")
        self.model_info.pack(fill="x", padx=15, pady=5)
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=15)
        
        self.load_btn = ctk.CTkButton(btn_frame, text="📥 Load", command=self.load_model, state="disabled")
        self.load_btn.pack(side="left", expand=True, fill="x", padx=(0,5))
        
        self.unload_btn = ctk.CTkButton(btn_frame, text="📤 Unload", command=self.unload_model, 
                                        state="disabled", fg_color="#ff9800", hover_color="#f57c00")
        self.unload_btn.pack(side="left", expand=True, fill="x", padx=(5,5))
        
        self.stop_btn = ctk.CTkButton(btn_frame, text="⏹️ Stop", command=self.stop_generation, 
                                      state="disabled", fg_color="red", hover_color="darkred")
        self.stop_btn.pack(side="right", expand=True, fill="x", padx=(5,0))
    
    def create_settings_card(self):
        card = ctk.CTkFrame(self.left_panel)
        card.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(card, text="🎛️ Setări LLM", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=(10,5))
        
        temp_frame = ctk.CTkFrame(card, fg_color="transparent")
        temp_frame.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(temp_frame, text="Temperatură:", width=90).pack(side="left")
        self.temp_var = ctk.DoubleVar(value=0.7)
        self.temp_slider = ctk.CTkSlider(temp_frame, from_=0.1, to=1.5, variable=self.temp_var, command=self.on_temp_change, width=150)
        self.temp_slider.pack(side="left", padx=(0,10))
        self.temp_label = ctk.CTkLabel(temp_frame, text="0.7", width=30)
        self.temp_label.pack(side="left")
        
        topp_frame = ctk.CTkFrame(card, fg_color="transparent")
        topp_frame.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(topp_frame, text="Top P:", width=90).pack(side="left")
        self.topp_var = ctk.DoubleVar(value=0.95)
        self.topp_slider = ctk.CTkSlider(topp_frame, from_=0.1, to=1.0, variable=self.topp_var, command=self.on_topp_change, width=150)
        self.topp_slider.pack(side="left", padx=(0,10))
        self.topp_label = ctk.CTkLabel(topp_frame, text="0.95", width=30)
        self.topp_label.pack(side="left")
        
        maxtokens_frame = ctk.CTkFrame(card, fg_color="transparent")
        maxtokens_frame.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(maxtokens_frame, text="Max Tokens:", width=90).pack(side="left")
        self.maxtokens_var = ctk.IntVar(value=2000)
        self.maxtokens_slider = ctk.CTkSlider(maxtokens_frame, from_=500, to=4000, variable=self.maxtokens_var, command=self.on_maxtokens_change, width=150)
        self.maxtokens_slider.pack(side="left", padx=(0,10))
        self.maxtokens_label = ctk.CTkLabel(maxtokens_frame, text="2000", width=30)
        self.maxtokens_label.pack(side="left")
        
        ctk.CTkButton(card, text="Aplică setări", command=self.apply_llm_settings, height=30).pack(fill="x", padx=15, pady=10)
    
    def create_control_card(self):
        card = ctk.CTkFrame(self.left_panel)
        card.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(card, text="🛠️ Control", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=(10,5))
        
        ctk.CTkButton(
            card,
            text="🛑 Oprește Server",
            command=self.stop_server,
            fg_color="#dc3545",
            hover_color="#b02a37",
            height=35
        ).pack(fill="x", padx=15, pady=(5,15))
    
    def create_logs_card(self):
        card = ctk.CTkFrame(self.left_panel)
        card.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10,5))
        
        ctk.CTkLabel(header, text="📋 Log", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="Clear", width=60, height=25, command=self.clear_logs, fg_color="gray").pack(side="right")
        
        self.log_display = ctk.CTkTextbox(card, wrap="word")
        self.log_display.pack(fill="both", expand=True, padx=15, pady=(0,15))
        
        self.log_display.tag_config("timestamp", foreground="#888888")
        self.log_display.tag_config("success", foreground="#00ff00")
        self.log_display.tag_config("error", foreground="#ff5555")
        self.log_display.tag_config("warning", foreground="#ffaa00")
        self.log_display.tag_config("stream_chunk", foreground="#00ffff")
    
    def create_chat_card(self):
        card = ctk.CTkFrame(self.right_panel)
        card.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10,5))
        
        ctk.CTkLabel(header, text="💬 Chat cu AI", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        
        # Chat history display - folosim CTkTextbox dar fără font în tag_config
        self.chat_history = ctk.CTkTextbox(card, wrap="word")
        self.chat_history.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Configurăm tag-urile doar cu culori, fără font
        self.chat_history.tag_config("user", foreground="#00ccff")
        self.chat_history.tag_config("ai", foreground="#ffaa00")
        self.chat_history.tag_config("system", foreground="#888888")
        
        # Input frame
        input_frame = ctk.CTkFrame(card, fg_color="transparent")
        input_frame.pack(fill="x", padx=15, pady=(5,15))
        
        self.chat_input = ctk.CTkEntry(input_frame, placeholder_text="Scrie cerința sau feedback pentru cod...")
        self.chat_input.pack(side="left", fill="x", expand=True, padx=(0,5))
        
        self.send_btn = ctk.CTkButton(
            input_frame, 
            text="🚀 Trimite", 
            command=self.send_message, 
            width=100,
            fg_color="#2e7d32",
            hover_color="#1e5a22",
            state="disabled"
        )
        self.send_btn.pack(side="right")
        
        self.chat_input.bind("<Return>", lambda e: self.send_message())
    
    def create_editor_card(self):
        card = ctk.CTkFrame(self.right_panel)
        card.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10,5))
        
        ctk.CTkLabel(header, text="📝 Cod generat", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")
        
        ctk.CTkButton(btn_frame, text="▶️ Rulează", width=70, height=28, command=self.run_code).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="💾 Salvează", width=70, height=28, command=self.save_code).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="🗑️ Șterge", width=70, height=28, fg_color="gray", command=self.clear_code).pack(side="left", padx=2)
        
        self.code_editor = ctk.CTkTextbox(card, wrap="word", font=ctk.CTkFont(family="Courier", size=12))
        self.code_editor.pack(fill="both", expand=True, padx=15, pady=15)
    
    def create_console_card(self):
        card = ctk.CTkFrame(self.right_panel)
        card.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0,10))
        
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10,5))
        
        ctk.CTkLabel(header, text="🖥️ Output", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="Clear", width=60, height=25, command=self.clear_console, fg_color="gray").pack(side="right")
        
        self.console = ctk.CTkTextbox(card, wrap="word", font=ctk.CTkFont(family="Courier", size=11))
        self.console.pack(fill="both", expand=True, padx=15, pady=(0,15))
    
    def clear_logs(self):
        self.log_display.delete("0.0", "end")
    
    def clear_console(self):
        self.console.delete("0.0", "end")
    
    def get_model_list(self):
        return list(self.model_manager.get_all_models().keys())
    
    def on_model_selected(self, choice):
        self.load_btn.configure(state="normal")
        models = self.model_manager.get_all_models()
        if choice in models:
            info = models[choice]
            self.model_info.delete("0.0", "end")
            self.model_info.insert("0.0", f"📦 {info['size']}\n{info.get('description', '')}")
    
    def log_message(self, msg):
        self.message_queue.put(msg)
    
    def process_queue(self):
        try:
            while True:
                msg = self.message_queue.get_nowait()
                self.display_message(msg)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_queue)
    
    def display_message(self, msg):
        timestamp = msg.get('timestamp', '')
        level = msg.get('level', 'info')
        text = msg.get('message', '')
        
        if level == 'stream_chunk':
            self.log_display.insert("end", text, "stream_chunk")
        elif level == 'code_complete':
            code = msg.get('code', '')
            self.code_editor.delete("0.0", "end")
            self.code_editor.insert("0.0", code)
            self.log_display.insert("end", f"[{timestamp}] ", "timestamp")
            self.log_display.insert("end", f"{msg.get('message', '')}\n", "success")
        else:
            if timestamp:
                self.log_display.insert("end", f"[{timestamp}] ", "timestamp")
            self.log_display.insert("end", f"{text}\n", level)
        
        self.log_display.see("end")
    
    def initial_check(self):
        if not self.llm_engine.check_dependencies():
            self.log_message({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "warning",
                "message": "⚠️ Dependințele lipsesc. Se vor instala la prima încărcare."
            })
        
        if self.llm_engine.gpu_info['available']:
            gpu = self.llm_engine.gpu_info['gpu_name']
            self.gpu_status.configure(text=f"🎮 {gpu}", text_color="green")
        else:
            self.gpu_status.configure(text="⚠️ Fără GPU", text_color="orange")
    
    def on_temp_change(self, value):
        self.temp_label.configure(text=f"{value:.1f}")
    
    def on_topp_change(self, value):
        self.topp_label.configure(text=f"{value:.2f}")
    
    def on_maxtokens_change(self, value):
        self.maxtokens_label.configure(text=str(int(value)))
    
    def apply_llm_settings(self):
        self.llm_engine.temperature = self.temp_var.get()
        self.llm_engine.top_p = self.topp_var.get()
        self.llm_engine.max_tokens = self.maxtokens_var.get()
        
        self.log_message({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "success",
            "message": f"✅ Setări aplicate: Temp={self.llm_engine.temperature:.1f}, Top_P={self.llm_engine.top_p:.2f}, MaxTokens={self.llm_engine.max_tokens}"
        })
    
    def load_model(self):
        model = self.model_var.get()
        if not model:
            return
        
        def load_thread():
            self.log_message({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "info",
                "message": f"🚀 Încarc {model}..."
            })
            
            if self.llm_engine.load_model(model):
                self.log_message({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "level": "success",
                    "message": "✅ Model încărcat!"
                })
                self.model_status.configure(text=f"✅ {model}", text_color="green")
                self.send_btn.configure(state="normal", fg_color="#2e7d32")
                self.stop_btn.configure(state="normal")
                self.unload_btn.configure(state="normal")
                self.load_btn.configure(state="disabled")
                
                # Mesaj de bun venit în chat
                self.after(0, lambda: self.chat_history.insert("end", "\n", "system"))
                self.after(0, lambda: self.chat_history.insert("end", "🤖 ASISTENT: ", "ai"))
                self.after(0, lambda: self.chat_history.insert("end", "Model încărcat! Scrie ce dorești să generezi.\n", "system"))
            else:
                self.log_message({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "level": "error",
                    "message": "❌ Eroare încărcare"
                })
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def unload_model(self):
        def unload_thread():
            if self.llm_engine.unload_model():
                self.model_status.configure(text="⏸️ Model neîncărcat", text_color="orange")
                self.send_btn.configure(state="disabled", fg_color="#2e7d32")
                self.stop_btn.configure(state="disabled")
                self.unload_btn.configure(state="disabled")
                self.load_btn.configure(state="normal")
        
        threading.Thread(target=unload_thread, daemon=True).start()
    
    def stop_generation(self):
        self.llm_engine.stop_generation()
        self.debug_agent.stop()
        self.log_message({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "warning",
            "message": "⏹️ Oprire generare..."
        })
    
    def stop_server(self):
        self.log_message({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "warning",
            "message": "🛑 Oprește server..."
        })
        
        def stop_thread():
            success = self.debug_agent.stop_server()
            if success:
                self.log_message({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "level": "success",
                    "message": "✅ Server oprit"
                })
        
        threading.Thread(target=stop_thread, daemon=True).start()
    
    def send_message(self):
        message = self.chat_input.get().strip()
        if not message:
            return
        
        # Dezactivează input-ul temporar
        self.chat_input.configure(state="disabled")
        self.send_btn.configure(state="disabled")
        
        # Afișează mesajul în chat
        self.chat_history.insert("end", "\n", "system")
        self.chat_history.insert("end", "🧑 TU: ", "user")
        self.chat_history.insert("end", f"{message}\n", "system")
        self.chat_history.see("end")
        
        self.chat_input.delete(0, "end")
        
        # Pornește procesarea în thread separat
        threading.Thread(target=self.process_message, args=(message,), daemon=True).start()
    
    def process_message(self, message):
        try:
            self.log_message({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "info",
                "message": "🤔 Procesez cerința..."
            })
            
            # Verifică dacă avem deja cod în editor
            current_code = self.code_editor.get("0.0", "end").strip()
            
            if current_code:
                # Avem cod, deci e feedback pentru rafinare
                self.after(0, lambda: self.chat_history.insert("end", "\n", "system"))
                self.after(0, lambda: self.chat_history.insert("end", "🤖 ASISTENT: ", "ai"))
                self.after(0, lambda: self.chat_history.insert("end", "Modific codul conform feedback-ului...\n", "system"))
                self.after(0, lambda: self.chat_history.see("end"))
                
                new_code = self.debug_agent.refine_code(current_code, message)
            else:
                # Prima cerință, generăm cod nou
                self.after(0, lambda: self.chat_history.insert("end", "\n", "system"))
                self.after(0, lambda: self.chat_history.insert("end", "🤖 ASISTENT: ", "ai"))
                self.after(0, lambda: self.chat_history.insert("end", "Generez codul...\n", "system"))
                self.after(0, lambda: self.chat_history.see("end"))
                
                new_code = self.debug_agent.generate_code(message)
            
            if new_code and not self.llm_engine.stop_generation_flag:
                self.after(0, lambda: self.code_editor.delete("0.0", "end"))
                self.after(0, lambda: self.code_editor.insert("0.0", new_code))
                
                self.after(0, lambda: self.chat_history.insert("end", "\n", "system"))
                self.after(0, lambda: self.chat_history.insert("end", "🤖 ASISTENT: ", "ai"))
                self.after(0, lambda: self.chat_history.insert("end", "✅ Cod generat! Poți să-l rulezi sau să dai feedback pentru modificări.\n", "system"))
                self.after(0, lambda: self.chat_history.see("end"))
                
                self.log_message({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "level": "success",
                    "message": "✅ Cod generat!"
                })
        finally:
            # Reactivează input-ul
            self.after(0, lambda: self.chat_input.configure(state="normal"))
            self.after(0, lambda: self.send_btn.configure(state="normal"))
            self.after(0, lambda: self.chat_input.focus())
    
    def run_code(self):
        code = self.code_editor.get("0.0", "end").strip()
        if not code:
            messagebox.showwarning("Atenție", "Nu există cod de rulat")
            return
        
        self.console.insert("end", f"\n{'='*60}\n")
        self.console.insert("end", f"🚀 Rulez codul...\n")
        self.console.insert("end", f"{'='*60}\n")
        
        def run_thread():
            try:
                if not self.env_manager.current_env:
                    self.after(0, lambda: self.console.insert("end", "📦 Creez mediu virtual...\n"))
                    self.env_manager.create_environment(f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                
                self.after(0, lambda: self.console.insert("end", "📦 Instalez dependențe...\n"))
                self.env_manager.auto_install_dependencies(code)
                
                result = self.env_manager.run_code(code)
                
                if result.get('output'):
                    self.after(0, lambda: self.console.insert("end", result['output']))
                if result.get('error'):
                    self.after(0, lambda: self.console.insert("end", f"\n❌ Eroare:\n{result['error']}\n"))
                else:
                    self.after(0, lambda: self.console.insert("end", "\n✅ Execuție finalizată!\n"))
                
                # Dacă e server, anunță
                if any(x in code for x in ['flask', 'http.server', 'serve_forever']):
                    self.after(0, lambda: self.console.insert("end", "\n🌐 Serverul rulează în fundal. Folosește 'Oprește Server' pentru a-l opri.\n"))
            except Exception as e:
                self.after(0, lambda: self.console.insert("end", f"\n🔥 Eroare: {e}\n"))
            finally:
                self.after(0, lambda: self.console.see("end"))
        
        threading.Thread(target=run_thread, daemon=True).start()
    
    def save_code(self):
        code = self.code_editor.get("0.0", "end").strip()
        if not code:
            return
        
        f = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python", "*.py"), ("Toate fișierele", "*.*")])
        if f:
            with open(f, 'w') as file:
                file.write(code)
            messagebox.showinfo("Succes", f"Salvat în {f}")
    
    def clear_code(self):
        self.code_editor.delete("0.0", "end")
    
    def show_add_model_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("➕ Adaugă Model")
        dialog.geometry("500x250")
        dialog.transient(self)
        dialog.grab_set()
        
        ctk.CTkLabel(dialog, text="Nume model:").pack(padx=20, pady=(20,5))
        name = ctk.CTkEntry(dialog)
        name.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(dialog, text="Fișier .gguf:").pack(padx=20, pady=5)
        
        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=5)
        
        path = ctk.StringVar()
        ctk.CTkEntry(frame, textvariable=path).pack(side="left", fill="x", expand=True, padx=(0,10))
        
        def browse():
            f = filedialog.askopenfilename(filetypes=[("GGUF", "*.gguf"), ("Toate fișierele", "*.*")])
            if f:
                path.set(f)
        
        ctk.CTkButton(frame, text="Răsfoiește", command=browse, width=80).pack(side="right")
        
        def add():
            if name.get() and path.get():
                success, _ = self.model_manager.add_custom_model(name.get(), path.get())
                if success:
                    self.model_menu.configure(values=self.get_model_list())
                    dialog.destroy()
                    messagebox.showinfo("Succes", "Model adăugat!")
        
        ctk.CTkButton(dialog, text="Adaugă", command=add).pack(pady=20)

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("🐍 Python Coding Assistant Pro")
    print("=" * 50)
    print("Un asistent general de codare cu feedback interactiv")
    print()
    
    app = CodingAssistantApp()
    app.mainloop()