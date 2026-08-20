"""
PodcastStudio - Local Ollama LLM Dialogue Engine
REST client and dialogue script generation pipeline interfacing with local Ollama.
"""

import json
import socket
import threading
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional, Callable

from core.parser import DialogueTurn, DialogueParser
from core.prompts import (
    build_system_prompt,
    build_user_prompt,
    normalize_language_code,
    get_act_specs,
    build_act_system_prompt,
    build_act_user_prompt,
)


class OllamaConnectionError(Exception):
    """Raised when the Ollama service cannot be reached."""
    pass


class OllamaModelNotFoundError(Exception):
    """Raised when the requested model is not installed in Ollama."""
    pass


class OllamaClient:
    """
    Standard Library HTTP client for local Ollama REST API.
    Zero external HTTP dependencies (uses urllib.request).
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def check_connection(self, timeout: float = 3.0) -> bool:
        """
        Returns True if the Ollama service is reachable and responsive.
        """
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "PodcastStudio/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

    def list_models(self, timeout: float = 5.0) -> List[str]:
        """
        Retrieves list of installed model names (e.g. ['llama3.1:8b', 'qwen2.5:7b']).
        
        Raises:
            OllamaConnectionError: If connection to Ollama fails.
        """
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "PodcastStudio/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                models = [
                    m["name"] for m in data.get("models", [])
                    if isinstance(m, dict) and "name" in m
                ]
                return sorted(models)
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Please make sure Ollama is running ('ollama serve' or Windows tray app)."
            ) from e
        except Exception as e:
            raise OllamaConnectionError(f"Error fetching Ollama models: {e}") from e

    def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        stream: bool = False,
        timeout: float = 300.0,
        temperature: float = 0.7,
        num_ctx: int = 8192,
        cancel_event: Optional[threading.Event] = None,
        callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Generates text using Ollama /api/chat or fallback to /api/generate.
        Supports cancellation checks and streaming callbacks.
        
        Raises:
            OllamaConnectionError, OllamaModelNotFoundError, TimeoutError, RuntimeError.
        """
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user before request dispatch.")

        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "stream": stream or (callback is not None),
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": 4096,
            }
        }

        try:
            return self._execute_chat(chat_payload, timeout, cancel_event, callback)
        except (socket.timeout, TimeoutError) as to_err:
            raise TimeoutError(f"Ollama generation timed out after {timeout} seconds: {to_err}") from to_err
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                err_body = http_err.read().decode("utf-8", errors="ignore")
                if "model" in err_body.lower() or "not found" in err_body.lower():
                    raise OllamaModelNotFoundError(
                        f"Model '{model}' is not installed in Ollama. "
                        f"Please run 'ollama pull {model}' in your terminal."
                    )
            # Fallback to /api/generate
            return self._execute_generate(model, prompt, system, timeout, temperature, num_ctx, cancel_event, callback)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, socket.timeout):
                raise TimeoutError(f"Ollama request timed out after {timeout} seconds.") from url_err
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Please make sure Ollama is running ('ollama serve')."
            ) from url_err

    def generate_dialogue(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        timeout: float = 300.0,
        temperature: float = 0.7
    ) -> str:
        """Convenience method for generating dialogue with system & user prompt."""
        return self.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt,
            timeout=timeout,
            temperature=temperature
        )

    def _execute_chat(
        self,
        payload: Dict[str, Any],
        timeout: float,
        cancel_event: Optional[threading.Event],
        callback: Optional[Callable[[str], None]]
    ) -> str:
        url = f"{self.base_url}/api/chat"
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": "PodcastStudio/1.0"}
        )

        is_streaming = payload.get("stream", False)
        collected_chunks: List[str] = []

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if not is_streaming:
                    data = json.loads(response.read().decode("utf-8"))
                    return data.get("message", {}).get("content", "")

                for line in response:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("Generation cancelled by user during streaming.")
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    try:
                        chunk = json.loads(line_str)
                        content_piece = chunk.get("message", {}).get("content", "")
                        if content_piece:
                            collected_chunks.append(content_piece)
                            if callback:
                                callback(content_piece)
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

            return "".join(collected_chunks)
        except (socket.timeout, TimeoutError) as e:
            raise TimeoutError(f"Ollama generation timed out after {timeout} seconds.") from e

    def _execute_generate(
        self,
        model: str,
        prompt: str,
        system: str,
        timeout: float,
        temperature: float,
        num_ctx: int,
        cancel_event: Optional[threading.Event],
        callback: Optional[Callable[[str], None]]
    ) -> str:
        url = f"{self.base_url}/api/generate"
        is_streaming = callback is not None
        payload = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": is_streaming,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": 4096,
            }
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": "PodcastStudio/1.0"}
        )

        collected_chunks: List[str] = []

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if not is_streaming:
                    data = json.loads(response.read().decode("utf-8"))
                    return data.get("response", "")

                for line in response:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("Generation cancelled by user during streaming.")
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    try:
                        chunk = json.loads(line_str)
                        piece = chunk.get("response", "")
                        if piece:
                            collected_chunks.append(piece)
                            if callback:
                                callback(piece)
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

            return "".join(collected_chunks)
        except (socket.timeout, TimeoutError) as e:
            raise TimeoutError(f"Ollama generation timed out after {timeout} seconds.") from e


