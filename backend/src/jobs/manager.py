"""
Session Manager for Pixel Prompt v2.

Manages session lifecycle with iteration tracking per model column.
Replaces the previous job-based storage with session-centric storage.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from botocore.exceptions import ClientError

from config import MAX_ITERATIONS


# Maximum retries for optimistic locking conflicts
MAX_RETRIES = 3
RETRY_DELAY_MS = 50


class SessionManager:
    """
    Manages image generation sessions with iteration tracking per model.

    Sessions are stored in S3 at: sessions/{session_id}/status.json

    Each session tracks:
    - Original prompt
    - 4 model columns (flux, recraft, gemini, openai)
    - Up to 7 iterations per model
    - Status per model and overall
    """

    def __init__(self, s3_client, bucket_name: str):
        """
        Initialize Session Manager.

        Args:
            s3_client: boto3 S3 client
            bucket_name: S3 bucket name for session storage
        """
        self.s3 = s3_client
        self.bucket = bucket_name

    def create_session(self, prompt: str, enabled_models: List[str]) -> str:
        """
        Create a new session with the given enabled models.

        Args:
            prompt: Original text prompt
            enabled_models: List of enabled model names ('flux', 'recraft', etc.)

        Returns:
            Session ID (UUID)
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Initialize model states for all 4 models
        models = {}
        for model_name in ['flux', 'recraft', 'gemini', 'openai']:
            models[model_name] = {
                'enabled': model_name in enabled_models,
                'status': 'pending' if model_name in enabled_models else 'disabled',
                'iterationCount': 0,
                'iterations': []
            }

        status = {
            'sessionId': session_id,
            'status': 'pending',
            'version': 1,
            'prompt': prompt,
            'createdAt': now,
            'updatedAt': now,
            'models': models
        }

        self._save_status(session_id, status)
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session status from S3.

        Args:
            session_id: Session identifier

        Returns:
            Session status dict or None if not found
        """
        try:
            key = f"sessions/{session_id}/status.json"
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise

    def add_iteration(
        self,
        session_id: str,
        model: str,
        prompt: str,
        is_outpaint: bool = False,
        outpaint_preset: Optional[str] = None
    ) -> int:
        """
        Add a new iteration to a model column.

        Args:
            session_id: Session identifier
            model: Model name ('flux', 'recraft', 'gemini', 'openai')
            prompt: Iteration prompt
            is_outpaint: Whether this is an outpaint operation
            outpaint_preset: Outpaint preset if applicable

        Returns:
            New iteration index

        Raises:
            ValueError: If session/model not found or iteration limit reached
        """
        for attempt in range(MAX_RETRIES):
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            if model not in session['models']:
                raise ValueError(f"Unknown model: {model}")

            model_data = session['models'][model]
            if not model_data['enabled']:
                raise ValueError(f"Model '{model}' is disabled")

            # Check iteration limit
            if model_data['iterationCount'] >= MAX_ITERATIONS:
                raise ValueError(
                    f"Iteration limit ({MAX_ITERATIONS}) reached for model '{model}'"
                )

            original_version = session.get('version', 1)
            iteration_index = model_data['iterationCount']
            now = datetime.now(timezone.utc).isoformat()

            # Add iteration
            iteration = {
                'index': iteration_index,
                'status': 'in_progress',
                'prompt': prompt,
                'startedAt': now,
                'isOutpaint': is_outpaint
            }
            if outpaint_preset:
                iteration['outpaintPreset'] = outpaint_preset

            model_data['iterations'].append(iteration)
            model_data['iterationCount'] = iteration_index + 1
            model_data['status'] = 'in_progress'

            # Update session
            session['status'] = self._compute_session_status(session)
            session['updatedAt'] = now
            session['version'] = original_version + 1

            if self._save_status_with_version(session_id, session, original_version):
                return iteration_index

            time.sleep(RETRY_DELAY_MS / 1000.0)

        # Force save on retry exhaustion
        self._save_status(session_id, session)
        return iteration_index

    def complete_iteration(
        self,
        session_id: str,
        model: str,
        index: int,
        image_key: str,
        duration: Optional[float] = None
    ) -> None:
        """
        Mark an iteration as completed with image key.

        Args:
            session_id: Session identifier
            model: Model name
            index: Iteration index
            image_key: S3 key of generated image
            duration: Processing duration in seconds (optional)
        """
        for attempt in range(MAX_RETRIES):
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            original_version = session.get('version', 1)
            model_data = session['models'][model]

            # Find iteration
            iteration = None
            for it in model_data['iterations']:
                if it['index'] == index:
                    iteration = it
                    break

            if not iteration:
                raise ValueError(f"Iteration {index} not found for model '{model}'")

            now = datetime.now(timezone.utc).isoformat()
            iteration['status'] = 'completed'
            iteration['imageKey'] = image_key
            iteration['completedAt'] = now
            if duration is not None:
                iteration['duration'] = duration

            # Update model status
            model_data['status'] = self._compute_model_status(model_data)

            # Update session
            session['status'] = self._compute_session_status(session)
            session['updatedAt'] = now
            session['version'] = original_version + 1

            if self._save_status_with_version(session_id, session, original_version):
                return

            time.sleep(RETRY_DELAY_MS / 1000.0)

        self._save_status(session_id, session)

    def fail_iteration(
        self,
        session_id: str,
        model: str,
        index: int,
        error: str
    ) -> None:
        """
        Mark an iteration as failed with error message.

        Args:
            session_id: Session identifier
            model: Model name
            index: Iteration index
            error: Error message
        """
        for attempt in range(MAX_RETRIES):
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            original_version = session.get('version', 1)
            model_data = session['models'][model]

            # Find iteration
            iteration = None
            for it in model_data['iterations']:
                if it['index'] == index:
                    iteration = it
                    break

            if not iteration:
                raise ValueError(f"Iteration {index} not found for model '{model}'")

            now = datetime.now(timezone.utc).isoformat()
            iteration['status'] = 'error'
            iteration['error'] = error
            iteration['completedAt'] = now

            # Update model status
            model_data['status'] = self._compute_model_status(model_data)

            # Update session
            session['status'] = self._compute_session_status(session)
            session['updatedAt'] = now
            session['version'] = original_version + 1

            if self._save_status_with_version(session_id, session, original_version):
                return

            time.sleep(RETRY_DELAY_MS / 1000.0)

        self._save_status(session_id, session)

    def get_iteration_count(self, session_id: str, model: str) -> int:
        """
        Get current iteration count for a model.

        Args:
            session_id: Session identifier
            model: Model name

        Returns:
            Current iteration count (0-7)
        """
        session = self.get_session(session_id)
        if not session:
            return 0

        model_data = session['models'].get(model)
        if not model_data:
            return 0

        return model_data.get('iterationCount', 0)

    def get_latest_image_key(self, session_id: str, model: str) -> Optional[str]:
        """
        Get the image key of the latest completed iteration.

        Args:
            session_id: Session identifier
            model: Model name

        Returns:
            S3 image key or None if no completed iterations
        """
        session = self.get_session(session_id)
        if not session:
            return None

        model_data = session['models'].get(model)
        if not model_data:
            return None

        # Find latest completed iteration
        completed = [
            it for it in model_data['iterations']
            if it['status'] == 'completed' and 'imageKey' in it
        ]

        if not completed:
            return None

        # Return the one with highest index
        latest = max(completed, key=lambda x: x['index'])
        return latest.get('imageKey')

    def _save_status(self, session_id: str, status: Dict) -> None:
        """Save session status to S3."""
        key = f"sessions/{session_id}/status.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(status, indent=2),
            ContentType='application/json'
        )

    def _save_status_with_version(
        self,
        session_id: str,
        status: Dict,
        expected_version: int
    ) -> bool:
        """
        Save with optimistic locking version check.

        Returns True if successful, False if version conflict.
        """
        current = self.get_session(session_id)
        if current and current.get('version', 1) != expected_version:
            return False
        self._save_status(session_id, status)
        return True

    def _compute_model_status(self, model_data: Dict) -> str:
        """Compute status for a single model based on its iterations."""
        if not model_data['enabled']:
            return 'disabled'

        iterations = model_data['iterations']
        if not iterations:
            return 'pending'

        # Check if any in progress
        if any(it['status'] == 'in_progress' for it in iterations):
            return 'in_progress'

        # All iterations complete
        has_error = any(it['status'] == 'error' for it in iterations)
        has_completed = any(it['status'] == 'completed' for it in iterations)

        if has_error and not has_completed:
            return 'error'
        elif has_error:
            return 'partial'
        else:
            return 'completed'

    def _compute_session_status(self, session: Dict) -> str:
        """Compute overall session status from model statuses."""
        models = session['models']
        enabled_models = [m for m in models.values() if m['enabled']]

        if not enabled_models:
            return 'failed'

        statuses = [m['status'] for m in enabled_models]

        if all(s == 'pending' for s in statuses):
            return 'pending'

        if any(s == 'in_progress' for s in statuses):
            return 'in_progress'

        # All done
        error_count = sum(1 for s in statuses if s in ['error', 'failed'])
        completed_count = sum(1 for s in statuses if s in ['completed', 'partial'])

        if error_count == len(enabled_models):
            return 'failed'
        elif error_count > 0:
            return 'partial'
        else:
            return 'completed'


# Backward compatibility alias
JobManager = SessionManager
