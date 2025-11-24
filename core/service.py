#!/usr/bin/env python3
"""
OpenAI Service Module
Handles the low-level network communication with OpenAI's Assistant API.
Updated: Supports 'json_mode' parameter to enforce valid JSON output.
"""

import asyncio
import time
import streamlit as st
from openai import OpenAI
from typing import Optional, Tuple
from utils.helpers import safe_log

class OpenAIService:
    """
    Manages the connection to OpenAI.
    """
    
    def __init__(self):
        try:
            self.client = OpenAI(api_key=st.secrets["openai_api_key"])
        except KeyError:
            safe_log("OpenAI Service: API Key not found in secrets!", "CRITICAL")
            raise

    async def get_response_async(self, 
                               content: str, 
                               assistant_id: str, 
                               timeout_seconds: int = 300,
                               task_name: str = "Audit",
                               json_mode: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Full async workflow with optional JSON Mode enforcement.
        """
        try:
            # 1. Create Thread & Message
            thread = await asyncio.to_thread(self.client.beta.threads.create)
            
            await asyncio.to_thread(
                self.client.beta.threads.messages.create,
                thread_id=thread.id,
                role="user",
                content=content
            )
            
            # 2. Start Run (With JSON Mode if requested)
            # Note: To use json_object, the prompt MUST contain the word "JSON".
            run_args = {
                "thread_id": thread.id,
                "assistant_id": assistant_id
            }
            
            if json_mode:
                run_args["response_format"] = {"type": "json_object"}

            run = await asyncio.to_thread(
                self.client.beta.threads.runs.create,
                **run_args
            )
            
            safe_log(f"{task_name}: Started Run {run.id} (JSON Mode: {json_mode})")
            
            # 3. Poll for completion
            start_time = time.time()
            while run.status in ['queued', 'in_progress', 'cancelling']:
                if time.time() - start_time > timeout_seconds:
                    return False, None, f"Timeout after {timeout_seconds}s"
                
                await asyncio.sleep(2.0)
                
                run = await asyncio.to_thread(
                    self.client.beta.threads.runs.retrieve,
                    thread_id=thread.id,
                    run_id=run.id
                )
            
            # 4. Handle Result
            if run.status == 'completed':
                messages = await asyncio.to_thread(
                    self.client.beta.threads.messages.list,
                    thread_id=thread.id
                )
                
                if not messages.data: return False, None, "No messages returned"
                
                latest_msg = messages.data[0]
                response_text = latest_msg.content[0].text.value
                safe_log(f"{task_name}: Success ({len(response_text)} chars)")
                return True, response_text, None
                
            elif run.status == 'failed':
                err = run.last_error
                msg = err.message if err else "Unknown error"
                return False, None, f"OpenAI Failed: {msg}"
            else:
                return False, None, f"Unexpected status: {run.status}"

        except Exception as e:
            safe_log(f"{task_name}: Exception - {str(e)}", "ERROR")
            return False, None, f"System Error: {str(e)}"

openai_service = OpenAIService()
