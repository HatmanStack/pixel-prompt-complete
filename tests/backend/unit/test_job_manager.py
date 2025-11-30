"""
Unit tests for job manager
"""

import pytest
import json
from datetime import datetime, timezone
from jobs.manager import JobManager


class TestJobManager:
    """Tests for JobManager class"""

    def test_create_job(self, mock_s3):
        """Test creating a new job"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        prompt = "a beautiful sunset"
        models = [
            {'id': 'model-a', 'index': 1},
            {'id': 'model-b', 'index': 2},
            {'id': 'model-c', 'index': 3}
        ]

        job_id = manager.create_job(prompt, models)

        # Verify job ID is a valid UUID-like string
        assert job_id is not None
        assert len(job_id) > 0

        # Verify job was saved to S3
        status = manager.get_job_status(job_id)

        assert status is not None
        assert status['jobId'] == job_id
        assert status['status'] == 'pending'
        assert status['totalModels'] == 3
        assert status['completedModels'] == 0
        assert status['prompt'] == prompt
        assert len(status['results']) == 3

        # Verify all results are initially pending
        for result in status['results']:
            assert result['status'] == 'pending'

    def test_get_nonexistent_job(self, mock_s3):
        """Test getting a job that doesn't exist"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        status = manager.get_job_status('nonexistent-job-id')

        assert status is None

    def test_mark_model_in_progress(self, mock_s3):
        """Test marking a model as in progress"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        # Create job
        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        # Mark model as in progress
        manager.mark_model_in_progress(job_id, 'model-a')

        # Verify status
        status = manager.get_job_status(job_id)

        assert status['status'] == 'in_progress'
        assert status['results'][0]['status'] == 'in_progress'
        assert 'startedAt' in status['results'][0]

    def test_mark_model_complete(self, mock_s3):
        """Test marking a model as completed"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        # Create job
        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        # Mark as in progress then complete
        manager.mark_model_in_progress(job_id, 'model-a')
        manager.mark_model_complete(job_id, 'model-a', 'images/test.png', 5.2)

        # Verify status
        status = manager.get_job_status(job_id)

        assert status['status'] == 'completed'
        assert status['completedModels'] == 1
        assert status['results'][0]['status'] == 'completed'
        assert status['results'][0]['imageKey'] == 'images/test.png'
        assert status['results'][0]['duration'] == 5.2
        assert 'completedAt' in status['results'][0]

    def test_mark_model_error(self, mock_s3):
        """Test marking a model as failed with error"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        # Create job
        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        # Mark as error
        manager.mark_model_error(job_id, 'model-a', 'API timeout')

        # Verify status
        status = manager.get_job_status(job_id)

        assert status['status'] == 'failed'
        assert status['results'][0]['status'] == 'error'
        assert status['results'][0]['error'] == 'API timeout'
        assert 'completedAt' in status['results'][0]

    def test_multiple_models_partial_completion(self, mock_s3):
        """Test job with multiple models in various states"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        # Create job with 3 models
        job_id = manager.create_job(
            "test prompt",
            [
                {'id': 'model-a', 'index': 1},
                {'id': 'model-b', 'index': 2},
                {'id': 'model-c', 'index': 3}
            ]
        )

        # Model A: completed
        manager.mark_model_in_progress(job_id, 'model-a')
        manager.mark_model_complete(job_id, 'model-a', 'images/a.png', 5.0)

        # Model B: error
        manager.mark_model_in_progress(job_id, 'model-b')
        manager.mark_model_error(job_id, 'model-b', 'Failed')

        # Model C: still pending

        # Verify overall status
        status = manager.get_job_status(job_id)

        assert status['status'] == 'in_progress'  # Model C still pending
        assert status['completedModels'] == 1

        # Complete Model C
        manager.mark_model_in_progress(job_id, 'model-c')
        manager.mark_model_complete(job_id, 'model-c', 'images/c.png', 6.0)

        # Now should be partial (mix of success and error)
        status = manager.get_job_status(job_id)
        assert status['status'] == 'partial'
        assert status['completedModels'] == 2

    def test_all_models_successful(self, mock_s3):
        """Test job status when all models complete successfully"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            [
                {'id': 'model-a', 'index': 1},
                {'id': 'model-b', 'index': 2}
            ]
        )

        # Complete both successfully
        manager.mark_model_complete(job_id, 'model-a', 'images/a.png', 5.0)
        manager.mark_model_complete(job_id, 'model-b', 'images/b.png', 6.0)

        status = manager.get_job_status(job_id)

        assert status['status'] == 'completed'
        assert status['completedModels'] == 2

    def test_all_models_failed(self, mock_s3):
        """Test job status when all models fail"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            [
                {'id': 'model-a', 'index': 1},
                {'id': 'model-b', 'index': 2}
            ]
        )

        # Both fail
        manager.mark_model_error(job_id, 'model-a', 'Error A')
        manager.mark_model_error(job_id, 'model-b', 'Error B')

        status = manager.get_job_status(job_id)

        assert status['status'] == 'failed'
        assert status['completedModels'] == 0

    def test_update_job_status(self, mock_s3):
        """Test updating job status with custom fields"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        # Update with custom fields
        manager.update_job_status(job_id, {
            'customField': 'custom value',
            'processingTime': 10.5
        })

        status = manager.get_job_status(job_id)

        assert status['customField'] == 'custom value'
        assert status['processingTime'] == 10.5
        assert 'updatedAt' in status

    def test_mark_nonexistent_model(self, mock_s3):
        """Test marking a model that doesn't exist in the job"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        # Try to mark nonexistent model
        with pytest.raises(ValueError, match="Model .* not found"):
            manager.mark_model_complete(job_id, 'nonexistent-model', 'images/test.png', 5.0)

    def test_update_nonexistent_job(self, mock_s3):
        """Test updating a job that doesn't exist"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        with pytest.raises(ValueError, match="Job .* not found"):
            manager.update_job_status('nonexistent-job', {})

    def test_job_timestamps_are_iso_format(self, mock_s3):
        """Test that all timestamps are in ISO format"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        status = manager.get_job_status(job_id)

        # Verify timestamps can be parsed
        assert datetime.fromisoformat(status['createdAt'])
        assert datetime.fromisoformat(status['updatedAt'])

        # Mark in progress and verify timestamp
        manager.mark_model_in_progress(job_id, 'model-a')
        status = manager.get_job_status(job_id)
        assert datetime.fromisoformat(status['results'][0]['startedAt'])

        # Mark complete and verify timestamp
        manager.mark_model_complete(job_id, 'model-a', 'images/test.png', 5.0)
        status = manager.get_job_status(job_id)
        assert datetime.fromisoformat(status['results'][0]['completedAt'])

    def test_job_results_preserve_model_index(self, mock_s3):
        """Test that model index is preserved in results"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        models = [
            {'id': 'model-a', 'index': 5},
            {'id': 'model-b', 'index': 10},
            {'id': 'model-c', 'index': 15}
        ]

        job_id = manager.create_job("test", models)

        status = manager.get_job_status(job_id)

        # Verify indices are preserved
        assert status['results'][0]['index'] == 5
        assert status['results'][1]['index'] == 10
        assert status['results'][2]['index'] == 15

    def test_completed_models_count_accuracy(self, mock_s3):
        """Test that completedModels count is accurate"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test",
            [
                {'id': 'model-a', 'index': 1},
                {'id': 'model-b', 'index': 2},
                {'id': 'model-c', 'index': 3}
            ]
        )

        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 0

        # Complete one model
        manager.mark_model_complete(job_id, 'model-a', 'images/a.png', 5.0)
        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 1

        # Error on one model (doesn't count as completed)
        manager.mark_model_error(job_id, 'model-b', 'Error')
        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 1

        # Complete another model
        manager.mark_model_complete(job_id, 'model-c', 'images/c.png', 6.0)
        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 2

    def test_job_data_persistence(self, mock_s3):
        """Test that job data persists correctly in S3"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            [{'id': 'model-a', 'index': 1}]
        )

        # Retrieve raw data from S3
        key = f"jobs/{job_id}/status.json"
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        raw_data = json.loads(response['Body'].read().decode('utf-8'))

        # Verify structure
        assert raw_data['jobId'] == job_id
        assert raw_data['prompt'] == "test prompt"
