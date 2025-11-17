"""
Job Manager for Pixel Prompt Complete.

Manages job lifecycle including creation, status updates, and S3 storage.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError


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

    def create_job(self, prompt: str, params: Dict, models: List[Dict]) -> str:
        """
        Create a new image generation job.

        Args:
            prompt: Text prompt for image generation
            params: Generation parameters (steps, guidance, etc.)
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
            'createdAt': now,
            'updatedAt': now,
            'totalModels': len(models),
            'completedModels': 0,
            'prompt': prompt,
            'parameters': params,
            'results': [
                {
                    'model': model['name'],
                    'status': 'pending',
                    'index': model['index']
                }
                for model in models
            ]
        }

        # Save to S3
        self._save_status(job_id, status)

        print(f"Created job {job_id} with {len(models)} models")

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

        Args:
            job_id: Job ID
            model_name: Name of the model
            image_key: S3 key where image is stored
            duration: Processing duration in seconds
        """
        status = self.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job {job_id} not found")

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

        # Update overall status
        status['status'] = self._compute_overall_status(status)
        status['updatedAt'] = datetime.now(timezone.utc).isoformat()

        # Save
        self._save_status(job_id, status)

        print(f"Job {job_id}: Model {model_name} completed ({status['completedModels']}/{status['totalModels']})")

    def mark_model_error(self, job_id: str, model_name: str, error: str) -> None:
        """
        Mark a model as failed with error.

        Args:
            job_id: Job ID
            model_name: Name of the model
            error: Error message
        """
        status = self.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job {job_id} not found")

        # Find and update the model result
        for result in status['results']:
            if result['model'] == model_name:
                result['status'] = 'error'
                result['error'] = error
                result['completedAt'] = datetime.now(timezone.utc).isoformat()
                break
        else:
            raise ValueError(f"Model {model_name} not found in job {job_id} results")

        # Update overall status
        status['status'] = self._compute_overall_status(status)
        status['updatedAt'] = datetime.now(timezone.utc).isoformat()

        # Save
        self._save_status(job_id, status)

        print(f"Job {job_id}: Model {model_name} failed: {error}")

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

        print(f"Job {job_id}: Model {model_name} started")

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
                print(f"Job {job_id} not found in S3")
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
