#!/usr/bin/env python3
"""
OpenAI Service Module - Assistants API (Polling)
Updated: Forces 'file_search' tool usage to prevent hallucinations.
"""

import asyncio
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

    async def get_assistant_response(self, 
                                   content: str, 
                                   assistant_id: str, 
                                   task_name: str = "Audit",
                                   timeout_seconds: int = 300) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Uses the Assistants API with Polling.
        Forces the model to use the 'file_search' tool to verify facts against the PDF.
        """
        try:
            # 1. Create a fresh Thread (Stateless for each audit)
            thread = await self.client.beta.threads.create()

            # 2. Add the User Message (The Payload)
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=content
            )

            # 3. Create & Poll the Run
            # FORCE TOOL USE: We explicitly tell the AI it MUST use file_search.
            # This prevents "instant" answers from internal memory.
            run = await self.client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=assistant_id,
                response_format={"type": "json_object"}, # Force JSON output
                tool_choice={"type": "file_search"}      # <--- THE FIX: Force PDF Search
            )

            # 4. Check Status
            if run.status == 'completed':
                messages = await self.client.beta.threads.messages.list(
                    thread_id=thread.id,
                    order="desc", 
                    limit=1
                )
                
                if not messages.data:
                    return False, None, "No messages returned"
                
                result_text = messages.data[0].content[0].text.value
                safe_log(f"{task_name}: Success ({len(result_text)} chars)")
                return True, result_text, None
            
            else:
                # Handle failures (e.g. content filter, rate limit)
                err_msg = run.last_error.message if run.last_error else run.status
                safe_log(f"{task_name}: Run Failed - {err_msg}", "ERROR")
                return False, None, f"AI Error: {err_msg}"

        except Exception as e:
            safe_log(f"{task_name}: Exception - {str(e)}", "ERROR")
            return False, None, f"System Error: {str(e)}"

openai_service = OpenAIService()
