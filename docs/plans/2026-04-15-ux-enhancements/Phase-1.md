# Phase 1: Backend Storage Refactor and Download Endpoint

## Phase Goal

Replace the base64-in-JSON image storage pattern with raw image files in S3. Update all read and write paths to handle the new format while maintaining backward compatibility with existing sessions during the 30-day S3 lifecycle window. Add a download endpoint that returns presigned S3 URLs.

**Success criteria:**

- `upload_image()` stores decoded PNG bytes with `ContentType: image/png`
- `_load_source_image()` reads both old JSON and new raw formats
- Gallery handlers work with both formats
- `GET /download/{sessionId}/{model}/{iterationIndex}` returns a presigned URL
- All existing backend tests continue to pass
- New tests cover both formats and the download endpoint
- `ruff check backend/src/` clean
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` passes

**Token estimate:** ~45,000

## Prerequisites

- Phase 0 complete (ADRs read and understood)
- `moto` installed in dev dependencies (`uv pip install -e "backend/.[dev]"`)

## Task 1.1: Refactor ImageStorage to Store Raw Images

### Goal

Modify `ImageStorage._store_image()` and `upload_image()` to decode base64 and store raw image bytes in S3 instead of JSON-wrapped base64.

### Files to Modify

- `backend/src/utils/storage.py` -- Core storage changes

### Implementation Steps

1. Modify `_store_image()` (currently at line 38):
   - Remove the JSON metadata dict construction (lines 48-56)
   - Decode the `base64_image` parameter from base64 string to raw bytes using `base64.b64decode()`
   - Call `_put_object_with_retry()` with the raw bytes as body and `content_type="image/png"`
   - Add `import base64` at the top of the file
   - The method signature changes: remove the `extra` parameter (metadata is now in status.json, not the image file). Keep `model_name`, `prompt`, `target` parameters for the S3 key construction but do not embed them in the file.
   - Simplify: `_store_image` now takes `(self, base64_image: str, key: str)` and just decodes + stores

1. Modify `upload_image()` (currently at line 80):
   - Change the file extension from `.json` to `.png` in the key construction (line 93)
   - Call the simplified `_store_image(base64_image, key)`
   - Return the new key (now ending in `.png`)

1. Modify `_put_object_with_retry()` (currently at line 66):
   - Change the `body` parameter type from `str` to `str | bytes` to accept both JSON strings and raw image bytes

1. Add a new method `get_image_bytes(self, image_key: str) -> bytes | None`:
   - Reads raw bytes from S3 for the given key
   - Returns `None` if `NoSuchKey`
   - Used by `_load_source_image()` in lambda_function.py

1. Modify `get_image()` (currently at line 100) for backward compatibility:
   - If `image_key` ends with `.json`, read and parse JSON as before (return the metadata dict with `output` field)
   - If `image_key` ends with `.png` or any other extension, read raw bytes, base64-encode them, and return a dict with `output` set to the base64 string (mimics old format for callers that still expect it)
   - This ensures `_load_source_image()` works during the transition

1. Modify `get_image_metadata()` (currently at line 144):
   - For `.json` keys: works as before (reads JSON, pops `output`)
   - For `.png` keys: return `None` (metadata is in status.json, not the image file). Gallery detail handler will be updated in Task 1.3 to read metadata from status.json instead.

1. Update `list_gallery_images()` (currently at line 199):
   - Change the filter from `.json` to include both `.json` and `.png` files (line 228: `if key.endswith(".json")` becomes `if key.endswith((".json", ".png"))`)

### Verification Checklist

- [x] `upload_image()` produces keys ending in `.png`
- [x] S3 objects have `ContentType: image/png`
- [x] `get_image()` returns valid data for both `.json` and `.png` keys
- [x] `get_image_bytes()` returns raw bytes for `.png` keys
- [x] `list_gallery_images()` returns both `.json` and `.png` files

### Testing Instructions

Write tests in a new file `tests/backend/unit/test_storage_refactor.py`:

- `test_upload_image_stores_raw_png` -- upload via `upload_image()`, verify S3 object is raw bytes (not JSON), ContentType is `image/png`, key ends in `.png`
- `test_get_image_reads_old_json_format` -- put a JSON-format image in mock S3, call `get_image()`, verify it returns the metadata dict with `output` field
- `test_get_image_reads_new_png_format` -- put raw bytes in mock S3 with `.png` key, call `get_image()`, verify it returns a dict with base64-encoded `output`
- `test_get_image_bytes_returns_raw` -- put raw bytes in mock S3, call `get_image_bytes()`, verify raw bytes returned
- `test_get_image_bytes_returns_none_for_missing` -- call `get_image_bytes()` with nonexistent key, verify `None`
- `test_list_gallery_images_includes_both_formats` -- put both `.json` and `.png` files in mock S3, verify both are listed

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage_refactor.py -v`

