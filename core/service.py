#!/usr/bin/env python3
"""
OpenAI Service Module
Handles the low-level network communication with OpenAI's Assistant API.
Isolates Thread management, Run polling, and Timeout handling from business logic.
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
    Responsible for sending prompts and retrieving raw text responses.
    Does NOT parse JSON or handle business logic.
    """
    
    def __init__(self):
        """Initialize OpenAI client using Streamlit secrets"""
        try:
            self.client = OpenAI(api_key=st.secrets["openai_api_key"])
        except KeyError:
            safe_log("OpenAI Service: API Key not found in secrets!", "CRITICAL")
            raise

    async def get_response_async(self, 
                               content: str, 
                               assistant_id: str, 
                               timeout_seconds: int = 300,
                               task_name: str = "Audit") -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Full async workflow: Create Thread -> Run Assistant -> Poll for Completion -> Get Text.
        
        Returns:
            Tuple(success: bool, response_text: str, error_message: str)
        """
        try:
            # 1. Create Thread & Message (Blocking call, run in executor if needed, but usually fast)
            # Note: OpenAI Python SDK is synchronous by default, but we wrap logically here
            # For true async IO, we'd need AsyncOpenAI, but this works for Streamlit's event loop
            thread = await asyncio.to_thread(self.client.beta.threads.create)
            
            await asyncio.to_thread(
                self.client.beta.threads.messages.create,
                thread_id=thread.id,
                role="user",
                content=content
            )
            
            # 2. Start Run
            run = await asyncio.to_thread(
                self.client.beta.threads.runs.create,
                thread_id=thread.id,
                assistant_id=assistant_id
            )
            
            safe_log(f"{task_name}: Started Run {run.id} on Thread {thread.id}")
            
            # 3. Poll for completion
            start_time = time.time()
            while run.status in ['queued', 'in_progress', 'cancelling']:
                
                # Check timeout
                if time.time() - start_time > timeout_seconds:
                    return False, None, f"Timeout after {timeout_seconds}s"
                
                # Wait before polling again
                await asyncio.sleep(2.0)
                
                # Check status
                run = await asyncio.to_thread(
                    self.client.beta.threads.runs.retrieve,
                    thread_id=thread.id,
                    run_id=run.id
                )
            
            # 4. Handle Final Status
            if run.status == 'completed':
                messages = await asyncio.to_thread(
                    self.client.beta.threads.messages.list,
                    thread_id=thread.id
                )
                
                # Extract text from the latest message
                if not messages.data:
                    return False, None, "Run completed but returned no messages"
                    
                latest_msg = messages.data[0]
                if latest_msg.role != "assistant":
                    return False, None, "Last message was not from assistant"
                    
                response_text = latest_msg.content[0].text.value
                safe_log(f"{task_name}: Success ({len(response_text)} chars)")
                return True, response_text, None
                
            elif run.status == 'failed':
                error_code = run.last_error.code if run.last_error else "unknown"
                error_msg = run.last_error.message if run.last_error else "Run failed"
                return False, None, f"OpenAI Error ({error_code}): {error_msg}"
                
            else:
                return False, None, f"Unexpected run status: {run.status}"

        except Exception as e:
            safe_log(f"{task_name}: Exception - {str(e)}", "ERROR")
            return False, None, f"System Error: {str(e)}"

# Singleton instance
openai_service = OpenAIService()
