import { Injectable } from '@angular/core';
import { CodeBlock } from '../models/generated-code';

@Injectable({ providedIn: 'root' })
export class PreviewBuilderService {
  buildSrcDoc(codeBlocks: CodeBlock[], designSystemVars: string): string {
    const htmlCode = this.findLatestBlock(codeBlocks, 'html');
    const cssCode = this.findLatestBlock(codeBlocks, 'css');

    return `
      <!DOCTYPE html>
      <html>
      <head>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
          tailwind.config = {
            theme: {
              extend: {
                colors: {
                  primary: 'var(--primary)',
                  secondary: 'var(--secondary)',
                  background: 'var(--background)',
                  surface: 'var(--surface)',
                  textPrimary: 'var(--textPrimary)',
                  textSecondary: 'var(--textSecondary)'
                }
              }
            }
          }
        </script>
        <style>${designSystemVars}</style>
        <style type="text/tailwindcss">${cssCode}</style>
      </head>
      <body class="antialiased min-h-screen w-full flex items-center justify-center p-8" style="background: radial-gradient(circle at center, var(--surface) 0%, var(--background) 100%);">
        <div class="w-full max-w-md mx-auto transition-all duration-500 hover:scale-105">
          ${htmlCode}
        </div>
      </body>
      </html>
    `;
  }

  private findLatestBlock(codeBlocks: CodeBlock[], language: 'html' | 'css'): string {
    return codeBlocks.filter((block) => block.language === language).at(-1)?.code ?? '';
  }
}