### Commit Message Template

```text
refactor(storage): store raw images in S3 instead of base64 JSON

- upload_image() decodes base64 and stores raw PNG bytes
- get_image() handles both old JSON and new PNG formats
- add get_image_bytes() for direct binary reads
- list_gallery_images() includes both .json and .png files
```

## Task 1.2: Update Lambda Image Write Path

### Goal

Update `_handle_successful_result()` in lambda_function.py to work with the new storage format. The function calls `image_storage.upload_image()` which now stores raw PNG -- no changes needed to the call itself, but verify the return value (image key) now ends in `.png` and that `get_cloudfront_url()` produces a working URL for the raw image.

### Files to Modify

- `backend/src/lambda_function.py` -- `_handle_successful_result()` (line 217)

### Implementation Steps

1. Read `_handle_successful_result()` at line 217. It calls `image_storage.upload_image(result["image"], ...)` where `result["image"]` is a base64 string from the handler. After Task 1.1, `upload_image()` decodes this and stores raw PNG. The returned `image_key` now ends in `.png`. `get_cloudfront_url(image_key)` produces a URL to the raw PNG file. **No code changes needed here** -- the function signature and return values are compatible. Verify this by reading the code and confirming.

1. Verify `complete_iteration()` in `SessionManager` stores the `image_key` in status.json. The key now ends in `.png` instead of `.json`, but `complete_iteration()` just stores it as a string -- no format assumption. **No code changes needed.**

1. Verify `create_context_entry()` stores the `image_key` in the context window. Same situation -- stores as string. **No code changes needed.**

### Verification Checklist

- [x] `_handle_successful_result()` works without modification after Task 1.1
- [x] `image_key` values in status.json end in `.png` for new sessions
- [x] CloudFront URLs point to raw PNG files

### Testing Instructions

No new test file needed. The existing handler tests (e.g., `test_gemini_handler.py`) exercise `_handle_successful_result()` indirectly via the generate flow. After Task 1.1, these tests will store `.png` keys. Verify existing tests still pass:

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v -k "handler"`

### Commit Message Template

```text
refactor(lambda): verify image write path with new storage format

- confirm _handle_successful_result compatible with raw PNG storage
- no code changes needed -- image_key is format-agnostic
```

## Task 1.3: Update Source Image Loading for Iterate/Outpaint

### Goal

Update `_load_source_image()` to read raw image bytes from S3 for new-format images while maintaining backward compatibility with old JSON-format images.

### Files to Modify

- `backend/src/lambda_function.py` -- `_load_source_image()` (line 609)

### Implementation Steps

1. Read `_load_source_image()` at line 609. Currently it:
   - Gets the `source_image_key` from the latest completed iteration (line 641)
   - Calls `image_storage.get_image(source_image_key)` which returns a dict with `output` field (line 645)
   - Returns `source_data["output"]` (base64 string) to the handler (line 648)

1. After Task 1.1, `get_image()` handles both formats and always returns a dict with an `output` field containing base64. **However**, this is inefficient for new-format images: it reads raw bytes, base64-encodes them, wraps in a dict, then the caller extracts the base64 string. For new-format images, we can skip the dict wrapper.

1. Replace the image loading logic:
   - Check if `source_image_key` ends with `.png` (or does not end with `.json`)
   - If new format: call `image_storage.get_image_bytes(source_image_key)` to get raw bytes, then `base64.b64encode(raw_bytes).decode("utf-8")` to get the base64 string the handlers expect
   - If old format (`.json`): call `image_storage.get_image(source_image_key)` and extract `source_data["output"]` as before
   - Return the base64 string in both cases

1. Add `import base64` to the imports at top of lambda_function.py (if not already present -- check first).

### Verification Checklist

- [x] `_load_source_image()` returns base64 string for both old and new format images
- [x] Iterate and outpaint work with new-format source images
- [x] Old sessions with JSON-format images still work for iterate/outpaint

### Testing Instructions

Add tests to `tests/backend/unit/test_storage_refactor.py`:

- `test_load_source_image_new_format` -- set up a session with a `.png` image key in status.json, put raw PNG bytes in mock S3 at that key, call the iterate endpoint (or unit-test `_load_source_image` directly), verify it returns a valid base64 string
- `test_load_source_image_old_format` -- set up a session with a `.json` image key, put old-format JSON in mock S3, verify `_load_source_image` returns the base64 string from the `output` field

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage_refactor.py -v`

