import json
import os
from pathlib import Path
import requests
import boto3
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

class LLMClient:
    """Unified LLM client supporting local Ollama (default) and AWS Bedrock."""

    def __init__(self, provider: str = None, role: str = "specialist"):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        self.role = role

        if self.provider == "ollama":
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            if role == "router":
                self.model = os.getenv("OLLAMA_ROUTER_MODEL", "llama3.2")
            else:
                self.model = os.getenv("OLLAMA_SPECIALIST_MODEL", "qwen2.5-coder:3b")
        elif self.provider == "bedrock":
            self.region = os.getenv("AWS_REGION", "us-east-1")
            self.bedrock = boto3.client("bedrock-runtime", region_name=self.region)
            if role == "router":
                self.model = os.getenv("BEDROCK_ROUTER_MODEL", "apac.amazon.nova-micro-v1:0")
            else:
                self.model = os.getenv("BEDROCK_SPECIALIST_MODEL", "apac.amazon.nova-lite-v1:0")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}. Use 'ollama' or 'bedrock'.")

    def generate(self, prompt: str, system_prompt: str = "", temperature: float = 0.1) -> str:
        if self.provider == "ollama":
            return self._generate_ollama(prompt, system_prompt, temperature)
        return self._generate_bedrock(prompt, system_prompt, temperature)

    def _generate_ollama(self, prompt: str, system_prompt: str, temperature: float) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    def _generate_bedrock(self, prompt: str, system_prompt: str, temperature: float) -> str:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        kwargs = {
            "modelId": self.model,
            "messages": messages,
            "inferenceConfig": {"temperature": temperature, "maxTokens": 2048},
        }
        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]

        response = self.bedrock.converse(**kwargs)
        content = response["output"]["message"]["content"]
        return content[0]["text"].strip()
