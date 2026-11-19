import type { DataSource, ProviderKind, TimeWindow } from '@/api/types';

export const TIME_WINDOWS: { value: TimeWindow; label: string; long: string }[] = [
  { value: '1h', label: '1h', long: 'last hour' },
  { value: '6h', label: '6h', long: 'last 6 hours' },
  { value: '24h', label: '24h', long: 'last 24 hours' },
  { value: '7d', label: '7d', long: 'last 7 days' },
];

export function windowLabel(window: TimeWindow): string {
  return TIME_WINDOWS.find((option) => option.value === window)?.long ?? window;
}

export const DATA_SOURCES: { value: DataSource; label: string }[] = [
  { value: 'all', label: 'All data' },
  { value: 'real', label: 'Real only' },
  { value: 'demo', label: 'Demo only' },
];

export const PROVIDERS: Record<
  ProviderKind,
  { label: string; description: string; urlPlaceholder: string; identifierPlaceholder: string }
> = {
  demo: {
    label: 'Demo (local)',
    description: 'Simulated responses generated in the backend. No network, GPU or credentials.',
    urlPlaceholder: '',
    identifierPlaceholder: 'orbit-8b',
  },
  openai_compatible: {
    label: 'OpenAI-compatible',
    description: 'Any /v1/chat/completions API: OpenAI, Together, Groq, Ollama, LM Studio and others.',
    urlPlaceholder: 'https://api.openai.com/v1',
    identifierPlaceholder: 'gpt-4o-mini',
  },
  vllm: {
    label: 'vLLM',
    description: 'vLLM OpenAI-compatible server. Its /metrics endpoint feeds the Infrastructure page.',
    urlPlaceholder: 'http://gpu-server:8000/v1',
    identifierPlaceholder: 'meta-llama/Llama-3.1-8B-Instruct',
  },
  huggingface: {
    label: 'Hugging Face',
    description: 'Inference Endpoints, self-hosted TGI, or the serverless text-generation API.',
    urlPlaceholder: 'https://xyz.endpoints.huggingface.cloud',
    identifierPlaceholder: 'mistralai/Mistral-7B-Instruct-v0.3',
  },
};

export const PROVIDER_ORDER: ProviderKind[] = ['openai_compatible', 'vllm', 'huggingface', 'demo'];
