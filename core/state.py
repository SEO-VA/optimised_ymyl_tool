#!/usr/bin/env python3
"""
State Manager Module
Centralizes all Streamlit session state interactions.
Replaces manual string key manipulation with typed method calls.
"""

import streamlit as st
from typing import Dict, List, Optional, Any
from datetime import datetime
from core.models import FileState, AnalysisResult

class StateManager:
    """
    Wrapper around st.session_state to provide type-safe access to app data.
    """
    
    # Internal Storage Keys
    _KEY_MULTI_FILES = "state_multi_files"  # Stores Dict[filename, FileState]
    _KEY_SINGLE_RESULT = "state_single_result" # Stores AnalysisResult
    _KEY_IS_PROCESSING = "state_is_processing"
    _KEY_STOP_SIGNAL = "state_stop_signal"
    _KEY_EXTRACTED = "state_extracted_content"
    
    def __init__(self):
        """Initialize session state structure if not present"""
        if self._KEY_MULTI_FILES not in st.session_state:
            st.session_state[self._KEY_MULTI_FILES] = {}
            
        if self._KEY_IS_PROCESSING not in st.session_state:
            st.session_state[self._KEY_IS_PROCESSING] = False

    # --- Global Processing Flags ---
    
    @property
    def is_processing(self) -> bool:
        return st.session_state.get(self._KEY_IS_PROCESSING, False)
    
    @is_processing.setter
    def is_processing(self, value: bool):
        st.session_state[self._KEY_IS_PROCESSING] = value

    @property
    def stop_signal(self) -> bool:
        return st.session_state.get(self._KEY_STOP_SIGNAL, False)

    def trigger_stop(self):
        st.session_state[self._KEY_STOP_SIGNAL] = True

    def clear_stop(self):
        st.session_state[self._KEY_STOP_SIGNAL] = False

    # --- Multi-File Management ---

    def init_multi_file(self, filename: str):
        """Initialize a file tracking state"""
        files = st.session_state[self._KEY_MULTI_FILES]
        files[filename] = FileState(
            filename=filename,
            status='pending',
            start_time=datetime.now().timestamp()
        )

    def update_multi_file(self, filename: str, status: str, 
                         result: Optional[AnalysisResult] = None, 
                         error: Optional[str] = None):
        """Update the state of a specific file"""
        files = st.session_state[self._KEY_MULTI_FILES]
        if filename in files:
            state = files[filename]
            state.status = status
            if result:
                state.result = result
            if error:
                state.error_message = error

    def get_multi_file_state(self, filename: str) -> Optional[FileState]:
        """Get strict typed state object for a file"""
        return st.session_state[self._KEY_MULTI_FILES].get(filename)

    def get_all_files(self) -> Dict[str, FileState]:
        """Get all tracked files"""
        return st.session_state[self._KEY_MULTI_FILES]

    def clear_multi_files(self):
        """Wipe all multi-file data"""
        st.session_state[self._KEY_MULTI_FILES] = {}

    # --- Single File Management ---

    def set_single_result(self, result: AnalysisResult):
        """Store result for single-file mode"""
        st.session_state[self._KEY_SINGLE_RESULT] = result

    def get_single_result(self) -> Optional[AnalysisResult]:
        """Get result for single-file mode"""
        return st.session_state.get(self._KEY_SINGLE_RESULT)

    def clear_single_result(self):
        if self._KEY_SINGLE_RESULT in st.session_state:
            del st.session_state[self._KEY_SINGLE_RESULT]

    # --- Utility ---

    def reset_all(self):
        """Full Factory Reset of Session State"""
        self.clear_multi_files()
        self.clear_single_result()
        self.is_processing = False
        self.clear_stop()
        # Clear any legacy keys if needed
        st.session_state.clear()
        self.__init__() # Re-init structure

# Singleton Instance
state_manager = StateManager()
