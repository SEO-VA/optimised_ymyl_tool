#!/usr/bin/env python3
"""
OpenAI Service Module - Assistants API (Polling)
Updated: Supports optional tool enforcement (force_tool=True).
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
                                   timeout_seconds: int = 300,
                                   force_tool: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Uses the Assistants API with Polling.
        If force_tool=True, it MANDATES the use of 'file_search'.
        """
        try:
            # 1. Create Thread
            thread = await self.client.beta.threads.create()

            # 2. Add Message
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=content
            )

            # 3. Configure Run
            run_args = {
                "thread_id": thread.id,
                "assistant_id": assistant_id,
                "response_format": {"type": "json_object"}
            }
            
            # FORCE TOOL USE (Only if requested)
            # This prevents the Analyzer from ignoring the PDF.
            if force_tool:
                run_args["tool_choice"] = {"type": "file_search"}

            # 4. Create & Poll
            run = await self.client.beta.threads.runs.create_and_poll(**run_args)

            # 5. Check Status
            if run.status == 'completed':
                messages = await self.client.beta.threads.messages.list(
                    thread_id=thread.id,
                    order="desc", 
                    limit=1
                )
                if not messages.data: return False, None, "No messages"
                
                result_text = messages.data[0].content[0].text.value
                safe_log(f"{task_name}: Success ({len(result_text)} chars)")
                return True, result_text, None
            else:
                err_msg = run.last_error.message if run.last_error else run.status
                safe_log(f"{task_name}: Run Failed - {err_msg}", "ERROR")
                return False, None, f"AI Error: {err_msg}"

        except Exception as e:
            safe_log(f"{task_name}: Exception - {str(e)}", "ERROR")
            return False, None, f"System Error: {str(e)}"

openai_service = OpenAIService()