### Commit Message Template

```text
fix(lambda): handle both old JSON and new PNG formats in source image loading

- _load_source_image reads raw bytes for .png keys
- falls back to JSON parsing for legacy .json keys
- iterate and outpaint work with both formats
```

## Task 1.4: Update Gallery Handlers

### Goal

Update `handle_gallery_detail()` to work with the new image format. Gallery images stored as `.png` no longer contain embedded metadata -- the metadata must come from elsewhere.

### Files to Modify

- `backend/src/lambda_function.py` -- `handle_gallery_detail()` (line 986)

### Implementation Steps

1. Read `handle_gallery_detail()` at line 986. Currently it:
   - Lists all image keys in the gallery folder (line 998)
   - For each key, calls `_load_image()` (line 1000) which calls `image_storage.get_image_metadata(key)` to get model/prompt/timestamp from the JSON file
   - Returns the metadata plus a CloudFront URL

1. For `.png` keys, `get_image_metadata()` returns `None` (per Task 1.1) because the raw image file has no embedded metadata.

1. Modify `_load_image()` (inner function at line 1000):
   - If the key ends with `.json`: use existing logic (read metadata from the file)
   - If the key ends with `.png`: extract metadata from the key itself. The key format is `sessions/{galleryId}/{model}-{timestamp}{-iter{N}}.png`. Parse out the model name and timestamp from the filename. The prompt is not available from the filename, so set it to `""` (gallery detail already works without prompt text for display).
   - In both cases, return the CloudFront URL via `image_storage.get_cloudfront_url(key)`

1. Note: Gallery preview URLs in `handle_gallery_list()` (line 900) use `image_storage.get_cloudfront_url(images[0])` which produces a URL to either a `.json` or `.png` file. For `.json` files, the browser cannot render the URL directly as an image. For `.png` files, it works. Since gallery previews are used in the frontend, the frontend likely already handles this (it fetches the full gallery detail). Verify the frontend gallery rendering path. If the preview URL is used as an `<img src>`, it will break for old `.json` files but work for new `.png` files. This is acceptable since old files age out in 30 days.

### Verification Checklist

- [x] Gallery detail returns CloudFront URLs for both `.json` and `.png` images
- [x] Model name is correctly parsed from `.png` filenames
- [x] Gallery list preview URLs work for `.png` images

### Testing Instructions

Add to `tests/backend/unit/test_storage_refactor.py`:

- `test_gallery_detail_new_format` -- put `.png` files in mock S3 under a gallery folder, call `handle_gallery_detail`, verify response includes CloudFront URLs and parsed model names
- `test_gallery_detail_mixed_formats` -- put both `.json` and `.png` files, verify all are returned

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage_refactor.py -v`

### Commit Message Template

```text
fix(gallery): handle new PNG image format in gallery detail

