import { Injectable } from '@angular/core';
import { DesignSystem } from '../models/design-system';
import { BackendHealth, CodeBlock, GenerateRequest } from '../models/generated-code';

@Injectable({ providedIn: 'root' })
export class GenerationApiService {
  getApiBaseUrl(): string {
    return localStorage.getItem('guided-component-architect:api-url') || 'http://127.0.0.1:8010';
  }

  setApiBaseUrl(url: string): void {
    localStorage.setItem('guided-component-architect:api-url', url);
  }

  async loadDesignSystem(): Promise<DesignSystem> {
    const response = await fetch(`${this.getApiBaseUrl()}/design-system`);
    if (!response.ok) {
      throw new Error(`Failed to load design system (${response.status})`);
    }
    return response.json();
  }

  async health(): Promise<BackendHealth> {
    const response = await fetch(`${this.getApiBaseUrl()}/health`);
    if (!response.ok) {
      throw new Error(`Backend health check failed (${response.status})`);
    }
    return response.json();
  }

  async generate(request: GenerateRequest, signal?: AbortSignal): Promise<Response> {
    const response = await fetch(`${this.getApiBaseUrl()}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });

    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Generation failed (${response.status})`);
    }

    if (!response.body) {
      throw new Error('ReadableStream is not supported by this browser.');
    }

    return response;
  }

  async publishPreview(sessionId: string, codeBlocks: CodeBlock[]): Promise<void> {
    const response = await fetch(`${this.getApiBaseUrl()}/sessions/${sessionId}/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code_blocks: codeBlocks }),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Preview publish failed (${response.status})`);
    }
  }

  async cancelGeneration(sessionId: string): Promise<void> {
    await fetch(`${this.getApiBaseUrl()}/sessions/${sessionId}/cancel`, { method: 'POST' });
  }

  async listVersions(sessionId: string): Promise<any> {
    const response = await fetch(`${this.getApiBaseUrl()}/sessions/${sessionId}/versions`);
    if (!response.ok) return null;
    return response.json();
  }

  async getVersion(sessionId: string, index: number): Promise<any> {
    const response = await fetch(`${this.getApiBaseUrl()}/sessions/${sessionId}/versions/${index}`);
    if (!response.ok) return null;
    return response.json();
  }
}