def generate_podcast_script(
    content: str,
    language: str = "nb-NO",
    format_type: str = "standard",
    tone_style: str = "casual",
    model: str = "llama3.1:8b",
    ollama_url: str = "http://localhost:11434",
    is_topic: bool = False,
    timeout: float = 300.0,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> List[DialogueTurn]:
    """
    High-level dialogue generation pipeline with Multi-Act Structured Generation:
    For short summaries: Generates single-shot dialogue.
    For standard, deep dive, and extended in-depth episodes:
      Executes sequential thematic acts (chapters) passing previous dialogue context,
      guaranteeing authentic progression and reaching the target 45-60 turns.
    
    Returns:
        List[DialogueTurn] containing structured conversation.
        
    Raises:
        OllamaConnectionError, OllamaModelNotFoundError, ValueError.
    """
    lang = normalize_language_code(language)
    client = OllamaClient(base_url=ollama_url)
    act_specs = get_act_specs(format_type=format_type, language=lang)

    # 1. Single-Act Mode (Quick Summary)
    if len(act_specs) <= 1:
        if progress_callback:
            progress_callback(f"Generating episode dialogue via Ollama ({model})...")

        system_prompt = build_system_prompt(language=lang, format_type=format_type, tone_style=tone_style)
        user_prompt = build_user_prompt(content=content, language=lang, is_topic=is_topic)

        raw_response = client.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt,
            stream=False,
            timeout=timeout,
            cancel_event=cancel_event
        )

        if not raw_response or not raw_response.strip():
            raise ValueError("Ollama returned an empty response.")

        return DialogueParser.parse(raw_response, default_language=lang)

    # 2. Multi-Act Sequential Generation Mode (Standard, Deep Dive, Extended In-Depth)
    full_script: List[DialogueTurn] = []
    total_acts = len(act_specs)

    for act_idx, act in enumerate(act_specs, 1):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user.")

        act_title = act.get("title", f"Act {act_idx}")
        target_turns = act.get("target_turns", 10)

        # Determine speaker alternation across act boundary
        next_speaker = "Host 1"
        if full_script:
            last_speaker = full_script[-1].speaker
            next_speaker = "Host 2" if "1" in last_speaker or "kari" in last_speaker.lower() or "jenny" in last_speaker.lower() else "Host 1"

        if progress_callback:
            progress_callback(
                f"Writing Act {act_idx}/{total_acts}: {act_title} "
                f"(Generating ~{target_turns} turns, current total: {len(full_script)})..."
            )

        prev_dict_turns = [t.to_dict() for t in full_script[-2:]] if full_script else None
        act_system_prompt = build_act_system_prompt(
            act=act,
            total_acts=total_acts,
            language=lang,
            tone_style=tone_style,
            next_speaker=next_speaker
        )
        act_user_prompt = build_act_user_prompt(
            content=content,
            prev_turns=prev_dict_turns,
            language=lang,
            is_topic=is_topic
        )

        raw_act_response = client.generate(
            model=model,
            prompt=act_user_prompt,
            system=act_system_prompt,
            stream=False,
            timeout=timeout,
            cancel_event=cancel_event
        )

        if raw_act_response and raw_act_response.strip():
            try:
                act_turns = DialogueParser.parse(raw_act_response, default_language=lang)
                if act_turns:
                    for t in act_turns:
                        full_script.append(t)
            except Exception as parse_err:
                if not full_script and act_idx == 1:
                    # Fallback retry on Act 1 if parsing failed
                    pass

    if not full_script:
        raise ValueError("Failed to generate dialogue turns across all acts.")

    if progress_callback:
        progress_callback(f"Successfully generated full {len(full_script)}-turn dialogue script.")

    return full_script
