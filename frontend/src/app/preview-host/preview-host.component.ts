import { Component } from '@angular/core';
import { GeneratedComponent } from '../generated-preview/generated.component';

@Component({
  selector: 'app-preview-host',
  standalone: true,
  imports: [GeneratedComponent],
  template: '<main class="preview-host"><app-generated-component /></main>',
  styles: [`
    :host {
      display: block;
      min-height: 100vh;
      background: radial-gradient(circle at center, var(--surface) 0%, var(--background) 100%);
      color: var(--textPrimary);
      font-family: var(--font-family);
    }
    .preview-host {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 32px;
      box-sizing: border-box;
    }
  `]
})
export class PreviewHostComponent {}

