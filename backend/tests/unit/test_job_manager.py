"""
Unit tests for job manager
"""

import pytest
import json
from datetime import datetime, timezone
from src.jobs.manager import JobManager


class TestJobManager:
    """Tests for JobManager class"""

    def test_create_job(self, mock_s3):
        """Test creating a new job"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        prompt = "a beautiful sunset"
        params = {'steps': 28, 'guidance': 7.5}
        models = [
            {'name': 'Model A', 'index': 0},
            {'name': 'Model B', 'index': 1},
            {'name': 'Model C', 'index': 2}
        ]

        job_id = manager.create_job(prompt, params, models)

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
        assert status['parameters'] == params
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
            {'steps': 28},
            [{'name': 'Model A', 'index': 0}]
        )

        # Mark model as in progress
        manager.mark_model_in_progress(job_id, 'Model A')

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
            {'steps': 28},
            [{'name': 'Model A', 'index': 0}]
        )

        # Mark as in progress then complete
        manager.mark_model_in_progress(job_id, 'Model A')
        manager.mark_model_complete(job_id, 'Model A', 'images/test.png', 5.2)

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
            {'steps': 28},
            [{'name': 'Model A', 'index': 0}]
        )

        # Mark as error
        manager.mark_model_error(job_id, 'Model A', 'API timeout')

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
            {'steps': 28},
            [
                {'name': 'Model A', 'index': 0},
                {'name': 'Model B', 'index': 1},
                {'name': 'Model C', 'index': 2}
            ]
        )

        # Model A: completed
        manager.mark_model_in_progress(job_id, 'Model A')
        manager.mark_model_complete(job_id, 'Model A', 'images/a.png', 5.0)

        # Model B: error
        manager.mark_model_in_progress(job_id, 'Model B')
        manager.mark_model_error(job_id, 'Model B', 'Failed')

        # Model C: still pending

        # Verify overall status
        status = manager.get_job_status(job_id)

        assert status['status'] == 'in_progress'  # Model C still pending
        assert status['completedModels'] == 1

        # Complete Model C
        manager.mark_model_in_progress(job_id, 'Model C')
        manager.mark_model_complete(job_id, 'Model C', 'images/c.png', 6.0)

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
            {'steps': 28},
            [
                {'name': 'Model A', 'index': 0},
                {'name': 'Model B', 'index': 1}
            ]
        )

        # Complete both successfully
        manager.mark_model_complete(job_id, 'Model A', 'images/a.png', 5.0)
        manager.mark_model_complete(job_id, 'Model B', 'images/b.png', 6.0)

        status = manager.get_job_status(job_id)

        assert status['status'] == 'completed'
        assert status['completedModels'] == 2

    def test_all_models_failed(self, mock_s3):
        """Test job status when all models fail"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            {'steps': 28},
            [
                {'name': 'Model A', 'index': 0},
                {'name': 'Model B', 'index': 1}
            ]
        )

        # Both fail
        manager.mark_model_error(job_id, 'Model A', 'Error A')
        manager.mark_model_error(job_id, 'Model B', 'Error B')

        status = manager.get_job_status(job_id)

        assert status['status'] == 'failed'
        assert status['completedModels'] == 0

    def test_update_job_status(self, mock_s3):
        """Test updating job status with custom fields"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            {'steps': 28},
            [{'name': 'Model A', 'index': 0}]
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
            {'steps': 28},
            [{'name': 'Model A', 'index': 0}]
        )

        # Try to mark nonexistent model
        with pytest.raises(ValueError, match="Model .* not found"):
            manager.mark_model_complete(job_id, 'Nonexistent Model', 'images/test.png', 5.0)

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
            {'steps': 28},
            [{'name': 'Model A', 'index': 0}]
        )

        status = manager.get_job_status(job_id)

        # Verify timestamps can be parsed
        assert datetime.fromisoformat(status['createdAt'])
        assert datetime.fromisoformat(status['updatedAt'])

        # Mark in progress and verify timestamp
        manager.mark_model_in_progress(job_id, 'Model A')
        status = manager.get_job_status(job_id)
        assert datetime.fromisoformat(status['results'][0]['startedAt'])

        # Mark complete and verify timestamp
        manager.mark_model_complete(job_id, 'Model A', 'images/test.png', 5.0)
        status = manager.get_job_status(job_id)
        assert datetime.fromisoformat(status['results'][0]['completedAt'])

    def test_job_results_preserve_model_index(self, mock_s3):
        """Test that model index is preserved in results"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        models = [
            {'name': 'Model A', 'index': 5},
            {'name': 'Model B', 'index': 10},
            {'name': 'Model C', 'index': 15}
        ]

        job_id = manager.create_job("test", {'steps': 28}, models)

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
            {'steps': 28},
            [
                {'name': 'Model A', 'index': 0},
                {'name': 'Model B', 'index': 1},
                {'name': 'Model C', 'index': 2}
            ]
        )

        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 0

        # Complete one model
        manager.mark_model_complete(job_id, 'Model A', 'images/a.png', 5.0)
        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 1

        # Error on one model (doesn't count as completed)
        manager.mark_model_error(job_id, 'Model B', 'Error')
        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 1

        # Complete another model
        manager.mark_model_complete(job_id, 'Model C', 'images/c.png', 6.0)
        status = manager.get_job_status(job_id)
        assert status['completedModels'] == 2

    def test_job_data_persistence(self, mock_s3):
        """Test that job data persists correctly in S3"""
        s3_client, bucket_name = mock_s3

        manager = JobManager(s3_client, bucket_name)

        job_id = manager.create_job(
            "test prompt",
            {'steps': 28, 'guidance': 7.5},
            [{'name': 'Model A', 'index': 0}]
        )

        # Retrieve raw data from S3
        key = f"jobs/{job_id}/status.json"
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        raw_data = json.loads(response['Body'].read().decode('utf-8'))

        # Verify structure
        assert raw_data['jobId'] == job_id
        assert raw_data['prompt'] == "test prompt"
        assert raw_data['parameters']['steps'] == 28
        assert raw_data['parameters']['guidance'] == 7.5
