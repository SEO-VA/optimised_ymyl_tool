#!/usr/bin/env python3
"""
OpenAI Service Module - Optimized
Updated: Uses Streaming to reduce latency while keeping Vector Store access.
"""

import asyncio
import streamlit as st
from openai import AsyncOpenAI
from typing import Optional, Tuple
from utils.helpers import safe_log

class OpenAIService:
    def __init__(self):
        try:
            # Use AsyncOpenAI for native async support
            self.client = AsyncOpenAI(api_key=st.secrets["openai_api_key"])
        except KeyError:
            safe_log("OpenAI Service: API Key not found!", "CRITICAL")
            raise

    async def get_response_async(self, 
                               content: str, 
                               assistant_id: str, 
                               timeout_seconds: int = 300,
                               task_name: str = "Audit",
                               json_mode: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            # 1. Create Thread (Stateless for each audit)
            thread = await self.client.beta.threads.create()

            # 2. Add Message
            await self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=content
            )

            # 3. Create Run with Stream (The Speed Fix)
            # We use a simple event handler to capture the final text
            full_response = []
            
            safe_log(f"{task_name}: Starting Stream...")
            
            # Helper to collect stream chunks
            async with self.client.beta.threads.runs.stream(
                thread_id=thread.id,
                assistant_id=assistant_id,
                response_format={"type": "json_object"} if json_mode else "auto"
            ) as stream:
                async for event in stream:
                    # We only care about text deltas to build the final string
                    if event.event == 'thread.message.delta':
                        # Extract text delta safely
                        if event.data.delta.content:
                            text_chunk = event.data.delta.content[0].text.value
                            full_response.append(text_chunk)
                    
                    # Log errors if run fails
                    elif event.event == 'thread.run.failed':
                        return False, None, f"Run Failed: {event.data.last_error.message}"

            # 4. Assemble Final Text
            final_text = "".join(full_response)
            
            if not final_text:
                return False, None, "Stream ended with no content"
                
            safe_log(f"{task_name}: Success ({len(final_text)} chars)")
            return True, final_text, None

        except Exception as e:
            safe_log(f"{task_name}: Error - {str(e)}", "ERROR")
            return False, None, f"System Error: {str(e)}"

openai_service = OpenAIService()
