"""Tests for the FastAPI endpoints."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app


client = TestClient(app)


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    def test_login_creates_new_user(self):
        """Login with new username should create user."""
        with patch('backend.main.db') as mock_db:
            # User doesn't exist
            mock_db.get_user_by_username.return_value = None

            # Create returns a user object
            mock_user = MagicMock()
            mock_user.user_id = 'test-user-id'
            mock_user.username = 'testuser'
            mock_user.onboarding_info = None
            mock_db.create_user_with_username.return_value = mock_user

            response = client.post('/api/auth/login', json={'username': 'testuser'})

            assert response.status_code == 200
            data = response.json()
            assert data['user_id'] == 'test-user-id'
            assert data['is_new_user'] == True

    def test_login_returns_existing_user(self):
        """Login with existing username should return user."""
        with patch('backend.main.db') as mock_db:
            # User exists
            mock_user = MagicMock()
            mock_user.user_id = 'existing-user-id'
            mock_user.username = 'existinguser'
            mock_user.onboarding_info = 'User background info'
            mock_db.get_user_by_username.return_value = mock_user

            response = client.post('/api/auth/login', json={'username': 'existinguser'})

            assert response.status_code == 200
            data = response.json()
            assert data['user_id'] == 'existing-user-id'
            assert data['is_new_user'] == False
            assert data['onboarding_info'] == 'User background info'


class TestDiscoveryEndpoints:
    """Tests for discovery session endpoints."""

    def test_start_discovery_creates_new_session(self):
        """Starting discovery should create a new session."""
        with patch('backend.main.db') as mock_db, \
             patch('backend.main.session_manager') as mock_sm, \
             patch('backend.main.audio_service'):
            
            mock_db.get_session_for_goal.return_value = None
            mock_db.get_or_create_exploration_session.return_value = {
                'is_new': True,
                'session_id': 'new-session-id',
            }
            
            # Create a mock session data
            mock_session_data = MagicMock()
            mock_session_data.discovery_session.start.return_value = 'Welcome!'
            mock_sm.create_session = AsyncMock(return_value=mock_session_data)
            
            response = client.post('/api/discovery/start', json={
                'models': {'interviewer': 'test-model'},
                'user_id': 'test-user',
            })
            
            assert response.status_code == 200
            data = response.json()
            assert 'session_id' in data

    def test_start_discovery_resumes_existing_session(self):
        """Starting discovery with existing session should resume."""
        with patch('backend.main.db') as mock_db, \
             patch('backend.main.session_manager') as mock_sm, \
             patch('backend.main.audio_service'):
            
            mock_db.get_session_for_goal.return_value = None
            mock_db.get_or_create_exploration_session.return_value = {
                'is_new': False,
                'session_id': 'existing-session-id',
                'conversation_history': [
                    {'role': 'assistant', 'content': 'Hello'},
                    {'role': 'user', 'content': 'Hi'},
                ],
                'schema_state': {},
                'profile_summary': 'User summary',
            }
            
            mock_session_data = MagicMock()
            mock_session_data.discovery_session.start.return_value = ''
            mock_sm.create_session = AsyncMock(return_value=mock_session_data)
            
            response = client.post('/api/discovery/start', json={
                'user_id': 'test-user',
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data['is_resumed'] == True
            assert len(data['conversation_history']) == 2


class TestGoalEndpoints:
    """Tests for goal management endpoints."""

    def test_create_goal_for_user(self):
        """Creating a goal should store it in database."""
        with patch('backend.main.db') as mock_db:
            # create_goal returns a UserGoal object, not an int
            mock_goal = MagicMock()
            mock_goal.id = 5
            mock_goal.goal_text = 'Learn backpropagation'
            mock_db.create_goal.return_value = mock_goal

            response = client.post('/api/user/goals', json={
                'user_id': 'test-user-id',
                'goal_text': 'Learn backpropagation',
            })

            assert response.status_code == 200
            data = response.json()
            assert data['id'] == 5
            assert data['goal_text'] == 'Learn backpropagation'

    def test_get_user_data_includes_goals(self):
        """Getting user data should include goals."""
        with patch('backend.main.db') as mock_db:
            # Mock user object
            mock_user = MagicMock()
            mock_user.user_id = 'test-user-id'
            mock_user.username = 'testuser'
            mock_user.onboarding_info = 'Background'
            mock_db.get_or_create_user.return_value = mock_user

            # Mock goals list (returns dicts that get unpacked into GoalResponse)
            mock_db.get_user_goals.return_value = [
                {'id': 1, 'goal_text': 'Goal 1', 'status': 'active', 'created_at': '2026-01-01', 'has_teaching_candidate': False},
                {'id': 2, 'goal_text': 'Goal 2', 'status': 'active', 'created_at': '2026-01-01', 'has_teaching_candidate': False},
            ]

            # Mock exploration session
            mock_db.get_user_exploration_session.return_value = None

            response = client.get('/api/user/test-user-id/data')

            assert response.status_code == 200
            data = response.json()
            assert len(data['goals']) == 2
            assert data['goals'][0]['goal_text'] == 'Goal 1'


class TestSessionPersistence:
    """Tests for session persistence behavior."""

    def test_goal_session_created_with_goal_id(self):
        """Goal sessions should be associated with goal_id."""
        with patch('backend.main.db') as mock_db, \
             patch('backend.main.session_manager') as mock_sm, \
             patch('backend.main.audio_service'):
            
            mock_db.get_session_for_goal.return_value = None
            
            mock_session_data = MagicMock()
            mock_session_data.discovery_session.start.return_value = 'Welcome to your goal!'
            mock_sm.create_session = AsyncMock(return_value=mock_session_data)
            
            response = client.post('/api/discovery/start', json={
                'goal_id': 123,
                'goal': 'Learn backpropagation',
                'user_id': 'test-user',
            })
            
            assert response.status_code == 200
            # Should create session with goal_id
            mock_db.create_session_with_type.assert_called()

    def test_resumed_session_with_empty_history_gets_opening(self):
        """Resumed session with empty history should get opening message."""
        with patch('backend.main.db') as mock_db, \
             patch('backend.main.session_manager') as mock_sm, \
             patch('backend.main.audio_service'):
            
            # Return existing session but with empty history
            mock_db.get_session_for_goal.return_value = {
                'session_id': 'existing-session',
                'conversation_history': [],  # Empty
                'schema_state': None,
            }
            
            mock_session_data = MagicMock()
            mock_session_data.discovery_session.start.return_value = 'Welcome!'
            mock_sm.create_session = AsyncMock(return_value=mock_session_data)
            
            response = client.post('/api/discovery/start', json={
                'goal_id': 123,
                'goal': 'Learn backpropagation',
                'user_id': 'test-user',
            })
            
            assert response.status_code == 200
            data = response.json()
            # Should have opening message even though is_resumed
            assert data['opening_message'] == 'Welcome!'





