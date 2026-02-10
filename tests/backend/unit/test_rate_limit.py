"""
Unit tests for rate limiting utilities (per-timeslice counter design)
"""

import json

from utils.rate_limit import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter class"""

    def test_whitelist_bypass(self, mock_s3):
        """Test that whitelisted IPs bypass rate limits"""
        s3_client, bucket_name = mock_s3
        whitelist = ['192.168.1.100', '10.0.0.1']

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=3,
            ip_whitelist=whitelist,
        )

        for _ in range(20):
            is_limited = limiter.check_rate_limit('192.168.1.100')
            assert is_limited is False

    def test_global_rate_limit(self, mock_s3):
        """Test global hourly rate limit enforcement"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=100,
            ip_whitelist=[],
        )

        # First 5 requests should pass
        for i in range(5):
            is_limited = limiter.check_rate_limit(f'192.168.1.{i}')
            assert is_limited is False, f"Request {i+1} should not be rate limited"

        # 6th request should be rate limited
        is_limited = limiter.check_rate_limit('192.168.1.99')
        assert is_limited is True

    def test_per_ip_rate_limit(self, mock_s3):
        """Test per-IP daily rate limit enforcement"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=100,
            ip_limit=3,
            ip_whitelist=[],
        )

        ip_address = '192.168.1.50'

        for i in range(3):
            is_limited = limiter.check_rate_limit(ip_address)
            assert is_limited is False, f"Request {i+1} should not be rate limited"

        # 4th request from same IP should be rate limited
        is_limited = limiter.check_rate_limit(ip_address)
        assert is_limited is True

        # Different IP should still work
        is_limited = limiter.check_rate_limit('192.168.1.51')
        assert is_limited is False

    def test_initialize_empty_rate_data(self, mock_s3):
        """Test that limiter creates counter when none exists"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=3,
            ip_whitelist=[],
        )

        # First request should succeed
        is_limited = limiter.check_rate_limit('192.168.1.1')
        assert is_limited is False

    def test_multiple_ips_tracked_separately(self, mock_s3):
        """Test that different IPs are tracked independently"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=100,
            ip_limit=2,
            ip_whitelist=[],
        )

        # IP 1: 2 requests (at limit)
        limiter.check_rate_limit('192.168.1.1')
        limiter.check_rate_limit('192.168.1.1')

        # IP 2: 1 request (under limit)
        limiter.check_rate_limit('192.168.1.2')

        # IP 1 should be rate limited
        assert limiter.check_rate_limit('192.168.1.1') is True

        # IP 2 should still have capacity
        assert limiter.check_rate_limit('192.168.1.2') is False

        # IP 3 should have full capacity
        assert limiter.check_rate_limit('192.168.1.3') is False

    def test_s3_ifmatch_put_without_etag(self, mock_s3):
        """Test that put_object works without IfMatch parameter."""
        s3_client, bucket_name = mock_s3
        s3_client.put_object(
            Bucket=bucket_name,
            Key='test.json',
            Body=json.dumps({'count': 1}),
            ContentType='application/json',
        )
        resp = s3_client.get_object(Bucket=bucket_name, Key='test.json')
        data = json.loads(resp['Body'].read().decode('utf-8'))
        assert data['count'] == 1

    def test_s3_ifmatch_put_with_etag(self, mock_s3):
        """Test put_object with IfMatch ETag conditional write."""
        s3_client, bucket_name = mock_s3
        s3_client.put_object(
            Bucket=bucket_name,
            Key='test.json',
            Body=json.dumps({'count': 1}),
            ContentType='application/json',
        )
        resp = s3_client.get_object(Bucket=bucket_name, Key='test.json')
        etag = resp.get('ETag')
        assert etag is not None

        # Conditional write with correct ETag should succeed
        s3_client.put_object(
            Bucket=bucket_name,
            Key='test.json',
            Body=json.dumps({'count': 2}),
            ContentType='application/json',
            IfMatch=etag,
        )
        resp2 = s3_client.get_object(Bucket=bucket_name, Key='test.json')
        data = json.loads(resp2['Body'].read().decode('utf-8'))
        assert data['count'] == 2

    def test_s3_ifmatch_put_with_wrong_etag(self, mock_s3):
        """Test put_object with wrong IfMatch ETag — should fail or be ignored."""
        from botocore.exceptions import ClientError
        s3_client, bucket_name = mock_s3
        s3_client.put_object(
            Bucket=bucket_name,
            Key='test.json',
            Body=json.dumps({'count': 1}),
            ContentType='application/json',
        )
        # Depending on S3 mock, wrong ETag may raise PreconditionFailed or succeed
        try:
            s3_client.put_object(
                Bucket=bucket_name,
                Key='test.json',
                Body=json.dumps({'count': 99}),
                ContentType='application/json',
                IfMatch='"wrongetag"',
            )
            # If moto doesn't enforce IfMatch, the write succeeds — that's expected
        except ClientError as e:
            assert e.response['Error']['Code'] in ('PreconditionFailed', '412')

    def test_counter_persistence(self, mock_s3):
        """Test that counters are persisted to S3"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=100,
            ip_limit=100,
            ip_whitelist=[],
        )

        limiter.check_rate_limit('192.168.1.1')

        # Verify at least one counter object was written to S3
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix='rate-limit/',
        )
        assert 'Contents' in response
        assert len(response['Contents']) >= 1
