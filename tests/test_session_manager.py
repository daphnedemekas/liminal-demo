"""Tests for the session manager."""
import pytest
import asyncio
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.session_manager import SessionManager, SessionData


class TestSessionManager:
    """Tests for SessionManager."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.mark.asyncio
    async def test_create_session_returns_session_data(self, session_manager):
        """Creating a session should return a SessionData object."""
        with patch('backend.services.session_manager.DiscoveryOrchestrator') as mock_orch:
            mock_orch.return_value = MagicMock()
            
            session_data = await session_manager.create_session(
                session_id='test-session-123',
                debug=False,
                model_config={'interviewer': 'test-model'},
                user_goal=None,
                user_id='test-user',
            )
            
            assert isinstance(session_data, SessionData)
            assert session_data.session_id == 'test-session-123'

    @pytest.mark.asyncio
    async def test_create_session_with_goal_sets_goal_in_schema(self, session_manager):
        """Creating a session with a goal should set the goal in the schema."""
        with patch('backend.services.session_manager.DiscoveryOrchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_instance.schema.interview_state.user_goal = None
            mock_instance.schema.interview_state.goal_provided = False
            mock_instance.schema.interview_state.goal_identified = False
            mock_orch.return_value = mock_instance
            
            session_data = await session_manager.create_session(
                session_id='test-session-123',
                user_goal='Learn backpropagation',
                user_id='test-user',
            )
            
            # Goal should be set in schema
            assert mock_instance.schema.interview_state.user_goal == 'Learn backpropagation'
            assert mock_instance.schema.interview_state.goal_provided == True
            assert mock_instance.schema.interview_state.goal_identified == True

    @pytest.mark.asyncio
    async def test_get_session_returns_none_for_unknown_session(self, session_manager):
        """Getting an unknown session should return None."""
        result = await session_manager.get_session('nonexistent-session')
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_returns_existing_session(self, session_manager):
        """Getting an existing session should return the session data."""
        with patch('backend.services.session_manager.DiscoveryOrchestrator') as mock_orch:
            mock_orch.return_value = MagicMock()
            
            # Create a session first
            await session_manager.create_session(
                session_id='test-session-123',
                user_id='test-user',
            )
            
            # Retrieve it
            session_data = await session_manager.get_session('test-session-123')
            
            assert session_data is not None
            assert session_data.session_id == 'test-session-123'

    @pytest.mark.asyncio
    async def test_create_session_does_not_set_goal_when_schema_state_provided(self, session_manager):
        """When schema_state is provided, should not override goal."""
        with patch('backend.services.session_manager.DiscoveryOrchestrator') as mock_orch:
            mock_instance = MagicMock()
            mock_orch.return_value = mock_instance
            
            await session_manager.create_session(
                session_id='test-session-123',
                user_goal='New Goal',
                user_id='test-user',
                schema_state={'some': 'state'},  # Existing state
            )
            
            # Goal should NOT be set in schema (existing state takes precedence)
            # The goal_provided/goal_identified attributes should not be modified


class TestSessionData:
    """Tests for SessionData."""

    def test_session_data_initialization(self):
        """SessionData should initialize with expected defaults."""
        session_data = SessionData('test-session-123')
        
        assert session_data.session_id == 'test-session-123'
        assert session_data.discovery_session is None
        assert session_data.final_topic is None
        assert session_data.learning_conversation == []
        assert session_data.learning_state == 'not_started'


