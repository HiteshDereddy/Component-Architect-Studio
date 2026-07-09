import { Component, ChangeDetectionStrategy, ChangeDetectorRef, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { DesignSystem } from './models/design-system';
import { CodeBlock, GenerationEvent, RunLogEntry } from './models/generated-code';
import { CodeParserService } from './services/code-parser.service';
import { GenerationApiService } from './services/generation-api.service';
import { PreviewBuilderService } from './services/preview-builder.service';
import { PreviewHostComponent } from './preview-host/preview-host.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, PreviewHostComponent],
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App implements OnInit {
  private readonly logStorageKey = 'guided-component-architect:run-log';
  private readonly sessionStorageKey = 'guided-component-architect:session-id';
  title = 'Guided Component Architect';
  isPreviewRoute = window.location.pathname.startsWith('/preview');
  prompt = '';
  generatedCode = '';
  codeBlocks: CodeBlock[] = [];
  isLoading = false;
  error = '';
  errorTitle = '';
  backendUrl = '';
  
  activeTab: 'code' | 'preview' = 'code';
  previewUrl: SafeResourceUrl | null = null;
  previewSrcDoc: string | null = null;
  designSystemVars = '';
  designSystemColors: {name: string, value: string}[] = [];
  providerLabel = 'Backend';
  sessionId = this.loadSessionId();
  isValidated: boolean | null = null;
  originalCodeBlocks: CodeBlock[] = [];
  runLog: RunLogEntry[] = [];
  thinkingText = '';
  isThinkingExpanded = false;
  thinkingEnabled = true;
  isEditingCode = false;

  private parseScheduled = false;
  private previewTimer: number | undefined;
  private abortController: AbortController | null = null;
  private runtimeErrorLoggingInstalled = false;

  constructor(
    private cdr: ChangeDetectorRef,
    private sanitizer: DomSanitizer,
    private api: GenerationApiService,
    private codeParser: CodeParserService,
    private previewBuilder: PreviewBuilderService,
  ) {}

  async ngOnInit() {
    this.backendUrl = this.api.getApiBaseUrl();
    this.loadRunLog();
    this.installRuntimeErrorLogging();
    try {
      const ds = await this.api.loadDesignSystem();
      this.designSystemVars = this.buildDesignSystemVars(ds);
      this.designSystemColors = Object.entries(ds.colors).map(([name, value]) => ({ name, value }));
      await this.loadBackendHealth();
      this.addLog('success', 'Backend connected', `Provider: ${this.providerLabel}`);
      this.error = '';
      this.errorTitle = '';
      await this.restoreLastSessionVersion();
      this.cdr.markForCheck();
    } catch(e) {
      console.error("Failed to load design system", e);
      const fallback = this.getFallbackDesignSystem();
      this.designSystemVars = this.buildDesignSystemVars(fallback);
      this.designSystemColors = Object.entries(fallback.colors).map(([name, value]) => ({ name, value }));
      this.errorTitle = 'Backend Offline';
      this.error = 'Using the local design-system fallback. Start the FastAPI backend before generating components.';
      this.addLog('error', this.errorTitle, this.toUserFacingError(e));
      this.cdr.markForCheck();
    }
  }

  private async restoreLastSessionVersion(): Promise<void> {
    const sessionId = this.loadSessionId();
    try {
      const versionsResponse = await this.api.listVersions(sessionId);
      if (versionsResponse && versionsResponse.versions && versionsResponse.versions.length > 0) {
        const latestIndex = versionsResponse.versions.length - 1;
        const versionData = await this.api.getVersion(sessionId, latestIndex);
        if (versionData && versionData.code) {
          this.generatedCode = versionData.code;
          this.parseMarkdownBlocks(this.generatedCode);
          this.isValidated = true;
          const url = `${window.location.origin}/preview?session=${this.sessionId}&v=${Date.now()}`;
          this.previewUrl = this.sanitizer.bypassSecurityTrustResourceUrl(url);
          this.cdr.markForCheck();
        }
      }
    } catch (e) {
      console.warn("No previous session version restored:", e);
    }
  }

  async onBackendUrlChange() {
    this.api.setApiBaseUrl(this.backendUrl);
    this.error = '';
    this.errorTitle = '';
    this.isValidated = null;
    await this.ngOnInit();
  }

  startNewComponent(): void {
    // Generate a fresh session ID and clear all context
    this.sessionId = crypto.randomUUID();
    localStorage.setItem(this.sessionStorageKey, this.sessionId);
    this.generatedCode = '';
    this.codeBlocks = [];
    this.originalCodeBlocks = [];
    this.previewUrl = null;
    this.isValidated = null;
    this.thinkingText = '';
    this.isThinkingExpanded = false;
    this.addLog('info', 'Started new session', 'Ready for a fresh component design.');
    this.cdr.markForCheck();
  }

  private async loadBackendHealth(): Promise<void> {
    const health = await this.api.health();
    const labels: Record<string, string> = {
      template: 'Fast Demo Provider',
      'openai-compatible': 'Hosted LLM',
      llama: 'Local llama.cpp',
    };
    this.providerLabel = labels[health.generation_provider] ?? health.generation_provider;
  }

  parseMarkdownBlocks(markdown: string) {
    this.codeBlocks = this.codeParser.parse(markdown, this.originalCodeBlocks);
  }

  buildPreview() {
    void this.publishAngularPreview();
  }

  updateSrcDoc() {
    this.previewSrcDoc = this.previewBuilder.buildSrcDoc(this.codeBlocks, this.designSystemVars);
  }

  schedulePreviewBuild() {
    window.clearTimeout(this.previewTimer);
    this.previewTimer = window.setTimeout(() => {
      this.buildPreview();
      this.cdr.markForCheck();
    }, 250);
  }

  toggleEditMode() {
    this.isEditingCode = !this.isEditingCode;
    if (!this.isEditingCode) {
      // User turned off edit mode, maybe we should re-render or just leave it.
      // But they have a separate "Render" button, so this just toggles UI state.
    }
  }

  renderEditedCode() {
    this.buildPreview();
    this.cdr.markForCheck();
    // Re-validate the code silently? Or just render it? 
    // The user said: "i get an option to render and i edit and render again jsut a small cool featuer, please dont fuck up llm because iof these changes"
    // So we just render it directly to the preview iframe.
  }

  async exportCode() {
    for (const block of this.codeBlocks) {
      let ext = block.language === 'typescript' ? 'ts' : block.language;
      const blob = new Blob([block.code], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `generated-component.${ext}`;
      a.click();
      window.URL.revokeObjectURL(url);
      
      // Add a small delay so the browser registers separate downloads and doesn't block them
      await new Promise(r => setTimeout(r, 200));
    }
  }

  exportAsTsx() {
    const ts = this.codeBlocks.find(b => b.language === 'typescript')?.code ?? '';
    const html = this.codeBlocks.find(b => b.language === 'html')?.code ?? '';
    const css = this.codeBlocks.find(b => b.language === 'css')?.code ?? '';

    const tsxContent = `// Auto-generated by Guided Component Architect
// Angular standalone component bundled as single .tsx file

// --- TypeScript ---
${ts}

// --- Template (HTML) ---
/*
${html}
*/

// --- Styles (CSS) ---
/*
${css}
*/
`;
    const blob = new Blob([tsxContent], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'generated-component.tsx';
    a.click();
    window.URL.revokeObjectURL(url);
  }

  async generateCode() {
    if (!this.prompt.trim() || this.isLoading) return;
    const submittedPrompt = this.prompt.trim();

    this.isLoading = true;
    this.isValidated = false;
    this.error = '';
    this.errorTitle = '';
    this.generatedCode = '';
    this.thinkingText = '';
    this.isThinkingExpanded = false;
    this.originalCodeBlocks = structuredClone(this.codeBlocks);
    this.abortController = new AbortController();
    this.addLog('info', 'Generation started', submittedPrompt);
    this.cdr.markForCheck();
    
    try {
      const response = await this.api.generate(
        { 
          prompt: this.prompt, 
          session_id: this.sessionId,
          current_code: this.codeBlocks,
          thinking_enabled: this.thinkingEnabled
        },
        this.abortController.signal,
      );
      
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const message = buffer.substring(0, boundary).trim();
          buffer = buffer.substring(boundary + 2);
          
          if (message.startsWith('data: ')) {
            try {
              const data = JSON.parse(message.substring(6)) as GenerationEvent;
              this.handleGenerationEvent(data);
            } catch (e) {
              console.error("Failed to parse SSE message", e, message);
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (err: any) {
      this.errorTitle = 'Generation Failed';
      this.error = this.toUserFacingError(err);
      this.addLog('error', this.errorTitle, this.error);
    } finally {
      this.isLoading = false;
      this.prompt = ''; // Clear prompt for next follow-up
      this.abortController = null;
      this.cdr.markForCheck();
    }
  }

  private handleGenerationEvent(data: GenerationEvent): void {
    if (data.type === 'thinking') {
      const isFirst = !this.thinkingText;
      this.thinkingText += data.content;
      if (isFirst) this.isThinkingExpanded = true;  // auto-open on first chunk
      this.cdr.markForCheck();
      requestAnimationFrame(() => {
        const el = document.getElementById('thinking-scroll');
        if (el) el.scrollTop = el.scrollHeight;
      });
      return;
    }

    if (data.type === 'chunk') {
      this.generatedCode += data.content;
      this.scheduleStreamParse();
      return;
    }

    if (data.type === 'error') {
      this.errorTitle = 'Validation Failed';
      this.error = "The model could not produce a valid component after retries: " + data.errors.join(" | ");
      this.isValidated = false;
      this.addLog('error', this.errorTitle, this.error);
      this.cdr.markForCheck();
      return;
    }

    if (data.type === 'cancelled') {
      this.errorTitle = 'Generation Cancelled';
      this.error = 'The active generation was stopped.';
      this.isValidated = false;
      this.addLog('warning', this.errorTitle, this.error);
      this.cdr.markForCheck();
      return;
    }

    if (data.type === 'replace') {
      this.generatedCode = data.code;
      this.parseMarkdownBlocks(this.generatedCode);
      void this.publishAngularPreview();
      this.cdr.markForCheck();
      return;
    }

    this.generatedCode = data.code;
    this.parseMarkdownBlocks(this.generatedCode);
    void this.publishAngularPreview();
    this.isValidated = true;
    this.errorTitle = '';
    this.error = '';
    this.addLog('success', 'Generation validated', this.metricsSummary(data.metrics));
    this.cdr.markForCheck();
  }

  private scheduleStreamParse(): void {
    if (this.parseScheduled) {
      return;
    }

    this.parseScheduled = true;
    window.requestAnimationFrame(() => {
      this.parseScheduled = false;
      this.parseMarkdownBlocks(this.generatedCode);
      // Removed this.updateSrcDoc() to prevent live rendering during generation stream
      this.cdr.markForCheck();
    });
  }

  private hasRenderablePreview(): boolean {
    return this.codeBlocks.some((block) => block.language === 'html' && block.code.trim());
  }

  toggleThinking(): void {
    this.isThinkingExpanded = !this.isThinkingExpanded;
    this.cdr.markForCheck();
  }

  toggleThinkingMode(): void {
    this.thinkingEnabled = !this.thinkingEnabled;
    this.cdr.markForCheck();
  }

  async cancelGeneration(): Promise<void> {
    this.abortController?.abort();
    await this.api.cancelGeneration(this.sessionId);
    this.isLoading = false;
    this.errorTitle = 'Generation Cancelled';
    this.error = 'The active generation was stopped.';
    this.addLog('warning', this.errorTitle, this.error);
    this.cdr.markForCheck();
  }



  private async publishAngularPreview(): Promise<void> {
    if (!this.hasCompleteComponent()) {
      return;
    }
    try {
      await this.api.publishPreview(this.sessionId, this.codeBlocks);
      // Give the Angular dev server a short moment to rebuild the generated component.
      window.setTimeout(() => {
        const url = `${window.location.origin}/preview?session=${this.sessionId}&v=${Date.now()}`;
        this.previewUrl = this.sanitizer.bypassSecurityTrustResourceUrl(url);
        this.addLog('success', 'Preview published', 'Generated Angular files compiled and /preview was refreshed.');
        this.cdr.markForCheck();
      }, 700);
    } catch (error) {
      this.errorTitle = 'Preview Publish Failed';
      this.error = this.toUserFacingError(error);
      this.addLog('error', this.errorTitle, this.error);
      this.cdr.markForCheck();
    }
  }

  private hasCompleteComponent(): boolean {
    return ['typescript', 'html', 'css'].every((language) =>
      this.codeBlocks.some((block) => block.language === language && block.code.trim()),
    );
  }

  private buildDesignSystemVars(ds: DesignSystem): string {
    let cssVars = ':root {\n';
    for (const [key, val] of Object.entries(ds.colors)) {
      cssVars += `  --${key}: ${val};\n`;
    }
    for (const [key, val] of Object.entries(ds.spacing)) {
      cssVars += `  --spacing-${key}: ${val};\n`;
    }
    cssVars += `  --radius: ${ds.borders.radius};\n`;
    cssVars += '}\n';
    cssVars += `body { font-family: ${ds.typography.fontFamily}; background-color: var(--background); color: var(--textPrimary); display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }\n`;
    cssVars += `
      .bg-glassmorphism {
        background-color: ${ds.effects.glassmorphism.backgroundColor};
        backdrop-filter: ${ds.effects.glassmorphism.backdropFilter};
        -webkit-backdrop-filter: ${ds.effects.glassmorphism.backdropFilter};
        border: ${ds.effects.glassmorphism.border};
      }
      .text-headings {
        font-family: ${ds.typography.fontFamily};
        color: var(--textPrimary);
      }
      .h1 { font-size: ${ds.typography.headings.h1}; font-weight: bold; }
      .h2 { font-size: ${ds.typography.headings.h2}; font-weight: bold; margin-bottom: 0.5rem; }
      .h3 { font-size: ${ds.typography.headings.h3}; font-weight: bold; }
      .btn {
        display: inline-block;
        padding: 0.5rem 1.5rem;
        border-radius: var(--radius);
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        text-align: center;
      }
      .btn-primary {
        background-color: var(--primary);
        color: white;
      }
      .btn-primary:hover {
        opacity: 0.9;
      }
    `;

    return cssVars;
  }

  private toUserFacingError(error: unknown): string {
    const message = error instanceof Error ? error.message : String(error || '');
    if (!message || message === 'Load failed' || message.includes('Failed to fetch')) {
      return 'Could not reach the backend at http://127.0.0.1:8010. Start the FastAPI server, then try again.';
    }
    try {
      const parsed = JSON.parse(message);
      if (parsed.detail) {
        return typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail);
      }
    } catch {
      // Keep the original message when it is not JSON.
    }
    return message;
  }

  clearRunLog(): void {
    this.runLog = [];
    localStorage.removeItem(this.logStorageKey);
    this.cdr.markForCheck();
  }

  private loadRunLog(): void {
    try {
      this.runLog = JSON.parse(localStorage.getItem(this.logStorageKey) || '[]');
    } catch {
      this.runLog = [];
    }
  }

  private loadSessionId(): string {
    const existing = localStorage.getItem(this.sessionStorageKey);
    if (existing) {
      return existing;
    }
    const created = crypto.randomUUID();
    localStorage.setItem(this.sessionStorageKey, created);
    return created;
  }

  private addLog(level: RunLogEntry['level'], title: string, detail: string): void {
    const entry: RunLogEntry = {
      id: crypto.randomUUID(),
      at: new Date().toLocaleTimeString(),
      level,
      title,
      detail,
    };
    this.runLog = [entry, ...this.runLog].slice(0, 80);
    localStorage.setItem(this.logStorageKey, JSON.stringify(this.runLog));
  }

  private installRuntimeErrorLogging(): void {
    if (this.runtimeErrorLoggingInstalled) {
      return;
    }
    this.runtimeErrorLoggingInstalled = true;

    window.addEventListener('error', (event) => {
      const location = event.filename
        ? `${event.filename}:${event.lineno}:${event.colno}`
        : 'unknown location';
      const message = event.message || this.toUserFacingError(event.error);
      this.addLog('error', 'Runtime Error', `${message}\n${location}`);
      this.cdr.markForCheck();
    });

    window.addEventListener('unhandledrejection', (event) => {
      this.addLog('error', 'Unhandled Promise Rejection', this.toUserFacingError(event.reason));
      this.cdr.markForCheck();
    });
  }

  private metricsSummary(metrics: Record<string, unknown> | undefined): string {
    if (!metrics) {
      return 'No metrics returned.';
    }
    const firstToken = metrics['first_token_ms'];
    const total = metrics['total_ms'];
    const iterations = metrics['iterations'];
    return `first_token=${firstToken ?? 'n/a'}ms, total=${total ?? 'n/a'}ms, retries=${iterations ?? 'n/a'}`;
  }

  private getFallbackDesignSystem(): DesignSystem {
    return {
      colors: {
        primary: '#6366f1',
        secondary: '#ec4899',
        background: '#0f172a',
        surface: '#1e293b',
        textPrimary: '#f8fafc',
        textSecondary: '#94a3b8',
      },
      typography: {
        fontFamily: "'Inter', sans-serif",
        baseSize: '16px',
        headings: {
          h1: '2.25rem',
          h2: '1.875rem',
          h3: '1.5rem',
        },
      },
      spacing: {
        small: '8px',
        medium: '16px',
        large: '24px',
      },
      borders: {
        radius: '8px',
        radiusLarge: '12px',
        radiusFull: '9999px',
      },
      effects: {
        glassmorphism: {
          backgroundColor: 'rgba(30, 41, 59, 0.7)',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        },
      },
    };
  }
}
