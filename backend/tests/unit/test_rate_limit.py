"""
Unit tests for rate limiting utilities
"""

import pytest
import json
from datetime import datetime, timedelta, timezone
from src.utils.rate_limit import RateLimiter


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
            ip_whitelist=whitelist
        )

        # Whitelisted IP should never be rate limited
        for _ in range(20):  # Well over both limits
            is_limited = limiter.check_rate_limit('192.168.1.100')
            assert is_limited is False

    def test_global_rate_limit(self, mock_s3):
        """Test global hourly rate limit enforcement"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=100,  # High IP limit so we only test global
            ip_whitelist=[]
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
            global_limit=100,  # High global limit so we only test IP limit
            ip_limit=3,
            ip_whitelist=[]
        )

        ip_address = '192.168.1.50'

        # First 3 requests from same IP should pass
        for i in range(3):
            is_limited = limiter.check_rate_limit(ip_address)
            assert is_limited is False, f"Request {i+1} from {ip_address} should not be rate limited"

        # 4th request from same IP should be rate limited
        is_limited = limiter.check_rate_limit(ip_address)
        assert is_limited is True

        # Different IP should still work
        is_limited = limiter.check_rate_limit('192.168.1.51')
        assert is_limited is False

    def test_cleanup_old_global_requests(self, mock_s3):
        """Test that global requests older than 1 hour are cleaned up"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=100,
            ip_whitelist=[]
        )

        # Create old rate data with requests from 2 hours ago
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

        old_rate_data = {
            'global_requests': [
                two_hours_ago.isoformat(),
                two_hours_ago.isoformat(),
                two_hours_ago.isoformat(),
                two_hours_ago.isoformat(),
                two_hours_ago.isoformat()
            ],
            'ip_requests': {}
        }

        # Save old data to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key='rate-limit/ratelimit.json',
            Body=json.dumps(old_rate_data),
            ContentType='application/json'
        )

        # New request should succeed because old requests are cleaned up
        is_limited = limiter.check_rate_limit('192.168.1.1')
        assert is_limited is False

    def test_cleanup_old_ip_requests(self, mock_s3):
        """Test that IP requests older than 1 day are cleaned up"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=100,
            ip_limit=3,
            ip_whitelist=[]
        )

        # Create old rate data with requests from 2 days ago
        now = datetime.now(timezone.utc)
        two_days_ago = now - timedelta(days=2)

        ip_address = '192.168.1.50'

        old_rate_data = {
            'global_requests': [],
            'ip_requests': {
                ip_address: [
                    two_days_ago.isoformat(),
                    two_days_ago.isoformat(),
                    two_days_ago.isoformat()
                ]
            }
        }

        # Save old data to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key='rate-limit/ratelimit.json',
            Body=json.dumps(old_rate_data),
            ContentType='application/json'
        )

        # New request from same IP should succeed because old requests are cleaned up
        is_limited = limiter.check_rate_limit(ip_address)
        assert is_limited is False

    def test_initialize_empty_rate_data(self, mock_s3):
        """Test that limiter creates empty rate data when none exists"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=3,
            ip_whitelist=[]
        )

        # First request should succeed
        is_limited = limiter.check_rate_limit('192.168.1.1')
        assert is_limited is False

        # Verify rate data was created in S3
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key='rate-limit/ratelimit.json'
        )
        rate_data = json.loads(response['Body'].read().decode('utf-8'))

        assert 'global_requests' in rate_data
        assert 'ip_requests' in rate_data
        assert len(rate_data['global_requests']) == 1
        assert '192.168.1.1' in rate_data['ip_requests']

    def test_is_rate_limited_alias(self, mock_s3):
        """Test is_rate_limited alias method"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=1,
            ip_limit=100,
            ip_whitelist=[]
        )

        # First request
        assert limiter.is_rate_limited('192.168.1.1') is False

        # Second request should be rate limited
        assert limiter.is_rate_limited('192.168.1.2') is True

    def test_mixed_old_and_new_requests(self, mock_s3):
        """Test cleanup preserves recent requests while removing old ones"""
        s3_client, bucket_name = mock_s3

        limiter = RateLimiter(
            s3_client=s3_client,
            bucket_name=bucket_name,
            global_limit=5,
            ip_limit=100,
            ip_whitelist=[]
        )

        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)
        thirty_minutes_ago = now - timedelta(minutes=30)

        # Create mixed rate data
        mixed_rate_data = {
            'global_requests': [
                two_hours_ago.isoformat(),  # Should be cleaned
                two_hours_ago.isoformat(),  # Should be cleaned
                thirty_minutes_ago.isoformat(),  # Should be kept
                thirty_minutes_ago.isoformat()  # Should be kept
            ],
            'ip_requests': {}
        }

        s3_client.put_object(
            Bucket=bucket_name,
            Key='rate-limit/ratelimit.json',
            Body=json.dumps(mixed_rate_data),
            ContentType='application/json'
        )

        # New request (5th in global, but only 3rd recent)
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
            ip_whitelist=[]
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
