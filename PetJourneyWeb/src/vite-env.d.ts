/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PETSOUL_DATA_MODE?: string;
  readonly VITE_PETSOUL_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
