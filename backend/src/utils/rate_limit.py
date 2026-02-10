"""
Rate Limiting module for Pixel Prompt Complete.

Implements S3-based rate limiting with per-timeslice counter keys.
Global: one counter per hour. Per-IP: one counter per day per hashed IP.
Uses ETag-conditional writes for atomic increment (no TOCTOU race).
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, List

from botocore.exceptions import ClientError

from utils.logger import StructuredLogger

# Max retries for atomic increment on ETag conflict
_ATOMIC_MAX_RETRIES = 3


def reset_cache() -> None:
    """No-op kept for test compatibility."""


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
        Uses atomic increment to avoid TOCTOU races.
        """
        if ip_address in self.ip_whitelist:
            return False

        now = datetime.now(timezone.utc)
        global_key = f"rate-limit/global/{now.strftime('%Y-%m-%dT%H')}.json"
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
        ip_key = f"rate-limit/ip/{ip_hash}/{now.strftime('%Y-%m-%d')}.json"

        # Check IP first to avoid inflating global counter on per-IP rejection
        ip_count = self._atomic_increment(ip_key, self.ip_limit)
        if ip_count is None:
            return True

        # Atomic check-and-increment global counter
        global_count = self._atomic_increment(global_key, self.global_limit)
        if global_count is None:
            return True

        StructuredLogger.debug(
            f"Rate limit check passed: global={global_count}/{self.global_limit}, "
            f"ip={ip_count}/{self.ip_limit}"
        )

        return False

    def _atomic_increment(self, key: str, limit: int) -> int | None:
        """
        Atomically read-check-increment a counter in S3.

        Returns the new count on success, or None if the limit would be exceeded.
        Uses ETag conditional writes to prevent concurrent overwrites.
        """
        for _attempt in range(_ATOMIC_MAX_RETRIES):
            count, etag = self._read_counter(key)

            if count >= limit:
                return None

            new_count = count + 1
            if self._write_counter_conditional(key, new_count, etag):
                return new_count

            time.sleep(0.05 * (_attempt + 1))

        # Final fallback: reject to avoid inconsistent counter state
        return None

    def _read_counter(self, key: str) -> tuple[int, str | None]:
        """Read a counter value and ETag from S3. Returns (count, etag)."""
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            return data.get('count', 0), response.get('ETag')
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return 0, None
            raise

    def _write_counter_conditional(self, key: str, count: int, expected_etag: str | None) -> bool:
        """Write counter with ETag condition. Returns True on success."""
        body = json.dumps({'count': count})
        put_kwargs = {
            'Bucket': self.bucket,
            'Key': key,
            'Body': body,
            'ContentType': 'application/json',
        }
        if expected_etag:
            put_kwargs['IfMatch'] = expected_etag
        else:
            put_kwargs['IfNoneMatch'] = '*'

        try:
            self.s3.put_object(**put_kwargs)
            return True
        except ClientError as e:
            code = e.response['Error']['Code']
            if code in ('PreconditionFailed', '412'):
                return False
            raise
