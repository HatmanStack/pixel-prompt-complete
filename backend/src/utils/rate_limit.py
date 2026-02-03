"""
Rate Limiting module for Pixel Prompt Complete.

Implements S3-based rate limiting with global and per-IP limits.
Uses module-level caching to reduce S3 calls during Lambda container reuse.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from botocore.exceptions import ClientError

# Module-level cache for Lambda container reuse
# Reduces S3 calls from 2 per request to ~0.2 during warm starts
_rate_limit_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0.0,
    'dirty': False
}
CACHE_TTL_SECONDS = 5.0


def reset_cache() -> None:
    """Reset the module-level cache. Used for testing."""
    global _rate_limit_cache
    _rate_limit_cache = {
        'data': None,
        'timestamp': 0.0,
        'dirty': False
    }


class RateLimiter:
    """
    S3-based rate limiting for API requests.

    Tracks global requests per hour and per-IP requests per day.
    """

    def __init__(
        self,
        s3_client: Any,
        bucket_name: str,
        global_limit: int,
        ip_limit: int,
        ip_whitelist: List[str]
    ) -> None:
        """
        Initialize Rate Limiter.

        Args:
            s3_client: boto3 S3 client
            bucket_name: S3 bucket name
            global_limit: Maximum requests per hour globally
            ip_limit: Maximum requests per day per IP
            ip_whitelist: List of IPs to bypass limits
        """
        self.s3 = s3_client
        self.bucket = bucket_name
        self.global_limit = global_limit
        self.ip_limit = ip_limit
        self.ip_whitelist = ip_whitelist
        self.rate_limit_key = 'rate-limit/ratelimit.json'
        self.cache_ttl = CACHE_TTL_SECONDS

    def check_rate_limit(self, ip_address: str) -> bool:
        """
        Check if request should be rate limited.

        Args:
            ip_address: Client IP address

        Returns:
            True if rate limited (reject request), False if allowed
        """
        # Check whitelist
        if ip_address in self.ip_whitelist:
            return False

        # Load rate limit data (with caching)
        rate_data = self._load_rate_data_cached()

        # Get current time
        now = datetime.now(timezone.utc)

        # Clean up old requests
        rate_data = self._cleanup_old_requests(rate_data, now)

        # Check global limit
        global_count = len(rate_data['global_requests'])
        if global_count >= self.global_limit:
            return True

        # Check IP limit
        ip_requests = rate_data['ip_requests'].get(ip_address, [])
        ip_count = len(ip_requests)
        if ip_count >= self.ip_limit:
            return True

        # Add current request
        timestamp = now.isoformat()
        rate_data['global_requests'].append(timestamp)

        if ip_address not in rate_data['ip_requests']:
            rate_data['ip_requests'][ip_address] = []
        rate_data['ip_requests'][ip_address].append(timestamp)

        # Save updated data
        self._save_rate_data(rate_data)

        print(f"Rate limit check passed: global={global_count + 1}/{self.global_limit}, "
              f"ip={ip_count + 1}/{self.ip_limit}")

        return False

    def _load_rate_data_cached(self) -> Dict[str, Any]:
        """
        Load rate limit data with caching for Lambda container reuse.

        Returns:
            Rate limit data dict (may be from cache)
        """
        global _rate_limit_cache

        cache_age = time.time() - _rate_limit_cache['timestamp']

        # Return cached data if fresh
        if _rate_limit_cache['data'] is not None and cache_age < self.cache_ttl:
            return _rate_limit_cache['data']

        # Load from S3 and update cache
        rate_data = self._load_rate_data()
        _rate_limit_cache['data'] = rate_data
        _rate_limit_cache['timestamp'] = time.time()

        return rate_data

    def _load_rate_data(self) -> Dict[str, Any]:
        """
        Load rate limit data from S3.

        Returns:
            Rate limit data dict
        """
        try:
            response = self.s3.get_object(
                Bucket=self.bucket,
                Key=self.rate_limit_key
            )
            data = json.loads(response['Body'].read().decode('utf-8'))
            return data

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                # Initialize empty rate data
                return {
                    'global_requests': [],
                    'ip_requests': {}
                }
            else:
                raise

    def _save_rate_data(self, data: Dict[str, Any]) -> None:
        """
        Save rate limit data to S3 and update cache.

        Args:
            data: Rate limit data dict
        """
        global _rate_limit_cache

        self.s3.put_object(
            Bucket=self.bucket,
            Key=self.rate_limit_key,
            Body=json.dumps(data),
            ContentType='application/json'
        )

        # Update cache after successful save
        _rate_limit_cache['data'] = data
        _rate_limit_cache['timestamp'] = time.time()

    def _cleanup_old_requests(self, data: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        """
        Remove requests outside time windows.

        Args:
            data: Rate limit data dict
            now: Current datetime

        Returns:
            Cleaned rate limit data
        """
        # Calculate time windows
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)

        # Clean global requests (1 hour window)
        data['global_requests'] = [
            ts for ts in data['global_requests']
            if datetime.fromisoformat(ts) > one_hour_ago
        ]

        # Clean IP requests (1 day window)
        cleaned_ip_requests = {}
        for ip, timestamps in data['ip_requests'].items():
            recent_timestamps = [
                ts for ts in timestamps
                if datetime.fromisoformat(ts) > one_day_ago
            ]
            if recent_timestamps:  # Only keep IPs with recent requests
                cleaned_ip_requests[ip] = recent_timestamps

        data['ip_requests'] = cleaned_ip_requests

        return data
