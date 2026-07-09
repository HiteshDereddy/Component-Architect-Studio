import { Injectable } from '@angular/core';
import { CodeBlock, CodeLanguage } from '../models/generated-code';

@Injectable({ providedIn: 'root' })
export class CodeParserService {
  parse(markdown: string, baseBlocks: CodeBlock[] = []): CodeBlock[] {
    const blocks = structuredClone(baseBlocks);

    this.applyMarkdownBlocks(markdown, blocks);
    this.applyEditPatches(markdown, blocks);

    return blocks;
  }

  private applyMarkdownBlocks(markdown: string, blocks: CodeBlock[]): void {
    const regex = /```([a-zA-Z0-9]*)\s*?\n([\s\S]*?)(```|$)/gi;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(markdown)) !== null) {
      const language = this.normalizeLanguage(match[1]);
      const existing = blocks.find((block) => block.language === language);

      if (existing) {
        existing.code = match[2];
      } else {
        blocks.push({ language, code: match[2] });
      }
    }
  }

  private applyEditPatches(markdown: string, blocks: CodeBlock[]): void {
    const editRegex = /<edit\s+file=["'](typescript|html|css)["']\s*>[\s\S]*?<old>([\s\S]*?)<\/old>[\s\S]*?<new>([\s\S]*?)(?:<\/new>|$)/gi;
    let editMatch: RegExpExecArray | null;

    while ((editMatch = editRegex.exec(markdown)) !== null) {
      const fileLanguage = editMatch[1] as CodeLanguage;
      const oldValue = editMatch[2].trim();
      const newValue = editMatch[3];
      const target = blocks.find((block) => block.language === fileLanguage);

      if (!target || !oldValue) {
        continue;
      }

      const escapedOld = oldValue.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const flexibleOld = escapedOld.replace(/\s+/g, '\\s+');
      target.code = target.code.replace(new RegExp(flexibleOld), newValue);
    }
  }

  private normalizeLanguage(rawLanguage: string): CodeLanguage {
    const language = (rawLanguage || '').toLowerCase().trim();
    if (language.includes('ts') || language.includes('typescript')) return 'typescript';
    if (language.includes('html')) return 'html';
    if (language.includes('css')) return 'css';
    return 'raw';
  }
}

