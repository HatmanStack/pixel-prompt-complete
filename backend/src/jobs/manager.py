"""
Job Manager for Pixel Prompt Complete.

Manages job lifecycle including creation, status updates, and S3 storage.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from botocore.exceptions import ClientError


# Maximum retries for optimistic locking conflicts
MAX_RETRIES = 3
RETRY_DELAY_MS = 50


class JobManager:
    """
    Manages image generation job lifecycle with S3-based status storage.
    """

    def __init__(self, s3_client, bucket_name: str):
        """
        Initialize Job Manager.

        Args:
            s3_client: boto3 S3 client
            bucket_name: S3 bucket name for job storage
        """
        self.s3 = s3_client
        self.bucket = bucket_name

    def create_job(self, prompt: str, models: List[Dict]) -> str:
        """
        Create a new image generation job.

        Args:
            prompt: Text prompt for image generation
            models: List of model configurations

        Returns:
            Job ID (UUID)
        """
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Build initial job status
        now = datetime.now(timezone.utc).isoformat()

        status = {
            'jobId': job_id,
            'status': 'pending',
            'version': 1,  # Optimistic locking version
            'createdAt': now,
            'updatedAt': now,
            'totalModels': len(models),
            'completedModels': 0,
            'prompt': prompt,
            'results': [
                {
                    'model': model['id'],
                    'status': 'pending',
                    'index': model['index']
                }
                for model in models
            ]
        }

        # Save to S3
        self._save_status(job_id, status)


        return job_id

    def update_job_status(self, job_id: str, updates: Dict) -> None:
        """
        Update job status with partial updates.

        Args:
            job_id: Job ID
            updates: Dictionary of fields to update
        """
        # Get current status
        status = self.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job {job_id} not found")

        # Apply updates
        status.update(updates)
        status['updatedAt'] = datetime.now(timezone.utc).isoformat()

        # Recompute overall status
        status['status'] = self._compute_overall_status(status)

        # Save to S3
        self._save_status(job_id, status)

    def mark_model_complete(self, job_id: str, model_name: str, image_key: str, duration: float) -> None:
        """
        Mark a model as completed successfully.

        Uses optimistic locking with retries to handle concurrent updates.

        Args:
            job_id: Job ID
            model_name: Name of the model
            image_key: S3 key where image is stored
            duration: Processing duration in seconds
        """
        for attempt in range(MAX_RETRIES):
            status = self.get_job_status(job_id)
            if not status:
                raise ValueError(f"Job {job_id} not found")

            original_version = status.get('version', 1)

            # Find and update the model result
            for result in status['results']:
                if result['model'] == model_name:
                    result['status'] = 'completed'
                    result['imageKey'] = image_key
                    result['completedAt'] = datetime.now(timezone.utc).isoformat()
                    result['duration'] = duration
                    break
            else:
                raise ValueError(f"Model {model_name} not found in job {job_id} results")

            # Update completed count
            status['completedModels'] = sum(
                1 for r in status['results'] if r['status'] == 'completed'
            )

            # Update overall status and version
            status['status'] = self._compute_overall_status(status)
            status['updatedAt'] = datetime.now(timezone.utc).isoformat()
            status['version'] = original_version + 1

            # Try to save with version check
            if self._save_status_with_version(job_id, status, original_version):
                return  # Success

            # Version conflict - retry after short delay
            time.sleep(RETRY_DELAY_MS / 1000.0)

        # All retries exhausted - force save (last writer wins)
        self._save_status(job_id, status)


    def mark_model_error(self, job_id: str, model_name: str, error: str) -> None:
        """
        Mark a model as failed with error.

        Uses optimistic locking with retries to handle concurrent updates.

        Args:
            job_id: Job ID
            model_name: Name of the model
            error: Error message
        """
        for attempt in range(MAX_RETRIES):
            status = self.get_job_status(job_id)
            if not status:
                raise ValueError(f"Job {job_id} not found")

            original_version = status.get('version', 1)

            # Find and update the model result
            for result in status['results']:
                if result['model'] == model_name:
                    result['status'] = 'error'
                    result['error'] = error
                    result['completedAt'] = datetime.now(timezone.utc).isoformat()
                    break
            else:
                raise ValueError(f"Model {model_name} not found in job {job_id} results")

            # Update overall status and version
            status['status'] = self._compute_overall_status(status)
            status['updatedAt'] = datetime.now(timezone.utc).isoformat()
            status['version'] = original_version + 1

            # Try to save with version check
            if self._save_status_with_version(job_id, status, original_version):
                return  # Success

            # Version conflict - retry after short delay
            time.sleep(RETRY_DELAY_MS / 1000.0)

        # All retries exhausted - force save
        self._save_status(job_id, status)


    def mark_model_in_progress(self, job_id: str, model_name: str) -> None:
        """
        Mark a model as in progress.

        Args:
            job_id: Job ID
            model_name: Name of the model
        """
        status = self.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job {job_id} not found")

        # Find and update the model result
        for result in status['results']:
            if result['model'] == model_name:
                result['status'] = 'in_progress'
                result['startedAt'] = datetime.now(timezone.utc).isoformat()
                break
        else:
            raise ValueError(f"Model {model_name} not found in job {job_id} results")

        # Update overall status if this is the first model to start
        if status['status'] == 'pending':
            status['status'] = 'in_progress'

        status['updatedAt'] = datetime.now(timezone.utc).isoformat()

        # Save
        self._save_status(job_id, status)


    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """
        Get job status from S3.

        Args:
            job_id: Job ID

        Returns:
            Job status dict or None if not found
        """
        try:
            key = f"jobs/{job_id}/status.json"
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            status = json.loads(response['Body'].read().decode('utf-8'))
            return status

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            else:
                raise

    def _save_status(self, job_id: str, status: Dict) -> None:
        """
        Save job status to S3.

        Args:
            job_id: Job ID
            status: Status dict to save
        """
        key = f"jobs/{job_id}/status.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(status, indent=2),
            ContentType='application/json'
        )

    def _save_status_with_version(self, job_id: str, status: Dict, expected_version: int) -> bool:
        """
        Save job status to S3 with optimistic locking version check.

        This provides a basic form of optimistic locking by checking if the
        version has changed since we read the status. Since S3 doesn't support
        conditional writes based on content, we re-read and verify.

        Args:
            job_id: Job ID
            status: Status dict to save
            expected_version: The version we expect the current status to have

        Returns:
            True if save was successful, False if version conflict detected
        """
        # Re-read current status to check version
        current = self.get_job_status(job_id)
        if current and current.get('version', 1) != expected_version:
            # Version conflict - another writer updated the status
            return False

        # Version matches - safe to write
        self._save_status(job_id, status)
        return True

    def _compute_overall_status(self, status: Dict) -> str:
        """
        Compute overall job status based on model statuses.

        Args:
            status: Job status dict

        Returns:
            Overall status string
        """
        results = status['results']
        total = len(results)

        pending_count = sum(1 for r in results if r['status'] == 'pending')
        in_progress_count = sum(1 for r in results if r['status'] == 'in_progress')
        completed_count = sum(1 for r in results if r['status'] == 'completed')
        error_count = sum(1 for r in results if r['status'] == 'error')

        # All pending
        if pending_count == total:
            return 'pending'

        # All done (completed or error)
        if pending_count == 0 and in_progress_count == 0:
            if error_count == 0:
                return 'completed'  # All successful
            elif completed_count == 0:
                return 'failed'  # All failed
            else:
                return 'partial'  # Mix of success and errors

        # Some still processing
        return 'in_progress'
