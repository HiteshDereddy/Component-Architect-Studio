export type CodeLanguage = 'typescript' | 'html' | 'css' | 'raw';

export interface CodeBlock {
  language: CodeLanguage;
  code: string;
}

export interface GenerateRequest {
  prompt: string;
  session_id: string;
  current_code?: CodeBlock[];
  thinking_enabled?: boolean;
}

export type GenerationEvent =
  | { type: 'thinking'; content: string }
  | { type: 'chunk'; content: string }
  | { type: 'replace'; code: string }
  | { type: 'error'; errors: string[]; metrics?: Record<string, unknown> }
  | { type: 'cancelled' }
  | { type: 'done'; code: string; metrics?: Record<string, unknown> };

export interface BackendHealth {
  ok: boolean;
  model_loaded: boolean;
  validator_loaded: boolean;
  agent_loaded: boolean;
  generation_provider: 'template' | 'openai-compatible' | 'llama' | string;
  model_error: string | null;
}

export interface RunLogEntry {
  id: string;
  at: string;
  level: 'info' | 'success' | 'warning' | 'error';
  title: string;
  detail: string;
}
