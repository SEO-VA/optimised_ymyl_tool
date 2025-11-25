#!/usr/bin/env python3
"""
OpenAI Service Module - Robust Chat Completion
Switched to Chat Completions for reliability and speed with gpt-4o-mini.
"""

import asyncio
import json
import streamlit as st
from openai import AsyncOpenAI
from typing import Optional, Tuple
from utils.helpers import safe_log

class OpenAIService:
    def __init__(self):
        try:
            self.client = AsyncOpenAI(api_key=st.secrets["openai_api_key"])
        except KeyError:
            safe_log("OpenAI Service: API Key not found!", "CRITICAL")
            raise

    async def get_response_async(self, 
                               content: str, 
                               assistant_id: str, # Kept for compatibility, but we use System Prompt now
                               task_name: str = "Audit",
                               timeout_seconds: int = 300,
                               json_mode: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Uses Chat Completions API (simpler and faster than Assistants API for this use case).
        Note: We need to retrieve the System Prompt from the Assistant ID if you want to keep using the Dashboard.
        OR, for simplicity now, we can just pass the instruction directly if you have it.
        
        Since your Orchestrator passes an Assistant ID, we will use the retrieve() call to get its instructions first.
        """
        try:
            # 1. Fetch the System Prompt from the Assistant ID (So you can still edit it in Dashboard)
            assistant = await self.client.beta.assistants.retrieve(assistant_id)
            system_prompt = assistant.instructions

            # 2. Call Chat Completion
            safe_log(f"{task_name}: Sending request to {assistant.model}...")
            
            response = await self.client.chat.completions.create(
                model=assistant.model, # Uses the model set in Dashboard (gpt-4o-mini)
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                response_format={"type": "json_object"} if json_mode else None,
                temperature=0.1 # Low temp for strict compliance
            )

            # 3. Extract Response
            result_text = response.choices[0].message.content
            
            if not result_text:
                return False, None, "Empty response from OpenAI"

            safe_log(f"{task_name}: Success ({len(result_text)} chars)")
            return True, result_text, None

        except Exception as e:
            safe_log(f"{task_name}: Error - {str(e)}", "ERROR")
            return False, None, f"System Error: {str(e)}"

openai_service = OpenAIService()
