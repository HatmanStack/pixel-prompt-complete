"""
Rate Limiting module for Pixel Prompt Complete.

Implements S3-based rate limiting with per-timeslice counter keys.
Global: one counter per hour. Per-IP: one counter per day per hashed IP.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from botocore.exceptions import ClientError

from utils.logger import StructuredLogger

# Module-level cache for Lambda container reuse
_rate_limit_cache: Dict[str, Any] = {
    'global_key': None,
    'global_count': 0,
    'ip_counts': {},  # {cache_key: count}
    'timestamp': 0.0,
}
CACHE_TTL_SECONDS = 5.0


def reset_cache() -> None:
    """Reset the module-level cache. Used for testing."""
    global _rate_limit_cache
    _rate_limit_cache = {
        'global_key': None,
        'global_count': 0,
        'ip_counts': {},
        'timestamp': 0.0,
    }


class RateLimiter:
    """
    S3-based rate limiting using per-timeslice counter keys.

    Global: rate-limit/global/{YYYY-MM-DDTHH}.json — one key per hour
    Per-IP: rate-limit/ip/{ip_hash}/{YYYY-MM-DD}.json — one key per day per IP
    """

    def __init__(
        self,
        s3_client: Any,
        bucket_name: str,
        global_limit: int,
        ip_limit: int,
        ip_whitelist: List[str],
    ) -> None:
        self.s3 = s3_client
        self.bucket = bucket_name
        self.global_limit = global_limit
        self.ip_limit = ip_limit
        self.ip_whitelist = ip_whitelist

    def check_rate_limit(self, ip_address: str) -> bool:
        """
        Check if request should be rate limited.

        Returns True if rate limited (reject), False if allowed.
        """
        if ip_address in self.ip_whitelist:
            return False

        now = datetime.now(timezone.utc)
        global_key = f"rate-limit/global/{now.strftime('%Y-%m-%dT%H')}.json"
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
        ip_key = f"rate-limit/ip/{ip_hash}/{now.strftime('%Y-%m-%d')}.json"

        # Read global count
        global_count = self._read_counter(global_key)
        if global_count >= self.global_limit:
            return True

        # Read IP count
        ip_count = self._read_counter(ip_key)
        if ip_count >= self.ip_limit:
            return True

        # Increment both counters
        self._write_counter(global_key, global_count + 1)
        self._write_counter(ip_key, ip_count + 1)

        StructuredLogger.debug(
            f"Rate limit check passed: global={global_count + 1}/{self.global_limit}, "
            f"ip={ip_count + 1}/{self.ip_limit}"
        )

        return False

    def _read_counter(self, key: str) -> int:
        """Read a counter value from S3, returning 0 if not found."""
        global _rate_limit_cache

        cache_age = time.time() - _rate_limit_cache['timestamp']

        # Check module-level cache
        if cache_age < CACHE_TTL_SECONDS and key in _rate_limit_cache['ip_counts']:
            return _rate_limit_cache['ip_counts'][key]
        if cache_age < CACHE_TTL_SECONDS and key == _rate_limit_cache.get('global_key'):
            return _rate_limit_cache['global_count']

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            count = data.get('count', 0)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                count = 0
            else:
                raise

        # Update cache
        _rate_limit_cache['ip_counts'][key] = count
        _rate_limit_cache['timestamp'] = time.time()

        return count

    def _write_counter(self, key: str, count: int) -> None:
        """Write a counter value to S3 and update cache."""
        global _rate_limit_cache

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps({'count': count}),
            ContentType='application/json',
        )

        # Update cache
        _rate_limit_cache['ip_counts'][key] = count
        _rate_limit_cache['timestamp'] = time.time()
