/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_ENDPOINT: string;
  readonly VITE_CLOUDFRONT_DOMAIN: string;
  readonly VITE_S3_BUCKET: string;
  readonly VITE_ENVIRONMENT: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