- parse model name from PNG filename for metadata
- support mixed old/new formats in gallery listing
```

## Task 1.5: Add Download Endpoint

### Goal

Add `GET /download/{sessionId}/{model}/{iterationIndex}` that returns a JSON response containing a presigned S3 URL for the raw image file.

### Files to Modify

- `backend/src/lambda_function.py` -- Add route and handler
- `backend/src/utils/storage.py` -- Add presigned URL generation

### Implementation Steps

1. Add `generate_presigned_download_url(self, image_key: str, filename: str, expires_in: int = 300) -> str` to `ImageStorage`:
   - Calls `self.s3.generate_presigned_url('get_object', Params={...}, ExpiresIn=expires_in)`
   - Params include `Bucket`, `Key`, and `ResponseContentDisposition: attachment; filename="{filename}"` and `ResponseContentType: image/png`
   - Returns the presigned URL string

1. Add `handle_download()` function in `lambda_function.py`:
   - Parse path: extract `session_id`, `model`, `iteration_index` from `/download/{sessionId}/{model}/{iterationIndex}`
   - Validate `session_id` format (reuse the regex from `_validate_refinement_request`: `^[a-zA-Z0-9\-]{1,64}$`)
   - Validate `model` is in `MODELS`
   - Validate `iteration_index` is a non-negative integer
   - Load session via `session_manager.get_session(session_id)`
   - Find the iteration at the given index for the given model
   - Get the `imageKey` from the iteration
   - If no imageKey or iteration not found: return 404
   - Generate filename: `{model}-iteration-{index}.png`
   - Call `image_storage.generate_presigned_download_url(image_key, filename)`
   - Return `{"url": presigned_url, "filename": filename}`

1. Add the route in `lambda_handler()`:
   - After the `/status/` route check (around line 381), add:
   - `elif path.startswith("/download/") and method == "GET": return handle_download(event, correlation_id)`

### Verification Checklist

- [x] `GET /download/{sessionId}/{model}/{iterationIndex}` returns a JSON body with `url` and `filename`
- [x] Presigned URL includes `Content-Disposition: attachment` header
- [x] 404 returned for nonexistent session, model, or iteration
- [x] 400 returned for invalid session ID format
- [x] Route is registered in `lambda_handler()`

### Testing Instructions

Add to `tests/backend/unit/test_storage_refactor.py`:

- `test_download_returns_presigned_url` -- create a session with a completed iteration, call the download endpoint, verify response contains `url` and `filename`
- `test_download_missing_session_returns_404` -- call with nonexistent session ID
- `test_download_missing_iteration_returns_404` -- call with valid session but nonexistent iteration index
- `test_download_invalid_session_id_returns_400` -- call with invalid session ID format
- `test_generate_presigned_download_url` -- unit test the `ImageStorage` method directly

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage_refactor.py -v`

### Commit Message Template

```text
feat(download): add presigned URL download endpoint

- GET /download/{sessionId}/{model}/{iterationIndex}
- returns presigned S3 URL with Content-Disposition: attachment
- 5-minute URL expiry
```

## Task 1.6: Update Existing Tests

### Goal

Update any existing tests that assume the old JSON image format to work with the new raw PNG format.

### Files to Modify

- `tests/backend/unit/test_gemini_handler.py`
- `tests/backend/unit/test_nova_handler.py`
- `tests/backend/unit/test_openai_handler.py`
- `tests/backend/unit/test_firefly_handler.py`
- Any other test files that create or read image files from mock S3

### Implementation Steps

1. Search all test files for references to `.json` image keys or JSON image payloads:
   - `grep -r "\.json" tests/backend/unit/` to find references
   - `grep -r "output" tests/backend/unit/` to find tests that read the `output` field from image files

1. For each test that creates mock image files in S3:
   - If the test puts a JSON object with an `output` field, update it to put raw bytes with a `.png` key instead (unless the test is specifically testing backward compatibility)
   - If the test reads image data and checks for the `output` field, update to work with raw bytes

1. Verify all existing tests pass after updates:

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80`

### Verification Checklist

- [ ] All existing tests pass with the new storage format
- [ ] No test hardcodes `.json` image keys (except backward compat tests)
- [ ] Coverage stays above 80%

### Testing Instructions

Run the full test suite:

```bash
PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80
```

### Commit Message Template

```text
test(storage): update existing tests for raw PNG storage format

- replace JSON image mocks with raw PNG bytes
- update gallery payload tests for .png keys
- verify backward compatibility tests cover old format
```

## Phase Verification

- [ ] All tasks committed (1.1 through 1.6)
- [ ] `ruff check backend/src/` returns clean
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` passes
- [ ] New sessions store `.png` files in S3 (not `.json` for images)
- [ ] Old sessions with `.json` image files still work for iterate, outpaint, and gallery
- [ ] `GET /download/{sessionId}/{model}/{iterationIndex}` returns presigned URLs
- [ ] `sam build` succeeds
