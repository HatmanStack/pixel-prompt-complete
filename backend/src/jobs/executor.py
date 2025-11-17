"""
Parallel Execution Engine for Pixel Prompt Complete.

Executes image generation across multiple AI models concurrently using threading.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict
from models.handlers import get_handler


class JobExecutor:
    """
    Executes image generation jobs with parallel model processing.
    """

    def __init__(self, job_manager, image_storage, model_registry):
        """
        Initialize Job Executor.

        Args:
            job_manager: JobManager instance
            image_storage: ImageStorage instance
            model_registry: ModelRegistry instance
        """
        self.job_manager = job_manager
        self.image_storage = image_storage
        self.model_registry = model_registry

    def execute_job(self, job_id: str, prompt: str, params: Dict, target: str) -> None:
        """
        Execute image generation job across all models in parallel.

        This method spawns threads for each model and processes them concurrently.
        It blocks until all models complete or fail.

        Args:
            job_id: Job ID
            prompt: Text prompt for image generation
            params: Generation parameters (steps, guidance, etc.)
            target: Target timestamp for grouping images
        """
        models = self.model_registry.get_all_models()

        print(f"Starting job {job_id} with {len(models)} models in parallel")

        # Create thread pool with one worker per model, capped at 10 to prevent resource exhaustion
        with ThreadPoolExecutor(max_workers=min(len(models), 10)) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    self._execute_model,
                    job_id,
                    model,
                    prompt,
                    params,
                    target
                ): model
                for model in models
            }

            # Process results as they complete
            for future in as_completed(futures):
                model = futures[future]
                try:
                    result = future.result()
                    if result['status'] == 'success':
                        print(f"Job {job_id}: Model {model['name']} completed successfully")
                    else:
                        print(f"Job {job_id}: Model {model['name']} failed: {result.get('error')}")

                except Exception as e:
                    print(f"Job {job_id}: Model {model['name']} raised exception: {str(e)}")
                    # Mark as error
                    try:
                        self.job_manager.mark_model_error(job_id, model['name'], str(e))
                    except Exception as update_error:
                        print(f"Failed to update job status: {update_error}")

        print(f"Job {job_id}: All models finished processing")

    def _execute_model(
        self,
        job_id: str,
        model: Dict,
        prompt: str,
        params: Dict,
        target: str
    ) -> Dict:
        """
        Execute image generation for a single model.

        Args:
            job_id: Job ID
            model: Model configuration dict
            prompt: Text prompt
            params: Generation parameters
            target: Target timestamp

        Returns:
            Result dict with status and image data or error
        """
        model_name = model['name']
        start_time = time.time()

        try:
            # Mark as in progress
            self.job_manager.mark_model_in_progress(job_id, model_name)

            # Get handler for this model's provider
            provider = model['provider']
            handler = get_handler(provider)

            print(f"Job {job_id}: Executing {model_name} (provider: {provider})")

            # Call handler with timeout wrapper
            result = self._execute_with_timeout(
                handler,
                model,
                prompt,
                params,
                timeout=120  # 2 minutes per model
            )

            # Calculate duration
            duration = time.time() - start_time

            if result['status'] == 'success':
                # Save image to S3
                image_key = self.image_storage.save_image(
                    base64_image=result['image'],
                    model_name=model_name,
                    prompt=prompt,
                    params=params,
                    target=target
                )

                # Mark as complete
                self.job_manager.mark_model_complete(
                    job_id,
                    model_name,
                    image_key,
                    duration
                )

                return {
                    'status': 'success',
                    'imageKey': image_key,
                    'duration': duration
                }

            else:
                # Handler returned error
                error = result.get('error', 'Unknown error')
                self.job_manager.mark_model_error(job_id, model_name, error)

                return {
                    'status': 'error',
                    'error': error
                }

        except TimeoutError as e:
            error_msg = f"Model execution timeout: {str(e)}"
            print(f"Job {job_id}: {model_name} - {error_msg}")
            self.job_manager.mark_model_error(job_id, model_name, error_msg)
            return {'status': 'error', 'error': error_msg}

        except Exception as e:
            error_msg = f"Model execution failed: {str(e)}"
            print(f"Job {job_id}: {model_name} - {error_msg}")
            self.job_manager.mark_model_error(job_id, model_name, error_msg)
            return {'status': 'error', 'error': error_msg}

    def _execute_with_timeout(
        self,
        handler,
        model: Dict,
        prompt: str,
        params: Dict
    ) -> Dict:
        """
        Execute handler (wrapper for future timeout implementation).

        Note: Individual handlers implement their own timeouts for API calls.
        A full timeout wrapper would require signal handling or subprocess
        execution, which adds complexity.

        Args:
            handler: Handler function to call
            model: Model configuration
            prompt: Text prompt
            params: Generation parameters

        Returns:
            Handler result dict
        """
        # For now, just call the handler directly
        # The individual handlers have their own timeouts for API calls
        return handler(model, prompt, params)
