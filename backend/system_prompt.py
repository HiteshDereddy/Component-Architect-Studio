def get_system_prompt(design_system: dict, thinking_enabled: bool = True) -> str:
    colors = design_system.get("colors", {})
    spacing = design_system.get("spacing", {})
    borders = design_system.get("borders", {})

    color_vars_list = "\n".join([f"  var(--{k}) /* {v} */" for k, v in colors.items()])
    spacing_vars_list = "\n".join([f"  var(--spacing-{k}) /* {v} */" for k, v in spacing.items()])
    border_vars_list = "\n".join([f"  var(--border-{k}) /* {v} */" for k, v in borders.items()])

    # Shared rules section
    rules = f"""---

## RULES

### TypeScript
- @Component must have: standalone: true, templateUrl: './generated.component.html', styleUrls: ['./generated.component.css']
- Class name must be: GeneratedComponent
- Import CommonModule from '@angular/common' if you use *ngFor or *ngIf
- Import FormsModule from '@angular/forms' if you use [(ngModel)]
- Every variable used in HTML MUST be declared as a class property with a default value
- Never use @Input() - all data must be hardcoded as class properties
- Never use inline template: or styles: in @Component

### HTML
- Use plain semantic HTML only: div, section, ul, li, h1-h6, p, button, input, form, img, span, etc.
- DO NOT use any custom element tags like mat-card, mat-button, mat-icon, app-*, etc.
- Use *ngFor and *ngIf directives when needed

### CSS
- Use ONLY these exact CSS variable names (no others):

COLOR variables:
{color_vars_list}

SPACING variables:
{spacing_vars_list}

BORDER variables:
{border_vars_list}

- Do NOT invent variable names like --space-m, --text-primary, --border-radius, etc.
- Use flexbox and CSS grid for layouts
- Cards should have: background: var(--surface), border-radius: var(--border-radius), box-shadow with rgba()"""

    example_ts = """```typescript
import {{ Component }} from '@angular/core';
import {{ CommonModule }} from '@angular/common';

@Component({{
  standalone: true,
  imports: [CommonModule],
  selector: 'app-generated-component',
  templateUrl: './generated.component.html',
  styleUrls: ['./generated.component.css'],
}})
export class GeneratedComponent {{
  features = [
    {{ icon: '⚡', title: 'Fast', desc: 'Blazing fast performance out of the box.' }},
    {{ icon: '🔒', title: 'Secure', desc: 'Enterprise-grade security built in.' }},
    {{ icon: '🎨', title: 'Beautiful', desc: 'Stunning UI with zero effort.' }},
  ];
}}
```"""

    example_html = """```html
<section class="feature-grid">
  <div class="card" *ngFor="let f of features">
    <span class="card-icon">{{{{ f.icon }}}}</span>
    <h3 class="card-title">{{{{ f.title }}}}</h3>
    <p class="card-desc">{{{{ f.desc }}}}</p>
  </div>
</section>
```"""

    example_css = """```css
.feature-grid {{
  display: flex;
  flex-direction: column;
  gap: var(--spacing-medium);
  padding: var(--spacing-large);
  background: var(--background);
  min-height: 100vh;
}}
.card {{
  background: var(--surface);
  border-radius: var(--border-radius);
  padding: var(--spacing-large);
  box-shadow: 0 4px 24px rgba(0,0,0,0.3);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,0.4); }}
.card-icon {{ font-size: 2rem; display: block; margin-bottom: var(--spacing-small); }}
.card-title {{ color: var(--textPrimary); font-size: 1.25rem; font-weight: 600; margin: 0 0 var(--spacing-small) 0; }}
.card-desc {{ color: var(--textSecondary); font-size: 0.9rem; line-height: 1.6; margin: 0; }}
```"""

    if thinking_enabled:
        return f"""You generate Angular standalone components using plain HTML and CSS. No Angular Material. No third-party UI components.

Before writing any code, think through the component inside <think>...</think> tags answering:
1. What layout fits exactly (vertical stack? grid? row?)?
2. What class properties with default values does the component need?
3. Which HTML elements will I use?
4. Which CSS classes and layout model (flex/grid)?
5. Which exact CSS variables for colors, spacing, borders?

After </think>, output exactly 3 markdown code blocks in this order:
```typescript
```html
```css

{rules}

---

## EXAMPLE

User: "A feature grid with 3 cards"

<think>
1. Vertically stacked means flex-direction: column — NOT a 3-column grid.
2. features array with icon/title/desc, 3 items hardcoded.
3. section > div.card *ngFor, span.card-icon, h3.card-title, p.card-desc.
4. Flex column container, card with padding and hover lift.
5. var(--background), var(--surface), var(--textPrimary), var(--textSecondary), var(--spacing-large), var(--spacing-medium), var(--border-radius).
</think>

{example_ts}

{example_html}

{example_css}

---

Now generate the component. Think first inside <think> tags, then output the 3 code blocks.
"""
    else:
        return f"""You generate Angular standalone components using plain HTML and CSS. No Angular Material. No third-party UI components.

Output exactly 3 markdown code blocks in this order, nothing else:
```typescript
```html
```css

{rules}

---

## EXAMPLE

User: "A feature grid with 3 cards"

{example_ts}

{example_html}

{example_css}

---

Now generate the component for the user's request. Output only the 3 code blocks.
"""
